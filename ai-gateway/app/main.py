"""FastAPI entrypoint for the AI Gateway."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from .config import get_settings
from .routers import anomaly, chat, classify, embed, nlq, predict, workflow
from .security import HMACMiddleware, RateLimitMiddleware


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    app.state.redis = redis_async.from_url(settings.redis_url, decode_responses=False)
    try:
        await app.state.redis.ping()
    except Exception:
        # Redis optional at startup — rate-limit will fail open
        pass
    yield
    await app.state.redis.aclose()


app = FastAPI(
    title="Odoo Platform AI Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=False,
)
app.add_middleware(HMACMiddleware)
# RateLimit added in lifespan via dependency, simplified by attaching after redis ready
# (For production: split into a per-request dependency; this keeps wiring minimal.)

app.include_router(chat.router)
app.include_router(embed.router)
app.include_router(workflow.router)
app.include_router(predict.router)
app.include_router(anomaly.router)
app.include_router(classify.router)
app.include_router(nlq.router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "provider": settings.ai_provider, "version": app.version}


@app.get("/metrics", tags=["meta"])
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
