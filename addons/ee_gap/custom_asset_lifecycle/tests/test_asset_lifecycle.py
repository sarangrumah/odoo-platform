# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAssetLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.group_ids |= cls.env.ref("custom_accounting_asset.group_asset_manager")

        chart = cls.env["account.account"]
        cls.acc_asset = chart.create({"name": "Test Asset", "code": "TA1000", "account_type": "asset_fixed"})
        cls.acc_accum = chart.create({"name": "Test Accum", "code": "TA1001", "account_type": "asset_fixed"})
        cls.acc_expense = chart.create({"name": "Test Dep Expense", "code": "TA6000", "account_type": "expense"})
        cls.acc_loss = chart.create({"name": "Test Asset Loss", "code": "TA6900", "account_type": "expense"})
        cls.acc_income = chart.create(
            {"name": "Test Compensation Income", "code": "TA8900", "account_type": "income_other"}
        )
        cls.journal = cls.env["account.journal"].create(
            {"name": "Test Asset Journal", "code": "TAJ", "type": "general"}
        )
        cls.company.write(
            {
                "asset_loss_account_id": cls.acc_loss.id,
                "asset_compensation_income_account_id": cls.acc_income.id,
                "asset_replacement_journal_id": cls.journal.id,
            }
        )
        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "Test Drones",
                "default_useful_life_months": 48,
                "default_asset_account_id": cls.acc_asset.id,
                "default_depreciation_account_id": cls.acc_accum.id,
                "default_expense_account_id": cls.acc_expense.id,
                "default_journal_id": cls.journal.id,
            }
        )

    def _make_asset(self, name="Drone Unit", value=48000.0, confirm=True):
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": name,
                "group_id": self.group.id,
                "acquisition_date": fields.Date.to_date("2026-01-31"),
                "posting_date": fields.Date.to_date("2026-01-31"),
                "acquisition_value": value,
                "useful_life_months": 48,
                "asset_account_id": self.acc_asset.id,
                "depreciation_account_id": self.acc_accum.id,
                "expense_account_id": self.acc_expense.id,
                "journal_id": self.journal.id,
            }
        )
        if confirm:
            asset.action_confirm()
        return asset

    # ------------------------------------------------------------------
    # The rule the whole module hangs on
    # ------------------------------------------------------------------
    def test_depreciation_continues_while_in_repair(self):
        """IAS 16.55 / PSAK 16: depreciation does not stop for an idle asset.

        Condition must therefore never touch state, and the monthly cron -- which
        searches on state == 'running' -- must keep picking the asset up.
        """
        asset = self._make_asset()
        schedule_before = len(asset.depreciation_line_ids)

        asset._log_condition_event("damage", condition_to="damaged", description="Rotor bent")
        self.assertEqual(asset.condition, "damaged")
        self.assertEqual(asset.state, "running", "A damaged asset must stay running")

        asset._log_condition_event("repair_start", condition_to="in_repair", description="Shop")
        self.assertEqual(asset.state, "running", "An asset under repair must stay running")
        self.assertEqual(
            len(asset.depreciation_line_ids),
            schedule_before,
            "The depreciation schedule must be untouched by condition changes",
        )
        self.assertIn(
            asset,
            self.env["custom.fixed.asset"].search([("state", "=", "running")]),
            "The depreciation cron must still see the asset",
        )

    def test_missing_asset_keeps_depreciating_until_written_off(self):
        asset = self._make_asset()
        wizard = self.env["custom.asset.report.missing.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Not returned from the Merdeka Run show",
                "reference": "BAP/2026/09/001",
                "move_serial": False,
            }
        )
        wizard.action_report_missing()
        self.assertEqual(asset.condition, "missing")
        self.assertEqual(asset.state, "running")
        self.assertEqual(asset.missing_reference, "BAP/2026/09/001")
        self.assertTrue(asset.missing_reported_on)

        log = asset.condition_log_ids.filtered(lambda log_: log_.event_type == "missing")
        self.assertEqual(len(log), 1)
        self.assertEqual(log.condition_from, "ok")
        self.assertEqual(log.condition_to, "missing")

    def test_write_off_stops_depreciation_and_closes_condition(self):
        asset = self._make_asset()
        asset._log_condition_event("missing", condition_to="missing", description="Lost")
        nbv = asset.net_book_value

        wizard = self.env["custom.fixed.asset.disposal.wizard"].create(
            {
                "asset_id": asset.id,
                "disposal_date": fields.Date.to_date("2026-09-30"),
                "disposal_value": 0.0,
                "loss_account_id": self.acc_loss.id,
            }
        )
        wizard.action_dispose()

        self.assertEqual(asset.state, "disposed")
        self.assertEqual(asset.condition, "written_off", "Derecognition must close the condition")
        self.assertNotIn(asset, self.env["custom.fixed.asset"].search([("state", "=", "running")]))
        self.assertAlmostEqual(asset.disposal_gain_loss, -nbv, places=2)
        self.assertTrue(asset.condition_log_ids.filtered(lambda log_: log_.event_type == "write_off"))

    # ------------------------------------------------------------------
    # Replacement
    # ------------------------------------------------------------------
    def test_replacement_posts_acquisition_entry_at_fair_value(self):
        """The register posts no acquisition entry, so the wizard must.

        Without it the register would grow while the GL stood still.
        """
        old = self._make_asset(value=48000.0)
        old._log_condition_event("missing", condition_to="missing", description="Lost")

        wizard = self.env["custom.asset.replacement.wizard"].create(
            {
                "replaced_asset_id": old.id,
                "name": "Drone Unit (replacement)",
                "acquisition_date": fields.Date.to_date("2026-09-08"),
                "market_value": 52000.0,
                "useful_life_months": 48,
                "group_id": self.group.id,
                "replacement_reason": "missing",
                "claim_ref": "CLAIM/2026/09/001",
                "post_journal_entry": True,
                "income_account_id": self.acc_income.id,
                "journal_id": self.journal.id,
            }
        )
        wizard.action_register()

        new = old.replaced_by_asset_id
        self.assertTrue(new, "The replaced unit must point at its replacement")
        self.assertEqual(new.replaces_asset_id, old)
        self.assertTrue(new.is_replacement)
        self.assertEqual(new.acquisition_value, 52000.0)
        self.assertEqual(new.state, "running")
        self.assertEqual(new.replacement_claim_ref, "CLAIM/2026/09/001")

        move = new.replacement_move_id
        self.assertTrue(move, "A replacement must carry its acquisition entry")
        self.assertEqual(move.state, "posted")
        debit = move.line_ids.filtered(lambda line: line.account_id == self.acc_asset)
        credit = move.line_ids.filtered(lambda line: line.account_id == self.acc_income)
        self.assertAlmostEqual(debit.debit, 52000.0, places=2)
        self.assertAlmostEqual(credit.credit, 52000.0, places=2)

        # A full life on the new unit, not the remainder of the old one.
        self.assertEqual(len(new.depreciation_line_ids), 48)
        self.assertTrue(old.condition_log_ids.filtered(lambda log_: log_.event_type == "replaced"))

    def test_replacement_refuses_a_second_time(self):
        old = self._make_asset()
        vals = {
            "replaced_asset_id": old.id,
            "name": "Replacement",
            "acquisition_date": fields.Date.to_date("2026-09-08"),
            "market_value": 1000.0,
            "useful_life_months": 48,
            "group_id": self.group.id,
            "replacement_reason": "damage",
            "income_account_id": self.acc_income.id,
            "journal_id": self.journal.id,
        }
        self.env["custom.asset.replacement.wizard"].create(vals).action_register()
        with self.assertRaises(UserError):
            self.env["custom.asset.replacement.wizard"].create(dict(vals)).action_register()

    def test_replacement_needs_a_positive_value(self):
        old = self._make_asset()
        wizard = self.env["custom.asset.replacement.wizard"].create(
            {
                "replaced_asset_id": old.id,
                "name": "Replacement",
                "acquisition_date": fields.Date.to_date("2026-09-08"),
                "market_value": 0.0,
                "useful_life_months": 48,
                "group_id": self.group.id,
                "replacement_reason": "damage",
            }
        )
        with self.assertRaises(UserError):
            wizard.action_register()

    # ------------------------------------------------------------------
    # Repair channels
    # ------------------------------------------------------------------
    def test_warranty_repair_is_excluded_from_lifetime_cost(self):
        asset = self._make_asset()
        asset._ensure_equipment()
        vendor = self.env["res.partner"].create({"name": "Drone Service Co"})
        Repair = self.env["repair.order"]
        in_house = Repair.create(
            {
                "x_fixed_asset_id": asset.id,
                "x_repair_channel": "in_house",
                "x_labor_hours": 2.0,
                "x_labor_rate": 100.0,
            }
        )
        warranty = Repair.create(
            {
                "x_fixed_asset_id": asset.id,
                "x_repair_channel": "warranty",
                "x_warranty_claim_ref": "WR/2026/01",
                "x_labor_hours": 5.0,
                "x_labor_rate": 100.0,
            }
        )
        asset.invalidate_recordset()
        self.assertEqual(asset.repair_count, 2)
        self.assertAlmostEqual(
            asset.repair_cost_total,
            in_house.x_total_repair_cost,
            places=2,
            msg="A warranty claim costs the company nothing and must not inflate the total",
        )
        self.assertTrue(warranty.x_is_warranty)
        self.assertTrue(warranty.under_warranty)

    def test_third_party_repair_requires_a_vendor(self):
        asset = self._make_asset()
        with self.assertRaises(UserError):
            self.env["repair.order"].create({"x_fixed_asset_id": asset.id, "x_repair_channel": "third_party"})

    def test_warranty_repair_requires_a_claim_reference(self):
        asset = self._make_asset()
        with self.assertRaises(UserError):
            self.env["repair.order"].create({"x_fixed_asset_id": asset.id, "x_repair_channel": "warranty"})

    # ------------------------------------------------------------------
    # Damage flow and equipment provisioning
    # ------------------------------------------------------------------
    def test_damage_wizard_opens_repair_and_provisions_equipment(self):
        asset = self._make_asset()
        self.assertFalse(asset.equipment_id)
        wizard = self.env["custom.asset.report.damage.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Arm snapped on landing",
                "move_serial": False,
                "create_repair": True,
                "repair_channel": "in_house",
            }
        )
        wizard.action_report_damage()

        self.assertEqual(
            asset.condition,
            "damaged",
            "A repair order that is still a draft has not taken the unit anywhere yet",
        )
        self.assertTrue(asset.equipment_id, "A repair needs an equipment card to record against")
        self.assertEqual(asset.repair_count, 1)
        self.assertEqual(asset.equipment_id.fixed_asset_id, asset)
        self.assertIn("damage", asset.condition_log_ids.mapped("event_type"))

        repair = asset.repair_order_ids
        repair.action_validate()
        asset.invalidate_recordset()
        self.assertEqual(asset.condition, "in_repair", "Confirming the repair moves the unit on")
        self.assertIn("repair_start", asset.condition_log_ids.mapped("event_type"))

        repair.action_repair_start()
        repair.action_repair_end()
        asset.invalidate_recordset()
        self.assertEqual(
            asset.condition,
            "repaired",
            "A finished repair leaves the unit repaired but still in the damage warehouse",
        )
        self.assertIn("repair_done", asset.condition_log_ids.mapped("event_type"))

    def test_cannot_report_the_same_damage_twice(self):
        asset = self._make_asset()
        first = self.env["custom.asset.report.damage.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Bent rotor",
                "move_serial": False,
                "create_repair": False,
            }
        )
        first.action_report_damage()
        second = self.env["custom.asset.report.damage.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Bent rotor again",
                "move_serial": False,
                "create_repair": False,
            }
        )
        with self.assertRaises(UserError):
            second.action_report_damage()

    def test_return_to_service_is_blocked_by_an_open_repair(self):
        asset = self._make_asset()
        wizard = self.env["custom.asset.report.damage.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Battery swelling",
                "move_serial": False,
                "create_repair": True,
                "repair_channel": "in_house",
            }
        )
        wizard.action_report_damage()
        with self.assertRaises(UserError):
            asset.action_return_to_service()

        asset.repair_order_ids.write({"state": "done"})
        asset.invalidate_recordset()
        asset.action_return_to_service()
        self.assertEqual(asset.condition, "ok")
        self.assertIn("return_service", asset.condition_log_ids.mapped("event_type"))

    def test_equipment_provisioning_is_idempotent(self):
        assets = self._make_asset("Unit A") | self._make_asset("Unit B")
        wizard = self.env["custom.asset.equipment.provision.wizard"].create({"asset_ids": [(6, 0, assets.ids)]})
        self.assertEqual(wizard.pending_count, 2)
        wizard.action_provision()
        self.assertTrue(all(assets.mapped("equipment_id")))

        again = self.env["custom.asset.equipment.provision.wizard"].create({"asset_ids": [(6, 0, assets.ids)]})
        self.assertEqual(again.pending_count, 0)
        with self.assertRaises(UserError):
            again.action_provision()

    def test_an_asset_cannot_replace_itself(self):
        asset = self._make_asset()
        with self.assertRaises(UserError):
            asset.replaces_asset_id = asset

    # ------------------------------------------------------------------
    # The serial actually moves
    # ------------------------------------------------------------------
    def _materialise(self, asset, location):
        """Give an asset a serial sitting in ``location``, the way
        ``custom_asset_stock_link`` does -- non-valuated, zero cost, so no
        journal entry can result from moving it."""
        category = self.env["product.category"].create(
            {"name": "Test FA Non-Valuated", "property_valuation": "periodic"}
        )
        product = self.env["product.product"].create(
            {
                "name": asset.name,
                "is_storable": True,
                "tracking": "serial",
                "categ_id": category.id,
                "standard_price": 0.0,
            }
        )
        lot = self.env["stock.lot"].create(
            {"name": asset.code, "product_id": product.id, "company_id": asset.company_id.id}
        )
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": product.id,
                "lot_id": lot.id,
                "location_id": location.id,
                "inventory_quantity": 1.0,
            }
        )._apply_inventory()
        asset.write({"product_id": product.id, "lot_id": lot.id})
        asset._sync_stock_from_lots(lot.ids)
        asset.invalidate_recordset()
        return product, lot

    def test_damage_moves_the_serial_and_posts_no_journal_entry(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        home = warehouse.lot_stock_id
        damage_location = self.env["stock.location"].create(
            {"name": "Damage Test", "usage": "internal", "location_id": warehouse.view_location_id.id}
        )
        self.company.asset_damage_location_id = damage_location

        asset = self._make_asset()
        asset.location_id = self.env["custom.fixed.asset.location"].create(
            {"name": "Test Asset Location", "stock_location_id": home.id}
        )
        self._materialise(asset, home)
        self.assertEqual(asset.stock_location_id, home)

        moves_before = self.env["account.move"].search_count([])
        wizard = self.env["custom.asset.report.damage.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Crashed on landing",
                "move_serial": True,
                "create_repair": False,
            }
        )
        wizard.action_report_damage()
        asset.invalidate_recordset()

        self.assertEqual(asset.condition, "damaged")
        self.assertEqual(
            asset.stock_location_id,
            damage_location,
            "The serial must actually be in the damage warehouse, not just flagged",
        )
        log = asset.condition_log_ids.filtered(lambda log_: log_.event_type == "damage")
        self.assertTrue(log.picking_id, "The move must leave a document behind")
        self.assertEqual(log.picking_id.state, "done")
        self.assertEqual(log.location_id, damage_location)
        self.assertEqual(
            self.env["account.move"].search_count([]),
            moves_before,
            "Moving an already-capitalised unit must post nothing to the ledger",
        )

        # ... and it comes home again.
        asset.action_return_to_service()
        asset.invalidate_recordset()
        self.assertEqual(asset.condition, "ok")
        self.assertEqual(asset.stock_location_id, home)

    def test_missing_serial_leaves_the_available_stock(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        home = warehouse.lot_stock_id
        missing_location = self.env["stock.location"].create(
            {"name": "Lost Test", "usage": "internal", "location_id": warehouse.view_location_id.id}
        )
        self.company.asset_missing_location_id = missing_location

        asset = self._make_asset()
        product, lot = self._materialise(asset, home)

        wizard = self.env["custom.asset.report.missing.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Never came back from the show",
                "reference": "BAP/2026/09/002",
                "move_serial": True,
            }
        )
        wizard.action_report_missing()
        asset.invalidate_recordset()

        self.assertEqual(asset.stock_location_id, missing_location)
        self.assertEqual(
            self.env["stock.quant"].search_count(
                [("lot_id", "=", lot.id), ("location_id", "=", home.id), ("quantity", ">", 0)]
            ),
            0,
            "A missing unit must stop counting as on-hand where it used to live",
        )

    def test_a_register_only_unit_without_a_serial_is_simply_skipped(self):
        """490 units on the ARKA-AIM register carry no serial at all."""
        self.company.asset_damage_location_id = False
        asset = self._make_asset()
        self.assertFalse(asset.lot_id)
        wizard = self.env["custom.asset.report.damage.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Casing cracked",
                "move_serial": True,
                "create_repair": False,
            }
        )
        wizard.action_report_damage()
        self.assertEqual(asset.condition, "damaged")
        self.assertEqual(wizard.without_serial_count, 1)

    def test_a_serial_with_an_offsetting_negative_quant_is_sourced_correctly(self):
        """The shape that put 2,572 ARKA-AIM units in the wrong warehouse.

        A badly-sourced picking leaves +1 and -1 in the same location while the
        unit really sits elsewhere. Reading the largest positive quant row names
        the wrong place; the position must be resolved from the net.
        """
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        home = warehouse.lot_stock_id
        elsewhere = self.env["stock.location"].create(
            {"name": "Real Shelf", "usage": "internal", "location_id": warehouse.view_location_id.id}
        )
        damage_location = self.env["stock.location"].create(
            {"name": "Damage Net Test", "usage": "internal", "location_id": warehouse.view_location_id.id}
        )
        self.company.asset_damage_location_id = damage_location

        asset = self._make_asset()
        product, lot = self._materialise(asset, elsewhere)
        # Bolt on the offsetting pair that the real data carries.
        Quant = self.env["stock.quant"].sudo()
        Quant.create({"product_id": product.id, "lot_id": lot.id, "location_id": home.id, "quantity": 1.0})
        Quant.create({"product_id": product.id, "lot_id": lot.id, "location_id": home.id, "quantity": -1.0})
        asset._sync_stock_from_lots(lot.ids)
        asset.invalidate_recordset()

        self.assertEqual(
            asset._resolve_serial_source_location(),
            elsewhere,
            "The net says the unit is on the real shelf, not where the +1/-1 pair sits",
        )
        self.assertEqual(
            asset.stock_location_id,
            elsewhere,
            "The register must show the net position too, not the largest quant row",
        )

        self.env["custom.asset.report.damage.wizard"].create(
            {
                "asset_ids": [(6, 0, asset.ids)],
                "description": "Sourced from the right shelf",
                "move_serial": True,
                "create_repair": False,
            }
        ).action_report_damage()
        asset.invalidate_recordset()
        self.assertEqual(asset.stock_location_id, damage_location)

    def test_a_serial_that_is_nowhere_is_refused_rather_than_minting_a_negative(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        damage_location = self.env["stock.location"].create(
            {"name": "Damage Nowhere Test", "usage": "internal", "location_id": warehouse.view_location_id.id}
        )
        self.company.asset_damage_location_id = damage_location

        asset = self._make_asset()
        product, lot = self._materialise(asset, warehouse.lot_stock_id)
        self.env["stock.quant"].sudo().create(
            {
                "product_id": product.id,
                "lot_id": lot.id,
                "location_id": warehouse.lot_stock_id.id,
                "quantity": -1.0,
            }
        )
        asset.invalidate_recordset()
        with self.assertRaises(UserError):
            asset._move_serial_to(damage_location)

    def test_equipment_cards_survive_duplicate_physical_serials(self):
        """The client's listing repeats eight battery serials.

        Core maintenance puts a global unique() on ``serial_no``, so keying the
        cards on the physical serial fails partway through the fleet. They are
        keyed on the asset code instead, and the physical serial is kept in the
        note and vendor reference.
        """
        first = self._make_asset("Battery A")
        second = self._make_asset("Battery B")
        (first | second).write({"serial_number": "24041700035"})

        cards = (first | second)._ensure_equipment()
        self.assertEqual(len(cards), 2, "A repeated physical serial must not block a card")
        self.assertEqual(first.equipment_id.serial_no, first.code)
        self.assertEqual(second.equipment_id.serial_no, second.code)
        self.assertNotEqual(first.equipment_id.serial_no, second.equipment_id.serial_no)
        self.assertIn("24041700035", first.equipment_id.note or "")
        self.assertEqual(first.equipment_id.partner_ref, "24041700035")
