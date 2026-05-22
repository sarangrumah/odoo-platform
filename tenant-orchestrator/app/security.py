"""HMAC verification middleware (parity with ai-gateway)."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import get_settings

log = structlog.get_logger()

EXEMPT_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}


def _err(code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": detail})


class HMACMiddleware(BaseHTTPMiddleware):
    """Verify ``X-Custom-Signature: t=<ts>,v1=<hex>`` for all /v1/* routes.

    HMAC over ``f"{ts}.{raw_body}"``, replay window from settings.
    Same scheme used by ai-gateway so Odoo can use one HMAC helper.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in EXEMPT_PATHS or not request.url.path.startswith("/v1/"):
            return await call_next(request)

        settings = get_settings()
        sig = request.headers.get("X-Custom-Signature", "")
        if not sig:
            return _err(status.HTTP_401_UNAUTHORIZED, "Missing X-Custom-Signature")

        try:
            parts = dict(p.split("=", 1) for p in sig.split(","))
            ts = parts["t"]
            given = parts["v1"]
        except (KeyError, ValueError) as e:
            return _err(status.HTTP_401_UNAUTHORIZED, f"Malformed signature: {e}")

        try:
            ts_int = int(ts)
        except ValueError:
            return _err(status.HTTP_401_UNAUTHORIZED, "Bad timestamp")

        skew = abs(time.time() - ts_int)
        if skew > settings.hmac_window_seconds:
            return _err(
                status.HTTP_401_UNAUTHORIZED,
                f"Timestamp out of window ({int(skew)}s > {settings.hmac_window_seconds}s)",
            )

        body = await request.body()
        msg = ts.encode() + b"." + body
        expected = hmac.new(settings.orchestrator_shared_secret.encode(), msg, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, given):
            log.warning("hmac.mismatch", path=request.url.path)
            return _err(status.HTTP_401_UNAUTHORIZED, "HMAC mismatch")

        # Reinject body for downstream handlers
        async def _receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = _receive  # type: ignore[attr-defined]

        # Surface the operator identity (set by Odoo when issuing the call) so we can audit.
        actor = request.headers.get("X-Custom-Actor", "system")
        request.state.actor = actor

        return await call_next(request)
