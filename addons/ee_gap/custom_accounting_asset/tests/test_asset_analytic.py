# -*- coding: utf-8 -*-
"""The asset's analytic distribution has to reach the entries it writes.

Sheet row #57: "Analytical Distribution belum otomatis terisi di Jurnal
Depresiasi". Row #24 (remark 07/09) asks for the Operating Unit to be settable
at acquisition. Both come down to one rule — whatever analytic distribution the
asset carries, every journal entry generated from it carries too, on **both**
legs — plus one consequence: a grouped monthly entry must never roll two
Operating Units together, or the distribution it carries would be a lie.
"""

from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAssetAnalytic(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env["account.account"]

        def account(name, code, atype):
            return Account.create(
                {
                    "name": name,
                    "code": code,
                    "account_type": atype,
                    "company_ids": [(6, 0, [cls.company.id])],
                }
            )

        cls.acc_asset = account("Equipment", "150310", "asset_fixed")
        cls.acc_accum = account("Accum. dep. equipment", "150911", "asset_fixed")
        cls.acc_expense = account("Dep. expense equipment", "610310", "expense")

        Journal = cls.env["account.journal"]
        cls.journal = Journal.search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1
        ) or Journal.create({"name": "Misc", "code": "MISCB", "type": "general", "company_id": cls.company.id})

        Plan = cls.env["account.analytic.plan"]
        cls.plan = Plan.create({"name": "Operating Unit"})
        Analytic = cls.env["account.analytic.account"]
        cls.ou_one = Analytic.create({"name": "Store One", "plan_id": cls.plan.id})
        cls.ou_two = Analytic.create({"name": "Store Two", "plan_id": cls.plan.id})

        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "Equipment",
                "code": "T05-EQ",
                "default_useful_life_months": 12,
                "default_asset_account_id": cls.acc_asset.id,
                "default_depreciation_account_id": cls.acc_accum.id,
                "default_expense_account_id": cls.acc_expense.id,
                "default_journal_id": cls.journal.id,
            }
        )

    def _asset(self, code, distribution=None, value=1200.0):
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "Asset %s" % code,
                "code": code,
                "group_id": self.group.id,
                "acquisition_date": date(2026, 1, 1),
                "acquisition_value": value,
                "analytic_distribution": distribution or False,
            }
        )
        asset.action_confirm()
        return asset

    def test_depreciation_entry_carries_the_distribution_on_both_legs(self):
        asset = self._asset("T05-A", {str(self.ou_one.id): 100})
        self.assertTrue(asset._post_due_depreciation(as_of=date(2026, 2, 28)))

        move = asset.depreciation_line_ids.filtered("posted")[:1].move_id
        self.assertTrue(move, "a due line must have produced an entry")
        self.assertEqual(len(move.line_ids), 2)
        for line in move.line_ids:
            self.assertEqual(
                line.analytic_distribution,
                {str(self.ou_one.id): 100},
                "both legs carry the asset's distribution, not just the P&L one",
            )

    def test_an_asset_without_a_distribution_still_posts(self):
        """The field is optional. ARKA-AIM runs 3,590 assets without one."""
        asset = self._asset("T05-B")
        self.assertTrue(asset._post_due_depreciation(as_of=date(2026, 2, 28)))
        move = asset.depreciation_line_ids.filtered("posted")[:1].move_id
        self.assertTrue(move)
        self.assertFalse(any(line.analytic_distribution for line in move.line_ids))

    def test_two_operating_units_never_share_one_entry(self):
        """Grouping is on by default, so both assets would otherwise land in a
        single entry — which could then carry only one of the two stores."""
        first = self._asset("T05-C", {str(self.ou_one.id): 100})
        second = self._asset("T05-D", {str(self.ou_two.id): 100})

        (first | second)._post_due_depreciation(as_of=date(2026, 2, 28))
        moves = (first | second).depreciation_line_ids.filtered("posted").move_id
        self.assertEqual(len(moves), 2, "one entry per Operating Unit, per date")

        by_ou = {}
        for move in moves:
            distributions = {tuple(sorted((line.analytic_distribution or {}).items())) for line in move.line_ids}
            self.assertEqual(len(distributions), 1, "an entry carries exactly one distribution")
            by_ou[distributions.pop()] = move
        self.assertEqual(
            set(by_ou),
            {((str(self.ou_one.id), 100),), ((str(self.ou_two.id), 100),)},
        )

    def test_same_operating_unit_still_groups_into_one_entry(self):
        """The OU is added to the grouping key, not substituted for it: two
        assets in the same store must still produce one document."""
        first = self._asset("T05-E", {str(self.ou_one.id): 100})
        second = self._asset("T05-F", {str(self.ou_one.id): 100})

        (first | second)._post_due_depreciation(as_of=date(2026, 2, 28))
        moves = (first | second).depreciation_line_ids.filtered("posted").move_id
        self.assertEqual(len(moves), 1, "same store, same date -> one entry")

    def test_reversal_carries_the_distribution(self):
        asset = self._asset("T05-G", {str(self.ou_one.id): 100})
        asset._post_due_depreciation(as_of=date(2026, 2, 28))
        line = asset.depreciation_line_ids.filtered("posted")[:1]
        reversal = line._reverse_partial(line.move_id)
        self.assertEqual(len(reversal.line_ids), 2)
        for leg in reversal.line_ids:
            self.assertEqual(leg.analytic_distribution, {str(self.ou_one.id): 100})
