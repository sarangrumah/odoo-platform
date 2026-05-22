"""Tenant orchestrator FastAPI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from .config import get_settings
from .db import close_all
from .routers import backups as backups_router
from .routers import intake as intake_router
from .routers import tenants as tenants_router
from .routers import vps as vps_router
from .security import HMACMiddleware


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

    # Start backup scheduler (importing lazily to avoid circulars at module load)
    if settings.enable_backup_scheduler:
        from . import scheduler

        scheduler.start()

    yield

    if settings.enable_backup_scheduler:
        from . import scheduler

        scheduler.stop()
    close_all()


app = FastAPI(
    title="Odoo Platform Tenant Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(HMACMiddleware)
app.include_router(tenants_router.router)
app.include_router(backups_router.router)
app.include_router(backups_router.admin_router)
app.include_router(vps_router.router)
app.include_router(intake_router.router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/metrics", tags=["meta"])
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
