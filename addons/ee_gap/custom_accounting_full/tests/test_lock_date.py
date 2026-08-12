# -*- coding: utf-8 -*-
"""Lock Dates wizard — the CE gap left by EE account_accountant."""

from __future__ import annotations

from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestLockDateWizard(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.sudo().write(
            {
                fname: False
                for fname in ("fiscalyear_lock_date", "tax_lock_date", "sale_lock_date", "purchase_lock_date")
            }
        )
        self.Wizard = self.env["custom.account.lock.date.wizard"]

    def _wizard(self, **vals):
        return self.Wizard.create({"company_id": self.company.id, **vals})

    def test_defaults_mirror_the_company(self):
        self.company.sudo().fiscalyear_lock_date = date(2026, 6, 30)
        wiz = self._wizard()
        self.assertEqual(wiz.fiscalyear_lock_date, date(2026, 6, 30))
        self.assertFalse(wiz.tax_lock_date)

    def test_apply_writes_all_four_dates(self):
        wiz = self._wizard(
            fiscalyear_lock_date=date(2026, 6, 30),
            tax_lock_date=date(2026, 5, 31),
            sale_lock_date=date(2026, 6, 30),
            purchase_lock_date=date(2026, 6, 30),
        )
        wiz.action_apply()
        self.assertEqual(self.company.fiscalyear_lock_date, date(2026, 6, 30))
        self.assertEqual(self.company.tax_lock_date, date(2026, 5, 31))
        self.assertEqual(self.company.sale_lock_date, date(2026, 6, 30))
        self.assertEqual(self.company.purchase_lock_date, date(2026, 6, 30))

    def test_a_soft_lock_can_be_lifted_again(self):
        # The whole reason hard_lock_date is not offered: a mistake must be
        # correctable by the same accountant who made it.
        self._wizard(fiscalyear_lock_date=date(2026, 6, 30)).action_apply()
        self._wizard(fiscalyear_lock_date=False).action_apply()
        self.assertFalse(self.company.fiscalyear_lock_date)

    def test_apply_without_a_change_is_rejected(self):
        self.company.sudo().fiscalyear_lock_date = date(2026, 6, 30)
        wiz = self._wizard()
        with self.assertRaises(UserError):
            wiz.action_apply()

    def test_hard_lock_date_is_not_exposed(self):
        self.assertNotIn("hard_lock_date", self.Wizard._fields)

    def test_draft_entries_in_the_period_are_counted(self):
        journal = self.env["account.journal"].create(
            {"name": "Lock Test J", "code": "LCKJ", "type": "general", "company_id": self.company.id}
        )
        account = self.env["account.account"].create(
            {
                "code": "LCKTA",
                "name": "Lock Test",
                "account_type": "asset_current",
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date(2026, 6, 1),
                "move_type": "entry",
                "line_ids": [
                    (0, 0, {"account_id": account.id, "name": "d", "debit": 10.0, "credit": 0.0}),
                    (0, 0, {"account_id": account.id, "name": "c", "debit": 0.0, "credit": 10.0}),
                ],
            }
        )
        wiz = self._wizard(fiscalyear_lock_date=date(2026, 6, 30))
        self.assertGreaterEqual(wiz.draft_move_count, 1)

    def test_unreconciled_redirect_action_carries_views(self):
        # Core hands this dict straight to RedirectWarning, so the web client
        # gets an action object and never derives `views` from `view_mode` the
        # way /web/action/load would. Without `views`, _preprocessAction blows
        # up on `action.views.map(...)` and the warning's button is dead.
        Line = self.env["account.bank.statement.line"]
        for lines in (Line, Line.browse([1]), Line.browse([1, 2])):
            action = self.company._get_unreconciled_statement_lines_redirect_action(lines)
            self.assertTrue(action.get("views"), "no views for %s line(s)" % len(lines))
            self.assertEqual(
                [v[1] for v in action["views"]],
                action["view_mode"].split(","),
                "views must match view_mode",
            )

    def test_non_manager_cannot_apply(self):
        user = self.env["res.users"].create(
            {
                "name": "Lock Billing User",
                "login": "lock_billing_user",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "group_ids": [(6, 0, [self.env.ref("account.group_account_invoice").id])],
            }
        )
        # The ACL already stops a billing user at create(); the group check in
        # action_apply is the second line of defence for anyone who gets a
        # wizard record some other way.
        with self.assertRaises(AccessError):
            self.Wizard.with_user(user).create(
                {"company_id": self.company.id, "fiscalyear_lock_date": date(2026, 6, 30)}
            ).action_apply()
