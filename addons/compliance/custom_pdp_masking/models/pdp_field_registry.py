# -*- coding: utf-8 -*-
"""PDP Field Registry — model-agnostic catalogue of PII fields and
per-field masking strategy.

This is a substitute for full breach/DPIA modules. It declares which
fields on which models hold PII and how they should be masked when read
by a non-privileged user. The :class:`pdp.masked.mixin` already hooks
``read()`` on models that opt into it; this registry tells the mixin
*what to do* for any model, even those that did not inherit the mixin
directly, via the registry's own override below.
"""

from __future__ import annotations

import hashlib
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


PII_CATEGORIES = [
    ("nik", "NIK (Nomor Induk Kependudukan)"),
    ("npwp", "NPWP"),
    ("phone", "Phone / Mobile"),
    ("email", "Email"),
    ("address", "Address"),
    ("dob", "Date of Birth"),
    ("account_no", "Internal Account No."),
    ("passport", "Passport"),
    ("bank_account", "Bank Account"),
    ("medical", "Medical / Health"),
    ("biometric", "Biometric"),
    ("salary", "Compensation"),
    ("other", "Other"),
]

MASK_PATTERNS = [
    ("full", "Full redaction ([REDACTED])"),
    ("last4", "Reveal last 4 chars"),
    ("first_letter", "Reveal first letter only"),
    ("email_domain", "Reveal domain only"),
    ("hash", "Show sha256 prefix (irreversible)"),
    ("redacted", "Replace with literal [REDACTED]"),
]


REDACTED = "[REDACTED]"


def _apply_pattern(value, pattern: str) -> str:
    """Render `value` per `pattern`. Always returns a string."""
    if value in (None, False, ""):
        return value
    s = str(value)
    if pattern == "full" or pattern == "redacted":
        return REDACTED
    if pattern == "last4":
        if len(s) <= 4:
            return REDACTED
        return ("•" * (len(s) - 4)) + s[-4:]
    if pattern == "first_letter":
        return s[0] + "***" if s else REDACTED
    if pattern == "email_domain":
        m = re.match(r"^([^@]+)@(.+)$", s)
        if not m:
            return REDACTED
        return f"***@{m.group(2)}"
    if pattern == "hash":
        return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
    return REDACTED


class CustomPdpFieldRegistry(models.Model):
    _name = "custom.pdp.field.registry"
    _inherit = ["pdp.audited.mixin"]
    _description = "PDP PII Field Registry"
    _order = "model_name, field_name"

    name = fields.Char(compute="_compute_name", store=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
    )
    model_name = fields.Char(
        related="model_id.model", store=True, index=True,
    )
    field_name = fields.Char(required=True, index=True)
    pii_category = fields.Selection(
        selection=PII_CATEGORIES, required=True, default="other",
    )
    mask_pattern = fields.Selection(
        selection=MASK_PATTERNS, required=True, default="redacted",
    )
    mask_groups = fields.Many2many(
        "res.groups",
        relation="pdp_field_registry_mask_groups_rel",
        string="Bypass Groups",
        help="Users in any of these groups see the value in clear.",
    )
    active = fields.Boolean(default=True)
    note = fields.Char()

    _sql_constraints = [
        (
            "model_field_unique",
            "UNIQUE(model_name, field_name)",
            "Each (model, field) can only be registered once.",
        ),
    ]

    @api.depends("model_name", "field_name", "pii_category")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.model_name or '?'}.{rec.field_name or '?'} [{rec.pii_category or '?'}]"

    @api.constrains("model_id", "field_name")
    def _check_field_exists(self):
        Fields = self.env["ir.model.fields"].sudo()
        for rec in self:
            if not rec.model_id:
                continue
            if not Fields.search_count(
                [("model", "=", rec.model_id.model), ("name", "=", rec.field_name)]
            ):
                raise ValidationError(
                    _("Field %(f)s does not exist on model %(m)s.")
                    % {"f": rec.field_name, "m": rec.model_id.model}
                )

    # ---------- public API used by mixin / ORM override ----------

    @api.model
    def _registry_for(self, model_name: str) -> list:
        """Return active registry rows for `model_name`.

        Cached on the env to avoid hammering the table on every read.
        """
        cache = self.env.context.get("__pdp_reg_cache")
        if cache is None:
            cache = {}
        if model_name in cache:
            return cache[model_name]
        recs = self.sudo().search(
            [("active", "=", True), ("model_name", "=", model_name)]
        )
        out = [
            {
                "field": r.field_name,
                "category": r.pii_category,
                "pattern": r.mask_pattern,
                "groups": tuple(r.mask_groups.ids),
            }
            for r in recs
        ]
        cache[model_name] = out
        return out

    @api.model
    def _user_bypasses(self, group_ids: tuple) -> bool:
        if not group_ids:
            return False
        user = self.env.user
        user_groups = set(user.groups_id.ids)
        return bool(user_groups.intersection(group_ids))

    @api.model
    def _apply(self, value, pattern: str):
        return _apply_pattern(value, pattern)

    # ---------- optional seeders (called from data XML) ----------

    @api.model
    def _seed_optional_hr_fields(self):
        """Seed HR PII fields if `hr` / `hr_recruitment` are installed.

        Called by the data XML via ``<function>``. Silently skips any
        model that isn't loaded in the current registry.
        """
        IrModel = self.env["ir.model"].sudo()
        view_group = self.env.ref(
            "custom_pdp_masking.group_view_pii", raise_if_not_found=False
        )
        groups_cmd = [(4, view_group.id)] if view_group else []
        seeds = [
            # (model, field, category, pattern)
            ("hr.employee", "identification_id", "nik", "last4"),
            ("hr.employee", "passport_id", "passport", "last4"),
            ("hr.employee", "private_email", "email", "email_domain"),
            ("hr.employee", "private_phone", "phone", "last4"),
            ("hr.employee", "private_street", "address", "first_letter"),
            ("hr.employee", "birthday", "dob", "redacted"),
            ("hr.employee", "marital", "other", "redacted"),
            ("hr.employee", "bank_account_id", "bank_account", "redacted"),
            ("hr.applicant", "partner_phone", "phone", "last4"),
            ("hr.applicant", "partner_name", "other", "first_letter"),
            ("hr.applicant", "email_from", "email", "email_domain"),
            ("hr.contract", "wage", "salary", "redacted"),
            ("hr.payslip", "net_wage", "salary", "redacted"),
        ]
        created = 0
        for model, field, cat, pat in seeds:
            mrec = IrModel.search([("model", "=", model)], limit=1)
            if not mrec:
                continue
            # Verify the field actually exists.
            if not self.env["ir.model.fields"].sudo().search_count(
                [("model", "=", model), ("name", "=", field)]
            ):
                continue
            if self.search_count(
                [("model_name", "=", model), ("field_name", "=", field)]
            ):
                continue
            try:
                self.create(
                    {
                        "model_id": mrec.id,
                        "field_name": field,
                        "pii_category": cat,
                        "mask_pattern": pat,
                        "mask_groups": groups_cmd,
                    }
                )
                created += 1
            except Exception:
                continue
        _logger.info("pdp.field.registry: seeded %d optional HR rows.", created)
        return created
