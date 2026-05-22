# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import hmac
import time
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..controllers import secure_endpoint as se


def _sign(secret: str, body: bytes, ts: str) -> str:
    return hmac.new(secret.encode("utf-8"), ts.encode("utf-8") + body, hashlib.sha256).hexdigest()


class _FakeHttpReq:
    def __init__(self, body=b"", headers=None, remote="10.0.0.5", path="/test"):
        self._body = body
        self.headers = headers or {}
        self.remote_addr = remote
        self.environ = {}
        self.path = path

    def get_data(self):
        return self._body


class _FakeRequest:
    def __init__(self, env, body=b"", headers=None, remote="10.0.0.5"):
        self.env = env
        self.httprequest = _FakeHttpReq(body=body, headers=headers, remote=remote)
        self.responses = []

    def make_json_response(self, payload, status=200):
        self.responses.append((status, payload))
        return (status, payload)


@tagged("post_install", "-at_install")
class TestSecureEndpoint(TransactionCase):
    SCOPE = "unittest"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.secret = "s3cr3t-very-long-key"
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param(f"custom_core.secure_endpoint.{cls.SCOPE}.secret", cls.secret)
        ICP.set_param(f"custom_core.secure_endpoint.{cls.SCOPE}.allowed_cidrs", "10.0.0.0/24,127.0.0.1")

    def setUp(self):
        super().setUp()
        # Reset process-local nonce cache between tests.
        se._NONCE_CACHE.clear()
        se._NonceStore._redis_client = None
        se._NonceStore._redis_probed = True  # skip probe in tests

    def _invoke(self, body=b'{"a":1}', sig=None, ts=None, remote="10.0.0.5"):
        ts = ts if ts is not None else str(int(time.time()))
        sig = sig if sig is not None else _sign(self.secret, body, ts)
        fake = _FakeRequest(self.env, body=body, headers={"X-Signature": sig, "X-Timestamp": ts}, remote=remote)

        @se.secure_endpoint(self.SCOPE)
        def handler():
            return ("ok", {"ok": True})

        with patch.object(se, "request", fake):
            return handler(), fake

    def test_happy_path(self):
        result, fake = self._invoke()
        self.assertEqual(result, ("ok", {"ok": True}))

    def test_bad_signature(self):
        result, fake = self._invoke(sig="0" * 64)
        self.assertEqual(result[0], 401)
        self.assertEqual(result[1]["error_code"], "BAD_SIGNATURE")

    def test_expired_timestamp(self):
        old_ts = str(int(time.time()) - 10_000)
        body = b'{"a":1}'
        sig = _sign(self.secret, body, old_ts)
        result, fake = self._invoke(body=body, sig=sig, ts=old_ts)
        self.assertEqual(result[0], 401)
        self.assertEqual(result[1]["error_code"], "EXPIRED_TIMESTAMP")

    def test_replay_nonce(self):
        body = b'{"a":1}'
        ts = str(int(time.time()))
        sig = _sign(self.secret, body, ts)
        r1, _ = self._invoke(body=body, sig=sig, ts=ts)
        self.assertEqual(r1, ("ok", {"ok": True}))
        r2, _ = self._invoke(body=body, sig=sig, ts=ts)
        self.assertEqual(r2[0], 401)
        self.assertEqual(r2[1]["error_code"], "REPLAY_NONCE")

    def test_ip_not_whitelisted(self):
        result, fake = self._invoke(remote="8.8.8.8")
        self.assertEqual(result[0], 403)
        self.assertEqual(result[1]["error_code"], "IP_NOT_ALLOWED")
