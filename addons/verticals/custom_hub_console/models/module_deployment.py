# -*- coding: utf-8 -*-
"""Module deployment: per-tenant install/upgrade/uninstall record.

Each row represents one orchestrator-mediated module operation on
exactly one tenant. The actual work is delegated to
``custom.super.admin.orchestrator.client`` — we only track requests,
state, and errors locally.
"""

from __future__ import annotations

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class CustomHubModuleDeployment(models.Model):
    _name = "custom.hub.module.deployment"
    _description = "Hub Module Deployment (per-tenant operation log)"
    _order = "requested_at desc, id desc"

    catalog_id = fields.Many2one(
        "custom.hub.module.catalog",
        string="Module",
        required=True,
        ondelete="restrict",
        index=True,
    )
    tenant_id = fields.Many2one(
        "tenant.registry",
        string="Tenant",
        required=True,
        ondelete="cascade",
        index=True,
    )
    deploy_mode = fields.Selection(
        [
            ("install", "Install"),
            ("upgrade", "Upgrade"),
            ("uninstall", "Uninstall"),
        ],
        required=True,
        default="install",
        index=True,
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("installing", "Installing"),
            ("installed", "Installed"),
            ("upgrading", "Upgrading"),
            ("failed", "Failed"),
            ("uninstalled", "Uninstalled"),
        ],
        required=True,
        default="pending",
        index=True,
        tracking=True,
    )
    requested_by_id = fields.Many2one(
        "res.users", string="Requested By",
        default=lambda self: self.env.user.id, required=True,
    )
    requested_at = fields.Datetime(default=fields.Datetime.now, required=True)
    started_at = fields.Datetime()
    completed_at = fields.Datetime()
    error_message = fields.Text()

    # ------------------------------------------------------------------
    def action_deploy(self):
        """Best-effort: call orchestrator API; if unreachable, mark failed
        with a clear message — do not raise so wizard commits."""
        for rec in self:
            rec.started_at = fields.Datetime.now()
            rec.state = "installing" if rec.deploy_mode == "install" else (
                "upgrading" if rec.deploy_mode == "upgrade" else "installing"
            )
            try:
                client = self.env["custom.super.admin.orchestrator.client"].sudo()
                slug = rec.tenant_id.slug
                module = rec.catalog_id.module_name
                # The orchestrator client doesn't yet have a generic
                # module-deploy endpoint helper; call ``_request`` directly.
                client._request(
                    "POST",
                    f"/v1/tenants/{slug}/modules/{rec.deploy_mode}",
                    body={"module": module},
                )
                rec.state = (
                    "uninstalled" if rec.deploy_mode == "uninstall"
                    else "installed"
                )
                rec.completed_at = fields.Datetime.now()
                rec.error_message = False
                self._log_audit(rec, "module_deploy", success=True)
            except Exception as exc:  # noqa: BLE001 - tolerant by design
                _logger.warning(
                    "[hub_deploy] orchestrator unreachable: %s", exc
                )
                rec.state = "failed"
                rec.completed_at = fields.Datetime.now()
                rec.error_message = (
                    f"Orchestrator API not reachable or returned error: {exc}"
                )
                self._log_audit(rec, "module_deploy", success=False, error=str(exc))
        return True

    @api.model
    def _log_audit(self, rec, event_type, success=True, error=None):
        try:
            self.env["custom.hub.audit.event"].sudo().log(
                event_type=event_type,
                tenant_id=rec.tenant_id.id,
                summary=(
                    f"{rec.deploy_mode} {rec.catalog_id.module_name} on "
                    f"{rec.tenant_id.slug} → "
                    f"{'OK' if success else 'FAILED'}"
                ),
                payload={
                    "deployment_id": rec.id,
                    "module": rec.catalog_id.module_name,
                    "tenant": rec.tenant_id.slug,
                    "mode": rec.deploy_mode,
                    "error": error,
                },
                object_ref=f"custom.hub.module.deployment,{rec.id}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            _logger.debug("[hub_deploy] audit log skipped: %s", exc)
