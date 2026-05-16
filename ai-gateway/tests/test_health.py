"""Health endpoint test."""

from __future__ import annotations

import os

import pytest

# Ensure required env exists for Settings(min_length=32)
os.environ.setdefault("GATEWAY_SHARED_SECRET", "x" * 64)


def test_health_returns_ok(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "provider" in body
