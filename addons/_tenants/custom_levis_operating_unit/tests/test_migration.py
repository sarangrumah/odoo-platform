# -*- coding: utf-8 -*-
"""The migration is additive and idempotent — the two properties that matter."""

from odoo.tests import TransactionCase, tagged

from ..models.setup import migrate_levis_operating_units


@tagged("post_install", "-at_install")
class TestLevisOperatingUnitMigration(TransactionCase):
    def test_01_every_wired_warehouse_has_a_unit(self):
        warehouses = self.env["stock.warehouse"].with_context(active_test=False).search(
            [("l10n_ou_analytic_id", "!=", False)]
        )
        units = self.env["operating.unit"].with_context(active_test=False)
        for warehouse in warehouses:
            unit = units.search([("warehouse_id", "=", warehouse.id)], limit=1)
            head_office = units.search(
                [("analytic_account_id", "=", warehouse.l10n_ou_analytic_id.id)], limit=1
            )
            self.assertTrue(
                unit or head_office,
                "warehouse %s has an OU analytic but no operating.unit" % warehouse.code,
            )
            if unit:
                self.assertEqual(
                    unit.code, warehouse.code, "the unit code is the warehouse code, copied"
                )

    def test_02_rerunning_creates_nothing(self):
        units = self.env["operating.unit"].with_context(active_test=False)
        before = units.search_count([])
        names_before = {u.id: u.name for u in units.search([])}

        created, _existing = migrate_levis_operating_units(self.env)

        self.assertEqual(created, 0, "a second run must create nothing")
        self.assertEqual(units.search_count([]), before)
        self.assertEqual({u.id: u.name for u in units.search([])}, names_before)

    def test_03_nothing_upstream_is_renamed(self):
        """The migration must never touch the records it links to."""
        warehouses = self.env["stock.warehouse"].with_context(active_test=False).search([])
        before = {w.id: (w.code, w.name) for w in warehouses}
        analytics = {
            u.analytic_account_id.id: u.analytic_account_id.name
            for u in self.env["operating.unit"].with_context(active_test=False).search([])
            if u.analytic_account_id
        }

        migrate_levis_operating_units(self.env)

        self.assertEqual({w.id: (w.code, w.name) for w in warehouses}, before)
        for analytic_id, name in analytics.items():
            self.assertEqual(
                self.env["account.analytic.account"].browse(analytic_id).name,
                name,
                "analytic names belong to 41_normalize_ou.py, not to this migration",
            )

    def test_04_picking_a_unit_fills_the_legacy_analytic(self):
        unit = self.env["operating.unit"].search([("analytic_account_id", "!=", False)], limit=1)
        if not unit:
            self.skipTest("no unit linked to an analytic account on this database")
        journal = self.env["account.journal"].search([("type", "=", "purchase")], limit=1)
        move = self.env["account.move"].create({"move_type": "entry", "journal_id": journal.id})
        account = self.env["account.account"].search([], limit=1)
        line = self.env["account.move.line"].create(
            {
                "move_id": move.id,
                "account_id": account.id,
                "balance": 0.0,
                "operating_unit_id": unit.id,
            }
        )
        self.assertEqual(line.l10n_ou_analytic_id, unit.analytic_account_id)
