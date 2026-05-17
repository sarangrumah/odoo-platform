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

import secrets
import string
from typing import Any

import httpx
import structlog

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
    ) -> None:
        """POST /web/database/create — form-encoded (Odoo expects multipart/form).

        Odoo returns a 303 redirect to /web on success.
        """
        data = {
            "master_pwd": self.master_pwd,
            "name": db_name,
            "login": login,
            "password": admin_password,
            "phone": "",
            "lang": lang,
            "country_code": country_code or "",
            "demo": "1" if demo else "",
        }
        r = self._client.post("/web/database/create", data=data)
        if r.status_code in (200, 303):
            log.info("odoo.db.created", db=db_name)
            return
        raise RuntimeError(
            f"Odoo create_database({db_name}) failed: HTTP {r.status_code} — {r.text[:200]}"
        )

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
        # 1. Authenticate
        auth = self._client.post(
            "/jsonrpc",
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
