# -*- coding: utf-8 -*-
"""Encrypted ir.config_parameter helper.

Provides env-keyed Fernet encryption for sensitive parameters that must be
stored in DB (API keys for outbound integrations, etc.). The master key is
sourced from the `CORETAX_SERTEL_MASTER_KEY` env variable (reused as the
platform-wide secret holder; rotate per `security/policies/secret-rotation.md`).
"""

from __future__ import annotations

import base64
import logging
import os

from odoo import api, models
from odoo.exceptions import UserError

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore

_logger = logging.getLogger(__name__)
_PREFIX = "ENC::"


def _get_master_key() -> bytes:
    raw = os.environ.get("CORETAX_SERTEL_MASTER_KEY", "")
    if not raw:
        raise UserError("CORETAX_SERTEL_MASTER_KEY env not set — cannot use encrypted parameters")
    # Accept either a 44-char urlsafe base64 Fernet key or a 32-byte hex string
    if len(raw) == 44:
        return raw.encode()
    if len(raw) == 64:
        return base64.urlsafe_b64encode(bytes.fromhex(raw))
    return base64.urlsafe_b64encode(raw.encode()[:32].ljust(32, b"\0"))


class CustomIrConfig(models.AbstractModel):
    _name = "custom.ir.config"
    _description = "Encrypted ir.config_parameter helpers"

    @api.model
    def set_encrypted(self, key: str, plaintext: str) -> None:
        if Fernet is None:
            raise UserError("cryptography library not installed")
        f = Fernet(_get_master_key())
        token = f.encrypt(plaintext.encode())
        self.env["ir.config_parameter"].sudo().set_param(key, _PREFIX + token.decode())

    @api.model
    def get_encrypted(self, key: str, default: str | None = None) -> str | None:
        val = self.env["ir.config_parameter"].sudo().get_param(key, default)
        if not val or not val.startswith(_PREFIX):
            return val
        if Fernet is None:
            return None
        f = Fernet(_get_master_key())
        try:
            return f.decrypt(val[len(_PREFIX):].encode()).decode()
        except InvalidToken:
            _logger.error("custom.ir.config: failed to decrypt %s", key)
            return None
