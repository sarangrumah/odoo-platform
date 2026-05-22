# -*- coding: utf-8 -*-
from datetime import date


from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCustomFixedAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Account = cls.env["account.account"]
        cls.Journal = cls.env["account.journal"]

        cls.asset_account = cls.Account.create(
            {
                "name": "FA - Equipment",
                "code": "150100",
                "account_type": "asset_fixed",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.accum_account = cls.Account.create(
            {
                "name": "FA - Accum. Depreciation",
                "code": "150900",
                "account_type": "asset_fixed",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.expense_account = cls.Account.create(
            {
                "name": "Depreciation Expense",
                "code": "610100",
                "account_type": "expense",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.journal = cls.Journal.search(
            [
                ("type", "=", "general"),
                ("company_id", "=", cls.company.id),
            ],
            limit=1,
        ) or cls.Journal.create(
            {
                "name": "Misc Operations",
                "code": "MISC",
                "type": "general",
                "company_id": cls.company.id,
            }
        )

        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "Equipment",
                "code": "EQ",
                "default_useful_life_months": 12,
                "default_asset_account_id": cls.asset_account.id,
                "default_depreciation_account_id": cls.accum_account.id,
                "default_expense_account_id": cls.expense_account.id,
                "default_journal_id": cls.journal.id,
            }
        )

    def _make_asset(self, **overrides):
        vals = {
            "name": "Test Laptop",
            "group_id": self.group.id,
            "acquisition_date": date(2025, 1, 1),
            "acquisition_value": 12000.0,
            "salvage_value": 0.0,
            "useful_life_months": 12,
            "depreciation_method": "straight_line",
            "asset_account_id": self.asset_account.id,
            "depreciation_account_id": self.accum_account.id,
            "expense_account_id": self.expense_account.id,
            "journal_id": self.journal.id,
        }
        vals.update(overrides)
        return self.env["custom.fixed.asset"].create(vals)

    def test_01_create_and_build_schedule(self):
        asset = self._make_asset()
        self.assertEqual(asset.state, "draft")
        self.assertTrue(asset.code and asset.code != "New")
        asset.action_confirm()
        self.assertEqual(asset.state, "running")
        self.assertEqual(len(asset.depreciation_line_ids), 12)
        # Sum of schedule equals depreciable base.
        total = sum(asset.depreciation_line_ids.mapped("amount"))
        self.assertAlmostEqual(total, 12000.0, places=2)
        # First line dated one month after acquisition.
        first = asset.depreciation_line_ids.sorted("sequence")[0]
        self.assertEqual(first.date, date(2025, 2, 1))

    def test_02_post_three_months(self):
        asset = self._make_asset()
        asset.action_confirm()
        as_of = date(2025, 4, 5)
        posted = asset._post_due_depreciation(as_of=as_of)
        self.assertEqual(posted, 3)
        posted_lines = asset.depreciation_line_ids.filtered("posted")
        self.assertEqual(len(posted_lines), 3)
        for line in posted_lines:
            self.assertTrue(line.move_id)
            self.assertEqual(line.move_id.state, "posted")
        # Accumulated depreciation should be 3 months worth (3000) and NBV 9000.
        self.assertAlmostEqual(asset.accumulated_depreciation, 3000.0, places=2)
        self.assertAlmostEqual(asset.net_book_value, 9000.0, places=2)

    def test_03_dispose_with_gain(self):
        asset = self._make_asset()
        asset.action_confirm()
        asset._post_due_depreciation(as_of=date(2025, 4, 5))

        gain_account = self.Account.create(
            {
                "name": "Gain on disposal",
                "code": "799100",
                "account_type": "income_other",
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        loss_account = self.Account.create(
            {
                "name": "Loss on disposal",
                "code": "699100",
                "account_type": "expense",
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        proceeds_account = self.Account.create(
            {
                "name": "Disposal proceeds clearing",
                "code": "110900",
                "account_type": "asset_current",
                "company_ids": [(6, 0, [self.company.id])],
            }
        )

        wiz = self.env["custom.fixed.asset.disposal.wizard"].create(
            {
                "asset_id": asset.id,
                "disposal_date": date(2025, 4, 30),
                "disposal_value": 10000.0,  # NBV is 9000 -> 1000 gain
                "gain_account_id": gain_account.id,
                "loss_account_id": loss_account.id,
                "receivable_account_id": proceeds_account.id,
                "create_journal_entry": True,
            }
        )
        self.assertAlmostEqual(wiz.gain_loss, 1000.0, places=2)
        wiz.action_dispose()
        self.assertEqual(asset.state, "disposed")
        self.assertAlmostEqual(asset.disposal_gain_loss, 1000.0, places=2)
        self.assertTrue(asset.disposal_move_id)
        # Move balanced.
        move = asset.disposal_move_id
        debits = sum(move.line_ids.mapped("debit"))
        credits = sum(move.line_ids.mapped("credit"))
        self.assertAlmostEqual(debits, credits, places=2)

    def test_04_constraints_and_cancel(self):
        # Salvage > acquisition forbidden.
        with self.assertRaises(ValidationError):
            self._make_asset(salvage_value=20000.0)
        # Useful life zero forbidden.
        with self.assertRaises(ValidationError):
            self._make_asset(useful_life_months=0)
        # Cancel from draft works; reset works.
        a = self._make_asset()
        a.action_cancel()
        self.assertEqual(a.state, "cancelled")
        a.action_reset_draft()
        self.assertEqual(a.state, "draft")
        # Cannot dispose draft asset.
        with self.assertRaises(UserError):
            a.action_open_dispose_wizard()

    def test_05_cron_posts_due_only(self):
        a1 = self._make_asset(name="Asset A")
        a2 = self._make_asset(name="Asset B")
        a1.action_confirm()
        a2.action_confirm()
        # Simulate cron run with a frozen as_of through direct invocation.
        with self._mock_today(date(2025, 3, 15)):
            count = self.env["custom.fixed.asset"]._cron_post_due_depreciation()
        # Two assets, 2 months due each -> 4 lines posted.
        self.assertEqual(count, 4)

    def _mock_today(self, today):
        """Lightweight context manager that monkey-patches
        fields.Date.context_today for the duration of the with-block.
        """
        from contextlib import contextmanager
        from odoo import fields as odoo_fields

        original = odoo_fields.Date.context_today

        @contextmanager
        def _cm():
            odoo_fields.Date.context_today = staticmethod(lambda *a, **k: today)
            try:
                yield
            finally:
                odoo_fields.Date.context_today = original

        return _cm()
