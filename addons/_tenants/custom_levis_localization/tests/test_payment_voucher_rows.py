# -*- coding: utf-8 -*-
"""The Payment Voucher must name every bill it settles, not itself and not only the first.

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
        payable = self.payment.move_id.line_ids.filtered(lambda ln: ln.account_id.account_type == "liability_payable")
        self.assertEqual(self.payment._edo_line_source_doc(payable), self.bill)

    def test_unreconciled_line_falls_back_to_the_payment(self):
        liquidity = self.payment.move_id.line_ids.filtered(
            lambda ln: ln.account_id == self.payment.outstanding_account_id
        )
        self.assertFalse(self.payment._edo_line_source_doc(liquidity))
        row = [r for r in self.payment._edo_voucher_rows() if r["coa"] == liquidity.account_id.name][0]
        self.assertEqual(row["doc_ap"], self.payment.name)


@tagged("post_install", "-at_install")
class TestPaymentVoucherMultiBill(AccountTestInvoicingCommon):
    """A payment settling several bills must name all of them, with amounts.

    Sheet "List Issue After Go Live" #21. One payment carries a single payable
    line however many bills it clears, so a row-per-journal-item voucher named
    the first bill and silently dropped the rest.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bills = cls.env["account.move"]
        for index, (amount, ref) in enumerate(
            [(31_373_340.0, "N260803131"), (31_373_340.0, "N260803132"), (31_373_341.0, "N260803133")]
        ):
            cls.bills |= cls.env["account.move"].create(
                {
                    "move_type": "in_invoice",
                    "partner_id": cls.partner_a.id,
                    "invoice_date": "2026-08-%02d" % (index + 1),
                    "date": "2026-08-%02d" % (index + 1),
                    "ref": ref,
                    "invoice_line_ids": [
                        Command.create({"name": "Sewa", "quantity": 1, "price_unit": amount, "tax_ids": []})
                    ],
                }
            )
        cls.bills.action_post()
        cls.payment = (
            cls.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=cls.bills.ids)
            .create({"journal_id": cls.company_data["default_journal_bank"].id, "group_payment": True})
            ._create_payments()
        )

    def _payable_rows(self):
        return [r for r in self.payment._edo_voucher_rows() if r["doc_ap"] in self.bills.mapped("name")]

    def test_every_settled_bill_gets_its_own_row(self):
        self.assertEqual(len(self.payment), 1, "the three bills must be paid by ONE payment")
        printed = [r["doc_ap"] for r in self._payable_rows()]
        self.assertCountEqual(printed, self.bills.mapped("name"))

    def test_each_row_carries_that_bill_s_vendor_reference(self):
        by_bill = {r["doc_ap"]: r["ref_vendor"] for r in self._payable_rows()}
        for bill in self.bills:
            self.assertEqual(by_bill[bill.name], bill.ref)

    def test_each_row_carries_the_amount_applied_to_that_bill(self):
        by_bill = {r["doc_ap"]: r["debit"] for r in self._payable_rows()}
        for bill in self.bills:
            self.assertAlmostEqual(by_bill[bill.name], bill.amount_total, places=2)

    def test_the_table_still_totals_the_journal_entry(self):
        rows = self.payment._edo_voucher_rows()
        move = self.payment.move_id
        self.assertAlmostEqual(sum(r["debit"] for r in rows), sum(move.line_ids.mapped("debit")), places=2)
        self.assertAlmostEqual(sum(r["credit"] for r in rows), sum(move.line_ids.mapped("credit")), places=2)

    def test_an_unapplied_remainder_keeps_the_payment_s_own_number(self):
        """Overpay a single bill: the settled part names the bill, the rest does
        not pretend to."""
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-08-10",
                "date": "2026-08-10",
                "ref": "N-OVER",
                "invoice_line_ids": [
                    Command.create({"name": "Sewa", "quantity": 1, "price_unit": 100_000.0, "tax_ids": []})
                ],
            }
        )
        bill.action_post()
        payment = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create({"journal_id": self.company_data["default_journal_bank"].id, "amount": 150_000.0})
            ._create_payments()
        )
        rows = payment._edo_voucher_rows()
        payable = [r for r in rows if r["debit"]]
        self.assertIn(bill.name, [r["doc_ap"] for r in payable])
        self.assertIn(payment.name, [r["doc_ap"] for r in payable])
        self.assertAlmostEqual(sum(r["debit"] for r in payable), 150_000.0, places=2)
