# -*- coding: utf-8 -*-
"""Putaway engine tests."""

from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "custom_wms_putaway")
class TestPutaway(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.stock_loc = cls.env.ref("stock.stock_location_stock")
        # Two internal sub-locations
        cls.loc_a = cls.env["stock.location"].create(
            {
                "name": "BIN-A",
                "usage": "internal",
                "location_id": cls.stock_loc.id,
                "volume_capacity_m3": 10.0,
            }
        )
        cls.loc_b = cls.env["stock.location"].create(
            {
                "name": "BIN-B",
                "usage": "internal",
                "location_id": cls.stock_loc.id,
                "volume_capacity_m3": 0.001,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Widget",
                "type": "consu",
                "is_storable": True,
                "volume": 0.5,
                "abc_class": "A",
            }
        )
        cls.strategy = cls.env["custom.wms.putaway.strategy"].create(
            {
                "name": "Test Strategy",
                "warehouse_id": cls.warehouse.id,
                "rule_set": "custom",
            }
        )

    def _make_move_line(self, qty=2.0):
        picking_type = self.warehouse.in_type_id
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.stock_loc.id,
            }
        )
        ml = self.env["stock.move.line"].create(
            {
                "picking_id": picking.id,
                "product_id": self.product.id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.stock_loc.id,
                "quantity": qty,
            }
        )
        return ml

    def test_fixed_location_strategy(self):
        rule = self.env["custom.wms.putaway.rule"].create(
            {
                "name": "fixed",
                "strategy_id": self.strategy.id,
                "kind": "fixed_location",
                "target_location_id": self.loc_a.id,
                "tier": 1,
            }
        )
        engine = self.env["custom.putaway.engine"]
        score, reason = engine._score_rule(rule, self._make_move_line())
        self.assertEqual(score, 100)
        self.assertIn("Fixed", reason)

    def test_nearest_empty_strategy(self):
        rule = self.env["custom.wms.putaway.rule"].create(
            {
                "name": "near-empty",
                "strategy_id": self.strategy.id,
                "kind": "nearest_empty",
                "target_location_domain": "[('id','in',[%d,%d])]" % (self.loc_a.id, self.loc_b.id),
                "tier": 1,
            }
        )
        engine = self.env["custom.putaway.engine"]
        score, _r = engine._score_rule(rule, self._make_move_line())
        self.assertGreater(score, 0)

    def test_by_volume_rejects_oversized(self):
        rule = self.env["custom.wms.putaway.rule"].create(
            {
                "name": "vol",
                "strategy_id": self.strategy.id,
                "kind": "by_volume",
                "target_location_id": self.loc_b.id,
                "tier": 1,
            }
        )
        engine = self.env["custom.putaway.engine"]
        score, reason = engine._score_rule(rule, self._make_move_line(qty=5.0))
        self.assertEqual(score, 0)
        self.assertIn("Oversized", reason)

    def test_by_abc_velocity_a_places_near_dock(self):
        rule = self.env["custom.wms.putaway.rule"].create(
            {
                "name": "abc",
                "strategy_id": self.strategy.id,
                "kind": "by_abc_velocity",
                "abc_class": "A",
                "target_location_id": self.loc_a.id,
                "tier": 1,
            }
        )
        engine = self.env["custom.putaway.engine"]
        score, _r = engine._score_rule(rule, self._make_move_line())
        self.assertGreaterEqual(score, 90)

    def test_custom_python_safe_eval_rejects_unsafe(self):
        rule = self.env["custom.wms.putaway.rule"].create(
            {
                "name": "unsafe",
                "strategy_id": self.strategy.id,
                "kind": "custom_python",
                "custom_python": "__import__('os').system('echo pwned')",
                "tier": 1,
            }
        )
        engine = self.env["custom.putaway.engine"]
        score, reason = engine._score_rule(rule, self._make_move_line())
        self.assertEqual(score, 0)
        self.assertTrue("unsafe" in reason or "rejected" in reason or reason == "")

    def test_custom_python_valid_returns_score(self):
        rule = self.env["custom.wms.putaway.rule"].create(
            {
                "name": "valid-py",
                "strategy_id": self.strategy.id,
                "kind": "custom_python",
                "custom_python": "(False, 50)",
                "tier": 1,
            }
        )
        engine = self.env["custom.putaway.engine"]
        score, _r = engine._score_rule(rule, self._make_move_line())
        self.assertEqual(score, 50)
