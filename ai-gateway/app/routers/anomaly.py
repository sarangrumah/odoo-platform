"""Anomaly detection endpoint — analyses a series + latest value."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..providers import get_provider
from ..providers.base import ChatRequest, Message

router = APIRouter(prefix="/v1/workflow", tags=["anomaly"])

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "anomaly_detect.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else ""


class AnomalyIn(BaseModel):
    model: str = Field(description="Odoo model name, e.g. account.move")
    res_id: int
    metric: str = Field(description="Metric key, e.g. 'amount_total'")
    latest_value: float
    history: list[float] = Field(description="Prior values, newest last")
    context: dict[str, Any] | None = None
    locale: str = "id_ID"


class AnomalyOut(BaseModel):
    is_anomaly: bool
    severity: str
    score: float
    rationale: str
    suggested_action: str
    raw_text: str


@router.post("/anomaly", response_model=AnomalyOut)
async def detect_anomaly(body: AnomalyIn) -> AnomalyOut:
    user_msg = (
        f"Model: {body.model}\nRecord ID: {body.res_id}\n"
        f"Metric: {body.metric}\nLatest value: {body.latest_value}\n"
        f"History ({len(body.history)} points, newest last): {body.history}\n"
        f"Locale: {body.locale}\n"
    )
    if body.context:
        user_msg += f"\nContext: {body.context}\n"

    try:
        provider = get_provider()
        resp = await provider.chat(
            ChatRequest(
                messages=[Message(role="user", content=user_msg)],
                system=_SYSTEM_PROMPT,
                cache_system=True,
                quality="fast",
                max_tokens=512,
                temperature=0.1,
            )
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Provider error: {e}") from e

    parsed: dict[str, Any] = {
        "is_anomaly": False,
        "severity": "info",
        "score": 0.0,
        "rationale": "",
        "suggested_action": "",
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

    return AnomalyOut(
        is_anomaly=bool(parsed.get("is_anomaly", False)),
        severity=str(parsed.get("severity", "info")),
        score=float(parsed.get("score", 0.0)),
        rationale=str(parsed.get("rationale", "")),
        suggested_action=str(parsed.get("suggested_action", "")),
        raw_text=resp.content,
    )
