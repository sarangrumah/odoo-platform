# -*- coding: utf-8 -*-
"""The store code on the warehouse, and the backfill that fills it.

The code is the one textual key shared by the retail feed, a cash-deposit
transfer memo and a bank statement. Everything downstream trusts it to name
exactly one store, so the tests here are mostly about the ways it must refuse
to: a duplicate, a steal, a guess.
"""

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install")
class TestStoreCode(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        Warehouse = cls.env["stock.warehouse"]
        cls.wh_a = Warehouse.create({"name": "Levi's Sunter", "code": "LSNT", "company_id": cls.company.id})
        cls.wh_b = Warehouse.create({"name": "Levi's Cibubur", "code": "LCBB", "company_id": cls.company.id})
        # These tests may run against a clone of a real tenant, where the retail
        # feed has already named dozens of stores. Absorb that baseline once so
        # each test's counters describe its own fixture and not the database it
        # happened to be run on.
        from odoo.addons.custom_levis_localization.models.setup import seed_store_codes

        seed_store_codes(cls.env)

    # ------------------------------------------------------------------
    # The field
    # ------------------------------------------------------------------
    def test_a_store_code_is_optional(self):
        # A warehouse may exist before anyone has decided its code.
        self.assertFalse(self.wh_a.l10n_store_code)

    def test_two_stores_cannot_share_a_code(self):
        self.wh_a.l10n_store_code = "SNC"
        # Odoo's assertRaises override does not accept a tuple of classes, and
        # the guard is a database unique constraint, so this is the one that
        # actually surfaces.
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self.wh_b.l10n_store_code = "SNC"
                self.env.flush_all()

    def test_many_stores_may_share_no_code(self):
        # NULLs stay distinct in Postgres, which is what lets the backfill run
        # over a fleet where most stores have no code yet.
        self.wh_a.l10n_store_code = False
        self.wh_b.l10n_store_code = False
        self.env.flush_all()
        self.assertFalse(self.wh_a.l10n_store_code)
        self.assertFalse(self.wh_b.l10n_store_code)

    # ------------------------------------------------------------------
    # The resolver
    # ------------------------------------------------------------------
    def test_a_code_resolves_to_its_store(self):
        analytic_plan = self.env["account.analytic.plan"].create({"name": "OU Test"})
        analytic = self.env["account.analytic.account"].create(
            {"name": "Sunter", "plan_id": analytic_plan.id, "company_id": self.company.id}
        )
        self.wh_a.write({"l10n_store_code": "SNC", "l10n_ou_analytic_id": analytic.id})
        warehouse, resolved = self.env["stock.warehouse"]._levis_store_by_code(self.company, "SNC")
        self.assertEqual(warehouse, self.wh_a)
        self.assertEqual(resolved, analytic)

    def test_a_code_resolves_whatever_case_it_is_typed_in(self):
        self.wh_a.l10n_store_code = "SNC"
        for typed in ("snc", " SnC ", "SNC"):
            warehouse, _analytic = self.env["stock.warehouse"]._levis_store_by_code(self.company, typed)
            self.assertEqual(warehouse, self.wh_a, "failed for %r" % typed)

    def test_an_unknown_code_resolves_to_nothing_rather_than_a_guess(self):
        self.wh_a.l10n_store_code = "SNC"
        warehouse, analytic = self.env["stock.warehouse"]._levis_store_by_code(self.company, "NOPE")
        self.assertFalse(warehouse)
        self.assertFalse(analytic)

    def test_an_empty_code_resolves_to_nothing(self):
        warehouse, analytic = self.env["stock.warehouse"]._levis_store_by_code(self.company, "")
        self.assertFalse(warehouse)
        self.assertFalse(analytic)

    def test_the_index_follows_a_renamed_code(self):
        self.wh_a.l10n_store_code = "SNC"
        self.env["stock.warehouse"]._levis_store_by_code(self.company, "SNC")  # warm the cache
        self.wh_a.l10n_store_code = "SNT"
        warehouse, _analytic = self.env["stock.warehouse"]._levis_store_by_code(self.company, "SNT")
        self.assertEqual(warehouse, self.wh_a)
        stale, _a = self.env["stock.warehouse"]._levis_store_by_code(self.company, "SNC")
        self.assertFalse(stale, "the old code must stop resolving")

    # ------------------------------------------------------------------
    # The backfill
    # ------------------------------------------------------------------
    def _xid_for(self, config, code):
        self.env["ir.model.data"].sudo().create(
            {
                "module": "levis",
                "name": "posconfig_%s" % code,
                "model": "pos.config",
                "res_id": config.id,
            }
        )

    def _pos_config(self, name, warehouse):
        # sudo: the accounting test user is not a POS manager, and what is under
        # test is the backfill's arithmetic, not who may configure a till.
        return self.env["pos.config"].sudo().create({"name": name, "warehouse_id": warehouse.id})

    def test_the_backfill_takes_the_code_from_the_retail_feed(self):
        from odoo.addons.custom_levis_localization.models.setup import seed_store_codes

        self._xid_for(self._pos_config("Sunter POS", self.wh_a), "SNCTEST")
        result = seed_store_codes(self.env)
        self.assertEqual(self.wh_a.l10n_store_code, "SNCTEST")
        self.assertEqual(result["filled"], 1)

    def test_the_backfill_never_overwrites_a_hand_correction(self):
        from odoo.addons.custom_levis_localization.models.setup import seed_store_codes

        self.wh_a.l10n_store_code = "SUNTERTEST"
        self._xid_for(self._pos_config("Sunter POS", self.wh_a), "SNCTEST")
        seed_store_codes(self.env)
        self.assertEqual(self.wh_a.l10n_store_code, "SUNTERTEST")

    def test_the_backfill_does_not_steal_a_code_from_another_store(self):
        from odoo.addons.custom_levis_localization.models.setup import seed_store_codes

        self.wh_a.l10n_store_code = "SNCTEST"
        self._xid_for(self._pos_config("Cibubur POS", self.wh_b), "SNCTEST")
        result = seed_store_codes(self.env)
        self.assertEqual(self.wh_a.l10n_store_code, "SNCTEST")
        self.assertFalse(self.wh_b.l10n_store_code, "the second store is left empty, not renamed")
        self.assertGreaterEqual(result["skipped"], 1)

    def test_the_backfill_is_idempotent(self):
        from odoo.addons.custom_levis_localization.models.setup import seed_store_codes

        self._xid_for(self._pos_config("Sunter POS", self.wh_a), "SNCTEST")
        first = seed_store_codes(self.env)
        second = seed_store_codes(self.env)
        self.assertEqual(first["filled"], 1)
        self.assertEqual(second["filled"], 0, "a second run must change nothing")
        self.assertEqual(self.wh_a.l10n_store_code, "SNCTEST")
