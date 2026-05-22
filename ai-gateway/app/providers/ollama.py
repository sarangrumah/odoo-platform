"""Ollama provider (local LLM)."""

from __future__ import annotations

import httpx

from ..config import get_settings
from .base import ChatRequest, ChatResponse, LLMProvider


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        s = get_settings()
        self._base_url = s.ollama_base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def chat(self, req: ChatRequest) -> ChatResponse:
        s = get_settings()
        if req.model:
            model = req.model
        elif req.quality == "high":
            model = s.ollama_model_quality
        else:
            model = s.ollama_model_default
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend({"role": m.role, "content": m.content} for m in req.messages)

        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": req.temperature, "num_predict": req.max_tokens},
        }
        r = await self._client.post(f"{self._base_url}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
        msg = data.get("message", {})
        return ChatResponse(
            content=msg.get("content", ""),
            model=data.get("model", model),
            provider=self.name,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    async def embed(self, text: str | list[str], model: str | None = None) -> list[list[float]]:
        items = [text] if isinstance(text, str) else text
        out: list[list[float]] = []
        for item in items:
            r = await self._client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": model or "nomic-embed-text", "prompt": item},
            )
            r.raise_for_status()
            out.append(r.json().get("embedding", []))
        return out
