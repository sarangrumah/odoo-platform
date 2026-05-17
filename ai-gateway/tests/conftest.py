"""Shared pytest fixtures: HMAC signer + fake LLM provider injection."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import pytest

# Make sure mandatory env vars are populated before app.config imports.
os.environ.setdefault("GATEWAY_SHARED_SECRET", "x" * 64)
os.environ.setdefault("AI_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")


def _sign(secret: str, body: bytes, ts: int | None = None) -> tuple[str, int]:
    """Build a valid ``X-Custom-Signature`` header value for ``body``.

    Format mirrors `app.security._compute_hmac`: ``t=<ts>,v1=<hex>`` where
    the HMAC is over ``f"{ts}.{body}"``.
    """
    ts = ts if ts is not None else int(time.time())
    msg = str(ts).encode() + b"." + body
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}", ts


@pytest.fixture
def signer() -> Callable[[bytes, int | None], tuple[str, int]]:
    """Return a function ``signer(body, ts=None) -> (header, ts)``."""

    def _do(body: bytes, ts: int | None = None) -> tuple[str, int]:
        return _sign(os.environ["GATEWAY_SHARED_SECRET"], body, ts)

    return _do


# --- Fake provider plumbing ---------------------------------------------------


@dataclass
class FakeChatResponse:
    content: str = '{"forecast": {}, "saturation_eta_days": {}, "recommend_upgrade": []}'
    model: str = "claude-sonnet-4-6"
    provider: str = "anthropic"
    input_tokens: int = 10
    output_tokens: int = 5
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    raw: dict[str, Any] | None = None


class FakeProvider:
    """Captures the last ChatRequest received for assertions."""

    name = "anthropic"

    def __init__(self, response: FakeChatResponse | None = None) -> None:
        self.response = response or FakeChatResponse()
        self.last_request: Any = None
        self.call_count = 0

    async def chat(self, req):  # type: ignore[no-untyped-def]
        self.last_request = req
        self.call_count += 1
        # Honour quality switch in the canned response model
        if req.quality == "high":
            self.response.model = "claude-opus-4-7"
        return self.response

    async def embed(self, text, model=None):  # type: ignore[no-untyped-def]
        return [[0.0]]


@pytest.fixture
def fake_provider(monkeypatch) -> FakeProvider:
    """Replace ``get_provider`` in every router module with a fake."""
    import app.providers as providers_pkg
    from app.routers import chat as chat_router
    from app.routers import predict as predict_router
    from app.routers import workflow as workflow_router

    provider = FakeProvider()
    monkeypatch.setattr(providers_pkg, "get_provider", lambda name=None: provider)
    monkeypatch.setattr(chat_router, "get_provider", lambda name=None: provider)
    monkeypatch.setattr(predict_router, "get_provider", lambda name=None: provider)
    monkeypatch.setattr(workflow_router, "get_provider", lambda name=None: provider)
    return provider


@pytest.fixture
def client():
    """FastAPI TestClient with lifespan (so middleware + redis stub initialise)."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
