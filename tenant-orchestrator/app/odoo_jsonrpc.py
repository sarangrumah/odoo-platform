"""Minimal JSON-RPC client for talking to the odoo-mgmt (control-plane) instance.

Used by the intake router (and future routers) to bridge external systems
(Next.js landing-public) into Odoo without exposing credentials to clients.

Auth strategy:
- Preferred: API key via ``ODOO_MGMT_API_KEY`` — sent through ``/jsonrpc`` using
  ``authenticate`` once per process and re-authenticating on session expiry.
- Fallback: username + password (``ODOO_MGMT_USER`` / ``ODOO_MGMT_PASSWORD``).

Env:
    ODOO_MGMT_URL        e.g. ``http://odoo-mgmt:8069``
    ODOO_MGMT_DB         e.g. ``odoo_mgmt``
    ODOO_MGMT_USER       e.g. ``orchestrator-bot``
    ODOO_MGMT_PASSWORD   plaintext (use Vault in prod; rotated regularly)
    ODOO_MGMT_API_KEY    optional API key (Odoo 14+ user API key)
    ODOO_MGMT_TIMEOUT    request timeout seconds, default 30

This module is intentionally small and synchronous (uses ``httpx.Client``) to
match the rest of the orchestrator codebase. All errors are surfaced as
``OdooRpcError`` so callers can map to HTTP status cleanly.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class OdooRpcError(RuntimeError):
    """Raised on RPC transport or Odoo-side errors."""


class _OdooConfig:
    def __init__(self) -> None:
        self.url = os.environ.get("ODOO_MGMT_URL", "http://odoo-mgmt:8069").rstrip("/")
        self.db = os.environ.get("ODOO_MGMT_DB", "odoo_mgmt")
        self.user = os.environ.get("ODOO_MGMT_USER", "admin")
        self.password = os.environ.get("ODOO_MGMT_PASSWORD") or os.environ.get(
            "ODOO_MGMT_API_KEY", ""
        )
        self.timeout = float(os.environ.get("ODOO_MGMT_TIMEOUT", "30"))


_lock = threading.Lock()
_uid_cache: dict[str, int] = {}


def _config() -> _OdooConfig:
    return _OdooConfig()


def _jsonrpc(url: str, method: str, params: dict[str, Any], timeout: float) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": params,
    }
    with httpx.Client(timeout=timeout) as client:
        try:
            resp = client.post(url, json=payload)
        except httpx.HTTPError as e:
            raise OdooRpcError(f"Transport error to {url}: {e}") from e
    if resp.status_code >= 400:
        raise OdooRpcError(f"Odoo {method} HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    if body.get("error"):
        err = body["error"]
        data = err.get("data") or {}
        raise OdooRpcError(
            f"Odoo RPC error: {err.get('message')}: {data.get('message') or data.get('debug', '')[:300]}"
        )
    return body.get("result")


def _authenticate(cfg: _OdooConfig) -> int:
    """Return cached uid for (db,user); authenticate if missing."""
    key = f"{cfg.db}:{cfg.user}"
    with _lock:
        cached = _uid_cache.get(key)
        if cached:
            return cached
        uid = _jsonrpc(
            f"{cfg.url}/jsonrpc",
            "common.authenticate",
            {
                "service": "common",
                "method": "authenticate",
                "args": [cfg.db, cfg.user, cfg.password, {}],
            },
            cfg.timeout,
        )
        if not uid:
            raise OdooRpcError(
                f"Odoo authentication failed for user={cfg.user} db={cfg.db}"
            )
        _uid_cache[key] = int(uid)
        log.info("odoo_jsonrpc.authenticated", user=cfg.user, db=cfg.db, uid=int(uid))
        return int(uid)


def _invalidate_session(cfg: _OdooConfig) -> None:
    with _lock:
        _uid_cache.pop(f"{cfg.db}:{cfg.user}", None)


def call(
    model: str,
    method: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> Any:
    """Call ``model.method(*args, **kwargs)`` on odoo-mgmt.

    Transparently authenticates and retries once if the session was invalidated.
    """
    cfg = _config()
    args = args or []
    kwargs = kwargs or {}

    def _exec() -> Any:
        uid = _authenticate(cfg)
        return _jsonrpc(
            f"{cfg.url}/jsonrpc",
            f"object.execute_kw({model}.{method})",
            {
                "service": "object",
                "method": "execute_kw",
                "args": [cfg.db, uid, cfg.password, model, method, args, kwargs],
            },
            cfg.timeout,
        )

    try:
        return _exec()
    except OdooRpcError as e:
        msg = str(e).lower()
        if "session" in msg or "access denied" in msg or "authentication" in msg:
            log.warning("odoo_jsonrpc.session_invalid_retry", error=str(e))
            _invalidate_session(cfg)
            return _exec()
        raise
