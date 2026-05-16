"""OpenAI provider."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from ..config import get_settings
from .base import ChatRequest, ChatResponse, LLMProvider


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        s = get_settings()
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self._client = AsyncOpenAI(api_key=s.openai_api_key)

    async def chat(self, req: ChatRequest) -> ChatResponse:
        s = get_settings()
        model = req.model or s.openai_model_default

        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend({"role": m.role, "content": m.content} for m in req.messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.tools:
            # OpenAI tool format differs — caller responsibility to supply correctly.
            kwargs["tools"] = req.tools

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        usage = resp.usage
        return ChatResponse(
            content=choice.message.content or "",
            model=resp.model,
            provider=self.name,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    async def embed(self, text: str | list[str], model: str | None = None) -> list[list[float]]:
        items = [text] if isinstance(text, str) else text
        resp = await self._client.embeddings.create(
            input=items, model=model or "text-embedding-3-small"
        )
        return [d.embedding for d in resp.data]
