"""Anthropic provider with prompt caching for system + tools."""

from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from ..config import get_settings
from .base import ChatRequest, ChatResponse, LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        s = get_settings()
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self._client = AsyncAnthropic(api_key=s.anthropic_api_key)

    async def chat(self, req: ChatRequest) -> ChatResponse:
        s = get_settings()
        model = req.model or (s.ai_model_quality if req.quality == "high" else s.ai_model_default)

        # Build system as a list with cache_control on the static block.
        # Anthropic SDK accepts string or list of TextBlocks; list lets us mark cache.
        system_param: list[dict[str, Any]] | str | None = None
        if req.system:
            if req.cache_system:
                system_param = [
                    {
                        "type": "text",
                        "text": req.system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                system_param = req.system

        # Tools: also marked cacheable when present
        tool_param = None
        if req.tools:
            tool_param = list(req.tools)
            if req.cache_system and tool_param:
                # mark last tool as cache anchor — Anthropic caches everything up to and incl. it
                tool_param[-1] = {**tool_param[-1], "cache_control": {"type": "ephemeral"}}

        messages = [{"role": m.role, "content": m.content} for m in req.messages if m.role != "system"]

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if system_param is not None:
            kwargs["system"] = system_param
        if tool_param is not None:
            kwargs["tools"] = tool_param

        resp = await self._client.messages.create(**kwargs)

        text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        usage = resp.usage
        return ChatResponse(
            content="".join(text_parts),
            model=resp.model,
            provider=self.name,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            raw=None,
        )

    async def embed(self, text: str | list[str], model: str | None = None) -> list[list[float]]:
        # Anthropic does not provide a public embeddings API as of May 2026.
        # Caller should route embed requests to a provider that supports it.
        raise NotImplementedError("Anthropic provider does not implement embeddings; use openai or ollama")
