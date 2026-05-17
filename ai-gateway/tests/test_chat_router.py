"""Tests for POST /v1/chat (HMAC, provider routing, quality escalation)."""

from __future__ import annotations

import json


def test_chat_without_hmac_returns_401(client):
    r = client.post("/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 401
    assert "Missing" in r.json()["detail"]


def test_chat_with_valid_hmac_returns_200(client, signer, fake_provider):
    body = json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode()
    header, _ = signer(body)
    r = client.post("/v1/chat", content=body, headers={
        "X-Custom-Signature": header,
        "Content-Type": "application/json",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert "content" in data
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-sonnet-4-6"
    assert fake_provider.call_count == 1


def test_chat_quality_high_escalates_to_opus(client, signer, fake_provider):
    body = json.dumps({
        "messages": [{"role": "user", "content": "complex"}],
        "quality": "high",
    }).encode()
    header, _ = signer(body)
    r = client.post("/v1/chat", content=body, headers={
        "X-Custom-Signature": header,
        "Content-Type": "application/json",
    })
    assert r.status_code == 200
    assert r.json()["model"] == "claude-opus-4-7"
    # Verify the provider was asked to use the high-quality tier
    assert fake_provider.last_request.quality == "high"


def test_chat_replay_old_timestamp_rejected(client, signer):
    body = json.dumps({"messages": [{"role": "user", "content": "stale"}]}).encode()
    # 10 minutes ago — outside the 300s default window
    import time
    header, _ = signer(body, ts=int(time.time()) - 600)
    r = client.post("/v1/chat", content=body, headers={
        "X-Custom-Signature": header,
        "Content-Type": "application/json",
    })
    assert r.status_code == 401
    assert "out of window" in r.json()["detail"]


def test_chat_malformed_signature_header_rejected(client):
    r = client.post(
        "/v1/chat",
        json={"messages": [{"role": "user", "content": "x"}]},
        headers={"X-Custom-Signature": "not-a-valid-sig"},
    )
    assert r.status_code == 401
    assert "Malformed" in r.json()["detail"] or "Bad" in r.json()["detail"]


def test_chat_passes_system_prompt_with_cache_flag(client, signer, fake_provider):
    body = json.dumps({
        "messages": [{"role": "user", "content": "hi"}],
        "system": "You are a precise assistant.",
        "cache_system": True,
    }).encode()
    header, _ = signer(body)
    r = client.post("/v1/chat", content=body, headers={
        "X-Custom-Signature": header,
        "Content-Type": "application/json",
    })
    assert r.status_code == 200
    assert fake_provider.last_request.system == "You are a precise assistant."
    assert fake_provider.last_request.cache_system is True
