# -*- coding: utf-8 -*-
"""Operating Unit is mandatory on P&L lines (sheet row #36).

The switch defaults OFF, so the first thing these lock is that an untouched
database behaves exactly as it did — a guard that changes behaviour before
anyone asks for it is worse than no guard.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOuRequired(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Move = cls.env["account.move"]
        cls.param = cls.env["ir.config_parameter"].sudo()

        Account = cls.env["account.account"]
        cls.expense = Account.create(
            {
                "name": "Bank admin charges (test)",
                "code": "7999001",
                "account_type": "expense",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.bank = Account.create(
            {
                "name": "Bank clearing (test)",
                "code": "1102999",
                "account_type": "asset_cash",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {"name": "OU guard test", "code": "TOUG", "type": "general", "company_id": cls.company.id}
        )
        plan = cls.env["account.analytic.plan"].search([("name", "=", "Operating Unit")], limit=1)
        if not plan:
            plan = cls.env["account.analytic.plan"].create({"name": "Operating Unit"})
        cls.plan = plan
        cls.ou = cls.env["account.analytic.account"].create(
            {"name": "OU guard store", "plan_id": plan.id, "company_id": cls.company.id}
        )

    def _entry(self, ou=None):
        line = {
            "name": "Bank admin fee",
            "account_id": self.expense.id,
            "debit": 1500.0,
            "credit": 0.0,
        }
        if ou:
            line["l10n_ou_analytic_id"] = ou.id
        return self.Move.create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "company_id": self.company.id,
                "line_ids": [
                    (0, 0, line),
                    (0, 0, {"name": "Bank", "account_id": self.bank.id, "debit": 0.0, "credit": 1500.0}),
                ],
            }
        )

    def _switch(self, value):
        self.param.set_param("custom_levis_localization.ou_required_pl", value)

    # --- the switch ----------------------------------------------------
    def test_off_by_default_posts_without_an_ou(self):
        self._switch("0")
        move = self._entry()
        move.action_post()
        self.assertEqual(move.state, "posted")

    def test_on_refuses_a_pl_line_without_an_ou(self):
        self._switch("1")
        move = self._entry()
        with self.assertRaises(UserError) as caught:
            move.action_post()
        # The message has to name the line, or nobody can act on it.
        self.assertIn(self.expense.code, str(caught.exception))
        self.assertEqual(move.state, "draft")

    def test_on_accepts_a_pl_line_that_carries_one(self):
        self._switch("1")
        move = self._entry(ou=self.ou)
        move.action_post()
        self.assertEqual(move.state, "posted")

    def test_a_balance_sheet_line_needs_no_ou(self):
        """1xxx accounts are out of scope even with the switch on."""
        self._switch("1")
        move = self.Move.create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "company_id": self.company.id,
                "line_ids": [
                    (0, 0, {"name": "in", "account_id": self.bank.id, "debit": 1000.0, "credit": 0.0}),
                    (0, 0, {"name": "out", "account_id": self.bank.id, "debit": 0.0, "credit": 1000.0}),
                ],
            }
        )
        move.action_post()
        self.assertEqual(move.state, "posted")

    def test_the_context_override_lets_it_through(self):
        self._switch("1")
        move = self._entry()
        move.with_context(levis_skip_ou_required=True).action_post()
        self.assertEqual(move.state, "posted")

    # --- how the OU is recognised --------------------------------------
    def test_an_ou_inside_a_multi_plan_distribution_counts(self):
        """The OU can sit anywhere in a comma-joined analytic key."""
        self._switch("1")
        other_plan = self.env["account.analytic.plan"].create({"name": "OU guard other plan"})
        other = self.env["account.analytic.account"].create(
            {"name": "Project X", "plan_id": other_plan.id, "company_id": self.company.id}
        )
        move = self._entry()
        line = move.line_ids.filtered(lambda ln: ln.account_id == self.expense)
        line.analytic_distribution = {"%s,%s" % (other.id, self.ou.id): 100.0}
        move.action_post()
        self.assertEqual(move.state, "posted")

    def test_a_distribution_without_the_ou_plan_does_not_count(self):
        self._switch("1")
        other_plan = self.env["account.analytic.plan"].create({"name": "OU guard other plan 2"})
        other = self.env["account.analytic.account"].create(
            {"name": "Project Y", "plan_id": other_plan.id, "company_id": self.company.id}
        )
        move = self._entry()
        line = move.line_ids.filtered(lambda ln: ln.account_id == self.expense)
        line.analytic_distribution = {str(other.id): 100.0}
        with self.assertRaises(UserError):
            move.action_post()

    def test_pl_account_ids_reads_the_company_column(self):
        ids = self.Move._levis_pl_account_ids(self.company)
        self.assertIn(self.expense.id, ids)
        self.assertNotIn(self.bank.id, ids)
