"""Workflow recommendation endpoint — Odoo records → structured next-action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..providers import get_provider
from ..providers.base import ChatRequest, Message

router = APIRouter(prefix="/v1/workflow", tags=["workflow"])

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "workflow_recommend.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else ""


class RecommendIn(BaseModel):
    model: str = Field(description="Odoo model name, e.g. helpdesk.ticket")
    res_id: int
    payload: dict[str, Any] = Field(description="Record fields snapshot relevant for reasoning")
    history: list[dict[str, Any]] | None = Field(default=None, description="Optional prior interactions")
    locale: str = "id_ID"


class RecommendOut(BaseModel):
    summary: str
    next_actions: list[dict[str, Any]]
    priority: str
    tags: list[str]
    raw_text: str


@router.post("/recommend", response_model=RecommendOut)
async def recommend(body: RecommendIn) -> RecommendOut:
    user_msg = (
        f"Model: {body.model}\nRecord ID: {body.res_id}\n"
        f"Locale: {body.locale}\n\n"
        f"Payload (JSON):\n{body.payload}\n"
    )
    if body.history:
        user_msg += f"\nHistory (last {len(body.history)} interactions):\n{body.history}"

    try:
        provider = get_provider()
        resp = await provider.chat(
            ChatRequest(
                messages=[Message(role="user", content=user_msg)],
                system=_SYSTEM_PROMPT,
                cache_system=True,
                quality="fast",
                max_tokens=2048,
            )
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Provider error: {e}") from e

    # Best-effort parse — model is instructed to emit JSON in the system prompt;
    # if parsing fails, fall back to raw_text only
    import json
    parsed: dict[str, Any] = {"summary": "", "next_actions": [], "priority": "normal", "tags": []}
    try:
        # Strip markdown fence if any
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json\n"):
                text = text[5:]
        parsed.update(json.loads(text))
    except Exception:
        pass

    return RecommendOut(
        summary=parsed.get("summary", ""),
        next_actions=parsed.get("next_actions", []),
        priority=parsed.get("priority", "normal"),
        tags=parsed.get("tags", []),
        raw_text=resp.content,
    )
