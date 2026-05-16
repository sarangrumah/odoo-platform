"""Capacity prediction endpoint — consumed by custom-predictor sidecar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..providers import get_provider
from ..providers.base import ChatRequest, Message

router = APIRouter(prefix="/v1/workflow", tags=["predict"])

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "predict_capacity.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else ""


class HostInfo(BaseModel):
    cpu_cores: int
    ram_gb: int
    disk_gb: int


class MetricSeries(BaseModel):
    name: str
    unit: str
    series: list[tuple[int, float]] = Field(description="List of [unix_ts, value] points, sorted by ts")
    current_max_capacity: float | None = None


class PredictIn(BaseModel):
    host: HostInfo
    metrics: list[MetricSeries]
    window_days: int = 7
    forecast_days: int = 30


class UpgradeAdvice(BaseModel):
    component: str
    urgency: str  # info | warn | critical
    rationale: str


class PredictOut(BaseModel):
    forecast: dict[str, Any]
    saturation_eta_days: dict[str, float | None]  # per-component
    recommend_upgrade: list[UpgradeAdvice]
    raw_text: str


@router.post("/predict-capacity", response_model=PredictOut)
async def predict_capacity(body: PredictIn) -> PredictOut:
    summary_lines = [
        f"Host: {body.host.cpu_cores} CPU cores, {body.host.ram_gb} GB RAM, {body.host.disk_gb} GB disk",
        f"Window: last {body.window_days}d, forecast: next {body.forecast_days}d",
        "",
        "Metrics (downsampled to last 50 points):",
    ]
    for m in body.metrics:
        last_50 = m.series[-50:]
        summary_lines.append(
            f"- {m.name} ({m.unit}, max={m.current_max_capacity}): "
            f"{[(ts, round(v, 3)) for ts, v in last_50]}"
        )
    user_msg = "\n".join(summary_lines)

    try:
        provider = get_provider()
        resp = await provider.chat(
            ChatRequest(
                messages=[Message(role="user", content=user_msg)],
                system=_SYSTEM_PROMPT,
                cache_system=True,
                quality="fast",
                max_tokens=2048,
                temperature=0.2,
            )
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Provider error: {e}") from e

    import json
    parsed: dict[str, Any] = {
        "forecast": {},
        "saturation_eta_days": {},
        "recommend_upgrade": [],
    }
    try:
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json\n"):
                text = text[5:]
        parsed.update(json.loads(text))
    except Exception:
        pass

    return PredictOut(
        forecast=parsed.get("forecast", {}),
        saturation_eta_days=parsed.get("saturation_eta_days", {}),
        recommend_upgrade=[UpgradeAdvice(**a) for a in parsed.get("recommend_upgrade", [])],
        raw_text=resp.content,
    )
