# -*- coding: utf-8 -*-
"""ARKA show-date: propagation, required gating, and due-date anchoring.

Uses AccountTestInvoicingCommon so the test company has a real chart of
accounts + journals (needed to create invoices from sales orders). A single
company is used and the gate flag is toggled per case — TransactionCase rolls
back each method to the setUpClass state, so toggles don't leak.
"""

from datetime import date

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install", "custom_arka_show_date")
class TestArkaShowDate(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.x_custom_show_date_enabled = True  # treat as "PT ARKA"

        cls.partner = cls.partner_a
        cls.product = cls.product_a
        cls.product.invoice_policy = "order"  # invoiceable on confirm

        cls.term30 = cls.env["account.payment.term"].create(
            {
                "name": "30 Days After (test)",
                "line_ids": [(0, 0, {"value": "percent", "value_amount": 100.0, "nb_days": 30})],
            }
        )
        cls.show = date(2026, 9, 1)

    def _make_so(self, show_date=False):
        # sudo(): AccountTestInvoicingCommon's user has accounting but not Sales
        # rights; the feature logic under test is independent of access groups.
        return (
            self.env["sale.order"]
            .with_company(self.company)
            .sudo()
            .create(
                {
                    "partner_id": self.partner.id,
                    "company_id": self.company.id,
                    "payment_term_id": self.term30.id,
                    "x_custom_show_date": show_date,
                    "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1})],
                }
            )
        )

    # (1) field propagates SO -> invoice via _prepare_invoice
    def test_show_date_propagates_to_invoice(self):
        so = self._make_so(self.show)
        so.action_confirm()
        invoice = so._create_invoices()
        self.assertEqual(invoice.x_custom_show_date, self.show)

    # (2) required enforced only when company flag is on
    def test_required_only_when_flag_on(self):
        so = self._make_so(show_date=False)
        with self.assertRaises(UserError):
            so.action_confirm()

        self.company.x_custom_show_date_enabled = False
        so2 = self._make_so(show_date=False)
        so2.action_confirm()  # must NOT raise
        self.assertEqual(so2.state, "sale")

    # (3) due date anchored to show_date for the flagged company
    def test_due_date_anchored_to_show_date(self):
        so = self._make_so(self.show)
        so.action_confirm()
        invoice = so._create_invoices()
        invoice.invoice_date = date(2026, 6, 1)  # deliberately != show date
        # 30 days after SHOW date (2026-09-01) => 2026-10-01, NOT 2026-07-01.
        self.assertEqual(invoice.invoice_date_due, date(2026, 10, 1))
        receivable = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        self.assertEqual(receivable.date_maturity, date(2026, 10, 1))

    # (4) flag off -> standard behaviour (anchored to invoice_date)
    def test_non_flagged_anchors_to_invoice_date(self):
        self.company.x_custom_show_date_enabled = False
        so = self._make_so(self.show)  # show date set, but flag off
        so.action_confirm()
        invoice = so._create_invoices()
        invoice.invoice_date = date(2026, 6, 1)
        # 30 days after INVOICE date (2026-06-01) => 2026-07-01.
        self.assertEqual(invoice.invoice_date_due, date(2026, 7, 1))
