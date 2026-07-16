"""finance-sap-bridge — FastAPI app.

Inbound (Odoo → bridge): HMAC-verified, then produced to Kafka (Portal → SAP) or
served as request/reply (master/PR lookup).
Background (SAP/HRIS → Portal): Kafka consumer translates and calls the Odoo
HMAC webhook via odoo_client.
"""

from __future__ import annotations

import logging
import threading

from fastapi import FastAPI, Request, Response

from .config import settings
from .hmac_util import verify
from .kafka_io import kafka
from . import odoo_client

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
_logger = logging.getLogger("finance-sap-bridge")

app = FastAPI(title="finance-sap-bridge", version="0.1.0")


async def _verified_body(request: Request) -> tuple[bytes | None, dict]:
    """Read raw body and verify HMAC against the inbound secret."""
    body = await request.body()
    err = verify(
        settings.inbound_secret,
        body,
        request.headers.get("X-Signature", ""),
        request.headers.get("X-Timestamp", ""),
        drift=settings.hmac_drift_seconds,
    )
    if err:
        return None, {"error": err}
    import json

    try:
        return body, json.loads(body or b"{}")
    except (ValueError, TypeError):
        return None, {"error": "BAD_JSON"}


def _json(payload: dict, status: int = 200) -> Response:
    import json

    return Response(content=json.dumps(payload), media_type="application/json", status_code=status)


@app.get("/health")
def health():
    return {"ok": True, "kafka": kafka.enabled, "mode": "live" if kafka.enabled else "mock"}


# also reachable as /from-odoo/health for the adapter health_check
@app.post("/from-odoo/health")
async def health_post():
    return {"ok": True}


@app.post("/from-odoo/finance/push")
async def from_odoo_push(request: Request):
    """Approved document from the portal → produce to portal.to-sap.<doctype>."""
    body, data = await _verified_body(request)
    if body is None:
        return _json({"ok": False, **data}, status=401 if data.get("error") != "BAD_JSON" else 400)
    doctype = (data.get("doc_type") or "unknown").split(".")[-1]
    topic = f"{settings.topic_prefix_to_sap}.{doctype}"
    key = data.get("reference") or ""
    kafka.produce(topic, key=key, payload=data)
    _logger.info("pushed %s to %s", key, topic)
    # In mock mode SAP never acks; production consumes sap.to-portal.ack and calls
    # odoo_client.push_status. We return accepted so the Odoo job completes.
    return _json({"ok": True, "topic": topic, "key": key})


@app.post("/from-odoo/finance/master/{kind}")
async def from_odoo_master(kind: str, request: Request):
    """Master pull (request/reply). Production queries SAP; mock returns empty."""
    body, data = await _verified_body(request)
    if body is None:
        return _json({"ok": False, **data}, status=401)
    # TODO: real request/reply to SAP over Kafka or OData. Mock: empty feed.
    return _json({"ok": True, "kind": kind, "records": []})


@app.post("/from-odoo/finance/pr/lookup")
async def from_odoo_pr_lookup(request: Request):
    """Realtime PR lookup. Mock returns not-found; production queries SAP."""
    body, data = await _verified_body(request)
    if body is None:
        return _json({"ok": False, **data}, status=401)
    return _json({"ok": True, "pr_number": data.get("pr_number"), "found": False, "value": 0, "status": None})


# --------------------------------------------------------------------------
# Background consumers: SAP/HRIS → Portal
# --------------------------------------------------------------------------
def _on_sap_message(topic: str, payload: dict):
    if topic.endswith(".status") or "status" in topic:
        odoo_client.push_status(payload)
    elif "master" in topic:
        odoo_client.push_master(payload.get("kind", "unknown"), payload.get("records", []))


def _on_hris_message(topic: str, payload: dict):
    odoo_client.push_master("travel", payload.get("records", []))


@app.on_event("startup")
def _start_consumers():
    if not kafka.enabled:
        _logger.info("startup: kafka mock mode — no consumers started")
        return
    threading.Thread(
        target=kafka.consume_loop,
        args=([settings.topic_from_sap], _on_sap_message),
        daemon=True,
    ).start()
    threading.Thread(
        target=kafka.consume_loop,
        args=([settings.topic_from_hris], _on_hris_message),
        daemon=True,
    ).start()
    _logger.info("startup: kafka consumers started")
