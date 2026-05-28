# -*- coding: utf-8 -*-
"""Masking strategy service."""

from __future__ import annotations

import re

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


REDACTED = "[REDACTED]"


def _mask_email(v: str) -> str:
    m = re.match(r"^([^@]+)@([^@]+)$", v or "")
    if not m:
        return REDACTED
    user, domain = m.group(1), m.group(2)
    dom_parts = domain.split(".")
    dom_head = dom_parts[0]
    dom_rest = "." + ".".join(dom_parts[1:]) if len(dom_parts) > 1 else ""
    return f"{user[0]}***@{dom_head[0]}***{dom_rest}"


def _mask_phone(v: str) -> str:
    if not v:
        return ""
    digits = re.sub(r"\D", "", v)
    if len(digits) < 6:
        return REDACTED
    return digits[:2] + ("•" * (len(digits) - 6)) + digits[-4:]


def _mask_nik(v: str) -> str:
    digits = re.sub(r"\D", "", v or "")
    if len(digits) < 8:
        return REDACTED
    return digits[:3] + ("•" * (len(digits) - 7)) + digits[-4:]


def _mask_name(v: str) -> str:
    if not v:
        return ""
    head = v[:2]
    return head + "***"


def _mask_generic(v):
    if v in (None, False, ""):
        return v
    return REDACTED


_STRATEGY_BY_FIELD_NAME = {
    "email": _mask_email,
    "phone": _mask_phone,
    "mobile": _mask_phone,
    "nik": _mask_nik,
    "vat": _mask_nik,
    "name": _mask_name,
    "display_name": _mask_name,
}


class PdpMaskingService(models.AbstractModel):
    _name = "pdp.masking"
    _description = "PDP Masking Service"

    @api.model
    def _mask(self, value, classification_code: str | None, user=None, field_name: str | None = None):
        """Mask `value` per classification & optional field-name hint.

        - If user has pdp.group_view_pii AND policy allows unmask, returns the
          value untouched (caller checks this; this method always masks).
        - Otherwise picks a strategy based on field name → falls back to
          classification → falls back to generic [REDACTED].
        """
        if value in (None, False, ""):
            return value
        if field_name and field_name in _STRATEGY_BY_FIELD_NAME:
            return _STRATEGY_BY_FIELD_NAME[field_name](str(value))
        if classification_code == "pii" or classification_code == "sensitive_pii":
            return _mask_name(str(value))
        if classification_code == "financial":
            return _mask_nik(str(value))
        return _mask_generic(value)

    @api.model
    def _policy(self) -> str:
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "pdp.masking.policy",
                "unmask_with_reason",
            )
        )

    @api.model
    def _user_can_view_pii(self, user=None) -> bool:
        user = user or self.env.user
        return user.has_group("custom_pdp_masking.group_view_pii")

    # ------------------------------------------------------------------
    # Per-field reveal (used by the `pdp_masked_field` OWL widget)
    # ------------------------------------------------------------------

    @api.model
    def _reveal_field(self, model_name: str, res_id: int, field_name: str, reason: str | None = None):
        """Return the clear value of one field for one record, with audit.

        Server-enforced: validates that the field is actually registered as
        masked, that the user is allowed to reveal under the active policy,
        and writes a ``pii_unmask`` audit row before returning.
        """
        if not model_name or not res_id or not field_name:
            raise UserError(_("Missing parameters for reveal."))
        if model_name not in self.env:
            raise UserError(_("Unknown model %s") % model_name)
        Reg = self.env["custom.pdp.field.registry"].sudo()
        rules = Reg._registry_for(model_name)
        rule = next((r for r in rules if r["field"] == field_name), None)
        if not rule:
            raise UserError(_("Field %s is not registered as masked.") % field_name)

        policy = self._policy()
        if policy == "always_mask":
            raise AccessError(_("Reveal is disabled by policy (always_mask)."))
        if policy == "unmask_with_reason":
            if not (reason and reason.strip()):
                raise UserError(_("A reason is required to reveal this field."))
            if not self._user_can_view_pii():
                raise AccessError(_("You are not allowed to reveal PII fields."))

        Model = self.env[model_name]
        rec = Model.browse(int(res_id)).exists()
        if not rec:
            raise UserError(_("Record not found."))
        rec.check_access("read")

        clear_value = rec.with_context(__pdp_skip_masking=True).read([field_name])[0].get(field_name)

        # Audit (best-effort). Use the audited mixin if the model has it,
        # else fall back to direct insert via the registry's own helper.
        try:
            if hasattr(rec, "_pdp_audit_write"):
                rec._pdp_audit_write(
                    "pii_unmask",
                    rec.id,
                    {field_name: rule["pattern"]},
                    reason=reason or None,
                )
            else:
                Reg._pdp_audit_write(
                    "pii_unmask",
                    rec.id,
                    {"model": model_name, "field": field_name},
                    reason=reason or None,
                )
        except Exception:
            pass

        return clear_value
