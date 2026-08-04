"""SSHCredentialError must never hand server internals to a caller.

Every resolver failure names something an operator needs and a client must not
see -- the env var, the key path, the Vault path. Those belong in ``str(exc)``,
which is logged; callers only ever get ``public_reason``.
"""

from __future__ import annotations

import pytest

from app.provisioner_ssh import SSHCredentialError, resolve_ssh_key

# Substrings that would identify server internals if they escaped.
_SECRETS = ("/etc/", "/srv/", "/root/", "secret/data/", "VAULT", "_SSH_KEY", "Traceback")


def _assert_public_is_clean(exc: SSHCredentialError) -> None:
    public = exc.public_reason
    assert public, "every SSHCredentialError needs a public reason"
    for needle in _SECRETS:
        assert needle not in public, f"public_reason leaked {needle!r}: {public!r}"


def test_missing_env_var_keeps_the_name_out_of_the_public_reason(monkeypatch):
    monkeypatch.delenv("TENANT_A_SSH_KEY", raising=False)
    with pytest.raises(SSHCredentialError) as ei:
        resolve_ssh_key("env://TENANT_A_SSH_KEY")
    # The operator still gets the variable name in the log message...
    assert "TENANT_A_SSH_KEY" in str(ei.value)
    # ...but the caller does not.
    assert "TENANT_A_SSH_KEY" not in ei.value.public_reason
    _assert_public_is_clean(ei.value)


def test_missing_key_file_keeps_the_path_out_of_the_public_reason():
    with pytest.raises(SSHCredentialError) as ei:
        resolve_ssh_key("file:///srv/secrets/tenant-a/id_ed25519")
    assert "/srv/secrets/tenant-a/id_ed25519" in str(ei.value)
    assert "/srv/secrets" not in ei.value.public_reason
    _assert_public_is_clean(ei.value)


def test_vault_path_stays_private(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://vault.internal:8200")
    monkeypatch.setenv("VAULT_TOKEN", "s.testtoken")
    with pytest.raises(SSHCredentialError) as ei:
        # No Vault is listening, so the lookup fails inside urlopen.
        resolve_ssh_key("vault://secret/data/tenants/tenant-a#private_key")
    assert "vault.internal" not in ei.value.public_reason
    assert "secret/data" not in ei.value.public_reason
    _assert_public_is_clean(ei.value)


def test_unsupported_scheme_and_empty_ref_are_public_safe():
    for ref in ("", "s3://bucket/key", "http://10.0.0.5/key.pem"):
        with pytest.raises(SSHCredentialError) as ei:
            resolve_ssh_key(ref)
        _assert_public_is_clean(ei.value)


def test_public_reason_defaults_when_not_given():
    exc = SSHCredentialError("internal detail with /etc/secret path")
    assert exc.public_reason == SSHCredentialError.DEFAULT_PUBLIC
    assert "/etc/secret" in str(exc)
    _assert_public_is_clean(exc)
