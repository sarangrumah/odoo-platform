# -*- coding: utf-8 -*-
"""The leak test: raw-SQL reports must not show a store user another store's numbers."""

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReportOperatingUnitScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        OU = cls.env["operating.unit"]
        cls.ho = OU.with_context(active_test=False).search(
            [("ou_type", "=", "company"), ("company_id", "=", cls.company.id)], limit=1
        ) or OU.create(
            {"code": "ZZR-HO", "name": "Head Office", "ou_type": "company",
             "company_id": cls.company.id}
        )
        cls.unit_a = OU.create(
            {"code": "ZZR-A", "name": "Report Store A", "parent_id": cls.ho.id,
             "company_id": cls.company.id}
        )
        cls.unit_b = OU.create(
            {"code": "ZZR-B", "name": "Report Store B", "parent_id": cls.ho.id,
             "company_id": cls.company.id}
        )

        groups = (
            cls.env.ref("base.group_user")
            | cls.env.ref("account.group_account_user")
            | cls.env.ref("custom_accounting_reports.group_report_user")
        )
        cls.store_user = cls.env["res.users"].create(
            {
                "login": "ou.report.store@test",
                "name": "Store reader",
                "group_ids": [Command.set(groups.ids)],
                "operating_unit_ids": [Command.set([cls.unit_a.id])],
            }
        )

        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1
        )
        cls.account = cls.env["account.account"].search(
            [("company_ids", "in", cls.company.id)], limit=1
        )
        cls.move_a = cls._post_move(cls.unit_a, 100.0)
        cls.move_b = cls._post_move(cls.unit_b, 250.0)

    @classmethod
    def _post_move(cls, unit, amount):
        move = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": cls.journal.id,
                "operating_unit_id": unit.id,
                "line_ids": [
                    Command.create({"account_id": cls.account.id, "balance": amount}),
                    Command.create({"account_id": cls.account.id, "balance": -amount}),
                ],
            }
        )
        move.action_post()
        return move

    def _filters(self):
        return {
            "date_from": "1990-01-01",
            "date_to": "2099-12-31",
            "company_ids": [self.company.id],
            "posted_only": True,
        }

    def test_01_scoped_reader_only_sums_own_unit(self):
        engine = self.env["custom.report.engine"]
        totals_hq = engine._sum_by_account(self._filters())
        totals_store = engine.with_user(self.store_user)._sum_by_account(self._filters())

        debit_hq = sum(row["debit"] for row in totals_hq.values())
        debit_store = sum(row["debit"] for row in totals_store.values())

        self.assertGreaterEqual(debit_hq, 350.0)
        self.assertLess(
            debit_store,
            debit_hq,
            "a store reader must not sum another store's journal items",
        )

    def test_02_hook_is_a_no_op_for_an_unscoped_reader(self):
        sql, params = self.env["custom.report.engine"]._ou_sql_filter("aml")
        self.assertEqual((sql, params), ("", []))

    def test_03_hook_restricts_a_scoped_reader(self):
        engine = self.env["custom.report.engine"].with_user(self.store_user)
        sql, params = engine._ou_sql_filter("aml")
        self.assertIn("operating_unit_id", sql)
        self.assertEqual(params, [(self.unit_a.id,)])

    def test_04_wizard_filter_cannot_widen_the_scope(self):
        """An explicit unit filter narrows; it never becomes a way around isolation."""
        engine = self.env["custom.report.engine"].with_user(self.store_user)
        sql, params = engine.with_context(
            report_operating_unit_ids=[self.unit_b.id]
        )._ou_sql_filter("aml")
        self.assertEqual(sql, " AND FALSE")
        self.assertEqual(params, [])

    def test_05_branch_columns_are_restricted(self):
        report = self.env["custom.report.profit.loss.branch"]
        columns_hq = report._branch_columns()
        columns_store = report.with_user(self.store_user)._branch_columns()
        self.assertLessEqual(len(columns_store), len(columns_hq))
        self.assertFalse(
            [c for c in columns_store if c[2] is None],
            "the head-office residual column must not reach a scoped reader",
        )
