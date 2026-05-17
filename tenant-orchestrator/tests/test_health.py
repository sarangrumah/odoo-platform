"""Health + HMAC gate sanity tests (no DB required)."""

from __future__ import annotations


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_v1_without_signature_returns_401(client):
    r = client.get("/v1/tenants")
    assert r.status_code == 401
    assert "Missing" in r.json()["detail"]


def test_v1_with_replay_old_ts_rejected(client, signer):
    import time
    header, _ = signer(b"", ts=int(time.time()) - 600)
    r = client.get("/v1/tenants", headers={"X-Custom-Signature": header})
    assert r.status_code == 401
    assert "out of window" in r.json()["detail"]


def test_v1_malformed_signature_rejected(client):
    r = client.get("/v1/tenants", headers={"X-Custom-Signature": "garbage"})
    assert r.status_code == 401


def test_metrics_endpoint_open(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"# HELP" in r.content or b"# TYPE" in r.content
