# -*- coding: utf-8 -*-
from odoo.addons.purchase_stock.tests.common import PurchaseTestCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestServiceReceipt(PurchaseTestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["product.product"].create(
            {
                "name": "Drone Show Operational - Manpower",
                "type": "service",
                "purchase_ok": True,
                "receive_on_gr": True,
            }
        )
        cls.plain_service = cls.env["product.product"].create(
            {
                "name": "Etiqa Insurance",
                "type": "service",
                "purchase_ok": True,
            }
        )
        cls.good = cls.env["product.product"].create(
            {
                "name": "Drone Unit",
                "type": "consu",
                "is_storable": True,
                "purchase_ok": True,
                "purchase_method": "receive",
            }
        )

    # ------------------------------------------------------------------
    # Product master
    # ------------------------------------------------------------------
    def test_flag_forces_receive_control(self):
        """Ticking the flag moves the product off 'On ordered quantities'."""
        self.assertEqual(self.service.purchase_method, "receive")

        later = self.env["product.product"].create({"name": "Venue", "type": "service", "purchase_ok": True})
        self.assertEqual(later.purchase_method, "purchase")
        later.receive_on_gr = True
        self.assertEqual(later.purchase_method, "receive")

    def test_flag_does_not_override_an_explicit_policy(self):
        """A caller setting the policy in the same write still wins."""
        product = self.env["product.product"].create(
            {
                "name": "Manpower on order",
                "type": "service",
                "receive_on_gr": True,
                "purchase_method": "purchase",
            }
        )
        self.assertEqual(product.purchase_method, "purchase")

    # ------------------------------------------------------------------
    # Core behaviour must be untouched for everything else
    # ------------------------------------------------------------------
    def test_unflagged_service_keeps_core_behaviour(self):
        po = self._create_purchase(self.plain_service, quantity=1.0)
        self.assertFalse(po.picking_ids, "an unflagged service must not build a receipt")
        self.assertEqual(po.order_line.qty_received_method, "manual")

    # ------------------------------------------------------------------
    # Receipt
    # ------------------------------------------------------------------
    def test_all_service_order_gets_a_receipt(self):
        """The shape core skips outright: an order with no goods line at all."""
        po = self._create_purchase(self.service, quantity=3.0, price_unit=250.0)

        self.assertEqual(len(po.picking_ids), 1)
        picking = po.picking_ids
        self.assertEqual(picking.picking_type_id.code, "incoming")
        move = picking.move_ids
        self.assertEqual(move.product_id, self.service)
        self.assertEqual(move.product_uom_qty, 3.0)
        # A service is never reserved, so the move is available on confirmation.
        self.assertEqual(move.state, "assigned")

        self.assertEqual(po.order_line.qty_received_method, "stock_moves")
        self.assertEqual(po.order_line.qty_received, 0.0)

        self._receive(po)
        self.assertEqual(picking.state, "done")
        self.assertEqual(po.order_line.qty_received, 3.0)

    def test_mixed_order_puts_both_on_one_receipt(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "order_line": [
                    (0, 0, {"product_id": self.good.id, "product_qty": 2.0, "price_unit": 100.0}),
                    (0, 0, {"product_id": self.service.id, "product_qty": 1.0, "price_unit": 500.0}),
                ],
            }
        )
        po.button_confirm()

        self.assertEqual(len(po.picking_ids), 1)
        self.assertEqual(po.picking_ids.move_ids.product_id, self.good | self.service)

        self._receive(po)
        for line in po.order_line:
            self.assertEqual(line.qty_received, line.product_qty)

    def test_partial_receipt_reports_the_accepted_quantity(self):
        po = self._create_purchase(self.service, quantity=10.0)
        picking = po.picking_ids
        picking.move_ids.quantity = 4.0
        picking.move_ids.picked = True
        picking.with_context(skip_backorder=True, picking_ids_not_to_backorder=picking.ids).button_validate()

        self.assertEqual(po.order_line.qty_received, 4.0)

    def test_increasing_the_quantity_updates_the_open_receipt(self):
        po = self._create_purchase(self.service, quantity=1.0)
        self.assertEqual(sum(po.picking_ids.move_ids.mapped("product_uom_qty")), 1.0)

        po.order_line.product_qty = 4.0
        self.assertEqual(len(po.picking_ids), 1, "the line must join the open receipt")
        self.assertEqual(sum(po.picking_ids.move_ids.mapped("product_uom_qty")), 4.0)

    # ------------------------------------------------------------------
    # No inventory and no accounting side effect
    # ------------------------------------------------------------------
    def test_receipt_values_nothing(self):
        po = self._create_purchase(self.service, quantity=2.0, price_unit=750.0)
        self._receive(po)

        move = po.picking_ids.move_ids
        self.assertFalse(move.account_move_id, "a service receipt must book no journal entry")
        self.assertFalse(
            self.env["stock.quant"].search([("product_id", "=", self.service.id)]),
            "a service receipt must create no quant",
        )

    # ------------------------------------------------------------------
    # Invoicing
    # ------------------------------------------------------------------
    def test_bill_is_gated_by_the_receipt(self):
        po = self._create_purchase(self.service, quantity=5.0, price_unit=200.0)
        self.assertEqual(po.order_line.qty_to_invoice, 0.0, "nothing to bill before acceptance")

        picking = po.picking_ids
        picking.move_ids.quantity = 2.0
        picking.move_ids.picked = True
        picking.with_context(skip_backorder=True, picking_ids_not_to_backorder=picking.ids).button_validate()

        self.assertEqual(po.order_line.qty_to_invoice, 2.0)
        bill = self._create_bill(purchase_order=po)
        self.assertEqual(bill.invoice_line_ids.quantity, 2.0)

    # ------------------------------------------------------------------
    # Flagging a product must not disturb orders already in flight
    # ------------------------------------------------------------------
    def test_flagging_leaves_a_confirmed_line_alone(self):
        """The regression that mattered on prd_arkaaim.

        Five Manpower lines and one Insurance line were confirmed and part-billed
        with a hand-typed received quantity and no receipt behind them. Flagging
        the product recomputes every line that ever used it -- and taking those
        over would zero the typed quantity, leaving three orders unbillable and
        three billed for more than they had received.
        """
        po = self._create_purchase(self.plain_service, quantity=1.0)
        po.order_line.qty_received = 1.0
        self.assertEqual(po.order_line.qty_received_method, "manual")
        self.assertFalse(po.order_line.move_ids)

        self.plain_service.receive_on_gr = True

        self.assertEqual(po.order_line.qty_received_method, "manual")
        self.assertEqual(po.order_line.qty_received, 1.0, "a typed quantity must survive")
        self.assertEqual(po.order_line.qty_to_invoice, 1.0, "the order must stay billable")

    def test_flagging_takes_over_a_line_that_has_a_receipt(self):
        """A confirmed line that DOES have a receipt is a different case: the
        moves can answer for the quantity, so they should."""
        self.plain_service.receive_on_gr = True
        po = self._create_purchase(self.plain_service, quantity=2.0)
        self.assertEqual(po.order_line.qty_received_method, "stock_moves")
        self.assertTrue(po.order_line.move_ids)

        self._receive(po)
        self.assertEqual(po.order_line.qty_received, 2.0)
