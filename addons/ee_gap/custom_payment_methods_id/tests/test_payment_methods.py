# -*- coding: utf-8 -*-
"""Giro / Bank Transfer are usable on a bank journal and post like a manual payment."""

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestIdPaymentMethods(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.bill = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2026-01-15",
                "date": "2026-01-15",
                "invoice_line_ids": [
                    Command.create({"name": "Service", "quantity": 1, "price_unit": 500000.0, "tax_ids": []})
                ],
            }
        )
        cls.bill.action_post()

    def _method(self, code, payment_type):
        return self.env["account.payment.method"].search(
            [("code", "=", code), ("payment_type", "=", payment_type)], limit=1
        )

    def test_methods_exist_for_both_directions(self):
        for code in ("giro", "bank_transfer"):
            for payment_type in ("inbound", "outbound"):
                self.assertTrue(
                    self._method(code, payment_type),
                    "payment method %s/%s was not created" % (code, payment_type),
                )

    def test_method_is_multi_and_bank_only(self):
        info = self.env["account.payment.method"]._get_payment_method_information()
        for code in ("giro", "bank_transfer"):
            self.assertEqual(info[code]["mode"], "multi")
            self.assertEqual(info[code]["type"], ("bank",))

    def test_hook_is_idempotent(self):
        """Re-running the hook must not raise on the unique (code, payment_type)."""
        from odoo.addons.custom_payment_methods_id.hooks import post_init_hook

        before = self.env["account.payment.method"].search_count([("code", "in", ("giro", "bank_transfer"))])
        post_init_hook(self.env)
        after = self.env["account.payment.method"].search_count([("code", "in", ("giro", "bank_transfer"))])
        self.assertEqual(before, after)

    def test_payment_via_giro_posts_to_the_journal_outstanding_account(self):
        # Direct-to-bank, the policy the ARKA journals are configured with.
        line = self.env["account.payment.method.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "payment_method_id": self._method("giro", "outbound").id,
                "payment_account_id": self.bank_journal.default_account_id.id,
            }
        )
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=self.bill.ids)
            .create({"journal_id": self.bank_journal.id, "payment_method_line_id": line.id})
        )
        payment = wizard._create_payments()

        self.assertEqual(payment.payment_method_line_id, line)
        self.assertEqual(payment.outstanding_account_id, self.bank_journal.default_account_id)
        liquidity = payment.move_id.line_ids.filtered(
            lambda ln: ln.account_id == self.bank_journal.default_account_id
        )
        self.assertEqual(liquidity.credit, 500000.0)
        self.assertEqual(self.bill.payment_state, "paid")
