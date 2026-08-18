# -*- coding: utf-8 -*-
"""A bill with no faktur pajak must print an EMPTY Tax Number.

`_edo_tax_number` used to fall back to `l10n_id_kode_transaksi`, which is the
two-digit DJP *transaction code*, not a faktur number. Every bill entered
without a faktur therefore printed "04" in the Tax Number row of the Journal
Billing voucher -- 80 posted bills in prd_levis_begbal on 18-Aug-2026 -- which
reads as a real faktur to whoever reviews the print-out.
"""

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestJournalBillingTaxNumber(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bill = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2026-07-15",
                "date": "2026-07-15",
                "invoice_line_ids": [
                    Command.create({"name": "Jasa", "quantity": 1, "price_unit": 1000.0, "tax_ids": []})
                ],
            }
        )

    def test_no_faktur_prints_empty(self):
        self.assertEqual(self.bill._edo_tax_number(), "")

    def test_kode_transaksi_is_not_a_faktur_number(self):
        """The regression itself: "04" in the transaction code must not leak."""
        if "l10n_id_kode_transaksi" not in self.bill._fields:
            self.skipTest("l10n_id e-faktur not installed on this DB")
        self.bill.l10n_id_kode_transaksi = "04"
        self.assertEqual(self.bill._edo_tax_number(), "")

    def test_real_faktur_still_prints(self):
        field = next(
            (f for f in ("x_custom_nsfp", "l10n_id_tax_number") if f in self.bill._fields),
            None,
        )
        if not field:
            self.skipTest("no faktur-number field on this DB")
        self.bill[field] = "0400002512345678"
        self.assertEqual(self.bill._edo_tax_number(), "0400002512345678")
