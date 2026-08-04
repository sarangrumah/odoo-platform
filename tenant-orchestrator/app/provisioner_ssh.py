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
from collections.abc import Iterator
from dataclasses import dataclass

try:
    import paramiko  # type: ignore
except ImportError:  # pragma: no cover
    paramiko = None  # noqa: N816

log = logging.getLogger(__name__)


class SSHCredentialError(RuntimeError):
    """Raised when ssh_credential_ref cannot be resolved.

    Carries two messages on purpose. ``str(exc)`` is the diagnostic one and is
    for logs only -- it names the env var, the key path or the Vault path that
    failed, which is exactly what an operator needs and exactly what a caller
    must not see. ``public_reason`` is the category-level sentence that is safe
    to put in an HTTP response or an SSE frame.

    Before this split every one of these messages was echoed straight back to
    the client (``yield f"ERROR credential: {e}"``), disclosing server paths,
    environment variable names and Vault locations to anyone who could reach
    the endpoint -- CodeQL py/stack-trace-exposure, and it was right.
    """

    #: Shown to callers when nothing more specific is set.
    DEFAULT_PUBLIC = "ssh credential could not be resolved"

    def __init__(self, message: str, *, public_reason: str | None = None) -> None:
        super().__init__(message)
        self.public_reason = public_reason or self.DEFAULT_PUBLIC


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
        raise SSHCredentialError("empty ssh_credential_ref", public_reason="no ssh credential configured")
    if ref.startswith("env://"):
        var = ref[len("env://") :]
        val = os.environ.get(var)
        if not val:
            raise SSHCredentialError(
                f"env var {var} not set", public_reason="ssh credential is not available on the server"
            )
        return val
    if ref.startswith("file://"):
        path = ref[len("file://") :]
        if path.startswith("/"):
            # file:///abs/path style
            path = "/" + path.lstrip("/")
        if not os.path.isfile(path):
            raise SSHCredentialError(
                f"key file not found: {path}", public_reason="ssh credential is not available on the server"
            )
        with open(path, encoding="utf-8") as f:
            return f.read()
    if ref.startswith("vault://"):
        return _resolve_vault_ref(ref)
    raise SSHCredentialError(
        f"unsupported credential scheme: {ref.split('://', 1)[0]}",
        public_reason="ssh credential ref uses an unsupported scheme",
    )


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
            "vault.skip: VAULT_ADDR not configured, skipping vault:// resolution for ref=%s",
            ref,
        )
        raise SSHCredentialError(
            "vault:// credential resolver not configured (VAULT_ADDR unset) — "
            "set up Vault or use file:// / env:// refs for dev",
            # Names no server path or variable, and the hint is the whole point
            # of the dev/UAT "skipped" response, so it stays public verbatim.
            public_reason=(
                "vault:// credential resolver not configured — set up Vault or use file:// / env:// refs for dev"
            ),
        )
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_token:
        raise SSHCredentialError(
            "VAULT_TOKEN not set — cannot authenticate to Vault",
            public_reason="ssh credential store is not reachable",
        )
    try:
        import urllib.request  # local import: avoid runtime cost when unused
    except ImportError as e:  # pragma: no cover
        raise SSHCredentialError(
            f"urllib unavailable: {e}", public_reason="ssh credential store is not reachable"
        ) from e

    body = ref[len("vault://") :]
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
        raise SSHCredentialError(
            f"vault lookup failed: {e}", public_reason="ssh credential store is not reachable"
        ) from e
    data = (payload.get("data") or {}).get("data") or payload.get("data") or {}
    val = data.get(field)
    if not val:
        raise SSHCredentialError(
            f"vault secret at {body} has no '{field}' key",
            public_reason="ssh credential is not available on the server",
        )
    return val


def _load_known_hosts(client) -> str:
    """Load the pinned host keys into ``client``. Returns the file path used.

    Returns "" when no file could be loaded, which is not fatal: the caller
    decides what to do about unknown hosts.
    """
    from .config import get_settings

    path = (get_settings().ssh_known_hosts_file or "").strip()
    if not path:
        return ""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            # Touch it so paramiko's save_host_keys() has somewhere to write.
            with open(path, "a", encoding="utf-8"):
                pass
        client.load_host_keys(path)
        return path
    except OSError as e:
        # A read-only or missing volume must not take provisioning down; it
        # degrades to "unknown host" handling, which is still stricter than
        # the old unconditional auto-add when strict mode is on.
        log.warning("ssh.known_hosts.unavailable path=%s err=%s", path, e)
        return ""


def _missing_host_key_policy(known_hosts: str):
    """Pick the policy for a host we have never seen.

    Known hosts are always verified by paramiko against the loaded keys, so a
    VPS whose key changes is refused either way -- that is the MITM case this
    exists for. The choice here only covers the *first* sight of a host:

      * strict mode -> reject; the key must be pre-seeded in known_hosts.
      * otherwise   -> trust on first use and persist it, so every later
        connection is verified. This keeps first-deploy bootstrap working,
        which is why AutoAddPolicy was there in the first place, while
        closing the window where every connection accepted any key forever.
    """
    from .config import get_settings

    if get_settings().ssh_strict_host_keys:
        return paramiko.RejectPolicy()
    if not known_hosts:
        # Nowhere to persist: this is the old behaviour, and it is why the
        # warning is loud. Fix the volume or turn strict mode on.
        log.warning("ssh.host_key.unpinned: no known_hosts file, host keys cannot be verified")
        return paramiko.AutoAddPolicy()
    return _PersistingAutoAdd(known_hosts)


class _PersistingAutoAdd(paramiko.MissingHostKeyPolicy if paramiko else object):
    """Trust on first use, then write the key so it is verified from then on."""

    def __init__(self, path: str) -> None:
        self._path = path

    def missing_host_key(self, client, hostname, key) -> None:
        log.warning(
            "ssh.host_key.pinned_on_first_use host=%s type=%s fp=%s",
            hostname,
            key.get_name(),
            key.get_fingerprint().hex(),
        )
        client.get_host_keys().add(hostname, key.get_name(), key)
        try:
            client.save_host_keys(self._path)
        except OSError as e:
            log.warning("ssh.host_key.persist_failed path=%s err=%s", self._path, e)


class RemoteDockerExecutor:
    """Thin paramiko wrapper for running idempotent shell scripts on a VPS.

    Each ``run_script`` invocation:
      1. SCP-uploads the (already-rendered) script body to ``/tmp/<name>``.
      2. ``chmod +x`` + ``sudo bash``.
      3. Streams stdout/stderr line-by-line (consumed by FastAPI SSE).
    """

    def __init__(self, target: VPSTarget):
        if paramiko is None:
            raise RuntimeError("paramiko not installed — add 'paramiko' to tenant-orchestrator deps")
        self.target = target
        self._client: paramiko.SSHClient | None = None

    def __enter__(self) -> RemoteDockerExecutor:
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
                raise SSHCredentialError(
                    f"could not parse ssh key: {e}", public_reason="ssh credential is not usable"
                ) from e
        client = paramiko.SSHClient()
        known_hosts = _load_known_hosts(client)
        client.set_missing_host_key_policy(_missing_host_key_policy(known_hosts))
        log.info(
            "ssh.connect",
            extra={
                "host": self.target.hostname,
                "user": self.target.ssh_user,
                "known_hosts": known_hosts or "none",
            },
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
