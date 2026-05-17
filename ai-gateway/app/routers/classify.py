"""Document auto-classification endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..providers import get_provider
from ..providers.base import ChatRequest, Message

router = APIRouter(prefix="/v1/workflow", tags=["classify"])

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "classify_document.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else ""

VALID_CODES = {"public", "internal", "confidential", "pii", "sensitive_pii", "financial", "health"}


class ClassifyIn(BaseModel):
    filename: str
    mimetype: str | None = None
    text_excerpt: str | None = Field(default=None, max_length=8000)
    locale: str = "id_ID"


class ClassifyOut(BaseModel):
    classification_code: str
    confidence: float
    tags: list[str]
    rationale: str
    raw_text: str


@router.post("/classify-document", response_model=ClassifyOut)
async def classify_document(body: ClassifyIn) -> ClassifyOut:
    user_msg = (
        f"Filename: {body.filename}\n"
        f"Mimetype: {body.mimetype or 'unknown'}\n"
        f"Locale: {body.locale}\n\n"
        f"Text excerpt (truncated):\n{body.text_excerpt or '(none)'}\n"
    )

    try:
        provider = get_provider()
        resp = await provider.chat(
            ChatRequest(
                messages=[Message(role="user", content=user_msg)],
                system=_SYSTEM_PROMPT,
                cache_system=True,
                quality="fast",
                max_tokens=512,
                temperature=0.0,
            )
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Provider error: {e}") from e

    parsed: dict[str, Any] = {
        "classification_code": "internal",
        "confidence": 0.0,
        "tags": [],
        "rationale": "",
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

    # Enforce the closed set — invalid codes degrade to 'internal'
    code = str(parsed.get("classification_code", "internal"))
    if code not in VALID_CODES:
        code = "internal"

    return ClassifyOut(
        classification_code=code,
        confidence=float(parsed.get("confidence", 0.0)),
        tags=[str(t) for t in (parsed.get("tags") or [])][:5],
        rationale=str(parsed.get("rationale", "")),
        raw_text=resp.content,
    )
