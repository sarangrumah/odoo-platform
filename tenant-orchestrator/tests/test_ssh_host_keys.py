"""Host-key policy: a VPS that changes identity must be refused.

The old code set AutoAddPolicy unconditionally and never persisted anything,
so every connection accepted whatever key was offered -- an MITM on any
connection, not just the first, went unnoticed.
"""

from __future__ import annotations

import pytest

paramiko = pytest.importorskip("paramiko")

from app import config, provisioner_ssh  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setenv("SSH_KNOWN_HOSTS_FILE", str(tmp_path / "known_hosts"))
    monkeypatch.setenv("SSH_STRICT_HOST_KEYS", "false")
    yield
    monkeypatch.setattr(config, "_settings", None)


def test_known_hosts_file_is_created_and_loaded(tmp_path):
    client = paramiko.SSHClient()
    path = provisioner_ssh._load_known_hosts(client)
    assert path == str(tmp_path / "known_hosts")
    assert (tmp_path / "known_hosts").exists()


def test_strict_mode_rejects_an_unknown_host(monkeypatch):
    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setenv("SSH_STRICT_HOST_KEYS", "true")
    policy = provisioner_ssh._missing_host_key_policy("/tmp/known_hosts")
    assert isinstance(policy, paramiko.RejectPolicy)


def test_default_mode_pins_on_first_use(tmp_path):
    """First sight is trusted, but the key is written so the next one is checked."""
    client = paramiko.SSHClient()
    path = provisioner_ssh._load_known_hosts(client)
    policy = provisioner_ssh._missing_host_key_policy(path)
    assert isinstance(policy, provisioner_ssh._PinOnFirstUse)
    assert not isinstance(policy, paramiko.AutoAddPolicy)

    key = paramiko.ECDSAKey.generate()
    policy.missing_host_key(client, "vps-a.example.com", key)

    # Persisted as a real known_hosts entry, not just a substring somewhere.
    entries = paramiko.HostKeys(str(tmp_path / "known_hosts"))
    assert entries.lookup("vps-a.example.com") is not None
    # ...and a fresh client now knows the host, so paramiko verifies it
    # instead of asking the policy again.
    reloaded = paramiko.SSHClient()
    reloaded.load_host_keys(str(tmp_path / "known_hosts"))
    assert reloaded.get_host_keys().lookup("vps-a.example.com") is not None


def test_a_changed_host_key_is_not_silently_accepted(tmp_path):
    """The MITM case: same host, different key. paramiko must not match it."""
    client = paramiko.SSHClient()
    path = provisioner_ssh._load_known_hosts(client)
    policy = provisioner_ssh._missing_host_key_policy(path)

    original = paramiko.ECDSAKey.generate()
    policy.missing_host_key(client, "vps-b.example.com", original)

    reloaded = paramiko.SSHClient()
    reloaded.load_host_keys(str(tmp_path / "known_hosts"))
    entry = reloaded.get_host_keys().lookup("vps-b.example.com")

    impostor = paramiko.ECDSAKey.generate()
    assert entry[original.get_name()] == original
    assert entry[original.get_name()] != impostor


def test_missing_known_hosts_file_still_pins_for_the_process(monkeypatch):
    """No writable file must not mean "accept anything", as it used to."""
    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setenv("SSH_KNOWN_HOSTS_FILE", "")
    provisioner_ssh._SESSION_HOST_KEYS.clear()

    client = paramiko.SSHClient()
    assert provisioner_ssh._load_known_hosts(client) == ""
    policy = provisioner_ssh._missing_host_key_policy("")
    # Never AutoAddPolicy: that re-trusts a changed key silently.
    assert not isinstance(policy, paramiko.AutoAddPolicy)

    original = paramiko.ECDSAKey.generate()
    policy.missing_host_key(client, "vps-c.example.com", original)

    # Same key again is fine; a different one for the same host is refused.
    policy.missing_host_key(client, "vps-c.example.com", original)
    impostor = paramiko.ECDSAKey.generate()
    with pytest.raises(paramiko.SSHException, match="changed since it was pinned"):
        policy.missing_host_key(client, "vps-c.example.com", impostor)

    # And a later client inherits the pin even with no file on disk.
    fresh = paramiko.SSHClient()
    provisioner_ssh._load_known_hosts(fresh)
    assert fresh.get_host_keys().lookup("vps-c.example.com") is not None
    provisioner_ssh._SESSION_HOST_KEYS.clear()
