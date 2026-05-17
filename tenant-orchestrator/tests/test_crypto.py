"""Per-tenant DEK wrap/unwrap roundtrip."""

from __future__ import annotations

from app.crypto import generate_tenant_dek, unwrap_dek, wrap_dek


def test_dek_roundtrip():
    dek = generate_tenant_dek()
    wrapped = wrap_dek(dek)
    assert wrapped != dek                # ciphertext differs from plaintext
    assert unwrap_dek(wrapped) == dek    # decrypts back exactly


def test_wrong_master_key_fails(monkeypatch):
    import pytest
    from app import config

    dek = generate_tenant_dek()
    wrapped = wrap_dek(dek)

    # Rotate master key in settings — unwrap should fail
    monkeypatch.setattr(
        config, "_settings", None
    )
    monkeypatch.setenv("MASTER_WRAPPING_KEY", "DIFFERENT_KEY_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx=")

    with pytest.raises(ValueError, match="unwrap"):
        unwrap_dek(wrapped)
