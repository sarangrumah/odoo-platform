# -*- coding: utf-8 -*-
"""Scan installed models and surface candidate PII fields.

Operators run this periodically (e.g. after installing a new module)
to keep the registry comprehensive. The wizard *suggests*; the operator
reviews and bulk-creates.
"""

from __future__ import annotations

import re

from odoo import _, api, fields, models


_PATTERN = re.compile(
    r"(email|phone|mobile|nik|npwp|passport|birth|salary|account|"
    r"iban|swift|address|street|zip|postcode|tax_id|gender|marital)",
    re.IGNORECASE,
)


_PATTERN_TO_CATEGORY = [
    (re.compile(r"email", re.I), ("email", "email_domain")),
    (re.compile(r"(phone|mobile)", re.I), ("phone", "last4")),
    (re.compile(r"nik", re.I), ("nik", "last4")),
    (re.compile(r"(npwp|vat|tax_id)", re.I), ("npwp", "last4")),
    (re.compile(r"passport", re.I), ("passport", "last4")),
    (re.compile(r"birth", re.I), ("dob", "redacted")),
    (re.compile(r"salary|wage|compensation", re.I), ("salary", "redacted")),
    (re.compile(r"(iban|swift|account_number|account_no|bank)", re.I), ("bank_account", "last4")),
    (re.compile(r"(address|street|zip|postcode|city)", re.I), ("address", "first_letter")),
    (re.compile(r"gender|marital", re.I), ("other", "redacted")),
]


def _guess(field_name: str):
    for rx, (cat, pat) in _PATTERN_TO_CATEGORY:
        if rx.search(field_name):
            return cat, pat
    return "other", "redacted"


class CustomPdpFieldDiscoveryWizard(models.TransientModel):
    _name = "custom.pdp.field.discovery.wizard"
    _description = "PDP Field Discovery — scan models for candidate PII fields"

    suggestion_ids = fields.One2many(
        "custom.pdp.field.discovery.suggestion",
        "wizard_id",
    )
    report = fields.Text(readonly=True)

    def action_scan(self):
        self.ensure_one()
        self.suggestion_ids.unlink()
        Registry = self.env["custom.pdp.field.registry"].sudo()
        existing = {
            (r.model_name, r.field_name)
            for r in Registry.search([])
        }
        Suggestion = self.env["custom.pdp.field.discovery.suggestion"]
        Fields = self.env["ir.model.fields"].sudo()
        # Only scan stored char/text/date fields on non-transient models.
        candidates = Fields.search(
            [
                ("ttype", "in", ("char", "text", "date", "datetime", "selection")),
                ("store", "=", True),
                ("model_id.transient", "=", False),
            ]
        )
        created = 0
        for f in candidates:
            if not f.name or not _PATTERN.search(f.name):
                continue
            if (f.model, f.name) in existing:
                continue
            cat, pattern = _guess(f.name)
            Suggestion.create(
                {
                    "wizard_id": self.id,
                    "model_name": f.model,
                    "field_name": f.name,
                    "pii_category": cat,
                    "mask_pattern": pattern,
                    "selected": False,
                }
            )
            created += 1
        self.report = _("Discovered %d new candidate fields.") % created
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_create_selected(self):
        self.ensure_one()
        Registry = self.env["custom.pdp.field.registry"].sudo()
        IrModel = self.env["ir.model"].sudo()
        created = 0
        for s in self.suggestion_ids.filtered("selected"):
            model = IrModel.search([("model", "=", s.model_name)], limit=1)
            if not model:
                continue
            try:
                Registry.create(
                    {
                        "model_id": model.id,
                        "field_name": s.field_name,
                        "pii_category": s.pii_category,
                        "mask_pattern": s.mask_pattern,
                    }
                )
                created += 1
            except Exception:
                continue
        self.report = (self.report or "") + (
            "\n" + (_("Created %d registry entries.") % created)
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class CustomPdpFieldDiscoverySuggestion(models.TransientModel):
    _name = "custom.pdp.field.discovery.suggestion"
    _description = "PDP Field Discovery Suggestion"

    wizard_id = fields.Many2one(
        "custom.pdp.field.discovery.wizard", required=True, ondelete="cascade",
    )
    model_name = fields.Char(required=True)
    field_name = fields.Char(required=True)
    pii_category = fields.Selection(
        selection=lambda self: self.env["custom.pdp.field.registry"]
        ._fields["pii_category"].selection,
    )
    mask_pattern = fields.Selection(
        selection=lambda self: self.env["custom.pdp.field.registry"]
        ._fields["mask_pattern"].selection,
    )
    selected = fields.Boolean(default=False)
