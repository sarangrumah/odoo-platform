"""Predictor service: scheduler + JSON output + Prom metrics endpoint."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response

from .advisor import request_capacity_advice
from .analyzer import build_bundle
from .config import get_settings
from .prom_client import PromClient


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )


SATURATION_GAUGE = Gauge(
    "custom_predictor_saturation_eta_days",
    "Predicted days until resource saturation (NaN if unknown)",
    ["component"],
)
ADVICE_GAUGE = Gauge(
    "custom_predictor_advice_count",
    "Count of upgrade recommendations by urgency",
    ["urgency"],
)


async def run_once(prom: PromClient) -> dict:
    s = get_settings()
    s.output_dir.mkdir(parents=True, exist_ok=True)
    bundle = await build_bundle(prom)
    advice = await request_capacity_advice(bundle.metrics)
    advice["generated_at"] = datetime.now(tz=timezone.utc).isoformat()

    # Update Prom gauges
    SATURATION_GAUGE.clear()
    for component, eta in (advice.get("saturation_eta_days") or {}).items():
        if eta is not None:
            SATURATION_GAUGE.labels(component=component).set(eta)

    counts: dict[str, int] = {}
    for r in advice.get("recommend_upgrade") or []:
        counts[r.get("urgency", "info")] = counts.get(r.get("urgency", "info"), 0) + 1
    ADVICE_GAUGE.clear()
    for urgency, count in counts.items():
        ADVICE_GAUGE.labels(urgency=urgency).set(count)

    # Persist
    out_latest = s.output_dir / "latest.json"
    out_history = s.output_dir / f"advice-{int(datetime.now().timestamp())}.json"
    out_latest.write_text(json.dumps(advice, indent=2), encoding="utf-8")
    out_history.write_text(json.dumps(advice, indent=2), encoding="utf-8")
    return advice


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    _configure_logging(s.log_level)
    prom = PromClient(s.prometheus_url)
    app.state.prom = prom

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_once, "interval", hours=s.interval_hours, args=[prom], id="predict_loop", next_run_time=None)
    # Seed run in 2 minutes (after Prom warms up)
    scheduler.add_job(
        run_once, "date", run_date=datetime.now() + __import__("datetime").timedelta(minutes=2), args=[prom]
    )
    scheduler.start()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await prom.aclose()


app = FastAPI(title="custom-predictor", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/run-now")
async def run_now() -> dict:
    """Manual trigger (operators). Returns the latest advice payload."""
    return await run_once(app.state.prom)
