# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPooledFixedAsset(TransactionCase):
    """A pooled asset: 5 waste bins under one asset number, one of them breaks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env["account.account"]
        cls.asset_account = Account.create(
            {
                "name": "FA - Equipment",
                "code": "150110",
                "account_type": "asset_fixed",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.accum_account = Account.create(
            {
                "name": "FA - Accum. Depreciation",
                "code": "150910",
                "account_type": "asset_fixed",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.expense_account = Account.create(
            {
                "name": "Depreciation Expense",
                "code": "610110",
                "account_type": "expense",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.loss_account = Account.create(
            {
                "name": "Loss on retirement",
                "code": "699110",
                "account_type": "expense",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.gain_account = Account.create(
            {
                "name": "Gain on retirement",
                "code": "799110",
                "account_type": "income_other",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.proceeds_account = Account.create(
            {
                "name": "Retirement proceeds clearing",
                "code": "110910",
                "account_type": "asset_current",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        Journal = cls.env["account.journal"]
        cls.journal = Journal.search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)],
            limit=1,
        ) or Journal.create(
            {
                "name": "Misc Operations",
                "code": "MISCQ",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "Bins",
                "code": "BIN",
                "default_useful_life_months": 10,
                "default_asset_account_id": cls.asset_account.id,
                "default_depreciation_account_id": cls.accum_account.id,
                "default_expense_account_id": cls.expense_account.id,
                "default_journal_id": cls.journal.id,
            }
        )

    def _make_pool(self, quantity=5.0, value=5000.0):
        """5 bins at 1,000 each, depreciated over 10 months = 500/month."""
        return self.env["custom.fixed.asset"].create(
            {
                "name": "Waste bin",
                "group_id": self.group.id,
                "acquisition_date": date(2025, 1, 1),
                "acquisition_value": value,
                "quantity": quantity,
                "useful_life_months": 10,
                "depreciation_method": "straight_line",
                "asset_account_id": self.asset_account.id,
                "depreciation_account_id": self.accum_account.id,
                "expense_account_id": self.expense_account.id,
                "journal_id": self.journal.id,
            }
        )

    def _retire(self, asset, quantity=1.0, proceeds=0.0, on=date(2025, 3, 31)):
        wiz = self.env["custom.fixed.asset.partial.disposal.wizard"].create(
            {
                "asset_id": asset.id,
                "quantity": quantity,
                "disposal_date": on,
                "reason": "scrap",
                "proceeds": proceeds,
                "loss_account_id": self.loss_account.id,
                "gain_account_id": self.gain_account.id,
                "receivable_account_id": self.proceeds_account.id,
                "create_journal_entry": True,
            }
        )
        return wiz

    def test_01_pool_created_with_quantity(self):
        asset = self._make_pool()
        self.assertEqual(asset.original_quantity, 5.0)
        self.assertTrue(asset.is_quantity_asset)
        self.assertAlmostEqual(asset.unit_acquisition_value, 1000.0, places=2)
        asset.action_confirm()
        self.assertEqual(len(asset.depreciation_line_ids), 10)
        self.assertAlmostEqual(asset.depreciation_line_ids[0].amount, 500.0, places=2)

    def test_02_retire_one_of_five_reduces_value_and_schedule(self):
        asset = self._make_pool()
        asset.action_confirm()
        # Two months posted: 1,000 accumulated, NBV 4,000.
        asset._post_due_depreciation(as_of=date(2025, 3, 10))
        self.assertAlmostEqual(asset.accumulated_depreciation, 1000.0, places=2)

        wiz = self._retire(asset)
        # A fifth of everything goes out with the broken bin.
        self.assertAlmostEqual(wiz.cost_removed, 1000.0, places=2)
        self.assertAlmostEqual(wiz.accumulated_removed, 200.0, places=2)
        self.assertAlmostEqual(wiz.net_book_value_removed, 800.0, places=2)
        self.assertAlmostEqual(wiz.gain_loss, -800.0, places=2)
        wiz.action_retire()

        self.assertEqual(asset.state, "running")
        self.assertAlmostEqual(asset.quantity, 4.0, places=2)
        self.assertAlmostEqual(asset.original_quantity, 5.0, places=2)
        self.assertAlmostEqual(asset.retired_quantity, 1.0, places=2)
        self.assertAlmostEqual(asset.acquisition_value, 4000.0, places=2)
        self.assertAlmostEqual(asset.accumulated_depreciation, 800.0, places=2)
        self.assertAlmostEqual(asset.net_book_value, 3200.0, places=2)
        self.assertAlmostEqual(asset.unit_acquisition_value, 1000.0, places=2)

        # The remaining 8 months now depreciate four bins: 3,200 / 8 = 400.
        remaining = asset.depreciation_line_ids.filtered(lambda line: not line.posted and not line.reversed)
        self.assertEqual(len(remaining), 8)
        self.assertAlmostEqual(sum(remaining.mapped("amount")), 3200.0, places=2)
        for line in remaining:
            self.assertAlmostEqual(line.amount, 400.0, places=2)
        # Posted history is untouched.
        self.assertEqual(len(asset.depreciation_line_ids.filtered("posted")), 2)

    def test_03_retirement_entry_is_balanced_and_hits_the_right_accounts(self):
        asset = self._make_pool()
        asset.action_confirm()
        asset._post_due_depreciation(as_of=date(2025, 3, 10))
        wiz = self._retire(asset)
        wiz.action_retire()

        record = asset.partial_disposal_ids
        self.assertEqual(len(record), 1)
        self.assertAlmostEqual(record.quantity_before, 5.0, places=2)
        self.assertAlmostEqual(record.quantity_after, 4.0, places=2)
        move = record.move_id
        self.assertTrue(move)
        self.assertEqual(move.state, "posted")
        self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit")), places=2)
        by_account = {line.account_id: line.debit - line.credit for line in move.line_ids}
        self.assertAlmostEqual(by_account[self.accum_account], 200.0, places=2)
        self.assertAlmostEqual(by_account[self.asset_account], -1000.0, places=2)
        self.assertAlmostEqual(by_account[self.loss_account], 800.0, places=2)

    def test_04_retirement_with_proceeds_books_a_gain(self):
        asset = self._make_pool()
        asset.action_confirm()
        asset._post_due_depreciation(as_of=date(2025, 3, 10))
        wiz = self._retire(asset, proceeds=1000.0)
        self.assertAlmostEqual(wiz.gain_loss, 200.0, places=2)
        wiz.action_retire()
        move = asset.partial_disposal_ids.move_id
        by_account = {line.account_id: line.debit - line.credit for line in move.line_ids}
        self.assertAlmostEqual(by_account[self.gain_account], -200.0, places=2)
        self.assertAlmostEqual(by_account[self.proceeds_account], 1000.0, places=2)

    def test_05_retiring_every_unit_disposes_the_asset(self):
        asset = self._make_pool()
        asset.action_confirm()
        asset._post_due_depreciation(as_of=date(2025, 3, 10))
        wiz = self._retire(asset, quantity=5.0)
        wiz.action_retire()
        self.assertEqual(asset.state, "disposed")
        self.assertTrue(asset.disposal_move_id)
        self.assertFalse(asset.depreciation_line_ids.filtered(lambda line: not line.posted and not line.reversed))

    def test_06_cannot_retire_more_than_held(self):
        asset = self._make_pool()
        asset.action_confirm()
        wiz = self._retire(asset, quantity=6.0)
        with self.assertRaises(UserError):
            wiz.action_retire()

    def test_07_quantity_cannot_grow_past_the_original(self):
        asset = self._make_pool()
        asset.action_confirm()
        with self.assertRaises(ValidationError):
            asset.quantity = 6.0

    def test_08_single_unit_asset_has_no_retire_button(self):
        asset = self._make_pool(quantity=1.0, value=1000.0)
        asset.action_confirm()
        self.assertFalse(asset.is_quantity_asset)
        with self.assertRaises(UserError):
            asset.action_open_partial_disposal_wizard()

    def test_09_successive_retirements_keep_the_pool_consistent(self):
        asset = self._make_pool()
        asset.action_confirm()
        asset._post_due_depreciation(as_of=date(2025, 3, 10))
        self._retire(asset).action_retire()
        self._retire(asset, on=date(2025, 4, 30)).action_retire()
        self.assertAlmostEqual(asset.quantity, 3.0, places=2)
        self.assertAlmostEqual(asset.acquisition_value, 3000.0, places=2)
        self.assertAlmostEqual(asset.accumulated_depreciation, 600.0, places=2)
        self.assertAlmostEqual(asset.net_book_value, 2400.0, places=2)
        self.assertEqual(len(asset.partial_disposal_ids), 2)
        remaining = asset.depreciation_line_ids.filtered(lambda line: not line.posted and not line.reversed)
        self.assertAlmostEqual(sum(remaining.mapped("amount")), 2400.0, places=2)

    def test_10_merging_per_unit_assets_creates_a_pool(self):
        """Five bins booked one record each become one pooled asset of five."""
        assets = self.env["custom.fixed.asset"]
        for _i in range(5):
            assets |= self._make_pool(quantity=1.0, value=1000.0)
        assets.action_confirm()
        assets._post_due_depreciation(as_of=date(2025, 3, 10))
        # Each carries 2 months of 100 (1,000 over 10 months).
        for asset in assets:
            self.assertAlmostEqual(asset.accumulated_depreciation, 200.0, places=2)
        nbv_before = sum(assets.mapped("net_book_value"))

        survivor = assets[0]
        survivor._merge_assets_into_pool(assets[1:])

        self.assertAlmostEqual(survivor.quantity, 5.0, places=2)
        self.assertAlmostEqual(survivor.original_quantity, 5.0, places=2)
        self.assertTrue(survivor.is_quantity_asset)
        self.assertAlmostEqual(survivor.acquisition_value, 5000.0, places=2)
        # 200 of its own posted lines + 800 carried from the four absorbed ones.
        self.assertAlmostEqual(survivor.opening_accumulated_depreciation, 800.0, places=2)
        self.assertAlmostEqual(survivor.accumulated_depreciation, 1000.0, places=2)
        self.assertAlmostEqual(survivor.net_book_value, 4000.0, places=2)
        self.assertAlmostEqual(survivor.net_book_value, nbv_before, places=2)

        absorbed = assets[1:]
        self.assertEqual(set(absorbed.mapped("state")), {"cancelled"})
        self.assertEqual(set(absorbed.mapped("merged_into_id")), {survivor})
        # Posted history stays attached to the record it was booked against.
        self.assertTrue(all(a.depreciation_line_ids.filtered("posted") for a in absorbed))
        self.assertFalse(absorbed.depreciation_line_ids.filtered(lambda line: not line.posted))

        # And the pool now depreciates five bins over the remaining 8 months.
        remaining = survivor.depreciation_line_ids.filtered(lambda line: not line.posted and not line.reversed)
        self.assertEqual(len(remaining), 8)
        self.assertAlmostEqual(sum(remaining.mapped("amount")), 4000.0, places=2)
        self.assertAlmostEqual(remaining[0].amount, 500.0, places=2)

    def test_11_retiring_from_a_merged_pool_keeps_the_maths(self):
        assets = self.env["custom.fixed.asset"]
        for _i in range(5):
            assets |= self._make_pool(quantity=1.0, value=1000.0)
        assets.action_confirm()
        assets._post_due_depreciation(as_of=date(2025, 3, 10))
        survivor = assets[0]
        survivor._merge_assets_into_pool(assets[1:])

        wiz = self._retire(survivor)
        self.assertAlmostEqual(wiz.cost_removed, 1000.0, places=2)
        self.assertAlmostEqual(wiz.accumulated_removed, 200.0, places=2)
        wiz.action_retire()
        self.assertAlmostEqual(survivor.quantity, 4.0, places=2)
        self.assertAlmostEqual(survivor.accumulated_depreciation, 800.0, places=2)
        self.assertAlmostEqual(survivor.net_book_value, 3200.0, places=2)
