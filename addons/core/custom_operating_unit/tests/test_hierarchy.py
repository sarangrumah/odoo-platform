# -*- coding: utf-8 -*-
"""The unit tree, its constraints, and the idempotent ``_ensure`` provisioning API."""

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import OperatingUnitTestCommon


@tagged("post_install", "-at_install")
class TestOperatingUnitHierarchy(OperatingUnitTestCommon):
    def test_01_complete_name(self):
        self.assertEqual(self.ou_store_a.complete_name, "Head Office / Area Jakarta / Store A")

    def test_02_descendants(self):
        ids = self.ou_area._descendant_ids()
        self.assertIn(self.ou_store_a.id, ids)
        self.assertIn(self.ou_store_b.id, ids)
        self.assertNotIn(self.ou_store_c.id, ids)

    def test_03_cycle_refused(self):
        # Core's _parent_store machinery raises "Recursion Detected." before our
        # own constraint gets a chance; either way the cycle never lands.
        with self.assertRaises(UserError):
            self.ou_ho.write({"parent_id": self.ou_store_a.id})

    def test_04_one_head_office_per_company(self):
        with self.assertRaises(ValidationError):
            self._make_ou("HO2", "Second Head Office", ou_type="company")

    def test_05_head_office_has_no_parent(self):
        # A unit outside the HO subtree, so this is the Head-Office constraint
        # talking and not the recursion guard.
        outside = self._make_ou("OTH", "Outside", ou_type="other")
        with self.assertRaises(ValidationError):
            self.ou_ho.write({"parent_id": outside.id})

    def test_06_code_unique_per_company(self):
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._make_ou("ST-A", "Duplicate code")

    def test_07_ensure_is_idempotent_and_never_renames(self):
        again = self.OU._ensure("ST-A", "A COMPLETELY DIFFERENT NAME", self.company)
        self.assertEqual(again, self.ou_store_a)
        self.assertEqual(
            again.name, "Store A", "_ensure must never rename an existing unit"
        )

    def test_08_ensure_fills_only_empty_links(self):
        analytic_plan = self.env["account.analytic.plan"].create({"name": "OU Test Plan"})
        first, second = [
            self.env["account.analytic.account"].create(
                {"name": name, "plan_id": analytic_plan.id, "company_id": self.company.id}
            )
            for name in ("Analytic One", "Analytic Two")
        ]
        self.OU._ensure("ST-B", "Store B", self.company, analytic_account_id=first.id)
        self.assertEqual(self.ou_store_b.analytic_account_id, first)

        self.OU._ensure("ST-B", "Store B", self.company, analytic_account_id=second.id)
        self.assertEqual(
            self.ou_store_b.analytic_account_id, first, "an existing link must not be overwritten"
        )

    def test_09_ensure_creates_with_parent(self):
        created = self.OU._ensure("ST-D", "Store D", self.company, parent=self.ou_area)
        self.assertEqual(created.parent_id, self.ou_area)
        self.assertEqual(created.ou_type, "store")

    def test_10_analytic_index(self):
        plan = self.env["account.analytic.plan"].create({"name": "OU Index Plan"})
        analytic = self.env["account.analytic.account"].create(
            {"name": "Store C analytic", "plan_id": plan.id, "company_id": self.company.id}
        )
        self.ou_store_c.analytic_account_id = analytic.id
        self.assertEqual(self.OU._analytic_index().get(analytic.id), self.ou_store_c.id)
