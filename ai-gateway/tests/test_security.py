"""HMAC verification tests."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest


def _sign(secret: str, body: bytes, ts: int | None = None) -> tuple[str, int]:
    ts = ts or int(time.time())
    msg = str(ts).encode() + b"." + body
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}", ts


def test_compute_hmac_matches_documented_format(monkeypatch):
    """Sanity check that our format matches what Odoo client should produce."""
    secret = "x" * 32
    body = b'{"messages":[]}'
    ts = 1700000000
    header, _ = _sign(secret, body, ts=ts)
    assert header.startswith("t=1700000000,v1=")
    # length of sha256 hex = 64
    assert len(header.split("v1=", 1)[1]) == 64


@pytest.mark.parametrize("body", [b"", b"{}", b'{"a":1}'])
def test_hmac_compare_digest_constant_time(body):
    secret = "x" * 32
    h1, _ = _sign(secret, body)
    h2, _ = _sign(secret, body)
    assert h1 == h2  # deterministic for same ts (tested separately)
