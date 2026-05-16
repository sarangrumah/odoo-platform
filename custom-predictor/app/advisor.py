"""Call ai-gateway /v1/workflow/predict-capacity with HMAC."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog

from .config import get_settings

log = structlog.get_logger()


def _sign(secret: str, body: bytes) -> tuple[str, int]:
    ts = int(time.time())
    msg = str(ts).encode() + b"." + body
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}", ts


async def request_capacity_advice(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    s = get_settings()
    body = {
        "host": {
            "cpu_cores": s.host_cpu_cores,
            "ram_gb": s.host_ram_gb,
            "disk_gb": s.host_disk_gb,
        },
        "metrics": metrics,
        "window_days": 7,
        "forecast_days": 30,
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    header, _ = _sign(s.gateway_shared_secret, raw)

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        r = await client.post(
            f"{s.ai_gateway_url}/v1/workflow/predict-capacity",
            content=raw,
            headers={"Content-Type": "application/json", "X-Custom-Signature": header, "X-Tenant-Id": "platform"},
        )
        if r.status_code != 200:
            log.error("advisor.error", status=r.status_code, body=r.text[:500])
            return {"error": r.text, "status": r.status_code}
        return r.json()
