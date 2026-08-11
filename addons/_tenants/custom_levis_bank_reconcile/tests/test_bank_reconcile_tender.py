# -*- coding: utf-8 -*-
"""Line-by-line matching of Levi's bank settlements.

The fixtures mirror ``custom_levis_localization``'s clearing tests — own control
accounts, three per-tender receivables, two stores with their own analytic, and
narratives in the real BCA grammar — because the two flows must agree about what
a settlement is.

The assertions that matter are again the negative ones: that another store's
receivable is never offered, that a cash suggestion never proposes more than the
bank actually deposited, and that a settlement whose merchant id is unmapped
falls back to the generic matching instead of inventing a store.
"""

from datetime import date

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged

MID_ONE = "885004600001"
MID_TWO = "885004600002"
MID_UNMAPPED = "885004609999"


@tagged("post_install", "-at_install")
class TestBankReconcileTender(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        Account = cls.env["account.account"]

        def account(name, code, kind, reconcile=False):
            return Account.create({"name": name, "code": code, "account_type": kind, "reconcile": reconcile})

        cls.suspense = account("Bank Suspense", "RECSUS", "asset_current")
        cls.mdr = account("MDR Expense", "RECMDR", "expense")
        cls.ar = account("Trade Receivable", "RECAR", "asset_receivable", reconcile=True)
        cls.sweep = account("Main Bank", "RECSWP", "asset_cash")
        cls.charge = account("Bank Charges", "RECCHG", "expense")
        cls.tender_card = account("POS Debit Card", "RECT01", "asset_receivable", reconcile=True)
        cls.tender_cash = account("POS Cash", "RECT02", "asset_receivable", reconcile=True)
        cls.tenders = cls.tender_card + cls.tender_cash

        plan = cls.env["account.analytic.plan"].create({"name": "Reconcile OU"})
        cls.store_one = cls.env["account.analytic.account"].create({"name": "STORE ONE", "plan_id": plan.id})
        cls.store_two = cls.env["account.analytic.account"].create({"name": "STORE TWO", "plan_id": plan.id})

        cls.gljv = cls.env["account.journal"].create({"name": "Clearing Journal", "code": "RGLJ", "type": "general"})
        cls.bank = cls.env["account.journal"].create(
            {
                "name": "BCA test",
                "code": "RBCA",
                "type": "bank",
                "suspense_account_id": cls.suspense.id,
                "levis_clearing_format": "bca",
            }
        )
        cls.config = cls.env["levis.clearing.config"].create(
            {
                "company_id": cls.company.id,
                "journal_id": cls.gljv.id,
                "bank_journal_ids": [Command.set(cls.bank.ids)],
                "suspense_account_id": cls.suspense.id,
                "mdr_account_id": cls.mdr.id,
                "ar_account_id": cls.ar.id,
                "sweep_account_id": cls.sweep.id,
                "bank_charge_account_id": cls.charge.id,
                "pos_receivable_account_ids": [Command.set(cls.tenders.ids)],
                "settlement_lag_days": 1,
                "lookback_days": 10,
            }
        )
        cls.env["levis.bank.mid.map"].create(
            [
                {
                    "name": "Store one",
                    "company_id": cls.company.id,
                    "journal_id": cls.bank.id,
                    "match_type": "mid",
                    "key": MID_ONE,
                    "channel": "debit",
                    "analytic_account_id": cls.store_one.id,
                },
                {
                    "name": "Store two",
                    "company_id": cls.company.id,
                    "journal_id": cls.bank.id,
                    "match_type": "mid",
                    "key": MID_TWO,
                    "channel": "debit",
                    "analytic_account_id": cls.store_two.id,
                },
                {
                    "name": "Store one cash deposit",
                    "company_id": cls.company.id,
                    "journal_id": cls.bank.id,
                    "match_type": "keyword",
                    "key": "cash sales store one",
                    "channel": "cash",
                    "analytic_account_id": cls.store_one.id,
                },
            ]
        )

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    @classmethod
    def _posrec(cls, account, analytic, when, amount):
        move = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": cls.gljv.id,
                "company_id": cls.company.id,
                "date": when,
                "ref": "POS %s %s" % (analytic.name, when),
                "line_ids": [
                    Command.create(
                        {
                            "account_id": account.id,
                            "name": "POS receivable",
                            "debit": amount,
                            "credit": 0.0,
                            "analytic_distribution": {str(analytic.id): 100.0},
                        }
                    ),
                    Command.create(
                        {
                            "account_id": cls.company_data["default_account_revenue"].id,
                            "name": "Sales",
                            "debit": 0.0,
                            "credit": amount,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(lambda aml: aml.account_id == account)

    @classmethod
    def _statement(cls, when, amount, payment_ref):
        line = cls.env["account.bank.statement.line"].create(
            {"journal_id": cls.bank.id, "date": when, "amount": amount, "payment_ref": payment_ref}
        )
        if line.move_id.state == "draft":
            line.move_id.action_post()
        return line

    @classmethod
    def _settlement_ref(cls, mid, gross, mdr, trans_day=None):
        stamp = " TANGGAL :%02d/%02d" % (trans_day.day, trans_day.month) if trans_day else ""
        return "KR OTOMATIS%s MID : %s LEVIS TEST TGH: %.2f DDR: %.2f" % (stamp, mid, gross, mdr)

    def _wizard(self, st_line):
        return self.env["custom.bank.reconcile.wizard"].with_context(default_st_line_id=st_line.id).create({})

    # ------------------------------------------------------------------
    # 4. The statement line knows its store
    # ------------------------------------------------------------------
    def test_statement_line_carries_store_gross_and_fee(self):
        day = date(2026, 7, 8)
        line = self._statement(day, 4_689_356.40, self._settlement_ref(MID_ONE, 4_722_112.00, 32_755.60, day))
        self.assertEqual(line.levis_narrative_kind, "settlement")
        self.assertEqual(line.levis_ou_analytic_id, self.store_one)
        self.assertEqual(line.levis_mid, MID_ONE)
        self.assertAlmostEqual(line.levis_gross, 4_722_112.00, 2)
        self.assertAlmostEqual(line.levis_mdr, 32_755.60, 2)
        self.assertEqual(line.levis_trans_date, day)
        self.assertTrue(line.levis_amount_matches_narrative)

    def test_unmapped_merchant_leaves_the_store_empty(self):
        day = date(2026, 7, 8)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_UNMAPPED, 1_000_000.0, 10_000.0, day))
        self.assertEqual(line.levis_narrative_kind, "settlement")
        self.assertFalse(line.levis_ou_analytic_id)
        self.assertFalse(line._levis_is_tender_line())

    def test_a_narrative_that_disagrees_with_the_money_is_flagged(self):
        day = date(2026, 7, 8)
        line = self._statement(day, 900_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, day))
        self.assertFalse(line.levis_amount_matches_narrative)

    def test_rereading_picks_up_a_mapping_added_later(self):
        day = date(2026, 7, 8)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_UNMAPPED, 1_000_000.0, 10_000.0, day))
        self.assertFalse(line.levis_ou_analytic_id)
        self.env["levis.bank.mid.map"].create(
            {
                "name": "Late mapping",
                "company_id": self.company.id,
                "journal_id": self.bank.id,
                "match_type": "mid",
                "key": MID_UNMAPPED,
                "analytic_account_id": self.store_two.id,
            }
        )
        line.action_levis_reread_narrative()
        self.assertEqual(line.levis_ou_analytic_id, self.store_two)

    # ------------------------------------------------------------------
    # 1. + 2. Candidates: the right store, measured at gross
    # ------------------------------------------------------------------
    def test_candidates_are_the_gross_of_this_store_only(self):
        day = date(2026, 7, 8)
        mine = self._posrec(self.tender_card, self.store_one, day, 1_000_000.0)
        theirs = self._posrec(self.tender_card, self.store_two, day, 1_000_000.0)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, day))

        candidates = line._get_match_candidates()
        self.assertIn(mine, candidates)
        self.assertNotIn(theirs, candidates, "another outlet's receivable must never be offered")
        # The money that landed is 990 000; the receivable is 1 000 000. Matching
        # on the net would find nothing at all.
        self.assertEqual(line._levis_match_target(), 1_000_000.0)
        self.assertEqual(candidates[0], mine)

    def test_wizard_preselects_the_gross_and_prefills_the_fee(self):
        day = date(2026, 7, 8)
        aml = self._posrec(self.tender_card, self.store_one, day, 1_000_000.0)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, day))

        wizard = self._wizard(line)
        self.assertTrue(wizard.levis_is_tender)
        self.assertEqual(wizard.candidate_ids.filtered("selected").aml_id, aml)
        self.assertTrue(wizard.writeoff)
        self.assertEqual(wizard.writeoff_account_id, self.mdr)
        self.assertAlmostEqual(wizard.levis_gap, 0.0, 2)

    def test_candidate_rows_show_the_store_of_each_tender_line(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_card, self.store_one, day, 1_000_000.0)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, day))
        wizard = self._wizard(line)
        row = wizard.candidate_ids[0]
        self.assertEqual(row.levis_ou_analytic_id, self.store_one)
        self.assertTrue(row.levis_ou_matches)

    def test_reconciling_books_the_fee_to_mdr_with_the_store_analytic(self):
        day = date(2026, 7, 8)
        aml = self._posrec(self.tender_card, self.store_one, day, 1_000_000.0)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, day))

        self._wizard(line).action_reconcile()

        self.assertTrue(aml.reconciled, "the receivable must clear at its full gross")
        fee = line.move_id.line_ids.filtered(lambda aml_: aml_.account_id == self.mdr)
        self.assertEqual(len(fee), 1)
        self.assertAlmostEqual(fee.balance, 10_000.0, 2)
        self.assertEqual(fee.analytic_distribution, {str(self.store_one.id): 100.0})
        self.assertFalse(
            line.move_id.line_ids.filtered(lambda aml_: aml_.account_id == self.suspense),
            "nothing may be left parked on suspense",
        )

    def test_the_fee_account_may_only_absorb_the_printed_fee(self):
        """A shortfall must not be booked as MDR just because the box is ticked."""
        day = date(2026, 7, 8)
        part_one = self._posrec(self.tender_card, self.store_one, day, 600_000.0)
        self._posrec(self.tender_card, self.store_one, day, 400_000.0)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, day))

        wizard = self._wizard(line)
        wizard.candidate_ids.selected = False
        wizard.candidate_ids.filtered(lambda c: c.aml_id == part_one).selected = True
        with self.assertRaises(UserError):
            wizard.action_reconcile()

        wizard.candidate_ids.selected = True
        wizard.action_reconcile()
        fee = line.move_id.line_ids.filtered(lambda aml_: aml_.account_id == self.mdr)
        self.assertAlmostEqual(fee.balance, 10_000.0, 2)

    def test_unmapped_line_falls_back_to_the_generic_matching(self):
        day = date(2026, 7, 8)
        other = self._posrec(self.ar, self.store_two, day, 990_000.0)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_UNMAPPED, 1_000_000.0, 10_000.0, day))
        wizard = self._wizard(line)
        self.assertFalse(wizard.levis_is_tender)
        # Generic scoring: exact residual against the amount that landed.
        self.assertIn(other, wizard.candidate_ids.mapped("aml_id"))
        with self.assertRaises(UserError):
            wizard.action_levis_suggest()

    # ------------------------------------------------------------------
    # 3. Cash: a suggestion that never exceeds the deposit
    # ------------------------------------------------------------------
    def test_cash_suggestion_stops_at_the_deposit(self):
        days = [date(2026, 7, 5), date(2026, 7, 6), date(2026, 7, 7)]
        for when, amount in zip(days, (4_000_000.0, 3_000_000.0, 2_500_000.0)):
            self._posrec(self.tender_cash, self.store_one, when, amount)
        line = self._statement(
            date(2026, 7, 8), 7_000_000.0, "TRSF E-BANKING CR 0807/FTSCY/WS95031 cash sales store one"
        )
        self.assertEqual(line.levis_narrative_kind, "cash_deposit")
        self.assertEqual(line.levis_ou_analytic_id, self.store_one)

        wizard = self._wizard(line)
        wizard.action_levis_suggest()
        picked = wizard.candidate_ids.filtered("selected")
        total = sum(picked.mapped("amount_residual"))
        self.assertLessEqual(total, 7_000_000.0, "never propose more cash than the bank received")
        self.assertAlmostEqual(total, 7_000_000.0, 2, "4 jt + 3 jt fits exactly")
        self.assertEqual(len(picked), 2)

    def test_cash_suggestion_leaves_the_shortfall_open_on_suspense(self):
        self._posrec(self.tender_cash, self.store_one, date(2026, 7, 5), 4_000_000.0)
        line = self._statement(
            date(2026, 7, 8), 6_000_000.0, "TRSF E-BANKING CR 0807/FTSCY/WS95031 cash sales store one"
        )
        wizard = self._wizard(line)
        wizard.action_levis_suggest()
        self.assertAlmostEqual(wizard.levis_gap, 2_000_000.0, 2)
        wizard.action_reconcile()
        left = line.move_id.line_ids.filtered(lambda aml: aml.account_id == self.suspense)
        self.assertAlmostEqual(sum(left.mapped("balance")), -2_000_000.0, 2)

    def test_cash_suggestion_ignores_another_store(self):
        self._posrec(self.tender_cash, self.store_two, date(2026, 7, 5), 5_000_000.0)
        line = self._statement(
            date(2026, 7, 8), 5_000_000.0, "TRSF E-BANKING CR 0807/FTSCY/WS95031 cash sales store one"
        )
        wizard = self._wizard(line)
        with self.assertRaises(UserError):
            wizard.action_levis_suggest()

    # ------------------------------------------------------------------
    # Auto-match
    # ------------------------------------------------------------------
    def test_auto_match_uses_the_gross_and_skips_cash(self):
        day = date(2026, 7, 8)
        aml = self._posrec(self.tender_card, self.store_one, day, 1_000_000.0)
        line = self._statement(day, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, day))
        self.assertEqual(line._get_auto_match_candidate(), aml)

        self._posrec(self.tender_cash, self.store_one, day, 500_000.0)
        cash = self._statement(day, 500_000.0, "TRSF E-BANKING CR 0807/FTSCY/WS95031 cash sales store one")
        self.assertFalse(
            cash._get_auto_match_candidate(),
            "a deposit is a sum of days — it must not be auto-matched on one coincidence",
        )
