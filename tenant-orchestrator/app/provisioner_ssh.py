"""SSH-based remote executor for VPS bootstrap + deploy operations.

Uses paramiko. SSH credentials are resolved at call-time from the
``ssh_credential_ref`` pointer (vault:// or env://) so they're never
held in memory longer than needed and never logged.

For MVP the resolver supports:
  - ``env://VAR_NAME``     → read PEM body from env var
  - ``file:///path/to/key``→ read PEM body from local file
  - ``vault://...``        → reserved (NotImplemented), placeholder for HashiCorp Vault

A future implementation should call the Vault HTTP API with a short-lived
token issued via Kubernetes/AppRole auth.
"""

from __future__ import annotations

import io
import logging
import os
import shlex
from dataclasses import dataclass
from typing import Iterator

try:
    import paramiko  # type: ignore
except ImportError:  # pragma: no cover
    paramiko = None  # noqa: N816

log = logging.getLogger(__name__)


class SSHCredentialError(RuntimeError):
    """Raised when ssh_credential_ref cannot be resolved."""


@dataclass(frozen=True)
class VPSTarget:
    hostname: str
    ssh_user: str
    ssh_port: int
    ssh_credential_ref: str


def resolve_ssh_key(ref: str) -> str:
    """Resolve a credential ref to a PEM private key body.

    Supported schemes:
      * ``env://VAR_NAME``        — read PEM body from env var
      * ``file:///abs/path``      — read PEM body from local file
      * ``vault://path/to/key``   — read from HashiCorp Vault if
        ``VAULT_ADDR`` is configured; otherwise raises
        ``SSHCredentialError`` with a friendly hint so callers can
        skip the action gracefully in dev/UAT.

    NEVER log the returned material.
    """
    if not ref:
        raise SSHCredentialError("empty ssh_credential_ref")
    if ref.startswith("env://"):
        var = ref[len("env://"):]
        val = os.environ.get(var)
        if not val:
            raise SSHCredentialError(f"env var {var} not set")
        return val
    if ref.startswith("file://"):
        path = ref[len("file://"):]
        if path.startswith("/"):
            # file:///abs/path style
            path = "/" + path.lstrip("/")
        if not os.path.isfile(path):
            raise SSHCredentialError(f"key file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    if ref.startswith("vault://"):
        return _resolve_vault_ref(ref)
    raise SSHCredentialError(f"unsupported credential scheme: {ref.split('://', 1)[0]}")


def _resolve_vault_ref(ref: str) -> str:
    """Resolve ``vault://path/to/secret#field`` against HashiCorp Vault.

    Requires ``VAULT_ADDR`` and ``VAULT_TOKEN`` env vars. If ``VAULT_ADDR``
    is not configured we raise ``SSHCredentialError`` with a friendly hint;
    the router-level handler then converts that to a 200 "skipped" response
    so dev/UAT does not get a 502 stack-trace.
    """
    vault_addr = os.environ.get("VAULT_ADDR")
    if not vault_addr:
        log.warning(
            "vault.skip: VAULT_ADDR not configured, skipping vault:// resolution "
            "for ref=%s",
            ref,
        )
        raise SSHCredentialError(
            "vault:// credential resolver not configured (VAULT_ADDR unset) — "
            "set up Vault or use file:// / env:// refs for dev"
        )
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_token:
        raise SSHCredentialError(
            "VAULT_TOKEN not set — cannot authenticate to Vault"
        )
    try:
        import urllib.request  # local import: avoid runtime cost when unused
    except ImportError as e:  # pragma: no cover
        raise SSHCredentialError(f"urllib unavailable: {e}") from e

    body = ref[len("vault://"):]
    # Allow optional ``#field`` suffix to pick a specific key from the secret.
    field = "private_key"
    if "#" in body:
        body, field = body.split("#", 1)
    url = f"{vault_addr.rstrip('/')}/v1/{body.lstrip('/')}"
    req = urllib.request.Request(url, headers={"X-Vault-Token": vault_token})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            import json as _json
            payload = _json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise SSHCredentialError(f"vault lookup failed: {e}") from e
    data = (payload.get("data") or {}).get("data") or payload.get("data") or {}
    val = data.get(field)
    if not val:
        raise SSHCredentialError(
            f"vault secret at {body} has no '{field}' key"
        )
    return val


class RemoteDockerExecutor:
    """Thin paramiko wrapper for running idempotent shell scripts on a VPS.

    Each ``run_script`` invocation:
      1. SCP-uploads the (already-rendered) script body to ``/tmp/<name>``.
      2. ``chmod +x`` + ``sudo bash``.
      3. Streams stdout/stderr line-by-line (consumed by FastAPI SSE).
    """

    def __init__(self, target: VPSTarget):
        if paramiko is None:
            raise RuntimeError(
                "paramiko not installed — add 'paramiko' to tenant-orchestrator deps"
            )
        self.target = target
        self._client: "paramiko.SSHClient | None" = None

    def __enter__(self) -> "RemoteDockerExecutor":
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def connect(self) -> None:
        if self._client is not None:
            return
        key_body = resolve_ssh_key(self.target.ssh_credential_ref)
        try:
            pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(key_body))
        except Exception:
            try:
                pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_body))
            except Exception as e:
                raise SSHCredentialError(f"could not parse ssh key: {e}") from e
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        log.info(
            "ssh.connect",
            extra={"host": self.target.hostname, "user": self.target.ssh_user},
        )
        client.connect(
            hostname=self.target.hostname,
            port=self.target.ssh_port,
            username=self.target.ssh_user,
            pkey=pkey,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            allow_agent=False,
            look_for_keys=False,
        )
        self._client = client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # ------------------------------------------------------------------

    def _exec(self, command: str) -> Iterator[str]:
        assert self._client is not None
        stdin, stdout, stderr = self._client.exec_command(command, get_pty=True, timeout=600)
        stdin.close()
        for raw in iter(stdout.readline, ""):
            if not raw:
                break
            yield raw.rstrip("\n")
        err = stderr.read().decode(errors="replace").strip()
        if err:
            for line in err.splitlines():
                yield f"STDERR {line}"
        rc = stdout.channel.recv_exit_status()
        yield f"__EXIT__ {rc}"

    def upload_text(self, remote_path: str, body: str) -> None:
        assert self._client is not None
        sftp = self._client.open_sftp()
        try:
            with sftp.file(remote_path, "w") as f:
                f.write(body)
            sftp.chmod(remote_path, 0o755)
        finally:
            sftp.close()

    def run_script(self, name: str, body: str) -> Iterator[str]:
        """Upload + execute a script. Yields log lines; last line is ``__EXIT__ <rc>``."""
        remote_path = f"/tmp/{name}"
        self.upload_text(remote_path, body)
        yield f"uploaded {remote_path} ({len(body)} bytes)"
        cmd = f"sudo bash {shlex.quote(remote_path)}"
        yield from self._exec(cmd)

    def healthcheck(self) -> dict:
        """Best-effort: docker ps + uname."""
        assert self._client is not None
        out_lines: list[str] = []
        ok = True
        for line in self._exec("docker ps --format '{{.Names}} {{.Status}}' && uname -a"):
            if line.startswith("__EXIT__"):
                rc = int(line.split(" ", 1)[1])
                ok = rc == 0
            else:
                out_lines.append(line)
        return {"ok": ok, "output": "\n".join(out_lines)}
