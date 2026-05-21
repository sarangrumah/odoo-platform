# -*- coding: utf-8 -*-
"""Sandbox-mode send: no real HTTP, fake message_id, state transitions."""

from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSendSandbox(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["whatsapp.account"]
        cls.Message = cls.env["whatsapp.message"]
        cls.Template = cls.env["whatsapp.template"]

        cls.account = cls.Account.create({
            "name": "Test WA Account",
            "provider": "meta_cloud",
            "phone_number_id": "1234567890",
            "business_account_id": "9876543210",
            "access_token": "fake-token",
            "webhook_verify_token": "verify-secret-xyz",
            "sandbox_mode": True,
            "is_active": True,
        })

    def test_sandbox_send_marks_sent_with_fake_id(self):
        msg = self.Message.create({
            "account_id": self.account.id,
            "to_phone": "+6281234567890",
            "body": "hello from sandbox",
            "direction": "outbound",
        })
        msg.action_send()
        msg.invalidate_recordset()
        self.assertEqual(msg.state, "sent")
        self.assertTrue(msg.provider_message_id)
        self.assertTrue(msg.provider_message_id.startswith("sandbox-"))
        self.assertTrue(msg.sent_at)
        self.assertFalse(msg.error_message)

    def test_sandbox_send_skips_inbound(self):
        msg = self.Message.create({
            "account_id": self.account.id,
            "to_phone": "+6281234567890",
            "body": "incoming",
            "direction": "inbound",
            "state": "received",
        })
        # action_send must be a no-op for inbound rows.
        msg.action_send()
        self.assertEqual(msg.state, "received")

    def test_inactive_account_marks_failed(self):
        self.account.is_active = False
        msg = self.Message.create({
            "account_id": self.account.id,
            "to_phone": "+6281234567890",
            "body": "ping",
        })
        msg.action_send()
        msg.invalidate_recordset()
        self.assertEqual(msg.state, "failed")
        self.assertIn("inactive", (msg.error_message or "").lower())

    def test_template_payload_uses_template_type_when_approved(self):
        tpl = self.Template.create({
            "name": "order_shipped_id",
            "account_id": self.account.id,
            "language_code": "id",
            "category": "utility",
            "body_text": "Halo {{1}}, pesanan {{2}} sudah dikirim.",
            "status": "approved",
        })
        msg = self.Message.create({
            "account_id": self.account.id,
            "template_id": tpl.id,
            "to_phone": "+6281234567890",
        })
        payload = msg._build_payload()
        self.assertEqual(payload["type"], "template")
        self.assertEqual(payload["template"]["name"], "order_shipped_id")
        self.assertEqual(payload["template"]["language"]["code"], "id")
        # E.164 plus should be stripped per Meta convention.
        self.assertEqual(payload["to"], "6281234567890")

    def test_text_payload_when_no_approved_template(self):
        msg = self.Message.create({
            "account_id": self.account.id,
            "to_phone": "+6281234567890",
            "body": "free text",
        })
        payload = msg._build_payload()
        self.assertEqual(payload["type"], "text")
        self.assertEqual(payload["text"]["body"], "free text")
