# -*- coding: utf-8 -*-
"""WMS reporting pack tests: SQL views populate, spot-check sampling, PDF."""

from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "custom_wms_reports")
class TestWmsReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.stock_loc = cls.env.ref("stock.stock_location_stock")
        cls.supplier_loc = cls.env.ref("stock.stock_location_suppliers")
        cls.bin = cls.env["stock.location"].create(
            {"name": "BIN-RPT", "usage": "internal", "location_id": cls.stock_loc.id}
        )
        cls.partner = cls.env["res.partner"].create({"name": "RPT Vendor"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "RPT Widget",
                "type": "consu",
                "is_storable": True,
                "standard_price": 25.0,
                "default_code": "RPT-001",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.bin, 40.0)

    def _done_move(self, src, dest, qty, partner=False):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "internal"), ("warehouse_id", "=", self.warehouse.id)], limit=1
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "partner_id": partner and partner.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "product_uom": self.product.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "picking_id": picking.id,
            }
        )
        picking.action_confirm()
        move.quantity = qty
        move.picked = True
        picking.button_validate()
        return move

    def test_stock_summary_view(self):
        rows = self.env["custom.wms.stock.summary.report"].search(
            [("product_id", "=", self.product.id), ("location_id", "=", self.bin.id)]
        )
        self.assertTrue(rows, "stock summary view should expose the seeded quant")
        row = rows[0]
        self.assertEqual(row.quantity, 40.0)
        self.assertEqual(row.warehouse_id, self.warehouse)
        self.assertAlmostEqual(row.value, 40.0 * 25.0)

    def test_purchase_return_view(self):
        move = self._done_move(self.bin, self.supplier_loc, 5.0, partner=self.partner)
        row = self.env["custom.wms.purchase.return.report"].search([("id", "=", move.id)])
        self.assertTrue(row, "done move to a supplier location should appear as a return")
        self.assertEqual(row.quantity, 5.0)
        self.assertEqual(row.partner_id, self.partner)
        self.assertGreater(row.value, 0.0)

    def test_transfer_report_view(self):
        move = self._done_move(self.bin, self.stock_loc, 3.0)
        row = self.env["custom.wms.transfer.report"].search([("id", "=", move.id)])
        self.assertTrue(row)
        self.assertEqual(row.transfer_kind, "internal")
        self.assertEqual(row.done_qty, 3.0)

    def test_spot_check_sampling_and_report(self):
        plan = self.env["custom.cycle.count.plan"].create(
            {
                "name": "Spot Plan",
                "warehouse_id": self.warehouse.id,
                "frequency": "adhoc",
                "method": "spot_check",
                "target_count_per_period": 50,
            }
        )
        wiz = self.env["custom.cycle.count.start.wizard"].create({"plan_id": plan.id})
        res = wiz.action_start()
        session = self.env["custom.cycle.count.session"].browse(res["res_id"])
        self.assertTrue(session.line_ids, "spot check should seed at least one line")
        sample_cap = int(
            self.env["ir.config_parameter"].sudo().get_param("custom_wms_reports.spot_check_sample_size", 10)
        )
        self.assertLessEqual(len(session.line_ids), sample_cap)

        rows = self.env["custom.wms.stock.take.report"].search([("session_id", "=", session.id)])
        self.assertEqual(len(rows), len(session.line_ids))
        self.assertTrue(all(r.method == "spot_check" for r in rows))

    def test_stock_take_pdf_renders(self):
        plan = self.env["custom.cycle.count.plan"].create(
            {
                "name": "PDF Plan",
                "warehouse_id": self.warehouse.id,
                "frequency": "adhoc",
                "method": "random",
            }
        )
        wiz = self.env["custom.cycle.count.start.wizard"].create({"plan_id": plan.id})
        res = wiz.action_start()
        session = self.env["custom.cycle.count.session"].browse(res["res_id"])
        html = self.env["ir.actions.report"]._render_qweb_html(
            "custom_wms_reports.report_wms_stock_take", session.ids
        )[0]
        self.assertIn(b"STOCK TAKE REPORT", html)
        self.assertIn(b"<main>", html)
