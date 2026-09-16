# -*- coding: utf-8 -*-
"""Asset Register: the accounts on the row, the as-of date, and the posted basis.

Sheet rows #51 (accounts + location + qty on the register) and #60 (pull it to
a date, not just a year). The basis matters most: an opname is reconciled
against the ledger, so "accumulated depreciation" has to mean *booked*, not
*planned*.
"""

from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAssetRegister(TransactionCase):
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

        cls.acc_asset = account("Register Equipment", "150410", "asset_fixed")
        cls.acc_accum = account("Register Accum Dep", "150912", "asset_fixed")
        cls.acc_expense = account("Register Dep Expense", "610410", "expense")

        Journal = cls.env["account.journal"]
        cls.journal = Journal.search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1
        ) or Journal.create({"name": "Misc", "code": "MISCR", "type": "general", "company_id": cls.company.id})

        cls.location = cls.env["custom.fixed.asset.location"].create(
            {"name": "OLS SES - TEST STORE", "code": "T07-LOC"}
        )
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Operating Unit"})
        cls.ou = cls.env["account.analytic.account"].create({"name": "OLS SES - TEST STORE", "plan_id": cls.plan.id})

        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "Register Equipment",
                "code": "T07-EQ",
                "default_useful_life_months": 12,
                "default_asset_account_id": cls.acc_asset.id,
                "default_depreciation_account_id": cls.acc_accum.id,
                "default_expense_account_id": cls.acc_expense.id,
                "default_journal_id": cls.journal.id,
            }
        )
        cls.asset = cls.env["custom.fixed.asset"].create(
            {
                "name": "Register Asset",
                "code": "T07-A",
                "group_id": cls.group.id,
                "location_id": cls.location.id,
                "acquisition_date": date(2026, 1, 1),
                "acquisition_value": 1200.0,
                "analytic_distribution": {str(cls.ou.id): 100},
            }
        )
        cls.asset.action_confirm()
        cls.report = cls.env["custom.report.asset.register"]

    def _filters(self, **over):
        f = {
            "date_from": date(2026, 1, 1),
            "date_to": date(2026, 12, 31),
            "company_ids": [self.company.id],
            "group_ids": [],
            "location_ids": [],
            "asset_states": ["running"],
            "year": 2026,
            "basis": "posted",
        }
        f.update(over)
        return f

    def _row(self, filters):
        return next(r for r in self.report._build_lines(filters) if r.get("code") == "T07-A")

    def test_row_carries_accounts_location_and_operating_unit(self):
        """#51: the monthly review must not mean opening 148 asset forms."""
        row = self._row(self._filters(basis="schedule"))
        self.assertIn("150410", row["acc_asset"])
        self.assertIn("150912", row["acc_accum"])
        self.assertIn("610410", row["acc_expense"])
        self.assertIn("TEST STORE", row["location"])
        self.assertIn("TEST STORE", row["analytic"])
        self.assertEqual(row["qty"], self.asset.quantity)

        headers = [c["header"] for c in self.report._xlsx_columns()]
        for wanted in (
            "Location",
            "Operating Unit",
            "Qty",
            "Asset Account",
            "Accum. Dep. Account",
            "Dep. Expense Account",
            "Period",
        ):
            self.assertIn(wanted, headers)
        self.assertNotIn("YTD", headers, "renamed: the range need not start in January")

    def test_posted_basis_ignores_lines_the_ledger_never_booked(self):
        """The default basis is what the ledger carries."""
        posted = self._row(self._filters())
        self.assertEqual(posted["ytd"], 0.0, "nothing posted yet")
        self.assertEqual(posted["accum_end"], 0.0)
        self.assertEqual(posted["book"], 1200.0, "book value is still the full cost")

        schedule = self._row(self._filters(basis="schedule"))
        self.assertGreater(schedule["ytd"], 0.0, "the schedule has planned lines")
        self.assertNotEqual(posted["accum_end"], schedule["accum_end"], "the two bases must differ here")

    def test_posted_basis_follows_what_was_actually_posted(self):
        self.asset._post_due_depreciation(as_of=date(2026, 3, 31))
        booked = sum(self.asset.depreciation_line_ids.filtered("posted").mapped("amount"))
        self.assertGreater(booked, 0.0, "fixture must have posted something")

        row = self._row(self._filters())
        self.assertAlmostEqual(row["ytd"], booked, places=2)
        self.assertAlmostEqual(row["accum_end"], booked, places=2)
        self.assertAlmostEqual(row["book"], 1200.0 - booked, places=2)

    def test_as_of_date_cuts_the_period(self):
        """#60: a register pulled on the 31st of March is not a year-end one."""
        self.asset._post_due_depreciation(as_of=date(2026, 6, 30))

        whole = self._row(self._filters())
        march = self._row(self._filters(date_to=date(2026, 3, 31)))
        self.assertLess(march["ytd"], whole["ytd"], "a shorter period books less")
        self.assertGreater(march["book"], whole["book"], "and leaves more book value")

        # Nothing after the cut-off leaks into the month columns.
        self.assertEqual(march["m5"], 0.0, "June is past the 31 March cut-off")
        self.assertGreater(whole["m5"], 0.0)

    def test_date_from_moves_depreciation_into_opening(self):
        self.asset._post_due_depreciation(as_of=date(2026, 6, 30))
        whole = self._row(self._filters())
        later = self._row(self._filters(date_from=date(2026, 4, 1)))

        self.assertGreater(later["opening"], 0.0, "Jan-Mar is now opening, not period")
        self.assertLess(later["ytd"], whole["ytd"])
        self.assertAlmostEqual(
            later["opening"] + later["ytd"],
            whole["accum_end"],
            places=2,
            msg="splitting the range must not change the total",
        )
        self.assertAlmostEqual(later["accum_end"], whole["accum_end"], places=2)
