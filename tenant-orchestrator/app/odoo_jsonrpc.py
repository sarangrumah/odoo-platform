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
        self.password = os.environ.get("ODOO_MGMT_PASSWORD") or os.environ.get("ODOO_MGMT_API_KEY", "")
        self.timeout = float(os.environ.get("ODOO_MGMT_TIMEOUT", "30"))


_lock = threading.Lock()
# Cache the session cookie per (db, user). Odoo 19 doesn't expose /jsonrpc
# external API on this build, so we use the same web-session flow that the
# browser uses: /web/session/authenticate sets a session cookie, then
# /web/dataset/call_kw runs models within that session.
_session_cache: dict[str, str] = {}


def _config() -> _OdooConfig:
    return _OdooConfig()


def _post_json(url: str, payload: dict[str, Any], timeout: float, cookie: str | None = None) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    with httpx.Client(timeout=timeout) as client:
        try:
            return client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise OdooRpcError(f"Transport error to {url}: {e}") from e


def _authenticate(cfg: _OdooConfig) -> str:
    """Return cached session cookie for (db,user); authenticate if missing."""
    key = f"{cfg.db}:{cfg.user}"
    with _lock:
        cached = _session_cache.get(key)
        if cached:
            return cached
        resp = _post_json(
            f"{cfg.url}/web/session/authenticate",
            {
                "jsonrpc": "2.0",
                "params": {"db": cfg.db, "login": cfg.user, "password": cfg.password},
            },
            cfg.timeout,
        )
        if resp.status_code >= 400:
            raise OdooRpcError(f"Odoo authenticate HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if body.get("error"):
            err = body["error"]
            raise OdooRpcError(f"Odoo auth error: {err.get('message')}: {(err.get('data') or {}).get('message', '')}")
        if not (body.get("result") or {}).get("uid"):
            raise OdooRpcError(f"Odoo authentication failed for user={cfg.user} db={cfg.db}")
        set_cookie = resp.headers.get("set-cookie", "")
        # Keep only the session_id=... part; rest is metadata.
        cookie = set_cookie.split(";")[0] if set_cookie else ""
        if not cookie:
            raise OdooRpcError("Odoo did not return a session cookie")
        _session_cache[key] = cookie
        log.info("odoo_jsonrpc.authenticated", user=cfg.user, db=cfg.db, uid=int(body["result"]["uid"]))
        return cookie


def _invalidate_session(cfg: _OdooConfig) -> None:
    with _lock:
        _session_cache.pop(f"{cfg.db}:{cfg.user}", None)


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
        cookie = _authenticate(cfg)
        resp = _post_json(
            f"{cfg.url}/web/dataset/call_kw",
            {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {"model": model, "method": method, "args": args, "kwargs": kwargs},
            },
            cfg.timeout,
            cookie=cookie,
        )
        if resp.status_code in (401, 403):
            raise OdooRpcError("session expired")
        if resp.status_code >= 400:
            raise OdooRpcError(f"Odoo call_kw HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if body.get("error"):
            err = body["error"]
            data = err.get("data") or {}
            detail = data.get("message") or data.get("debug", "")[:300]
            raise OdooRpcError(f"Odoo RPC error on {model}.{method}: {err.get('message')}: {detail}")
        return body.get("result")

    try:
        return _exec()
    except OdooRpcError as e:
        msg = str(e).lower()
        if "session" in msg or "access denied" in msg or "authentication" in msg:
            log.warning("odoo_jsonrpc.session_invalid_retry", error=str(e))
            _invalidate_session(cfg)
            return _exec()
        raise
