# -*- coding: utf-8 -*-
"""Credit-limit enforcement on sale order confirmation."""

from __future__ import annotations

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCreditLimit(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({
            "name": "CreditCust",
            "custom_credit_limit": 100.0,
            "custom_credit_limit_check_method": "block",
        })
        # Build minimal sellable product to put on the sale order
        self.product = self.env["product.product"].create({
            "name": "Credit-Demo",
            "type": "consu",
            "list_price": 500.0,
            "sale_ok": True,
        })

    def test_block_on_confirm_when_order_exceeds_limit(self):
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": 500.0,
            })],
        })
        with self.assertRaises(UserError):
            so.action_confirm()
        # A log row should still have been written
        log = self.env["custom.credit.check.log"].search([
            ("sale_order_id", "=", so.id),
        ], limit=1)
        self.assertTrue(log)
        self.assertEqual(log.decision, "blocked")

    def test_pass_when_under_limit(self):
        self.partner.custom_credit_limit = 1000.0
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            })],
        })
        so.action_confirm()
        self.assertIn(so.state, ("sale", "done"))
