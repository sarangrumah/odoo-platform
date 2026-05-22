"""Tests for POST /v1/workflow/predict-capacity (capacity advisor endpoint)."""

from __future__ import annotations

import json

from tests.conftest import FakeChatResponse


def _valid_payload() -> dict:
    return {
        "host": {"cpu_cores": 8, "ram_gb": 32, "disk_gb": 200},
        "metrics": [
            {
                "name": "disk_used_pct",
                "unit": "percent",
                "series": [[1700000000 + i * 3600, 50.0 + i * 0.3] for i in range(50)],
                "current_max_capacity": 100.0,
            },
        ],
        "window_days": 7,
        "forecast_days": 30,
    }


def test_predict_without_hmac_returns_401(client):
    r = client.post("/v1/workflow/predict-capacity", json=_valid_payload())
    assert r.status_code == 401


def test_predict_parses_structured_json_response(client, signer, fake_provider):
    fake_provider.response = FakeChatResponse(
        content=json.dumps(
            {
                "forecast": {"disk_used_pct": {"30d": 92.5}},
                "saturation_eta_days": {"disk": 18.0},
                "recommend_upgrade": [
                    {"component": "disk", "urgency": "warn", "rationale": "ETA <30d"},
                ],
            }
        )
    )

    body = json.dumps(_valid_payload()).encode()
    header, _ = signer(body)
    r = client.post(
        "/v1/workflow/predict-capacity",
        content=body,
        headers={"X-Custom-Signature": header, "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["saturation_eta_days"] == {"disk": 18.0}
    assert data["recommend_upgrade"][0]["component"] == "disk"
    assert data["recommend_upgrade"][0]["urgency"] == "warn"
    assert "disk_used_pct" in data["forecast"]


def test_predict_handles_fenced_json_response(client, signer, fake_provider):
    """LLMs sometimes wrap JSON in a ```json fence — the router should strip it."""
    fenced = (
        "```json\n"
        + json.dumps(
            {
                "forecast": {},
                "saturation_eta_days": {"cpu": None},
                "recommend_upgrade": [],
            }
        )
        + "\n```"
    )
    fake_provider.response = FakeChatResponse(content=fenced)

    body = json.dumps(_valid_payload()).encode()
    header, _ = signer(body)
    r = client.post(
        "/v1/workflow/predict-capacity",
        content=body,
        headers={"X-Custom-Signature": header, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["saturation_eta_days"] == {"cpu": None}


def test_predict_invalid_payload_returns_422(client, signer):
    bad = {"host": {"cpu_cores": "not-an-int"}, "metrics": []}
    body = json.dumps(bad).encode()
    header, _ = signer(body)
    r = client.post(
        "/v1/workflow/predict-capacity",
        content=body,
        headers={"X-Custom-Signature": header, "Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_predict_returns_raw_text_for_diagnostic(client, signer, fake_provider):
    fake_provider.response = FakeChatResponse(content="not-valid-json")

    body = json.dumps(_valid_payload()).encode()
    header, _ = signer(body)
    r = client.post(
        "/v1/workflow/predict-capacity",
        content=body,
        headers={"X-Custom-Signature": header, "Content-Type": "application/json"},
    )
    # Even when the LLM doesn't return JSON, endpoint should still respond 200
    # with the raw_text field so the predictor can fall back to its own metrics.
    assert r.status_code == 200
    data = r.json()
    assert data["raw_text"] == "not-valid-json"
    assert data["recommend_upgrade"] == []


def test_predict_uses_cached_system_prompt(client, signer, fake_provider):
    body = json.dumps(_valid_payload()).encode()
    header, _ = signer(body)
    client.post(
        "/v1/workflow/predict-capacity",
        content=body,
        headers={"X-Custom-Signature": header, "Content-Type": "application/json"},
    )
    # The router forwards the predict_capacity.md prompt with cache_system=True
    # so prompt caching is engaged on Anthropic's side.
    assert fake_provider.last_request.cache_system is True
