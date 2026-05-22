"""Anthropic provider with prompt caching for system + tools."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from anthropic import APIStatusError, AsyncAnthropic, BadRequestError, InternalServerError

from ..config import get_settings
from .base import ChatRequest, ChatResponse, LLMProvider

log = logging.getLogger(__name__)

# Newer reasoning-class models (Opus 4.7+, Sonnet 4.7+, …) no longer accept the
# `temperature` sampling parameter. Hardcode the known list so we don't even
# send it on the first attempt, AND keep a runtime fallback in case Anthropic
# deprecates it for more models later.
_NO_TEMPERATURE_MODELS = {
    "claude-opus-4-7",
    "claude-opus-4-7[1m]",
}


def _supports_temperature(model: str) -> bool:
    return model not in _NO_TEMPERATURE_MODELS


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
        }
        if _supports_temperature(model):
            kwargs["temperature"] = req.temperature
        if system_param is not None:
            kwargs["system"] = system_param
        if tool_param is not None:
            kwargs["tools"] = tool_param

        # Retry on Anthropic 529 (Overloaded) / 502 / 503 with exponential
        # back-off. The SDK auto-retries some of these but caps quickly; we
        # add a slightly more patient outer loop because BRD analysis is not
        # latency-sensitive and a transient overload should not bubble up as
        # a hard 500 to the user.
        last_exc: Exception | None = None
        for attempt in range(4):  # total wait ≤ 1+3+7+15 = 26s
            try:
                resp = await self._client.messages.create(**kwargs)
                break
            except BadRequestError as e:
                # Future-proof: if Anthropic deprecates `temperature` for more
                # models, retry once without it instead of 500-ing.
                msg = str(getattr(e, "message", e)).lower()
                if "temperature" in msg and "deprecated" in msg and "temperature" in kwargs:
                    log.warning("anthropic: temperature deprecated for model=%s, retrying without it", model)
                    _NO_TEMPERATURE_MODELS.add(model)
                    kwargs.pop("temperature", None)
                    continue
                raise
            except (InternalServerError, APIStatusError) as e:
                # The SDK's class attribute `status_code` is the family default
                # (e.g. 500 for InternalServerError). We need the *real* HTTP
                # status from the underlying response, which is where 529
                # ("overloaded") lives.
                resp_obj = getattr(e, "response", None)
                real_status = getattr(resp_obj, "status_code", None)
                class_status = getattr(e, "status_code", None)
                msg = str(getattr(e, "message", e)).lower()
                is_transient = (
                    real_status in (500, 502, 503, 504, 529)
                    or class_status in (500, 502, 503, 504, 529)
                    or "overloaded" in msg
                    or "timeout" in msg
                )
                if is_transient and attempt < 3:
                    wait = 1 + (attempt * attempt) * 2 + attempt  # 1, 3, 7, 15
                    log.warning(
                        "anthropic: transient error (status=%s, msg=%r), retry %d/3 after %ds",
                        real_status or class_status,
                        msg[:120],
                        attempt + 1,
                        wait,
                    )
                    last_exc = e
                    await asyncio.sleep(wait)
                    continue
                raise
        else:
            # Exhausted retries — surface a clearer message than the SDK default.
            raise RuntimeError(
                f"Anthropic API overloaded after 4 attempts (last: {last_exc}). "
                "This is a transient upstream issue at Anthropic; please retry in a minute."
            ) from last_exc

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
