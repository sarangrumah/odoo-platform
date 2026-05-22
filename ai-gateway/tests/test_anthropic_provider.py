"""Tests for ``app.providers.anthropic.AnthropicProvider``.

These talk to a stubbed Anthropic client (no network). The point is to
verify that:
  * the correct model is chosen per ``quality``,
  * ``cache_control: ephemeral`` is attached to the system prompt and
    last tool when ``cache_system=True``,
  * usage tokens (incl. cache reads/creates) propagate to ``ChatResponse``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.base import ChatRequest, Message


@dataclass
class _Usage:
    input_tokens: int = 7
    output_tokens: int = 3
    cache_read_input_tokens: int = 11
    cache_creation_input_tokens: int = 13


@dataclass
class _TextBlock:
    type: str = "text"
    text: str = "hello-from-claude"


@dataclass
class _RawResp:
    content: list[_TextBlock]
    model: str
    usage: _Usage


class _FakeMessages:
    def __init__(self) -> None:
        self.captured_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> _RawResp:
        self.captured_kwargs = kwargs
        return _RawResp(
            content=[_TextBlock(text="ok")],
            model=kwargs["model"],
            usage=_Usage(),
        )


class _FakeAsyncAnthropic:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        self.messages = _FakeMessages()


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Patch ``AsyncAnthropic`` inside the provider module."""
    import app.providers.anthropic as mod

    instances: list[_FakeAsyncAnthropic] = []

    def _factory(*args: Any, **kwargs: Any) -> _FakeAsyncAnthropic:
        inst = _FakeAsyncAnthropic()
        instances.append(inst)
        return inst

    monkeypatch.setattr(mod, "AsyncAnthropic", _factory)
    return instances


async def test_default_quality_uses_sonnet(fake_anthropic):
    provider = AnthropicProvider()
    req = ChatRequest(messages=[Message(role="user", content="hi")], quality="fast")
    resp = await provider.chat(req)
    assert resp.model == "claude-sonnet-4-6"
    assert fake_anthropic[0].messages.captured_kwargs["model"] == "claude-sonnet-4-6"


async def test_high_quality_escalates_to_opus(fake_anthropic):
    provider = AnthropicProvider()
    req = ChatRequest(messages=[Message(role="user", content="hi")], quality="high")
    resp = await provider.chat(req)
    assert resp.model == "claude-opus-4-7"
    assert fake_anthropic[0].messages.captured_kwargs["model"] == "claude-opus-4-7"


async def test_explicit_model_overrides_quality(fake_anthropic):
    provider = AnthropicProvider()
    req = ChatRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-haiku-4-5-20251001",
        quality="high",
    )
    resp = await provider.chat(req)
    assert resp.model == "claude-haiku-4-5-20251001"


async def test_system_prompt_marked_ephemeral_cache(fake_anthropic):
    provider = AnthropicProvider()
    req = ChatRequest(
        messages=[Message(role="user", content="q")],
        system="LARGE STATIC SYSTEM PROMPT",
        cache_system=True,
    )
    await provider.chat(req)
    sent = fake_anthropic[0].messages.captured_kwargs
    assert isinstance(sent["system"], list)
    block = sent["system"][0]
    assert block["text"] == "LARGE STATIC SYSTEM PROMPT"
    assert block["cache_control"] == {"type": "ephemeral"}


async def test_system_prompt_plain_string_when_cache_disabled(fake_anthropic):
    provider = AnthropicProvider()
    req = ChatRequest(
        messages=[Message(role="user", content="q")],
        system="DYNAMIC PROMPT",
        cache_system=False,
    )
    await provider.chat(req)
    sent = fake_anthropic[0].messages.captured_kwargs
    assert sent["system"] == "DYNAMIC PROMPT"


async def test_last_tool_marked_cacheable(fake_anthropic):
    provider = AnthropicProvider()
    req = ChatRequest(
        messages=[Message(role="user", content="q")],
        tools=[
            {"name": "search", "input_schema": {"type": "object"}},
            {"name": "calc", "input_schema": {"type": "object"}},
        ],
        cache_system=True,
    )
    await provider.chat(req)
    sent_tools = fake_anthropic[0].messages.captured_kwargs["tools"]
    assert sent_tools[0].get("cache_control") is None  # only the last one
    assert sent_tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert sent_tools[-1]["name"] == "calc"


async def test_usage_tokens_propagate(fake_anthropic):
    provider = AnthropicProvider()
    resp = await provider.chat(ChatRequest(messages=[Message(role="user", content="hi")]))
    assert resp.input_tokens == 7
    assert resp.output_tokens == 3
    assert resp.cache_read_tokens == 11
    assert resp.cache_creation_tokens == 13


def test_missing_api_key_raises(monkeypatch):
    """When ANTHROPIC_API_KEY is absent the provider refuses to start."""
    from app import config as cfg

    monkeypatch.setattr(cfg, "_settings", None)
    # build a fresh Settings with the key cleared
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()
