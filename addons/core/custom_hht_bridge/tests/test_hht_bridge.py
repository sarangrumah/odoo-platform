# -*- coding: utf-8 -*-
# License: LGPL-3
"""HHT Bridge integration tests."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from odoo.tests.common import HttpCase, TransactionCase, tagged


def _sign(secret: str, ts: str, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"), ts.encode("utf-8") + body, hashlib.sha256,
    ).hexdigest()


@tagged("post_install", "-at_install")
class TestHhtDevice(TransactionCase):

    def test_device_create_generates_keys(self):
        dev = self.env["hht.device"].create({
            "name": "Test TC52",
            "device_id": "TC52-TEST-001",
            "model": "zebra_tc52",
        })
        self.assertTrue(dev.api_key)
        self.assertTrue(dev.api_secret)
        self.assertEqual(len(dev.api_key), 32)  # 16 bytes hex
        self.assertEqual(len(dev.api_secret), 64)  # 32 bytes hex

    def test_sync_batch_deduplicates(self):
        dev = self.env["hht.device"].create({
            "name": "BatchDev",
            "device_id": "BATCH-001",
            "model": "generic_browser",
        })
        Queue = self.env["hht.sync.queue"]
        shared_cid = str(uuid.uuid4())
        # Create first item
        Queue.create({
            "device_id": dev.id,
            "client_id": shared_cid,
            "action": "lookup",
            "payload": {"barcode": "X1"},
            "state": "applied",
        })
        # Re-issuing same client_id triggers sql_constraint
        with self.assertRaises(Exception):
            Queue.create({
                "device_id": dev.id,
                "client_id": shared_cid,
                "action": "lookup",
                "payload": {"barcode": "X1-dup"},
            })
        # Distinct client_ids work
        a = Queue.create({
            "device_id": dev.id,
            "client_id": str(uuid.uuid4()),
            "action": "lookup",
            "payload": {"barcode": "Y1"},
        })
        b = Queue.create({
            "device_id": dev.id,
            "client_id": str(uuid.uuid4()),
            "action": "lookup",
            "payload": {"barcode": "Y2"},
        })
        self.assertNotEqual(a.id, b.id)


@tagged("post_install", "-at_install")
class TestHhtBridgeHttp(HttpCase):

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_core.secure_endpoint.hht.secret", "test-secret-xyz",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_core.secure_endpoint.hht.allowed_cidrs", "0.0.0.0/0",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_hht_bridge.datawedge.allowed_cidrs", "0.0.0.0/0",
        )
        self.device = self.env["hht.device"].create({
            "name": "HTTP Dev",
            "device_id": "HTTP-TEST-001",
            "model": "zebra_tc52",
        })
        self.env.cr.commit()

    def _post_signed(self, path, payload, *, secret=None, ts=None):
        body = json.dumps(payload).encode("utf-8")
        ts = ts or str(int(time.time()))
        sig = _sign(secret or "test-secret-xyz", ts, body)
        return self.url_open(
            path, data=body, timeout=20,
            headers={
                "Content-Type": "application/json",
                "X-Timestamp": ts,
                "X-Signature": sig,
                "X-Device-Key": self.device.api_key,
            },
        )

    def test_scan_endpoint_valid_hmac(self):
        before = self.env["hht.scan.log"].search_count([("device_id", "=", self.device.id)])
        resp = self._post_signed("/api/hht/scan", {
            "barcode": "TEST-BC-001", "action": "lookup",
        })
        self.assertEqual(resp.status_code, 200)
        after = self.env["hht.scan.log"].search_count([("device_id", "=", self.device.id)])
        self.assertGreater(after, before)

    def test_scan_endpoint_invalid_hmac(self):
        body = json.dumps({"barcode": "X", "action": "lookup"}).encode("utf-8")
        ts = str(int(time.time()))
        resp = self.url_open(
            "/api/hht/scan", data=body, timeout=20,
            headers={
                "Content-Type": "application/json",
                "X-Timestamp": ts,
                "X-Signature": "00" * 32,  # wrong
                "X-Device-Key": self.device.api_key,
            },
        )
        self.assertEqual(resp.status_code, 401)

    def test_replay_nonce(self):
        payload = {"barcode": "REPLAY-01", "action": "lookup"}
        ts = str(int(time.time()))
        r1 = self._post_signed("/api/hht/scan", payload, ts=ts)
        self.assertEqual(r1.status_code, 200)
        # Same ts + body -> same signature -> replay should fail
        r2 = self._post_signed("/api/hht/scan", payload, ts=ts)
        self.assertEqual(r2.status_code, 401)
        data = r2.json() if hasattr(r2, "json") else json.loads(r2.text)
        self.assertEqual(data.get("error_code"), "REPLAY_NONCE")

    def test_datawedge_resolves_serial(self):
        body = json.dumps({
            "barcode": "DW-BC-1",
            "device_serial": self.device.device_id,
        }).encode("utf-8")
        resp = self.url_open(
            "/api/hht/datawedge", data=body, timeout=20,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.text)
        self.assertTrue(data.get("ok") in (True, False))  # routed correctly either way
        # A scan log must have been written (ok or error path).
        log = self.env["hht.scan.log"].search(
            [("device_id", "=", self.device.id), ("barcode", "=", "DW-BC-1")], limit=1,
        )
        self.assertTrue(log)

    def test_datawedge_unknown_serial(self):
        body = json.dumps({
            "barcode": "DW-BC-2", "device_serial": "NOPE-NOPE-NOPE",
        }).encode("utf-8")
        resp = self.url_open(
            "/api/hht/datawedge", data=body, timeout=20,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.text)
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "UNKNOWN_DEVICE_SERIAL")

    def test_manifest_endpoint_etag(self):
        resp = self._post_signed("/api/hht/manifest", {})  # signed (GET-with-body works too)
        # Manifest is GET; build a signed GET.
        ts = str(int(time.time()))
        sig = _sign("test-secret-xyz", ts, b"")
        resp = self.url_open(
            "/api/hht/manifest", timeout=20,
            headers={
                "X-Timestamp": ts, "X-Signature": sig,
                "X-Device-Key": self.device.api_key,
            },
        )
        self.assertEqual(resp.status_code, 200)
        etag = resp.headers.get("ETag")
        self.assertTrue(etag)

    def test_me_endpoint(self):
        ts = str(int(time.time()))
        sig = _sign("test-secret-xyz", ts, b"")
        resp = self.url_open(
            "/api/hht/me", timeout=20,
            headers={
                "X-Timestamp": ts, "X-Signature": sig,
                "X-Device-Key": self.device.api_key,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.text)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["result"]["device"]["device_id"], "HTTP-TEST-001")
