"""HMAC verification + replay defense + rate limiting middleware."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Awaitable, Callable

import redis.asyncio as redis_async
import structlog
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import get_settings

log = structlog.get_logger()

EXEMPT_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}


def _compute_hmac(secret: str, ts: str, body: bytes) -> str:
    msg = ts.encode() + b"." + body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _err(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


class HMACMiddleware(BaseHTTPMiddleware):
    """Verify X-Custom-Signature header for /v1/* routes.

    Header format: ``t=<unix_ts>,v1=<hex_hmac>``
    HMAC computed as: HMAC-SHA256(secret, "<ts>.<raw_body>")
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
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

        # Replay window
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

        # Compute expected
        body = await request.body()
        expected = _compute_hmac(settings.gateway_shared_secret, ts, body)
        if not hmac.compare_digest(expected, given):
            log.warning("hmac.mismatch", path=request.url.path, ts=ts)
            return _err(status.HTTP_401_UNAUTHORIZED, "HMAC mismatch")

        # Re-inject body so downstream can read it
        async def _receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = _receive  # type: ignore[attr-defined]
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-tenant rate limit via Redis."""

    def __init__(self, app, redis_client: redis_async.Redis):
        super().__init__(app)
        self.redis = redis_client

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in EXEMPT_PATHS or not request.url.path.startswith("/v1/"):
            return await call_next(request)

        settings = get_settings()
        tenant = request.headers.get("X-Tenant-Id", "anonymous")
        key = f"ratelimit:{tenant}:{int(time.time() // 60)}"
        try:
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, 65)
        except Exception as e:  # redis down — fail open with warning
            log.warning("ratelimit.redis_error", err=str(e))
            return await call_next(request)

        if current > settings.rate_limit_per_minute:
            return _err(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit {settings.rate_limit_per_minute}/min exceeded",
            )
        return await call_next(request)
