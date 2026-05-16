# -*- coding: utf-8 -*-
"""Masking strategy service."""

from __future__ import annotations

import re

from odoo import api, models


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
        return self.env["ir.config_parameter"].sudo().get_param(
            "pdp.masking.policy", "unmask_with_reason",
        )

    @api.model
    def _user_can_view_pii(self, user=None) -> bool:
        user = user or self.env.user
        return user.has_group("custom_pdp_masking.group_view_pii")
