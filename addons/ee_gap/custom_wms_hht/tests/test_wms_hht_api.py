# -*- coding: utf-8 -*-
"""WMS handheld API tests.

The controller methods are called directly (with a faked `request`) rather
than over HTTP: what needs proving is that each endpoint drives the real WMS
models correctly, not that Odoo can route a URL.
"""

from __future__ import annotations

import contextlib
from unittest.mock import patch

import odoo.http

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.custom_wms_hht.controllers import wms_api


class _FakeRequest:
    """Only what the controller touches: env + params."""

    def __init__(self, env, params=None):
        self.env = env
        self.params = params or {}


@tagged("post_install", "-at_install", "custom_wms_hht")
class TestWmsHhtApi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.supplier_loc = cls.env.ref("stock.stock_location_suppliers")
        cls.customer_loc = cls.env.ref("stock.stock_location_customers")
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.partner = cls.env["res.partner"].create({"name": "HHT Vendor"})
        cls.bin_a = cls.env["stock.location"].create(
            {
                "name": "HHT-A-01",
                "usage": "internal",
                "location_id": cls.stock_loc.id,
                "barcode": "HHT-A-01",
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "HHT Widget",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "barcode": "5901234123457",
                "default_code": "HHT-W1",
            }
        )
        cls.plain = cls.env["product.product"].create(
            {
                "name": "HHT Plain",
                "type": "consu",
                "is_storable": True,
                "barcode": "4006381333931",
                "default_code": "HHT-P1",
            }
        )
        cls.controller = wms_api.WmsHhtApi()

    # -- helpers -------------------------------------------------------

    @contextlib.contextmanager
    def _patch_request(self, params=None):
        """Fake the request in the controller AND in odoo.http.

        `_()` resolves the language through `odoo.http.request` first; with
        that left as None it falls through to frame inspection and dies on
        `NoneType.uid` inside a controller frame, turning every business
        error into an INTERNAL one.
        """
        fake = _FakeRequest(self.env, params)
        with patch.object(wms_api, "request", fake), patch.object(odoo.http, "request", fake):
            yield fake

    def _receipt(self, demands):
        ptype = self.env["stock.picking.type"].search(
            [("code", "=", "incoming"), ("warehouse_id", "=", self.warehouse.id)], limit=1
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": ptype.id,
                "partner_id": self.partner.id,
                "location_id": self.supplier_loc.id,
                "location_dest_id": self.stock_loc.id,
            }
        )
        for product, qty in demands:
            self.env["stock.move"].create(
                {
                    "product_id": product.id,
                    "product_uom_qty": qty,
                    "product_uom": product.uom_id.id,
                    "location_id": self.supplier_loc.id,
                    "location_dest_id": self.stock_loc.id,
                    "picking_id": picking.id,
                }
            )
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _delivery(self, product, qty):
        self.env["stock.quant"]._update_available_quantity(product, self.bin_a, qty)
        ptype = self.env["stock.picking.type"].search(
            [("code", "=", "outgoing"), ("warehouse_id", "=", self.warehouse.id)], limit=1
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": ptype.id,
                "partner_id": self.partner.id,
                "location_id": self.stock_loc.id,
                "location_dest_id": self.customer_loc.id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": self.stock_loc.id,
                "location_dest_id": self.customer_loc.id,
                "picking_id": picking.id,
            }
        )
        picking.action_confirm()
        picking.action_assign()
        return picking

    # -- queue / scan --------------------------------------------------

    def test_queue_counts_open_work(self):
        self._receipt([(self.plain, 5)])
        with self._patch_request():
            res = self.controller.queue()
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res["queue"]["receive"], 1)
        self.assertIn("pick", res["queue"])

    def test_scan_resolve_distinguishes_bin_from_product(self):
        with self._patch_request():
            loc = self.controller.scan_resolve(barcode="HHT-A-01")
            prod = self.controller.scan_resolve(barcode="4006381333931")
            miss = self.controller.scan_resolve(barcode="NOPE-999")
        self.assertEqual(loc["kind"], "location")
        self.assertEqual(prod["kind"], "product")
        self.assertEqual(prod["record"]["default_code"], "HHT-P1")
        self.assertFalse(miss["ok"])
        self.assertEqual(miss["error_code"], "NOT_FOUND")

    def test_scan_resolve_expect_rejects_wrong_kind(self):
        """A product scanned into a 'scan the bin' prompt must not resolve."""
        with self._patch_request():
            res = self.controller.scan_resolve(barcode="4006381333931", expect="location")
        self.assertFalse(res["ok"])

    def test_scan_resolve_reads_gs1(self):
        with self._patch_request():
            res = self.controller.scan_resolve(barcode="0105901234123457" + "10LOT-9")
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(res["kind"], "product")
        self.assertEqual(res["gs1"].get("lot"), "LOT-9")

    # -- receiving -----------------------------------------------------

    def test_receive_scan_sets_quantity_and_validates(self):
        picking = self._receipt([(self.plain, 6)])
        with self._patch_request():
            res = self.controller.receive_scan(
                picking_id=picking.id, barcode="4006381333931", quantity=6
            )
            self.assertTrue(res["ok"], res.get("error"))
            self.assertEqual(sum(picking.move_line_ids.mapped("quantity")), 6.0)
            done = self.controller.receive_validate(picking_id=picking.id)
        self.assertTrue(done["ok"], done.get("error"))
        self.assertEqual(picking.state, "done")

    def test_receive_scan_reports_unknown_barcode_without_leaving_a_line(self):
        picking = self._receipt([(self.plain, 1)])
        with self._patch_request():
            res = self.controller.receive_scan(picking_id=picking.id, barcode="GHOST-1")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error_code"], "NOT_FOUND")
        session = self.env["custom.barcode.scan.session"].search([("picking_id", "=", picking.id)])
        self.assertFalse(session.line_ids, "a rejected scan must not leave a dangling line")

    # -- putaway -------------------------------------------------------

    def test_putaway_apply_moves_destination_to_scanned_bin(self):
        picking = self._receipt([(self.plain, 4)])
        ml = picking.move_line_ids[:1]
        with self._patch_request():
            res = self.controller.putaway_apply(move_line_id=ml.id, barcode="HHT-A-01")
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(ml.location_dest_id, self.bin_a)

    def test_putaway_apply_rejects_unknown_bin(self):
        picking = self._receipt([(self.plain, 4)])
        ml = picking.move_line_ids[:1]
        with self._patch_request():
            res = self.controller.putaway_apply(move_line_id=ml.id, barcode="NO-SUCH-BIN")
        self.assertFalse(res["ok"])

    def test_putaway_suggest_returns_ranked_bins(self):
        picking = self._receipt([(self.plain, 4)])
        with self._patch_request():
            res = self.controller.putaway_suggest(picking_id=picking.id)
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(len(res["rows"]), len(picking.move_line_ids))
        self.assertIn("proposals", res["rows"][0])

    # -- picking -------------------------------------------------------

    def test_pick_confirm_rejects_the_wrong_item(self):
        picking = self._delivery(self.plain, 3)
        ml = picking.move_line_ids[:1]
        with self._patch_request():
            res = self.controller.pick_confirm(move_line_id=ml.id, barcode="5901234123457")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error_code"], "MISMATCH")
        self.assertEqual(ml.quantity, 3.0, "a rejected scan must not change the line")

    def test_pick_confirm_then_validate(self):
        picking = self._delivery(self.plain, 3)
        ml = picking.move_line_ids[:1]
        with self._patch_request():
            ok = self.controller.pick_confirm(move_line_id=ml.id, barcode="4006381333931", quantity=3)
            self.assertTrue(ok["ok"], ok.get("error"))
            res = self.controller.pick_validate(picking_id=picking.id)
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(picking.state, "done")

    def test_pick_pack_creates_a_package_with_contents(self):
        picking = self._delivery(self.plain, 3)
        ml = picking.move_line_ids[:1]
        with self._patch_request():
            self.controller.pick_confirm(move_line_id=ml.id, quantity=3)
            res = self.controller.pick_pack(picking_id=picking.id)
        self.assertTrue(res["ok"], res.get("error"))
        self.assertTrue(res["package"], "put in pack must return the package")
        self.assertTrue(ml.result_package_id)

    # -- package -------------------------------------------------------

    def test_package_lookup_by_barcode(self):
        pack = self.env["stock.package"].create({"name": "HHT-PACK-1"})
        with self._patch_request():
            res = self.controller.package(barcode="HHT-PACK-1")
            missing = self.controller.package(barcode="HHT-PACK-NOPE")
        self.assertTrue(res["ok"])
        self.assertEqual(res["package"]["name"], pack.name)
        self.assertFalse(missing["ok"])

    # -- transfer orders / counting ------------------------------------
    #
    # These call the *list* endpoints against populated data on purpose: the
    # first version of bin2bin_list read `to.picking_id`, a field that does
    # not exist on custom.transfer.order, and no test noticed because the
    # fixture had no transfer order to serialise.

    def _transfer_order(self):
        bin_b = self.env["stock.location"].create(
            {
                "name": "HHT-B-01",
                "usage": "internal",
                "location_id": self.stock_loc.id,
                "barcode": "HHT-B-01",
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.plain, self.bin_a, 10)
        move = self.env["custom.to.engine"].materialize(
            {
                "source_location_id": self.bin_a.id,
                "target_location_id": bin_b.id,
                "product_id": self.plain.id,
                "planned_qty": 4.0,
                "company_id": self.env.company.id,
            }
        )
        return self.env["custom.transfer.order"].search(
            [("stock_move_id", "=", move.id)], limit=1
        ), bin_b

    def test_bin2bin_list_serialises_a_real_order(self):
        order, _bin_b = self._transfer_order()
        with self._patch_request():
            res = self.controller.bin2bin_list()
        self.assertTrue(res["ok"], res.get("error"))
        names = [o["name"] for o in res["orders"]]
        self.assertIn(order.name, names)

    def test_bin2bin_execute_moves_the_stock(self):
        order, bin_b = self._transfer_order()
        with self._patch_request():
            res = self.controller.bin2bin_execute(
                transfer_order_id=order.id,
                source_barcode="HHT-A-01",
                target_barcode="HHT-B-01",
            )
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(order.stock_move_id.state, "done")
        moved = self.env["stock.quant"]._get_available_quantity(self.plain, bin_b)
        self.assertEqual(moved, 4.0)

    def test_bin2bin_execute_rejects_the_wrong_bin(self):
        order, _bin_b = self._transfer_order()
        with self._patch_request():
            res = self.controller.bin2bin_execute(
                transfer_order_id=order.id, source_barcode="HHT-B-01"
            )
        self.assertFalse(res["ok"])
        self.assertEqual(res["error_code"], "MISMATCH")
        self.assertNotEqual(order.stock_move_id.state, "done")

    def _count_session(self):
        self.env["stock.quant"]._update_available_quantity(self.plain, self.bin_a, 7)
        plan = self.env["custom.cycle.count.plan"].create(
            {
                "name": "HHT Count Plan",
                "warehouse_id": self.warehouse.id,
                "method": "random",
                "company_id": self.env.company.id,
            }
        )
        wiz = self.env["custom.cycle.count.start.wizard"].create(
            {"plan_id": plan.id, "target_count": 5}
        )
        action = wiz.action_start()
        return self.env["custom.cycle.count.session"].browse(action["res_id"])

    def test_count_lines_and_submit(self):
        session = self._count_session()
        with self._patch_request():
            listed = self.controller.count_sessions()
            lines = self.controller.count_lines(session_id=session.id)
            self.assertTrue(lines["ok"], lines.get("error"))
            self.assertTrue(lines["lines"], "the session should expose its lines")
            line = lines["lines"][0]
            res = self.controller.count_submit(line_id=line["id"], quantity=line["expected_qty"] - 1)
        self.assertTrue(listed["ok"])
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(res["line"]["variance_qty"], -1.0)

    def test_every_list_endpoint_answers_ok(self):
        """Smoke: each screen's first call must not blow up on real data."""
        self._transfer_order()
        self._count_session()
        self._receipt([(self.plain, 2)])
        self._delivery(self.plain, 1)
        with self._patch_request():
            results = {
                "queue": self.controller.queue(),
                "warehouses": self.controller.warehouses(),
                "incoming": self.controller.pickings(code="incoming"),
                "internal": self.controller.pickings(code="internal"),
                "outgoing": self.controller.pickings(code="outgoing"),
                "bin2bin": self.controller.bin2bin_list(),
                "count": self.controller.count_sessions(),
            }
        broken = {k: v.get("error") for k, v in results.items() if not v["ok"]}
        self.assertFalse(broken, f"list endpoints failing: {broken}")

    # -- errors --------------------------------------------------------

    def test_business_error_is_json_not_a_traceback(self):
        """A UserError from the model must reach the handheld as {ok: false}."""
        picking = self._receipt([(self.plain, 5)])
        with self._patch_request():
            # Nothing scanned yet: validating an untouched receipt raises.
            res = self.controller.qc(picking_id=picking.id, verdict="pass")
        self.assertFalse(res["ok"])
        self.assertIn(res["error_code"], ("BUSINESS", "ACCESS", "INTERNAL"))
