# -*- coding: utf-8 -*-
"""Public intake landing zone.

Raw submissions land here first. A BA/CSM reviews them and clicks
"Promote to Journey" to materialize an ``onboarding.journey`` record.
"""

from __future__ import annotations

import json
import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OnboardingPublicSubmission(models.Model):
    _name = "onboarding.public.submission"
    _description = "Public Onboarding Submission (raw inbox)"
    _order = "submitted_at desc"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    raw_payload_json = fields.Text(required=True)
    public_token = fields.Char(
        required=True,
        copy=False,
        index=True,
        default=lambda self: secrets.token_urlsafe(24),
    )
    source_ip_hash = fields.Char(
        help="SHA-256 of the source IP (no raw IP stored, PDP-friendly).",
        index=True,
    )
    submitted_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    status = fields.Selection(
        [
            ("submitted", "Submitted"),
            ("promoted", "Promoted"),
            ("rejected", "Rejected"),
        ],
        default="submitted",
        required=True,
        index=True,
    )
    journey_id = fields.Many2one(
        "onboarding.journey",
        ondelete="set null",
        copy=False,
    )
    rejection_reason = fields.Text()

    _sql_constraints = [
        (
            "public_token_uniq",
            "unique(public_token)",
            "Submission token must be unique.",
        ),
    ]

    # ------------------------------------------------------------------ API
    @api.model
    def create_from_payload(self, payload):
        """Create a submission from a JSON payload (called by orchestrator /v1/intake).

        Returns ``{token, status_url, id}`` so the public landing can
        immediately show the customer a status link.
        """
        import hashlib
        if not isinstance(payload, dict):
            raise UserError(_("payload must be a dict"))
        if not payload.get("company_name"):
            raise UserError(_("company_name is required"))
        source_ip = payload.pop("source_ip", None)
        ip_hash = hashlib.sha256(source_ip.encode("utf-8")).hexdigest()[:32] if source_ip else False
        rec = self.sudo().create({
            "raw_payload_json": json.dumps(payload),
            "source_ip_hash": ip_hash,
        })
        return {
            "id": rec.id,
            "token": rec.public_token,
            "status_url": f"/onboarding/public/status/{rec.public_token}",
        }

    @api.depends("raw_payload_json", "submitted_at")
    def _compute_name(self):
        for rec in self:
            label = "Submission"
            try:
                data = json.loads(rec.raw_payload_json or "{}")
                label = data.get("partner_name") or data.get("company_name") or label
            except Exception:
                pass
            rec.name = f"{label} @ {rec.submitted_at or ''}"

    # ------------------------------------------------------------------ actions
    def action_promote_to_journey(self):
        self.ensure_one()
        if self.status == "promoted" and self.journey_id:
            return self._open_journey()
        try:
            data = json.loads(self.raw_payload_json or "{}")
        except Exception as exc:
            raise UserError(_("Cannot parse submission payload: %s") % exc) from exc

        partner_name = data.get("partner_name") or data.get("company_name") or _("Unknown")
        partner_email = data.get("partner_email")
        Partner = self.env["res.partner"].sudo()
        partner = False
        if partner_email:
            partner = Partner.search([("email", "=", partner_email)], limit=1)
        if not partner:
            partner = Partner.create({"name": partner_name, "email": partner_email or False})

        journey = self.env["onboarding.journey"].sudo().create(
            {
                "name": _("Onboarding - %s") % partner_name,
                "partner_id": partner.id,
                "stage": "intake",
                "company_profile_json": self.raw_payload_json,
            }
        )
        self.write({"status": "promoted", "journey_id": journey.id})
        return self._open_journey()

    def action_reject(self):
        for rec in self:
            rec.status = "rejected"
        return True

    def _open_journey(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "onboarding.journey",
            "res_id": self.journey_id.id,
            "view_mode": "form",
        }
