# -*- coding: utf-8 -*-
"""GR extension tests: GS1 expiry/batch write-through + template import."""

from __future__ import annotations

import base64
import json

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "custom_wms_receiving_ext")
class TestReceivingExt(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.supplier_loc = cls.env.ref("stock.stock_location_suppliers")
        cls.stock_loc = cls.env.ref("stock.stock_location_stock")
        cls.partner = cls.env["res.partner"].create({"name": "GR Vendor"})
        cls.lot_product = cls.env["product.product"].create(
            {
                "name": "GR Lot Widget",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "use_expiration_date": True,
                "expiration_time": 365,
                "barcode": "1234567890128",
            }
        )
        cls.serial_product = cls.env["product.product"].create(
            {
                "name": "GR Serial Device",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "default_code": "GR-DEV-01",
            }
        )
        cls.receipt_type = cls.env["stock.picking.type"].search(
            [("code", "=", "incoming"), ("warehouse_id", "=", cls.warehouse.id)], limit=1
        )

    def _make_receipt(self, demands):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.receipt_type.id,
                "location_id": self.supplier_loc.id,
                "location_dest_id": self.stock_loc.id,
                "partner_id": self.partner.id,
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
        return picking

    def test_scan_apply_writes_expiry_and_batch(self):
        picking = self._make_receipt([(self.lot_product, 10)])
        session = self.env["custom.barcode.scan.session"].create({"picking_id": picking.id})
        self.env["custom.barcode.scan.line"].create(
            {
                "session_id": session.id,
                "product_id": self.lot_product.id,
                "raw_barcode": "0112345678901281 10BATCH-A1 17270115",
                "quantity": 5.0,
                "status": "ok",
                "supplier_batch_ref": "VND-77",
                "x_gs1_parsed": json.dumps(
                    {"gtin": "12345678901281", "lot": "BATCH-A1", "exp_date": "2027-01-15"}
                ),
            }
        )
        session.action_apply_to_picking()
        lot = self.env["stock.lot"].search(
            [("name", "=", "BATCH-A1"), ("product_id", "=", self.lot_product.id)]
        )
        self.assertTrue(lot, "apply should have created the lot")
        self.assertEqual(
            fields.Date.to_date(lot.expiration_date),
            fields.Date.to_date("2027-01-15"),
            "GS1 AI 17 must land on stock.lot.expiration_date",
        )
        self.assertEqual(lot.supplier_batch_ref, "VND-77")

    def test_import_csv_lot_and_serial(self):
        picking = self._make_receipt([(self.lot_product, 10), (self.serial_product, 2)])
        csv_content = (
            "barcode,serial,lot,qty,expiry,supplier_batch\r\n"
            "1234567890128,,LOT-CSV-1,4,15/01/2027,SUP-B9\r\n"
            "GR-DEV-01,SN-0001,,1,,\r\n"
            "GR-DEV-01,SN-0002,,1,,\r\n"
        )
        wiz = self.env["custom.wms.receipt.import.wizard"].create(
            {
                "picking_id": picking.id,
                "data_file": base64.b64encode(csv_content.encode()),
                "data_file_name": "template.csv",
            }
        )
        wiz.action_import()

        lot = self.env["stock.lot"].search(
            [("name", "=", "LOT-CSV-1"), ("product_id", "=", self.lot_product.id)]
        )
        self.assertTrue(lot)
        self.assertEqual(fields.Date.to_date(lot.expiration_date), fields.Date.to_date("2027-01-15"))
        self.assertEqual(lot.supplier_batch_ref, "SUP-B9")

        lot_ml = picking.move_line_ids.filtered(lambda l: l.lot_id == lot)
        self.assertEqual(len(lot_ml), 1)
        self.assertEqual(lot_ml.quantity, 4.0)

        serials = self.env["stock.lot"].search(
            [("product_id", "=", self.serial_product.id), ("name", "like", "SN-000%")]
        )
        self.assertEqual(len(serials), 2, "one serial lot per row")
        serial_mls = picking.move_line_ids.filtered(lambda l: l.product_id == self.serial_product and l.lot_id)
        self.assertEqual(len(serial_mls), 2)
        self.assertTrue(all(ml.quantity == 1.0 for ml in serial_mls))

    def test_import_rejects_bad_rows(self):
        picking = self._make_receipt([(self.lot_product, 10)])
        csv_content = (
            "barcode,serial,lot,qty,expiry,supplier_batch\r\n"
            "NO-SUCH-BARCODE,,L1,1,,\r\n"
            "1234567890128,,,3,,\r\n"
        )
        wiz = self.env["custom.wms.receipt.import.wizard"].create(
            {
                "picking_id": picking.id,
                "data_file": base64.b64encode(csv_content.encode()),
                "data_file_name": "bad.csv",
            }
        )
        with self.assertRaises(UserError) as err:
            wiz.action_import()
        message = str(err.exception)
        self.assertIn("NO-SUCH-BARCODE", message)
        self.assertIn("serial/lot is required", message)
        self.assertFalse(
            self.env["stock.lot"].search([("name", "=", "L1")]),
            "all-or-nothing: no lot may be created when any row fails",
        )
