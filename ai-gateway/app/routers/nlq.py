"""Natural Language Query → Odoo domain plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..providers import get_provider
from ..providers.base import ChatRequest, Message

router = APIRouter(prefix="/v1/workflow", tags=["nlq"])

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "nlq_to_domain.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else ""


class SchemaModel(BaseModel):
    model: str
    fields: list[str]
    description: str | None = None


class NlqIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    schema_hint: list[SchemaModel] = Field(
        description="Allowed models + fields. Result must use only these.",
    )
    locale: str = "id_ID"
    user_can_view_pii: bool = False


class NlqOut(BaseModel):
    model: str | None = None
    domain: list[Any] = []
    fields: list[str] = []
    order: str | None = None
    limit: int = 25
    rationale: str = ""
    follow_up: str | None = None
    error: str | None = None
    raw_text: str


@router.post("/nlq", response_model=NlqOut)
async def nlq(body: NlqIn) -> NlqOut:
    schema_text = "\n".join(
        f"- {m.model}: {', '.join(m.fields)}" + (f"  ({m.description})" if m.description else "")
        for m in body.schema_hint
    )
    user_msg = (
        f"User locale: {body.locale}\n"
        f"User can view PII: {body.user_can_view_pii}\n\n"
        f"Schema hint:\n{schema_text}\n\n"
        f"User question:\n{body.question}\n"
    )

    try:
        provider = get_provider()
        resp = await provider.chat(
            ChatRequest(
                messages=[Message(role="user", content=user_msg)],
                system=_SYSTEM_PROMPT,
                cache_system=True,
                quality="fast",
                max_tokens=1024,
                temperature=0.0,
            )
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Provider error: {e}") from e

    parsed: dict[str, Any] = {}
    try:
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json\n"):
                text = text[5:]
        parsed = json.loads(text)
    except Exception:
        parsed = {"error": "parse_failed", "rationale": resp.content[:200]}

    return NlqOut(
        model=parsed.get("model"),
        domain=parsed.get("domain") or [],
        fields=parsed.get("fields") or [],
        order=parsed.get("order"),
        limit=min(int(parsed.get("limit") or 25), 100),
        rationale=str(parsed.get("rationale", "")),
        follow_up=parsed.get("follow_up"),
        error=parsed.get("error"),
        raw_text=resp.content,
    )
