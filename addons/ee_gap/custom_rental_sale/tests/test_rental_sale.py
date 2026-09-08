# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRentalSaleBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.group_ids |= cls.env.ref("custom_accounting_asset.group_asset_manager")

        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.home = cls.warehouse.lot_stock_id
        view = cls.warehouse.view_location_id
        cls.on_deployment = cls.env["stock.location"].create(
            {"name": "On Deployment Test", "usage": "internal", "location_id": view.id}
        )
        cls.damage_loc = cls.env["stock.location"].create(
            {"name": "Damage Test RS", "usage": "internal", "location_id": view.id}
        )
        cls.missing_loc = cls.env["stock.location"].create(
            {"name": "Missing Test RS", "usage": "internal", "location_id": view.id}
        )
        cls.company.write(
            {
                "deployment_location_id": cls.on_deployment.id,
                "deployment_source_location_id": cls.home.id,
                "asset_damage_location_id": cls.damage_loc.id,
                "asset_missing_location_id": cls.missing_loc.id,
            }
        )

        chart = cls.env["account.account"]
        cls.acc_asset = chart.create({"name": "RS Asset", "code": "RS1000", "account_type": "asset_fixed"})
        cls.acc_accum = chart.create({"name": "RS Accum", "code": "RS1001", "account_type": "asset_fixed"})
        cls.acc_expense = chart.create({"name": "RS Dep Exp", "code": "RS6000", "account_type": "expense"})
        cls.journal = cls.env["account.journal"].create({"name": "RS Asset Journal", "code": "RSJ", "type": "general"})
        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "RS Drones",
                "default_useful_life_months": 48,
                "default_asset_account_id": cls.acc_asset.id,
                "default_depreciation_account_id": cls.acc_accum.id,
                "default_expense_account_id": cls.acc_expense.id,
                "default_journal_id": cls.journal.id,
            }
        )
        cls.categ = cls.env["product.category"].create({"name": "RS FA Non-Valuated", "property_valuation": "periodic"})
        cls.drone = cls.env["product.product"].create(
            {
                "name": "RS Drone",
                "is_storable": True,
                "tracking": "serial",
                "categ_id": cls.categ.id,
                "standard_price": 0.0,
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "RS Event Customer"})
        cls.service = cls.env["product.product"].create(
            {"name": "RS Drone Show Service", "type": "service", "list_price": 100000.0}
        )

    # ------------------------------------------------------------------
    def _make_unit(self, name):
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": name,
                "group_id": self.group.id,
                "acquisition_date": fields.Date.to_date("2026-01-31"),
                "posting_date": fields.Date.to_date("2026-01-31"),
                "acquisition_value": 48000.0,
                "useful_life_months": 48,
                "asset_account_id": self.acc_asset.id,
                "depreciation_account_id": self.acc_accum.id,
                "expense_account_id": self.acc_expense.id,
                "journal_id": self.journal.id,
            }
        )
        asset.action_confirm()
        lot = self.env["stock.lot"].create(
            {"name": asset.code, "product_id": self.drone.id, "company_id": self.company.id}
        )
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.drone.id,
                "lot_id": lot.id,
                "location_id": self.home.id,
                "inventory_quantity": 1.0,
            }
        )._apply_inventory()
        asset.write({"product_id": self.drone.id, "lot_id": lot.id})
        asset._sync_stock_from_lots(lot.ids)
        return asset

    def _make_sale(self, auto=False):
        self.company.deployment_auto_create = auto
        return self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
                "deployment_product_id": self.drone.id,
                "deployment_qty": 2,
                "deployment_start": fields.Datetime.to_datetime("2026-09-10 08:00:00"),
                "deployment_end": fields.Datetime.to_datetime("2026-09-12 08:00:00"),
            }
        )

    # ------------------------------------------------------------------
    # The bridge
    # ------------------------------------------------------------------
    def test_confirming_a_sale_creates_a_money_free_deployment(self):
        order = self._make_sale(auto=True)
        order.action_confirm()

        self.assertEqual(order.deployment_count, 1)
        deployment = order.deployment_ids
        self.assertTrue(deployment.is_deployment)
        self.assertEqual(deployment.sale_order_id, order)
        self.assertEqual(deployment.product_id, self.drone)
        self.assertEqual(deployment.qty, 2)
        self.assertTrue(
            deployment.is_internal_loan,
            "A deployment must move units inside the company, never to a customer",
        )
        self.assertEqual(deployment.on_loan_location_id, self.on_deployment)
        self.assertEqual(deployment.daily_rate, 0.0)
        self.assertEqual(deployment.rental_fee, 0.0)
        self.assertEqual(deployment.total_due, 0.0)

    def test_sales_is_untouched_when_the_company_has_not_opted_in(self):
        order = self._make_sale(auto=False)
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.deployment_count, 0, "Opt-out must leave Sales exactly as it was")

    def test_an_order_without_a_deployment_product_confirms_normally(self):
        self.company.deployment_auto_create = True
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
            }
        )
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.deployment_count, 0)

    def test_a_missing_location_notes_the_order_instead_of_blocking_the_sale(self):
        self.company.deployment_location_id = False
        order = self._make_sale(auto=True)
        order.action_confirm()
        self.assertEqual(order.state, "sale", "A warehouse gap must never block a sale")
        self.assertEqual(order.deployment_count, 0)
        self.assertTrue(any("no dispatch document" in (m.body or "") for m in order.message_ids))

    def test_a_deployment_cannot_carry_money(self):
        order = self._make_sale(auto=True)
        order.action_confirm()
        with self.assertRaises(UserError):
            order.deployment_ids.daily_rate = 500.0

    def test_a_deployment_refuses_to_invoice_itself(self):
        order = self._make_sale(auto=True)
        order.action_confirm()
        with self.assertRaises(UserError):
            order.deployment_ids.action_create_invoice()

    def test_the_window_defaults_from_the_show_date_when_dates_are_blank(self):
        self.company.deployment_auto_create = True
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
                "deployment_product_id": self.drone.id,
            }
        )
        order.action_confirm()
        deployment = order.deployment_ids
        self.assertTrue(deployment.pickup_dt)
        self.assertTrue(deployment.return_dt_expected)
        self.assertLess(deployment.pickup_dt, deployment.return_dt_expected)

    # ------------------------------------------------------------------
    # Return reconciliation -- the point of the whole thing
    # ------------------------------------------------------------------
    def _deployment_out_and_back(self, out_assets, back_assets):
        """Drive a deployment through dispatch and return with chosen serials."""
        order = self._make_sale(auto=True)
        order.deployment_qty = len(out_assets)
        order.action_confirm()
        deployment = order.deployment_ids
        self.assertEqual(
            deployment.state,
            "draft",
            "A sale creates the dispatch as a draft; Ops confirms it when ready",
        )

        deployment.action_confirm()
        pickup = deployment.pickup_picking_id
        self.assertTrue(pickup, "Confirming a deployment must raise the outbound picking")
        self._set_picking_serials(pickup, out_assets)
        pickup.button_validate()

        deployment.action_pickup()
        deployment.action_return()
        ret = deployment.return_picking_id
        self.assertTrue(ret)
        self._set_picking_serials(ret, back_assets)
        if back_assets:
            ret.button_validate()
        return order, deployment

    def _set_picking_serials(self, picking, assets):
        move = picking.move_ids[:1]
        move.move_line_ids.unlink()
        if not assets:
            return
        move.product_uom_qty = len(assets)
        for asset in assets:
            self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": self.drone.id,
                    "product_uom_id": self.drone.uom_id.id,
                    "lot_id": asset.lot_id.id,
                    "quantity": 1.0,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "company_id": self.company.id,
                }
            )

    def test_a_serial_that_never_came_back_becomes_a_missing_asset(self):
        kept = self._make_unit("RS Unit Kept")
        lost = self._make_unit("RS Unit Lost")
        order, deployment = self._deployment_out_and_back([kept, lost], [kept])

        missing, unexpected = deployment._returned_serial_discrepancy()
        self.assertEqual(missing, lost.lot_id)
        self.assertFalse(unexpected)

        # The old behaviour was a dead-end UserError; now it routes to a wizard.
        action = deployment.action_validate_loan_return()
        self.assertEqual(action["res_model"], "custom.rental.return.reconcile.wizard")

        wizard = (
            self.env["custom.rental.return.reconcile.wizard"]
            .with_context(default_rental_order_id=deployment.id)
            .create({"reference": "BAP/RS/001", "description": "Lost during the show"})
        )
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.asset_id, lost)
        self.assertEqual(wizard.missing_count, 1)
        wizard.action_reconcile()

        lost.invalidate_recordset()
        self.assertEqual(lost.condition, "missing")
        self.assertEqual(lost.state, "running", "A missing unit keeps depreciating")
        self.assertEqual(lost.missing_reference, "BAP/RS/001")
        self.assertEqual(lost.stock_location_id, self.missing_loc)
        kept.invalidate_recordset()
        self.assertEqual(kept.condition, "ok", "The unit that came back is untouched")

    def test_a_unit_that_came_back_broken_becomes_a_damaged_asset(self):
        good = self._make_unit("RS Unit Good")
        broken = self._make_unit("RS Unit Broken")
        order, deployment = self._deployment_out_and_back([good, broken], [good, broken])

        missing, _unexpected = deployment._returned_serial_discrepancy()
        self.assertFalse(missing, "Both units came back")

        wizard = (
            self.env["custom.rental.return.reconcile.wizard"]
            .with_context(default_rental_order_id=deployment.id)
            .create(
                {
                    "reference": "BAP/RS/002",
                    "description": "Arm snapped on landing",
                    "damaged_lot_ids": [(6, 0, broken.lot_id.ids)],
                    "open_repair": True,
                    "repair_channel": "in_house",
                }
            )
        )
        self.assertEqual(wizard.damaged_count, 1)
        wizard.action_reconcile()

        broken.invalidate_recordset()
        self.assertEqual(broken.condition, "damaged")
        self.assertEqual(broken.stock_location_id, self.damage_loc)
        self.assertEqual(broken.repair_count, 1)
        good.invalidate_recordset()
        self.assertEqual(good.condition, "ok")

    def test_reconciling_notes_both_the_deployment_and_the_sale(self):
        kept = self._make_unit("RS Unit A")
        lost = self._make_unit("RS Unit B")
        order, deployment = self._deployment_out_and_back([kept, lost], [kept])
        wizard = (
            self.env["custom.rental.return.reconcile.wizard"]
            .with_context(default_rental_order_id=deployment.id)
            .create({"reference": "BAP/RS/003", "description": "Blown away"})
        )
        wizard.action_reconcile()
        self.assertTrue(
            any("came back short" in (m.body or "") for m in order.message_ids),
            "The seller must learn that their event lost units",
        )

    def test_leaving_everything_open_books_nothing(self):
        kept = self._make_unit("RS Unit C")
        lost = self._make_unit("RS Unit D")
        order, deployment = self._deployment_out_and_back([kept, lost], [kept])
        wizard = (
            self.env["custom.rental.return.reconcile.wizard"]
            .with_context(default_rental_order_id=deployment.id)
            .create({"reference": "BAP/RS/004", "description": "Still looking"})
        )
        wizard.line_ids.outcome = "ignore"
        with self.assertRaises(UserError):
            wizard.action_reconcile()
        lost.invalidate_recordset()
        self.assertEqual(lost.condition, "ok")

    def test_a_clean_return_still_closes_the_old_way(self):
        good = self._make_unit("RS Unit E")
        order, deployment = self._deployment_out_and_back([good], [good])
        self.assertTrue(
            deployment.action_validate_loan_return(),
            "A return with no discrepancy must not open a wizard",
        )

    def test_dispatch_picks_from_where_the_units_are(self):
        """The dispatch must move the units, not mint a negative quant.

        custom_rental sources an internal loan from the first internal picking
        type's default source, which in a multi-step warehouse is the Input dock.
        Reserving from a location the units are not in does not fail -- it books
        -1 there, +1 at the destination, and leaves the original stock alone, so
        the unit is in two places at once. That is the pattern that had 2,572
        ARKA-AIM units reporting the wrong warehouse.
        """
        unit = self._make_unit("RS Unit Dispatch")
        order = self._make_sale(auto=True)
        order.deployment_qty = 1
        order.action_confirm()
        deployment = order.deployment_ids
        deployment.action_confirm()

        pickup = deployment.pickup_picking_id
        self.assertEqual(
            pickup.location_id,
            self.home,
            "The dispatch must be sourced from where the fleet actually lives",
        )
        self.assertEqual(pickup.location_dest_id, self.on_deployment)

        self._set_picking_serials(pickup, [unit])
        pickup.button_validate()
        unit.invalidate_recordset()

        self.assertEqual(unit.stock_location_id, self.on_deployment)
        negatives = self.env["stock.quant"].search(
            [("lot_id", "=", unit.lot_id.id), ("quantity", "<", 0), ("location_id.usage", "=", "internal")]
        )
        self.assertFalse(
            negatives,
            "Dispatching a unit must not leave a negative quant behind: %s"
            % negatives.mapped("location_id.complete_name"),
        )
        positives = self.env["stock.quant"].search(
            [("lot_id", "=", unit.lot_id.id), ("quantity", ">", 0), ("location_id.usage", "=", "internal")]
        )
        self.assertEqual(
            positives.location_id,
            self.on_deployment,
            "A serial must be in exactly one place after a dispatch",
        )

    # ------------------------------------------------------------------
    # What may be dispatched
    # ------------------------------------------------------------------
    def test_a_service_with_no_kit_cannot_be_dispatched(self):
        """The mis-selection this guard exists for.

        Before it, picking a plain service produced a deployment and then a
        picking whose only move was for a service product -- a dispatch document
        that moves nothing, discovered by Ops rather than by the person who
        chose it.
        """
        with self.assertRaises(ValidationError):
            self.env["sale.order"].create(
                {
                    "partner_id": self.customer.id,
                    "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
                    "deployment_product_id": self.service.id,
                }
            )

    def test_a_kit_of_storable_components_is_accepted_even_though_it_is_a_service(self):
        """The rule is dispatchable, not storable, and the difference is the case.

        ARKA-AIM's "Sewa Drone Show 1500 Unit" is a *service* product holding no
        stock, carrying a phantom BOM that explodes into 1,500 serial-tracked
        drones. A guard demanding a storable product would reject the client's
        own bundle -- the primary case this module was built for.
        """
        bundle = self.env["product.product"].create({"name": "RS Show Bundle", "type": "service"})
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": bundle.product_tmpl_id.id,
                "type": "phantom",
                "product_qty": 1.0,
                "bom_line_ids": [(0, 0, {"product_id": self.drone.id, "product_qty": 1500.0})],
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
                "deployment_product_id": bundle.id,
            }
        )
        self.assertEqual(order.deployment_product_id, bundle)
        self.assertTrue(
            order.deployment_reconcilable,
            "A kit of serial-tracked components does yield serials to reconcile",
        )

    def test_a_storable_product_is_accepted(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
                "deployment_product_id": self.drone.id,
            }
        )
        self.assertEqual(order.deployment_product_id, self.drone)
        self.assertTrue(order.deployment_reconcilable)

    def test_a_dispatch_with_no_serials_warns_rather_than_blocks(self):
        """Quantity-only dispatch is legitimate; silent non-checking is not."""
        bulk = self.env["product.product"].create(
            {
                "name": "RS Bulk Crate",
                "is_storable": True,
                "tracking": "none",
                "categ_id": self.categ.id,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 1})],
                "deployment_product_id": bulk.id,
            }
        )
        self.assertFalse(
            order.deployment_reconcilable,
            "Nothing serial-tracked, so the return check would compare nothing",
        )
        warning = order._onchange_deployment_product_id()
        self.assertTrue(warning and "warning" in warning)
        self.assertIn("no serials", warning["warning"]["title"].lower())
