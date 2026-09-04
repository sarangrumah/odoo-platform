# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAssetStockLink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.inventory_valuation = "periodic"

        # Multi-location and internal transfers are off in a bare database.
        cls.env.ref("stock.group_stock_multi_locations").sudo().write({"user_ids": [(4, cls.env.user.id)]})
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.internal_type = cls.warehouse.int_type_id
        cls.internal_type.active = True
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.other_loc = cls.env["stock.location"].create(
            {
                "name": "Site Palem",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
            }
        )

        cls.asset_loc = cls.env["custom.fixed.asset.location"].create(
            {"name": "RUKO GUDANG PALEM", "stock_location_id": cls.stock_loc.id}
        )
        cls.asset_account = cls._account("ASL100", "FA - Drones", "asset_fixed")
        cls.accum_account = cls._account("ASL190", "FA - Accum", "asset_fixed")
        cls.expense_account = cls._account("ASL610", "Depreciation", "expense")
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1
        ) or cls.env["account.journal"].create(
            {
                "name": "Asset Depreciation",
                "code": "ASTD",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        # Distinct from any real register group -- the group code is unique per
        # company, and these tests run against live tenant databases too.
        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "Device (asset-stock test)",
                "code": "ASL-TEST-DEVICE",
                "default_useful_life_months": 48,
                "default_asset_account_id": cls.asset_account.id,
                "default_depreciation_account_id": cls.accum_account.id,
                "default_expense_account_id": cls.expense_account.id,
                "default_journal_id": cls.journal.id,
            }
        )
        cls.assets = cls.env["custom.fixed.asset"].create(
            [
                {
                    "code": "ASL-TEST-%s" % i,
                    "name": "Damoda Drone DMD (asset-stock test)",
                    "group_id": cls.group.id,
                    "location_id": cls.asset_loc.id,
                    "acquisition_date": date(2025, 1, 30),
                    "acquisition_value": 15094132.0,
                    "useful_life_months": 48,
                    "asset_account_id": cls.asset_account.id,
                    "depreciation_account_id": cls.accum_account.id,
                    "expense_account_id": cls.expense_account.id,
                    "journal_id": cls.journal.id,
                }
                for i in range(3)
            ]
        )

    @classmethod
    def _account(cls, code, name, account_type):
        Account = cls.env["account.account"]
        return Account.search([("code", "=", code), ("company_ids", "in", cls.company.id)], limit=1) or Account.create(
            {
                "name": name,
                "code": code,
                "account_type": account_type,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

    def _wizard(self, assets=None, **kwargs):
        vals = {"asset_ids": [(6, 0, (assets or self.assets).ids)]}
        vals.update(kwargs)
        return self.env["custom.asset.stock.materialize.wizard"].create(vals)

    # ------------------------------------------------------------------
    # Materialisation
    # ------------------------------------------------------------------
    def test_materialise_creates_serial_and_stock(self):
        self._wizard().action_confirm()
        for asset in self.assets:
            self.assertTrue(asset.lot_id, "every asset gets a serial")
            self.assertEqual(asset.lot_id.name, asset.code)
            self.assertEqual(asset.stock_location_id, self.stock_loc)
            self.assertEqual(asset.stock_state, "in_stock")
            self.assertEqual(asset.stock_qty, 1.0)
        # one product for the three identically-named units
        self.assertEqual(len(self.assets.product_id), 1)
        self.assertEqual(self.assets.product_id.tracking, "serial")
        self.assertEqual(self.assets.product_id.standard_price, 0.0)

    def test_materialise_posts_no_journal_entry(self):
        before = self.env["account.move"].search_count([])
        self._wizard().action_confirm()
        self.assertEqual(
            self.env["account.move"].search_count([]),
            before,
            "materialising already-capitalised assets must not touch the ledger",
        )

    def test_materialise_is_idempotent(self):
        self._wizard().action_confirm()
        lots = self.assets.lot_id
        quants_before = self.env["stock.quant"].search_count([("lot_id", "in", lots.ids)])
        with self.assertRaises(UserError):
            self._wizard().action_confirm()
        self.assertEqual(self.assets.lot_id, lots)
        self.assertEqual(
            self.env["stock.quant"].search_count([("lot_id", "in", lots.ids)]),
            quants_before,
        )

    def test_partial_batch_skips_already_linked(self):
        self._wizard(assets=self.assets[:1]).action_confirm()
        self._wizard().action_confirm()
        self.assertEqual(len(self.assets.filtered("lot_id")), 3)
        self.assertEqual(len(set(self.assets.mapped("lot_id.id"))), 3)

    def test_missing_location_is_refused(self):
        self.asset_loc.stock_location_id = False
        with self.assertRaises(UserError):
            self._wizard().action_confirm()

    # ------------------------------------------------------------------
    # Zero-valuation guard
    # ------------------------------------------------------------------
    def test_guard_refuses_real_time_category(self):
        wizard = self._wizard()
        wizard.categ_id = self.env["product.category"].create({"name": "Valued"})
        wizard.categ_id.with_company(self.company).property_valuation = "real_time"
        # _ensure_category_valuation resets it, so assert on the guard directly
        with self.assertRaises(UserError):
            wizard._assert_zero_valuation(
                self.company,
                wizard.categ_id,
                self.env["stock.location"],
                self.env["product.product"],
            )

    def test_guard_refuses_nonzero_cost_product(self):
        wizard = self._wizard()
        product = self.env["product.product"].create(
            {
                "name": "Priced Drone",
                "type": "consu",
                "is_storable": True,
                "categ_id": wizard.categ_id.id,
                "standard_price": 1500.0,
            }
        )
        with self.assertRaises(UserError):
            wizard._assert_zero_valuation(self.company, wizard.categ_id, self.env["stock.location"], product)

    def test_guard_refuses_location_with_valuation_account(self):
        wizard = self._wizard()
        self.other_loc.valuation_account_id = self.asset_account.id
        with self.assertRaises(UserError):
            wizard._assert_zero_valuation(
                self.company,
                wizard.categ_id,
                self.other_loc,
                self.env["product.product"],
            )

    # ------------------------------------------------------------------
    # Movement tracking
    # ------------------------------------------------------------------
    def _transfer(self, asset, destination, skip_sync=False):
        """Move the asset's serial from wherever it is to ``destination``."""
        source = asset.stock_location_id
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.internal_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": asset.product_id.id,
                            "product_uom_qty": 1.0,
                            "location_id": source.id,
                            "location_dest_id": destination.id,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.move_ids.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            {
                "move_id": picking.move_ids.id,
                "picking_id": picking.id,
                "product_id": asset.product_id.id,
                "product_uom_id": asset.product_id.uom_id.id,
                "lot_id": asset.lot_id.id,
                "quantity": 1.0,
                "location_id": source.id,
                "location_dest_id": destination.id,
            }
        )
        picking.with_context(skip_asset_stock_sync=skip_sync).button_validate()
        return picking

    def test_internal_transfer_moves_asset_but_not_accounting_location(self):
        self._wizard().action_confirm()
        asset = self.assets[0]
        self._transfer(asset, self.other_loc)

        self.assertEqual(asset.stock_location_id, self.other_loc)
        self.assertEqual(asset.stock_state, "in_stock")
        self.assertEqual(
            asset.location_id,
            self.asset_loc,
            "the accounting asset location is Finance's field and must not move",
        )
        self.assertEqual(asset.move_line_count, 2, "the seeding adjustment plus the transfer")

    def test_resync_recovers_position_changed_behind_our_back(self):
        self._wizard().action_confirm()
        asset = self.assets[0]
        # A move validated with the sync suppressed stands in for the real
        # cases the cron exists for: SQL fixes, restores, bulk loads.
        self._transfer(asset, self.other_loc, skip_sync=True)
        self.assertEqual(asset.stock_location_id, self.stock_loc, "stale until resynced")
        asset.action_resync_stock_location()
        self.assertEqual(asset.stock_location_id, self.other_loc)

    def test_cron_syncs_stale_positions(self):
        self._wizard().action_confirm()
        asset = self.assets[0]
        self._transfer(asset, self.other_loc, skip_sync=True)
        self.env["custom.fixed.asset"]._cron_sync_stock_locations()
        self.assertEqual(asset.stock_location_id, self.other_loc)

    # ------------------------------------------------------------------
    # Rental availability
    # ------------------------------------------------------------------
    def test_rental_units_created_and_available(self):
        self._wizard().action_confirm()
        self.assets.action_confirm()
        for asset in self.assets:
            self.assertTrue(asset.rental_asset_id)
            self.assertEqual(asset.rental_asset_id.state, "available")
            self.assertTrue(asset.is_rentable)
            self.assertTrue(asset.rental_asset_id.is_available_now)
            self.assertEqual(asset.rental_asset_id.lot_id, asset.lot_id)

    def test_draft_asset_is_not_rentable(self):
        self._wizard().action_confirm()
        self.assertFalse(self.assets[0].is_rentable, "a draft asset is not on the rental floor")

    def test_no_rental_units_when_unticked(self):
        self._wizard(create_rental_asset=False).action_confirm()
        self.assertFalse(self.assets.rental_asset_ids)
        self.assertFalse(self.assets.product_id.auto_create_rental_asset)

    def _loan_order(self, asset):
        self.env["ir.config_parameter"].sudo().set_param("custom_rental.config_stock_integration", "True")
        now = datetime(2026, 6, 1, 9, 0)
        return self.env["rental.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Show Client"}).id,
                "asset_id": asset.rental_asset_id.id,
                "pickup_dt": now,
                "return_dt_expected": now + timedelta(days=2),
                "daily_rate": 100.0,
                "is_internal_loan": True,
                "on_loan_location_id": self.other_loc.id,
            }
        )

    def test_rental_pickup_assigns_the_units_serial(self):
        self._wizard().action_confirm()
        self.assets.action_confirm()
        asset = self.assets[0]
        order = self._loan_order(asset)
        order.action_confirm()
        picking = order.pickup_picking_id
        self.assertTrue(picking, "stock integration produces a pickup picking")
        self.assertEqual(
            picking.move_ids.move_line_ids.lot_id,
            asset.lot_id,
            "the drone's own serial is pre-assigned, so the picking can be validated",
        )
        self.assertEqual(
            picking.location_id,
            self.stock_loc,
            "the loan ships from where the unit actually is, not the warehouse dock",
        )
        self.assertEqual(picking.location_dest_id, self.other_loc)
        self.assertEqual(picking.picking_type_id, self.internal_type)

    def test_rental_loan_round_trip_moves_the_unit_and_posts_nothing(self):
        self._wizard().action_confirm()
        self.assets.action_confirm()
        asset = self.assets[0]
        moves_before = self.env["account.move"].search_count([])

        order = self._loan_order(asset)
        order.action_confirm()
        order.pickup_picking_id.button_validate()
        order.action_pickup()
        self.assertEqual(asset.stock_location_id, self.other_loc)
        self.assertEqual(asset.rental_state, "on_rent")
        self.assertFalse(asset.is_rentable)

        order.action_return()
        order.return_picking_id.button_validate()
        self.assertEqual(asset.stock_location_id, self.stock_loc, "the unit comes home")
        self.assertEqual(asset.rental_state, "available")
        self.assertTrue(asset.is_rentable)

        self.assertEqual(
            self.env["account.move"].search_count([]),
            moves_before,
            "renting out an already-capitalised asset posts no inventory entry",
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def test_search_by_physical_location(self):
        self._wizard().action_confirm()
        Asset = self.env["custom.fixed.asset"]
        found = Asset.search([("stock_location_id", "=", self.stock_loc.id)])
        self.assertEqual(found & self.assets, self.assets)
        self.assertFalse(Asset.search([("stock_location_id", "=", self.other_loc.id)]) & self.assets)
