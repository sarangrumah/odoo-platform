# -*- coding: utf-8 -*-
"""Mirror of master-DB ``tenant_registry.backups`` for UI listing + restore action."""

from __future__ import annotations

import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TenantBackup(models.Model):
    _name = "tenant.backup"
    _description = "Tenant Backup Ledger (mirror)"
    _order = "started_at desc"

    master_id = fields.Integer(index=True, required=True)
    tenant_id = fields.Many2one("tenant.registry", ondelete="cascade", index=True)
    tenant_slug = fields.Char(index=True, required=True)
    kind = fields.Selection(
        [("manual", "Manual"), ("daily", "Daily"), ("monthly", "Monthly"), ("yearly", "Yearly")],
        required=True,
    )
    started_at = fields.Datetime(required=True)
    finished_at = fields.Datetime()
    size_bytes = fields.Integer()
    size_human = fields.Char(compute="_compute_size_human")
    s3_key = fields.Char()
    checksum_sha256 = fields.Char()
    outcome = fields.Selection(
        [("pending", "Pending"), ("success", "Success"), ("failure", "Failure")],
        required=True,
    )
    error = fields.Text()
    expires_at = fields.Datetime()

    _master_id_uniq = models.Constraint(
        'unique(master_id)',
        'Master backup id must be unique in mirror.',
    )

    @api.depends("size_bytes")
    def _compute_size_human(self):
        for rec in self:
            n = rec.size_bytes or 0
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if n < 1024:
                    rec.size_human = f"{n:.1f} {unit}"
                    break
                n /= 1024.0
            else:
                rec.size_human = f"{n:.1f} PB"

    # ------------------------------------------------------------------
    # Sync (orchestrator API for active tenants)
    # ------------------------------------------------------------------

    @api.model
    def _cron_sync_all(self) -> None:
        for tenant in self.env["tenant.registry"].sudo().search([
            ("state", "in", ("active", "suspended")),
        ]):
            self._cron_sync_for(tenant.slug)

    @api.model
    def _cron_sync_for(self, slug: str) -> None:
        try:
            rows = self.env["custom.super.admin.orchestrator.client"].sudo().list_backups(slug)
        except Exception as e:
            _logger.warning("tenant.backup.sync_failed slug=%s err=%s", slug, e)
            return
        tenant = self.env["tenant.registry"].sudo().search([("slug", "=", slug)], limit=1)
        existing = {b.master_id: b for b in self.sudo().search([("tenant_slug", "=", slug)])}
        for r in rows:
            mid = r["id"]
            vals = {
                "master_id": mid,
                "tenant_id": tenant.id if tenant else False,
                "tenant_slug": slug,
                "kind": r["kind"],
                "started_at": self._to_dt(r["started_at"]),
                "finished_at": self._to_dt(r.get("finished_at")),
                "size_bytes": r.get("size_bytes") or 0,
                "s3_key": r.get("s3_key"),
                "checksum_sha256": r.get("checksum_sha256"),
                "outcome": r["outcome"],
                "error": r.get("error"),
                "expires_at": self._to_dt(r.get("expires_at")),
            }
            if mid in existing:
                existing[mid].sudo().write(vals)
            else:
                self.sudo().create(vals)

    @staticmethod
    def _to_dt(value):
        if not value:
            return False
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Restore action
    # ------------------------------------------------------------------

    def action_restore_to_staging(self):
        self.ensure_one()
        if self.outcome != "success" or not self.s3_key:
            raise UserError(_("Cannot restore: backup did not complete successfully."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Restore Backup"),
            "res_model": "tenant.restore.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_tenant_id": self.tenant_id.id,
                "default_slug": self.tenant_slug,
                "default_s3_key": self.s3_key,
            },
        }
