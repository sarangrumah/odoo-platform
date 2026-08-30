# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPooledAssetConversion(TransactionCase):
    """5 waste bins received on one line become ONE asset carrying quantity 5."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env["account.account"]
        cls.asset_account = Account.create(
            {
                "name": "FA - Equipment (conv)",
                "code": "150120",
                "account_type": "asset_fixed",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.accum_account = Account.create(
            {
                "name": "FA - Accum. Depreciation (conv)",
                "code": "150920",
                "account_type": "asset_fixed",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.expense_account = Account.create(
            {
                "name": "Depreciation Expense (conv)",
                "code": "610120",
                "account_type": "expense",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        Journal = cls.env["account.journal"]
        cls.journal = Journal.search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1
        ) or Journal.create({"name": "Misc", "code": "MISCC", "type": "general", "company_id": cls.company.id})
        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "Bins (conv)",
                "code": "BINC",
                "default_useful_life_months": 10,
                "default_asset_account_id": cls.asset_account.id,
                "default_depreciation_account_id": cls.accum_account.id,
                "default_expense_account_id": cls.expense_account.id,
                "default_journal_id": cls.journal.id,
            }
        )
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.product = cls.env["product.product"].create(
            {
                "name": "Waste bin 60L",
                "is_storable": True,
                "standard_price": 1000.0,
                "is_fixed_asset": True,
                "asset_tracking_mode": "quantity",
                "asset_group_id": cls.group.id,
            }
        )

    def _receive(self, quantity=5.0):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.in_type_id.id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            # Odoo 19 dropped stock.move.name.
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": self.env.ref("stock.stock_location_suppliers").id,
                            "location_dest_id": self.warehouse.lot_stock_id.id,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = quantity
            move.picked = True
        picking.button_validate()
        return picking

    def test_01_untracked_product_is_allowed_in_pooled_mode(self):
        # The per-serial mode demands lot/serial tracking; the pooled one does not.
        self.assertEqual(self.product.product_tmpl_id._asset_conversion_mode(), "quantity")
        self.assertEqual(self.product.tracking, "none")

    def test_02_receipt_converts_to_one_pooled_asset(self):
        picking = self._receive(5.0)
        self.assertTrue(picking.has_rental_asset_lines)
        wizard = self.env["custom.asset.conversion.wizard"].create({"picking_id": picking.id})
        wizard._populate_lines()
        self.assertEqual(len(wizard.line_ids), 1)
        line = wizard.line_ids
        self.assertEqual(line.conversion_mode, "quantity")
        self.assertFalse(line.lot_id)
        self.assertAlmostEqual(line.quantity, 5.0, places=2)
        self.assertAlmostEqual(line.unit_cost, 1000.0, places=2)
        self.assertAlmostEqual(line.subtotal, 5000.0, places=2)

        wizard.action_confirm()
        assets = self.env["custom.fixed.asset"].search([("picking_id", "=", picking.id)])
        self.assertEqual(len(assets), 1)
        self.assertAlmostEqual(assets.quantity, 5.0, places=2)
        self.assertAlmostEqual(assets.original_quantity, 5.0, places=2)
        self.assertAlmostEqual(assets.acquisition_value, 5000.0, places=2)
        self.assertAlmostEqual(assets.unit_acquisition_value, 1000.0, places=2)
        self.assertTrue(assets.is_quantity_asset)
        self.assertFalse(assets.rental_asset_ids)

    def test_03_conversion_is_idempotent(self):
        picking = self._receive(5.0)
        wizard = self.env["custom.asset.conversion.wizard"].create({"picking_id": picking.id})
        wizard._populate_lines()
        wizard.action_confirm()

        again = self.env["custom.asset.conversion.wizard"].create({"picking_id": picking.id})
        again._populate_lines()
        self.assertTrue(again.line_ids.existing_asset_id)
        self.assertFalse(again.line_ids.selected)
        # And a full retirement round-trip still leaves exactly one asset.
        self.assertEqual(len(self.env["custom.fixed.asset"].search([("picking_id", "=", picking.id)])), 1)
