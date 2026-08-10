# -*- coding: utf-8 -*-
"""Payment Voucher rendering + the outstanding-account override."""

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.custom_payment_voucher.models.terbilang import terbilang_id
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPaymentVoucher(AccountTestInvoicingCommon):
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
                "ref": "INV-VENDOR-9",
                "invoice_line_ids": [
                    Command.create({"name": "Jasa", "quantity": 1, "price_unit": 270045.0, "tax_ids": []})
                ],
            }
        )
        cls.bill.action_post()
        cls.payment = (
            cls.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=cls.bill.ids)
            .create({"journal_id": cls.bank_journal.id})
            ._create_payments()
        )

    def test_voucher_rows_carry_the_reconciled_bill(self):
        rows = self.payment._pv_voucher_rows()
        self.assertEqual(len(rows), len(self.payment.move_id.line_ids))
        self.assertIn(self.bill.name, [r["doc_ap"] for r in rows])
        self.assertIn("INV-VENDOR-9", [r["ref_vendor"] for r in rows])
        self.assertAlmostEqual(sum(r["debit"] for r in rows), sum(r["credit"] for r in rows))

    def test_amount_in_words(self):
        self.assertEqual(terbilang_id(270045), "Dua Ratus Tujuh Puluh Ribu Empat Puluh Lima Rupiah")
        self.assertEqual(terbilang_id(0), "Nol Rupiah")

    def test_voucher_html_renders(self):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "custom_payment_voucher.report_payment_voucher", self.payment.ids
        )[0]
        body = html.decode() if isinstance(html, bytes) else html
        self.assertIn("PAYMENT VOUCHER", body)
        self.assertIn("Terbilang", body)
        # The style/charset must survive inside <main>: _prepare_html drops <head>.
        self.assertIn("<main>", body)
        self.assertLess(body.index("<style>"), body.index("PAYMENT VOUCHER"))

    def test_receipt_html_renders(self):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "custom_payment_voucher.report_payment_receipt", self.payment.ids
        )[0]
        body = html.decode() if isinstance(html, bytes) else html
        self.assertIn("PAYMENT RECEIPT", body)

    def test_override_outstanding_account_changes_the_posted_gl(self):
        other = self.env["account.account"].create(
            {"name": "Clearing", "code": "CLR0001", "account_type": "asset_current", "reconcile": True}
        )
        bill = self.bill.copy({"invoice_date": "2026-02-15", "date": "2026-02-15"})
        bill.action_post()
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create({"journal_id": self.bank_journal.id})
        )
        payment = wizard._create_payments()
        payment.pv_override_outstanding_account_id = other
        self.assertEqual(payment.outstanding_account_id, other)
