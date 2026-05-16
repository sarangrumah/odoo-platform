"""Provider implementations and factory."""

from __future__ import annotations

from ..config import get_settings
from .anthropic import AnthropicProvider
from .base import LLMProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider

_REGISTRY: dict[str, LLMProvider] = {}


def get_provider(name: str | None = None) -> LLMProvider:
    settings = get_settings()
    name = name or settings.ai_provider
    if name not in _REGISTRY:
        if name == "anthropic":
            _REGISTRY[name] = AnthropicProvider()
        elif name == "openai":
            _REGISTRY[name] = OpenAIProvider()
        elif name == "ollama":
            _REGISTRY[name] = OllamaProvider()
        else:
            raise ValueError(f"Unknown provider: {name}")
    return _REGISTRY[name]
