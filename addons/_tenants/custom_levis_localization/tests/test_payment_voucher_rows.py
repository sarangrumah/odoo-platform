# -*- coding: utf-8 -*-
"""The Payment Voucher must name the bill it settles, not itself.

Regression guard for `_edo_line_source_doc`: it used to read the near side of
`matched_debit_ids` / `matched_credit_ids`, which resolves to the line itself,
so NOMOR DOC AP and REF Invoice Vendor printed the payment's own number on
every row.
"""

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestPaymentVoucherRows(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
            .create({"journal_id": cls.company_data["default_journal_bank"].id})
            ._create_payments()
        )

    def test_counterpart_row_names_the_bill(self):
        rows = self.payment._edo_voucher_rows()
        self.assertIn(self.bill.name, [r["doc_ap"] for r in rows])
        self.assertIn("INV-VENDOR-9", [r["ref_vendor"] for r in rows])

    def test_source_doc_is_the_bill_not_the_payment(self):
        payable = self.payment.move_id.line_ids.filtered(
            lambda ln: ln.account_id.account_type == "liability_payable"
        )
        self.assertEqual(self.payment._edo_line_source_doc(payable), self.bill)

    def test_unreconciled_line_falls_back_to_the_payment(self):
        liquidity = self.payment.move_id.line_ids.filtered(
            lambda ln: ln.account_id == self.payment.outstanding_account_id
        )
        self.assertFalse(self.payment._edo_line_source_doc(liquidity))
        row = [r for r in self.payment._edo_voucher_rows() if r["coa"] == liquidity.account_id.name][0]
        self.assertEqual(row["doc_ap"], self.payment.name)
