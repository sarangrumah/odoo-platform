"""Outbound HTTP to Odoo's HMAC-secured Finance Portal webhook."""

from __future__ import annotations

import json
import logging

import httpx

from .config import settings
from .hmac_util import sign

_logger = logging.getLogger("finance-sap-bridge.odoo")


def _post(path: str, payload: dict) -> bool:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts, sig = sign(settings.outbound_secret, body)
    headers = {
        "Content-Type": "application/json",
        "X-Timestamp": ts,
        "X-Signature": sig,
    }
    url = settings.odoo_base_url.rstrip("/") + path
    try:
        resp = httpx.post(url, content=body, headers=headers, timeout=15)
        ok = 200 <= resp.status_code < 300
        if not ok:
            _logger.error("Odoo %s -> %s %s", path, resp.status_code, resp.text[:300])
        return ok
    except httpx.HTTPError as e:  # pragma: no cover - network
        _logger.error("Odoo %s failed: %s", path, e)
        return False


def push_status(payload: dict) -> bool:
    """Mirror a SAP payment status/plan-date onto a portal document."""
    return _post("/finance/sap/status", payload)


def push_master(kind: str, records: list) -> bool:
    """Realtime master delta into the portal."""
    return _post("/finance/sap/master", {"kind": kind, "records": records})
