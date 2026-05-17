"""Shared fixtures — populate required env, build HMAC signer."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Callable

import pytest

# Mandatory env BEFORE app.config imports
os.environ.setdefault("PG_SUPER_PASSWORD", "x" * 32)
os.environ.setdefault("PG_ORCHESTRATOR_PASSWORD", "x" * 32)
os.environ.setdefault("ORCHESTRATOR_SHARED_SECRET", "x" * 64)
os.environ.setdefault("S3_SECRET_KEY", "miniopass123")
os.environ.setdefault("ODOO_ADMIN_PASSWD", "changeme-master")
# Valid 32-byte URL-safe base64 key (44 chars)
os.environ.setdefault("MASTER_WRAPPING_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
# Disable scheduler during tests
os.environ.setdefault("ENABLE_BACKUP_SCHEDULER", "false")


@pytest.fixture
def signer() -> Callable[[bytes, int | None], tuple[str, int]]:
    def _do(body: bytes, ts: int | None = None) -> tuple[str, int]:
        ts = ts if ts is not None else int(time.time())
        msg = str(ts).encode() + b"." + body
        sig = hmac.new(
            os.environ["ORCHESTRATOR_SHARED_SECRET"].encode(), msg, hashlib.sha256
        ).hexdigest()
        return f"t={ts},v1={sig}", ts
    return _do


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
