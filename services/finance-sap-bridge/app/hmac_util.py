"""HMAC signing/verification — byte-identical to the Odoo side.

Canonical string = ascii(timestamp) bytes || raw body bytes.
signature = HMAC_SHA256(secret, canonical).hexdigest()

Matches:
  * custom_core.controllers.secure_endpoint._verify_hmac   (Odoo inbound)
  * custom_adapter_framework.BaseAdapter._sign_request     (Odoo outbound)
"""

from __future__ import annotations

import hashlib
import hmac
import time


def sign(secret: str, body: bytes, ts: str | None = None) -> tuple[str, str]:
    """Return (timestamp, signature_hex) for an outbound request body."""
    ts = ts or str(int(time.time()))
    sig = hmac.new(secret.encode("utf-8"), ts.encode("utf-8") + body, hashlib.sha256).hexdigest()
    return ts, sig


def verify(secret: str, body: bytes, signature: str, timestamp: str, drift: int = 300) -> str | None:
    """Return None when valid, else an error code string."""
    if not signature or not timestamp:
        return "MISSING_AUTH_HEADERS"
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return "BAD_TIMESTAMP"
    if abs(time.time() - ts) > drift:
        return "EXPIRED_TIMESTAMP"
    if not secret:
        return "NO_SECRET_CONFIGURED"
    expected = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return "BAD_SIGNATURE"
    return None
