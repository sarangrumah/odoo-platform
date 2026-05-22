"""Talk to Odoo's master / database manager endpoints.

Odoo exposes `/web/database/create`, `/web/database/drop`, and JSON-RPC
endpoints that we use to:
  * Create the DB *through* Odoo (so it installs `base` properly).
  * Install modules (`base.module.upgrade`) after provisioning.

We prefer this over manual `CREATE DATABASE + odoo -d X --init` because the
running Odoo container already has all addons mounted and avoids a
container restart loop.
"""

from __future__ import annotations

import os
import secrets
import string
import subprocess
from typing import Any

import httpx
import structlog

from . import dbops
from .config import get_settings

log = structlog.get_logger()


def gen_initial_admin_password(length: int = 24) -> str:
    """Strong, copy-pasteable initial admin password (no ambiguous chars)."""
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class OdooAdminClient:
    """Thin wrapper around Odoo's database manager + JSON-RPC."""

    def __init__(self, base_url: str | None = None) -> None:
        s = get_settings()
        self.base_url = base_url or f"http://{s.odoo_host}:{s.odoo_port}"
        self.master_pwd = s.odoo_admin_passwd
        self._client = httpx.Client(base_url=self.base_url, timeout=180.0, follow_redirects=False)
        # Container name for CLI provisioning. Default matches docker-compose.multitenant.yml.
        self._mgmt_container = os.environ.get("ODOO_MGMT_CONTAINER", "odoo19-platform-odoo-mgmt")
        self._tenant_owner = s.pg_tenant_owner_role

    def close(self) -> None:
        self._client.close()

    # -----------------------------------------------------------------
    # DB lifecycle
    # -----------------------------------------------------------------

    def create_database(
        self,
        db_name: str,
        admin_password: str,
        *,
        lang: str = "en_US",
        country_code: str | None = "ID",
        login: str = "admin",
        demo: bool = False,
        init_modules: list[str] | None = None,
    ) -> None:
        """Create a tenant database and initialise it deterministically.

        Two-phase to avoid the unreliability of Odoo 19's ``/web/database/create``
        HTTP endpoint (which returns 200 even when ``-i base`` fails inside):

          1. ``CREATE DATABASE`` via psycopg as superuser (atomic, fast).
          2. ``odoo -d <db> --init=<modules> --stop-after-init --without-demo``
             executed inside the ``odoo-mgmt`` container via ``docker exec``.
             Surface failures by exit code instead of HTML.

        ``init_modules`` defaults to ``['base']`` — caller is expected to install
        the platform's custom module set via ``install_modules()`` afterwards.
        """
        mods = init_modules or ["base"]
        # 1. Direct psycopg CREATE DATABASE
        if not dbops.db_exists(db_name):
            dbops.create_database(db_name=db_name, owner_role=self._tenant_owner)
            log.info("odoo.db.created", db=db_name, mode="psycopg")

        # 2. Init base + custom modules via CLI
        cmd = [
            "docker",
            "exec",
            self._mgmt_container,
            "odoo",
            "-d",
            db_name,
            "--init",
            ",".join(mods),
            "--stop-after-init",
            "--without-demo",
        ]
        log.info("odoo.db.init.cli", db=db_name, modules=mods)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            tail = (result.stderr or "")[-1500:]
            raise RuntimeError(f"Odoo init({db_name}) CLI failed (exit {result.returncode}): {tail}")
        # The admin user (login=admin) password defaults to 'admin' after a -i base.
        # Reset it to the orchestrator-supplied value so subsequent JSON-RPC works.
        # We do this with a one-shot psql update through dbops.
        dbops.set_admin_password(db_name=db_name, login=login, password=admin_password)
        log.info("odoo.db.init.done", db=db_name)

    def drop_database(self, db_name: str) -> None:
        data = {"master_pwd": self.master_pwd, "name": db_name}
        r = self._client.post("/web/database/drop", data=data)
        if r.status_code in (200, 303):
            log.info("odoo.db.dropped", db=db_name)
            return
        raise RuntimeError(f"Odoo drop_database({db_name}) failed: HTTP {r.status_code}")

    def list_databases(self) -> list[str]:
        r = self._client.post("/web/database/list", json={"jsonrpc": "2.0", "params": {}})
        r.raise_for_status()
        return r.json().get("result", [])

    # -----------------------------------------------------------------
    # JSON-RPC against a specific tenant DB
    # -----------------------------------------------------------------

    def _rpc(self, db: str, model: str, method: str, args: list[Any], login: str, password: str) -> Any:
        # The orchestrator targets the private ``odoo-mgmt`` service which runs
        # with DBFILTER=^.*$ and LIST_DB=True. ``X-Odoo-Database`` is still set
        # as belt-and-braces: it gives Odoo 19's dispatcher an unambiguous DB
        # signal even if the host header is ever changed by a proxy.
        headers = {"X-Odoo-Database": db}
        # 1. Authenticate
        auth = self._client.post(
            "/jsonrpc",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "common",
                    "method": "authenticate",
                    "args": [db, login, password, {}],
                },
            },
        )
        auth.raise_for_status()
        uid = auth.json().get("result")
        if not uid:
            raise PermissionError(f"Odoo authenticate failed for db={db} login={login}")

        # 2. Call
        r = self._client.post(
            "/jsonrpc",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": [db, uid, password, model, method, args],
                },
            },
        )
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload.get("result")

    def install_modules(self, db: str, login: str, password: str, module_names: list[str]) -> None:
        """Install (or upgrade) modules in the tenant DB."""
        if not module_names:
            return
        ir_module = "ir.module.module"
        module_ids = self._rpc(
            db,
            ir_module,
            "search",
            [[("name", "in", module_names)]],
            login,
            password,
        )
        if module_ids:
            self._rpc(db, ir_module, "button_immediate_install", [module_ids], login, password)
            log.info("odoo.modules.installed", db=db, modules=module_names)
