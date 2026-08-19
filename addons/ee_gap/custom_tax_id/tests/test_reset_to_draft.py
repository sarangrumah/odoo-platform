# -*- coding: utf-8 -*-
"""Resetting a vendor bill to draft must move the state and nothing else.

Sheet "[Levi's] List Issue After Go Live" #7 (keterangan) and #8 (nominal):
Accounting adjusts the PPN / PPh line on a bill to match the faktur, posts it,
and then has to reset to draft for an unrelated correction — at which point
Odoo rebuilt the tax lines from the base lines and both the typed keterangan
and the typed nominal were gone, the payable line moving with them.

Built on ``AccountTestInvoicingCommon`` rather than this module's own
``TaxIdCommon``: these cases need a company with a real chart (payable account,
purchase tax), not the withholding fixtures.
"""

from __future__ import annotations

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestResetToDraftKeepsTaxLines(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax_ppn = cls.env["account.tax"].create(
            {
                "name": "PPN Masukan 11% (test)",
                "type_tax_use": "purchase",
                "amount_type": "percent",
                "amount": 11.0,
                "price_include_override": "tax_excluded",
                "company_id": cls.env.company.id,
            }
        )
        cls.tax_pph_23 = cls.env["account.tax"].create(
            {
                "name": "PPh 23 (2%) (test)",
                "type_tax_use": "purchase",
                "amount_type": "percent",
                "amount": -2.0,
                "price_include_override": "tax_excluded",
                "company_id": cls.env.company.id,
            }
        )

    def _bill(self, taxes, price=1_000_000.0):
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-08-19",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Jasa konsultan",
                            "quantity": 1.0,
                            "price_unit": price,
                            "tax_ids": [(6, 0, taxes.ids)],
                        },
                    )
                ],
            }
        )

    def _tax_line(self, bill, tax=None):
        return bill.line_ids.filtered(lambda line: line.display_type == "tax" and (not tax or line.tax_line_id == tax))

    def _payable_line(self, bill):
        return bill.line_ids.filtered(lambda line: line.display_type == "payment_term")

    def _retype(self, bill, values, payable_balance):
        """Retype tax lines the way the Journal Items tab does — every touched
        line in ONE write, so the entry is never momentarily unbalanced.

        ``values`` maps a tax record to ``(label, balance)``.
        """
        commands = []
        for tax, (label, balance) in values.items():
            line = self._tax_line(bill, tax)
            commands.append((1, line.id, {"name": label, "amount_currency": balance, "balance": balance}))
        commands.append(
            (
                1,
                self._payable_line(bill).id,
                {"amount_currency": payable_balance, "balance": payable_balance},
            )
        )
        bill.write({"line_ids": commands})

    def test_reset_to_draft_keeps_the_typed_amount(self):
        bill = self._bill(self.tax_ppn)
        self._retype(bill, {self.tax_ppn: ("PPN Masukan — FP 010", 105_000.0)}, -1_105_000.0)
        bill.action_post()
        self.assertEqual(self._tax_line(bill).balance, 105_000.0)

        bill.button_draft()

        self.assertEqual(bill.state, "draft")
        self.assertEqual(self._tax_line(bill).balance, 105_000.0, "the typed PPN was recomputed")
        self.assertEqual(self._payable_line(bill).balance, -1_105_000.0)
        self.assertEqual(sum(bill.line_ids.mapped("balance")), 0.0)

    def test_reset_to_draft_keeps_the_typed_keterangan(self):
        bill = self._bill(self.tax_ppn)
        self._retype(bill, {self.tax_ppn: ("PPN Masukan — FP 010", 105_000.0)}, -1_105_000.0)
        bill.action_post()

        bill.button_draft()

        self.assertEqual(self._tax_line(bill).name, "PPN Masukan — FP 010")

    def test_the_bill_can_be_posted_again_unchanged(self):
        bill = self._bill(self.tax_ppn)
        self._retype(bill, {self.tax_ppn: ("PPN Masukan — FP 010", 105_000.0)}, -1_105_000.0)
        bill.action_post()
        bill.button_draft()

        bill.action_post()

        self.assertEqual(bill.state, "posted")
        self.assertEqual(self._tax_line(bill).balance, 105_000.0)
        self.assertEqual(self._tax_line(bill).name, "PPN Masukan — FP 010")

    def test_an_untouched_bill_is_left_exactly_as_computed(self):
        """The restore must be a no-op when nothing was typed — otherwise it
        would freeze whatever the last computation produced."""
        bill = self._bill(self.tax_ppn)
        bill.action_post()
        self.assertEqual(self._tax_line(bill).balance, 110_000.0)

        bill.button_draft()

        self.assertEqual(self._tax_line(bill).balance, 110_000.0)
        self.assertEqual(sum(bill.line_ids.mapped("balance")), 0.0)

    def test_editing_a_base_line_afterwards_still_recomputes(self):
        """Preserving the amount across the reset must not freeze the tax: a
        real edit in draft has to flow through to the PPN again."""
        bill = self._bill(self.tax_ppn)
        self._retype(bill, {self.tax_ppn: ("PPN Masukan — FP 010", 105_000.0)}, -1_105_000.0)
        bill.action_post()
        bill.button_draft()

        bill.invoice_line_ids.price_unit = 2_000_000.0

        self.assertEqual(self._tax_line(bill).balance, 220_000.0)

    def test_a_retyped_pph_line_survives_the_reset_too(self):
        """PPh is booked as a negative purchase tax on the bill line — the same
        tax-line path as PPN, and the client reported the two together."""
        bill = self._bill(self.tax_ppn | self.tax_pph_23)
        self._retype(
            bill,
            {
                self.tax_ppn: ("PPN Masukan — FP 010", 105_000.0),
                self.tax_pph_23: ("PPh 23 jasa konsultan", -25_000.0),
            },
            -1_080_000.0,
        )
        bill.action_post()

        bill.button_draft()

        self.assertEqual(self._tax_line(bill, self.tax_ppn).balance, 105_000.0)
        self.assertEqual(self._tax_line(bill, self.tax_pph_23).balance, -25_000.0)
        self.assertEqual(self._tax_line(bill, self.tax_pph_23).name, "PPh 23 jasa konsultan")
        self.assertEqual(sum(bill.line_ids.mapped("balance")), 0.0)
