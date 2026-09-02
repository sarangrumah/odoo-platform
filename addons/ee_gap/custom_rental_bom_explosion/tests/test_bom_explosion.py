# -*- coding: utf-8 -*-
"""A bundle rented as one qty-1 line must move every unit it is made of."""

from datetime import datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBomExplosion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("custom_rental.config_stock_integration", "True")
        cls.partner = cls.env["res.partner"].create({"name": "Show Organiser"})

        Product = cls.env["product.product"]
        cls.drone = Product.create({"name": "Drone Unit", "type": "consu", "is_storable": True})
        cls.battery = Product.create({"name": "Drone Battery", "type": "consu", "is_storable": True})
        # The commercial line: one package, priced as one, with no stock of its own.
        cls.bundle = Product.create({"name": "Sewa Drone Show 10 Unit", "type": "consu", "is_storable": False})
        # A plain rental product with no BOM at all — the fallback path.
        cls.plain = Product.create({"name": "Plain Rental Item", "type": "consu", "is_storable": True})

        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.bundle.product_tmpl_id.id,
                "product_qty": 1.0,
                "type": "phantom",
                "bom_line_ids": [
                    (0, 0, {"product_id": cls.drone.id, "product_qty": 10.0}),
                    (0, 0, {"product_id": cls.battery.id, "product_qty": 20.0}),
                ],
            }
        )
        cls.now = datetime(2026, 9, 1, 9, 0)

    def _order(self, product, qty=1, loan_qty=0):
        return self.env["rental.order"].create(
            {
                "partner_id": self.partner.id,
                "product_id": product.id,
                "qty": qty,
                "loan_qty": loan_qty,
                "pickup_dt": self.now,
                "return_dt_expected": self.now + timedelta(days=2),
                "daily_rate": 100.0,
            }
        )

    def _require_outgoing(self):
        if not self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1):
            self.skipTest("no outgoing picking type available")

    # ------------------------------------------------------------------
    # Explosion helper
    # ------------------------------------------------------------------
    def test_explode_bundle_returns_components(self):
        order = self._order(self.bundle)
        comps = order._explode_bundle(qty=1.0)
        by_product = {c["product"].id: c["qty"] for c in comps}
        self.assertEqual(by_product.get(self.drone.id), 10.0)
        self.assertEqual(by_product.get(self.battery.id), 20.0)

    def test_explode_scales_with_qty(self):
        order = self._order(self.bundle, qty=3)
        by_product = {c["product"].id: c["qty"] for c in order._explode_bundle(qty=3.0)}
        self.assertEqual(by_product.get(self.drone.id), 30.0)

    def test_explode_without_bom_is_empty(self):
        self.assertEqual(self._order(self.plain)._explode_bundle(qty=1.0), [])

    # ------------------------------------------------------------------
    # Stock moves — the point of the whole module
    # ------------------------------------------------------------------
    def test_qty_one_bundle_moves_every_component(self):
        self._require_outgoing()
        order = self._order(self.bundle, qty=1)
        order.action_confirm()
        moves = order.pickup_picking_id.move_ids
        self.assertEqual(len(moves), 2)
        self.assertNotIn(self.bundle.id, moves.mapped("product_id").ids)
        qty_by_product = {m.product_id.id: m.product_uom_qty for m in moves}
        self.assertEqual(qty_by_product[self.drone.id], 10.0)
        self.assertEqual(qty_by_product[self.battery.id], 20.0)

    def test_loan_bundles_explode_and_are_flagged(self):
        self._require_outgoing()
        order = self._order(self.bundle, qty=1, loan_qty=2)
        order.action_confirm()
        moves = order.pickup_picking_id.move_ids
        loan = moves.filtered("is_loan")
        main = moves.filtered(lambda m: not m.is_loan)
        self.assertEqual(len(main), 2)
        self.assertEqual(len(loan), 2)
        # loan_qty counts bundles, so 2 spare bundles = 20 drones
        self.assertEqual(loan.filtered(lambda m: m.product_id == self.drone).product_uom_qty, 20.0)
        self.assertTrue(all(m.description_picking.startswith("[LOAN]") for m in loan))

    def test_product_without_bom_keeps_single_move(self):
        self._require_outgoing()
        order = self._order(self.plain, qty=7)
        order.action_confirm()
        moves = order.pickup_picking_id.move_ids
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves.product_id, self.plain)
        self.assertEqual(moves.product_uom_qty, 7.0)

    def test_return_picking_also_explodes(self):
        if not self.env["stock.picking.type"].search([("code", "=", "incoming")], limit=1):
            self.skipTest("no incoming picking type available")
        order = self._order(self.bundle, qty=1)
        order.action_confirm()
        order.action_pickup()
        order.action_return()
        moves = order.return_picking_id.move_ids
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves.filtered(lambda m: m.product_id == self.drone).product_uom_qty, 10.0)

    # ------------------------------------------------------------------
    # BAST
    # ------------------------------------------------------------------
    def test_bast_pickup_lists_components(self):
        order = self._order(self.bundle, qty=1)
        order.action_generate_bast_pickup()
        lines = order.bast_pickup_id.line_ids
        self.assertEqual(len(lines), 2)
        self.assertNotIn(self.bundle.id, lines.mapped("product_id").ids)
        qty_by_product = {line.product_id.id: line.qty for line in lines}
        self.assertEqual(qty_by_product[self.drone.id], 10.0)

    def test_bast_marks_loan_components(self):
        order = self._order(self.bundle, qty=1, loan_qty=1)
        order.action_generate_bast_pickup()
        loan_lines = order.bast_pickup_id.line_ids.filtered("is_loan")
        self.assertEqual(len(loan_lines), 2)
        self.assertTrue(all(line.item_description.startswith("[LOAN]") for line in loan_lines))

    def test_bast_without_bom_falls_back_to_bundle_line(self):
        order = self._order(self.plain, qty=4)
        order.action_generate_bast_pickup()
        lines = order.bast_pickup_id.line_ids
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.product_id, self.plain)
        self.assertEqual(lines.qty, 4.0)


@tagged("post_install", "-at_install")
class TestSerialCheckAcrossBundle(TransactionCase):
    """The serial reconciliation must follow the components, not the kit line.

    Regression guard: the check used to bail out whenever the *rented* product
    was not serial-tracked, which is exactly the case for a bundle — so a
    missing drone came back unnoticed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("custom_rental.config_stock_integration", "True")
        cls.partner = cls.env["res.partner"].create({"name": "Serial Organiser"})
        cls.drone = cls.env["product.product"].create(
            {"name": "Serial Drone", "type": "consu", "is_storable": True, "tracking": "serial"}
        )
        # Bundle itself carries no tracking — that is the whole point.
        cls.bundle = cls.env["product.product"].create(
            {"name": "Sewa Serial Show", "type": "consu", "is_storable": False}
        )
        cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.bundle.product_tmpl_id.id,
                "product_qty": 1.0,
                "type": "phantom",
                "bom_line_ids": [(0, 0, {"product_id": cls.drone.id, "product_qty": 2.0})],
            }
        )
        cls.lot_a, cls.lot_b, cls.lot_c = [
            cls.env["stock.lot"].create({"name": name, "product_id": cls.drone.id}) for name in ("SN-A", "SN-B", "SN-C")
        ]
        cls.now = datetime(2026, 9, 1, 9, 0)

    def _dispatched_order(self):
        order = self.env["rental.order"].create(
            {
                "partner_id": self.partner.id,
                "product_id": self.bundle.id,
                "qty": 1,
                "pickup_dt": self.now,
                "return_dt_expected": self.now + timedelta(days=2),
                "daily_rate": 100.0,
            }
        )
        order.action_confirm()
        order.action_pickup()
        order.action_return()
        return order

    def _add_lot(self, picking, lot):
        move = picking.move_ids.filtered(lambda m: m.product_id == self.drone)[:1]
        return self.env["stock.move.line"].create(
            {
                "picking_id": picking.id,
                "move_id": move.id,
                "product_id": self.drone.id,
                "lot_id": lot.id,
                "quantity": 1.0,
            }
        )

    def test_missing_component_serial_raises(self):
        for code in ("outgoing", "incoming"):
            if not self.env["stock.picking.type"].search([("code", "=", code)], limit=1):
                self.skipTest("no %s picking type available" % code)
        order = self._dispatched_order()
        self._add_lot(order.pickup_picking_id, self.lot_a)
        self._add_lot(order.pickup_picking_id, self.lot_b)
        # Only one of the two drones comes back.
        self._add_lot(order.return_picking_id, self.lot_a)
        with self.assertRaises(UserError):
            order._check_returned_serials()

    def test_matching_component_serials_pass(self):
        for code in ("outgoing", "incoming"):
            if not self.env["stock.picking.type"].search([("code", "=", code)], limit=1):
                self.skipTest("no %s picking type available" % code)
        order = self._dispatched_order()
        self._add_lot(order.pickup_picking_id, self.lot_a)
        self._add_lot(order.return_picking_id, self.lot_a)
        self.assertIsNone(order._check_returned_serials())
