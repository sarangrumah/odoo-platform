"""Envelope encryption for per-tenant Fernet keys.

The orchestrator holds a *master wrapping key* (from env, 32-byte URL-safe b64
Fernet key). Each tenant gets its own DEK (data-encryption key) that we wrap
with the master key and store in ``tenant_registry.tenants.fernet_key_wrapped``.

When Odoo for a tenant needs to encrypt sertel etc., it asks the orchestrator
``GET /v1/tenants/{slug}/dek`` (HMAC-protected); the orchestrator unwraps and
returns the DEK over the trusted internal network. (Optionally cache the DEK
in Odoo's in-process memory only — never persist.)
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _master_fernet() -> Fernet:
    return Fernet(get_settings().master_wrapping_key.encode())


def generate_tenant_dek() -> bytes:
    """Return a fresh 32-byte URL-safe-base64 Fernet key (44 bytes)."""
    return Fernet.generate_key()


def wrap_dek(dek: bytes) -> bytes:
    return _master_fernet().encrypt(dek)


def unwrap_dek(wrapped: bytes) -> bytes:
    try:
        return _master_fernet().decrypt(wrapped)
    except InvalidToken as e:
        raise ValueError("Failed to unwrap DEK — wrong master key?") from e
