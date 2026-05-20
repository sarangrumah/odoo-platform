"""VPS lifecycle endpoints — register, bootstrap, deploy-stack, sync-addons, health, decommission.

All routes are HMAC-signed (same middleware as ``routers/tenants.py``).
Long-running operations stream logs via Server-Sent Events (SSE) so the
OWL ``vps_console`` can render them live.

NOTE: this router is intentionally NOT registered in ``app/main.py`` here —
the merge step will wire it in. The variable name MUST stay ``router``.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from ..provisioner_ssh import (
    RemoteDockerExecutor,
    SSHCredentialError,
    VPSTarget,
)
from ..validators import (
    BootstrapRequest,
    DeployStackRequest,
    SyncAddonsRequest,
    VPSRegisterRequest,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/vps", tags=["vps"])

# Bootstrap templates live both in the Odoo addon (source of truth) and
# in tenant-orchestrator/bootstrap_templates/ (duplicate for MVP — see
# README/TODO in that directory).
TEMPLATES_DIR = Path(
    os.environ.get(
        "VPS_BOOTSTRAP_TEMPLATES_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "bootstrap_templates"),
    )
)


def _render_template(name: str, ctx: dict) -> str:
    """Render a bootstrap template with a very small {{ var }} substitution.

    We deliberately avoid pulling jinja2 as a hard dep for MVP; the templates
    only use simple ``{{ var }}`` and ``{{ var | default(x) }}`` placeholders.
    For production replace with jinja2.Environment(undefined=StrictUndefined).
    """
    path = TEMPLATES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"template not found: {path}")
    body = path.read_text(encoding="utf-8")
    # Extremely minimal stand-in for jinja2 — only literal var substitution.
    for k, v in ctx.items():
        body = body.replace(f"{{{{ {k} }}}}", str(v))
    return body


def _target_from(req) -> VPSTarget:
    return VPSTarget(
        hostname=req.hostname,
        ssh_user=req.ssh_user,
        ssh_port=req.ssh_port,
        ssh_credential_ref=req.ssh_credential_ref,
    )


def _sse(stream: Iterator[str]) -> Iterator[bytes]:
    """Wrap a line-stream as SSE ``data:`` frames."""
    for line in stream:
        payload = json.dumps({"line": line})
        yield f"data: {payload}\n\n".encode()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_200_OK)
def register_vps(body: VPSRegisterRequest, request: Request) -> dict:
    """Validate SSH reachability + return ``registered`` state.

    NEVER logs credential material.
    """
    actor = getattr(request.state, "actor", "system")
    target = _target_from(body)
    try:
        with RemoteDockerExecutor(target) as ex:
            hc = ex.healthcheck()
    except SSHCredentialError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"credential error: {e}") from e
    except Exception as e:  # noqa: BLE001
        log.warning("vps.register.ssh_failed host=%s err=%s", target.hostname, e)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"SSH connect failed: {e}"
        ) from e
    log.info("vps.registered host=%s actor=%s", target.hostname, actor)
    return {
        "ok": True,
        "vps_id": body.vps_id,
        "hostname": target.hostname,
        "state": "registered",
        "healthcheck": hc,
    }


@router.post("/{vps_id}/bootstrap")
def bootstrap_vps(vps_id: int, body: BootstrapRequest, request: Request) -> StreamingResponse:
    """Execute harden_os + install_docker + install_caddy, SSE-stream logs."""
    target = _target_from(body)
    ctx = {
        "vps_hostname": target.hostname,
        "ssh_port": target.ssh_port,
        "tenant_slug": body.tenant_slug or "shared",
    }
    scripts = ["harden_os.sh.template", "install_docker.sh.template", "install_caddy.sh.template"]

    def gen() -> Iterator[str]:
        try:
            with RemoteDockerExecutor(target) as ex:
                for s in scripts:
                    yield f"=== running {s} ==="
                    body_text = _render_template(s, ctx)
                    yield from ex.run_script(s.replace(".template", ""), body_text)
        except SSHCredentialError as e:
            yield f"ERROR credential: {e}"
        except Exception as e:  # noqa: BLE001
            yield f"ERROR bootstrap: {e}"

    return StreamingResponse(_sse(gen()), media_type="text/event-stream")


@router.post("/{vps_id}/deploy-stack")
def deploy_stack(vps_id: int, body: DeployStackRequest, request: Request) -> StreamingResponse:
    """Generate docker-compose.yml + bring stack up, SSE-stream logs."""
    target = _target_from(body)
    ctx = {
        "vps_hostname": target.hostname,
        "tenant_slug": body.tenant_slug,
        "env_type": body.env_type,
        "db_name": body.db_name,
        "pg_password": body.pg_password or "changeme-bootstrap",
        "workers": body.workers or 2,
    }

    def gen() -> Iterator[str]:
        try:
            with RemoteDockerExecutor(target) as ex:
                yield "=== rendering deploy_odoo ==="
                body_text = _render_template("deploy_odoo.sh.template", ctx)
                yield from ex.run_script("deploy_odoo.sh", body_text)
        except SSHCredentialError as e:
            yield f"ERROR credential: {e}"
        except Exception as e:  # noqa: BLE001
            yield f"ERROR deploy_stack: {e}"

    return StreamingResponse(_sse(gen()), media_type="text/event-stream")


@router.post("/{vps_id}/sync-addons")
def sync_addons(vps_id: int, body: SyncAddonsRequest, request: Request) -> StreamingResponse:
    """Rsync addons → VPS, restart Odoo, ``-u all`` on the tenant DB.

    MVP: emits a stub script. The real rsync wiring will need a known
    source path on the orchestrator host (mounted at /platform-addons).
    """
    target = _target_from(body)
    stack_dir = f"/opt/odoo/{body.tenant_slug}-{body.env_type}"
    script = f"""#!/usr/bin/env bash
set -euo pipefail
echo "[sync_addons] restarting odoo + -u all on {body.db_name}"
cd {stack_dir}
docker compose restart odoo
docker compose exec -T odoo odoo -d {body.db_name} -u all --stop-after-init || true
echo "[sync_addons] DONE"
"""

    def gen() -> Iterator[str]:
        try:
            with RemoteDockerExecutor(target) as ex:
                yield "=== sync_addons ==="
                yield from ex.run_script("sync_addons.sh", script)
        except SSHCredentialError as e:
            yield f"ERROR credential: {e}"
        except Exception as e:  # noqa: BLE001
            yield f"ERROR sync_addons: {e}"

    return StreamingResponse(_sse(gen()), media_type="text/event-stream")


@router.get("/{vps_id}/health")
def health(
    vps_id: int,
    hostname: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    ssh_credential_ref: Optional[str] = None,
) -> dict:
    """Quick SSH + docker-ps probe. Returns ``{ok: bool, output: str}``."""
    if not ssh_credential_ref:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ssh_credential_ref required")
    target = VPSTarget(
        hostname=hostname,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
        ssh_credential_ref=ssh_credential_ref,
    )
    try:
        with RemoteDockerExecutor(target) as ex:
            return ex.healthcheck()
    except SSHCredentialError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@router.post("/{vps_id}/decommission")
def decommission(vps_id: int, body: BootstrapRequest, request: Request) -> dict:
    """Graceful shutdown: stop docker stacks. Does NOT delete the VPS itself."""
    target = _target_from(body)
    script = """#!/usr/bin/env bash
set -euo pipefail
echo "[decommission] stopping all docker compose stacks under /opt/odoo"
for d in /opt/odoo/*/; do
  if [ -f "$d/docker-compose.yml" ]; then
    (cd "$d" && docker compose down) || true
  fi
done
echo "[decommission] DONE"
"""
    try:
        with RemoteDockerExecutor(target) as ex:
            lines = list(ex.run_script("decommission.sh", script))
    except SSHCredentialError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    rc_line = next((l for l in lines if l.startswith("__EXIT__")), "__EXIT__ -1")
    rc = int(rc_line.split(" ", 1)[1])
    return {"ok": rc == 0, "vps_id": vps_id, "exit_code": rc, "log": "\n".join(lines)}
