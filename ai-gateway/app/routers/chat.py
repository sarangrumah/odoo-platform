"""Unified chat endpoint."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..providers import get_provider
from ..providers.base import ChatRequest, Message

router = APIRouter(prefix="/v1", tags=["chat"])


class MessageIn(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatIn(BaseModel):
    messages: list[MessageIn]
    model: str | None = None
    system: str | None = None
    tools: list[dict[str, Any]] | None = None
    max_tokens: int = Field(default=4096, ge=1, le=64000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    quality: Literal["fast", "high"] = "fast"
    provider_override: Literal["anthropic", "openai", "ollama"] | None = None
    cache_system: bool = True


class ChatOut(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn) -> ChatOut:
    try:
        provider = get_provider(body.provider_override)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e

    req = ChatRequest(
        messages=[Message(role=m.role, content=m.content) for m in body.messages],
        model=body.model,
        system=body.system,
        tools=body.tools,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        quality=body.quality,
        cache_system=body.cache_system,
    )
    resp = await provider.chat(req)
    return ChatOut(
        content=resp.content,
        model=resp.model,
        provider=resp.provider,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        cache_read_tokens=resp.cache_read_tokens,
        cache_creation_tokens=resp.cache_creation_tokens,
    )
