# -*- coding: utf-8 -*-
"""FG_UANG_MUKA: which faktur is a down payment and which only settles one.

The flag used to be hard-coded '0', so a faktur uang muka went to Coretax
looking like an ordinary sale.
"""

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

FK_FG_UANG_MUKA = 22


@tagged("post_install", "-at_install", "custom_coretax_export")
class TestCoretaxUangMuka(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.builder = cls.env["custom.coretax.fk.builder"]
        cls.company = cls.company_data["company"]
        cls.company.partner_id.x_custom_npwp = "0012345678901000"
        cls.company.x_custom_nitku_suffix = "000000"
        cls.service = cls.env["product.product"].create(
            {"name": "Jasa Drone", "type": "service", "invoice_policy": "order"}
        )

    def _order(self):
        order = (
            self.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
                }
            )
        )
        order.action_confirm()
        return order

    def _downpayment_invoice(self, order):
        wizard = (
            self.env["sale.advance.payment.inv"]
            .sudo()
            .with_context(active_ids=order.ids, active_model="sale.order")
            .create({"advance_payment_method": "percentage", "amount": 50.0})
        )
        return wizard._create_invoices(order)

    def _fk_flag(self, invoice):
        invoice.invoice_date = "2026-07-03"
        invoice.action_post()
        _headers, rows = self.builder._coretax_fk_rows(invoice, company=self.company)
        fk_row = next(r for r in rows if r[0] == "FK")
        return fk_row[FK_FG_UANG_MUKA]

    def test_down_payment_invoice_is_flagged(self):
        invoice = self._downpayment_invoice(self._order())
        self.assertEqual(self._fk_flag(invoice), "1")

    def test_ordinary_invoice_is_not_flagged(self):
        invoice = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2026-07-03",
                    "invoice_line_ids": [(0, 0, {"product_id": self.service.id, "quantity": 1, "price_unit": 100.0})],
                }
            )
        )
        self.assertEqual(self._fk_flag(invoice), "0")

    def test_settlement_invoice_is_not_flagged(self):
        """The final faktur carries the deducted down payment, but it settles
        goods — flagging it would tell Coretax two down payments were issued."""
        order = self._order()
        self._downpayment_invoice(order).action_post()
        wizard = (
            self.env["sale.advance.payment.inv"]
            .sudo()
            .with_context(active_ids=order.ids, active_model="sale.order")
            .create({"advance_payment_method": "delivered"})
        )
        final = wizard._create_invoices(order)
        self.assertEqual(self._fk_flag(final), "0")
