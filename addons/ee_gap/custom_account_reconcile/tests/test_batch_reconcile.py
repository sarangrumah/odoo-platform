# -*- coding: utf-8 -*-
"""Clearing massal (sheet #61) and the FIFO helper behind it."""

from datetime import date

from odoo.tests import TransactionCase, tagged

from ..tools.fifo import match_fifo


@tagged("post_install", "-at_install")
class TestFifoHelper(TransactionCase):
    def test_exact_pair(self):
        self.assertEqual(match_fifo([("d", 100.0)], [("c", 100.0)]), [("d", "c", 100.0)])

    def test_one_debit_covers_two_credits(self):
        self.assertEqual(
            match_fifo([("d", 100.0)], [("c1", 60.0), ("c2", 40.0)]),
            [("d", "c1", 60.0), ("d", "c2", 40.0)],
        )

    def test_oldest_first(self):
        pairs = match_fifo([("d1", 50.0), ("d2", 50.0)], [("c", 60.0)])
        self.assertEqual(pairs, [("d1", "c", 50.0), ("d2", "c", 10.0)])

    def test_a_crumb_is_not_worth_a_partial_reconcile(self):
        self.assertEqual(match_fifo([("d", 10.0)], [("c", 0.001)]), [])

    def test_inputs_are_not_mutated(self):
        debits = [("d", 100.0)]
        credits = [("c", 40.0)]
        match_fifo(debits, credits)
        self.assertEqual(debits, [("d", 100.0)])
        self.assertEqual(credits, [("c", 40.0)])


@tagged("post_install", "-at_install")
class TestBatchReconcileWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.account = cls.env["account.account"].create(
            {
                "code": "BR2100",
                "name": "Batch clearing test",
                "account_type": "liability_current",
                "reconcile": True,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.other = cls.env["account.account"].create(
            {
                "code": "BR1100",
                "name": "Batch counterpart test",
                "account_type": "asset_current",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {"name": "Batch clearing", "code": "BRJ", "type": "general", "company_id": cls.company.id}
        )
        cls.partner_a = cls.env["res.partner"].create({"name": "Batch partner A"})
        cls.partner_b = cls.env["res.partner"].create({"name": "Batch partner B"})

    def _entry(self, partner, amount, when):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "company_id": self.company.id,
                "date": when,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "x",
                            "account_id": self.account.id,
                            "partner_id": partner.id,
                            "debit": amount if amount > 0 else 0.0,
                            "credit": -amount if amount < 0 else 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "y",
                            "account_id": self.other.id,
                            "partner_id": partner.id,
                            "debit": -amount if amount < 0 else 0.0,
                            "credit": amount if amount > 0 else 0.0,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move

    def _wizard(self, **extra):
        return self.env["custom.account.reconcile.batch.wizard"].create(
            {
                "account_id": self.account.id,
                "company_id": self.company.id,
                "date_to": date(2030, 12, 31),
                **extra,
            }
        )

    def test_dry_run_changes_nothing(self):
        self._entry(self.partner_a, 100.0, date(2026, 1, 10))
        self._entry(self.partner_a, -100.0, date(2026, 1, 20))
        wizard = self._wizard(dry_run=True)
        wizard.action_run()
        self.assertEqual(wizard.matched_lines, 2)
        still_open = self.env["account.move.line"].search_count(wizard._line_domain())
        self.assertEqual(still_open, 2, "dry run must not reconcile anything")

    def test_a_matching_pair_is_cleared(self):
        self._entry(self.partner_a, 100.0, date(2026, 1, 10))
        self._entry(self.partner_a, -100.0, date(2026, 1, 20))
        wizard = self._wizard(dry_run=False, scope="partner")
        wizard.action_run()
        self.assertEqual(wizard.matched_lines, 2)
        self.assertEqual(wizard.remaining_lines, 0)

    def test_a_one_sided_group_is_left_alone(self):
        """An open position is not a reconciliation waiting to happen."""
        self._entry(self.partner_a, 100.0, date(2026, 1, 10))
        wizard = self._wizard(dry_run=False, scope="partner")
        wizard.action_run()
        self.assertEqual(wizard.matched_lines, 0)
        self.assertEqual(wizard.remaining_lines, 1)

    def test_scope_keeps_partners_apart(self):
        """Without scope these four lines net into one giant full reconcile."""
        self._entry(self.partner_a, 100.0, date(2026, 1, 10))
        self._entry(self.partner_b, -100.0, date(2026, 1, 20))
        wizard = self._wizard(dry_run=False, scope="partner")
        wizard.action_run()
        self.assertEqual(wizard.matched_lines, 0, "different partners must not be netted together")
        self.assertEqual(wizard.remaining_lines, 2)

    def test_group_key_separates_months(self):
        """Pure check: a tenant database's lock date can move a posted date,
        so the grouping itself is asserted on the key, not on what posted."""
        AML = self.env["account.move.line"]
        january = AML.new({"partner_id": self.partner_a.id, "date": date(2026, 1, 10)})
        february = AML.new({"partner_id": self.partner_a.id, "date": date(2026, 2, 10)})
        wizard = self._wizard(scope="partner_month")
        self.assertNotEqual(wizard._group_key(january), wizard._group_key(february))
        by_partner = self._wizard(scope="partner")
        self.assertEqual(by_partner._group_key(january), by_partner._group_key(february))

    def test_month_scope_keeps_months_apart(self):
        first = self._entry(self.partner_a, 100.0, date(2026, 1, 10))
        second = self._entry(self.partner_a, -100.0, date(2026, 2, 10))
        if first.date.strftime("%Y-%m") == second.date.strftime("%Y-%m"):
            # A lock date on this database pushed both entries into one period.
            self.skipTest("posting dates collapsed into one month on this database")
        wizard = self._wizard(dry_run=False, scope="partner_month")
        wizard.action_run()
        self.assertEqual(wizard.matched_lines, 0)
        wizard2 = self._wizard(dry_run=False, scope="partner")
        wizard2.action_run()
        self.assertEqual(wizard2.matched_lines, 2)

    def test_max_groups_bounds_the_run(self):
        for index in range(3):
            partner = self.env["res.partner"].create({"name": "Batch bulk %s" % index})
            self._entry(partner, 50.0, date(2026, 1, 10))
            self._entry(partner, -50.0, date(2026, 1, 20))
        wizard = self._wizard(dry_run=False, scope="partner", max_groups=1)
        wizard.action_run()
        self.assertEqual(wizard.matched_lines, 2, "only one group may be processed")
        self.assertIn("jalankan lagi", wizard.result_note.lower())

    def test_it_never_loads_the_lines_themselves(self):
        """The old wizard freezes precisely because it does."""
        self.assertNotIn("line_ids", self.env["custom.account.reconcile.batch.wizard"]._fields)
