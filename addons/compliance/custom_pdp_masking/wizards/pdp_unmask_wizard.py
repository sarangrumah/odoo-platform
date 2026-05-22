# -*- coding: utf-8 -*-
"""Wizard: request unmasked view of records with an audited reason."""

from odoo import fields, models
from odoo.exceptions import UserError


class PdpUnmaskWizard(models.TransientModel):
    _name = "pdp.unmask.wizard"
    _description = "Unmask PII (with reason)"

    model_name = fields.Char(required=True, readonly=True)
    res_ids_csv = fields.Char(string="Record IDs (CSV)", required=True)
    reason = fields.Text(required=True)

    def action_unmask(self):
        self.ensure_one()
        ids = [int(x) for x in (self.res_ids_csv or "").split(",") if x.strip().isdigit()]
        if not ids:
            raise UserError("No record IDs provided.")
        if self.model_name not in self.env:
            raise UserError(f"Unknown model {self.model_name}")
        Model = self.env[self.model_name]
        # Audit the unmask request
        if hasattr(Model, "_pdp_audit_write"):
            for rid in ids:
                Model.browse(rid)._pdp_audit_write(
                    "unmask",
                    rid,
                    {"reason": self.reason},
                    reason=self.reason,
                )
        action = {
            "type": "ir.actions.act_window",
            "res_model": self.model_name,
            "view_mode": "list,form",
            "domain": [("id", "in", ids)],
            "context": {
                "pdp_unmasked_ids": ids,
                "pdp_unmask_reason": self.reason,
            },
            "target": "current",
        }
        return action
