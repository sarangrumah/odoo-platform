# -*- coding: utf-8 -*-
"""Monthly POS clearing (``levis.pos.clearing``).

Self-contained fixtures: own control accounts, three per-tender receivable
accounts, a bank journal parking on its own suspense account, two stores with
their own Operating-Unit analytic, and hand-written narratives in the real BCA
grammar.

The assertions that matter most are the negative ones: that computing a summary
writes nothing, that an unmapped terminal blocks generation instead of guessing,
and that a store which came up short is not quietly covered by another store's
excess on the same account.
"""

from datetime import date

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged

MID_ONE = "885004600001"
MID_TWO = "885004600002"
# Deliberately has no mapping rule: this is what the mapping wizard must find.
MID_UNMAPPED = "885004600009"


@tagged("post_install", "-at_install")
class TestPosClearing(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        Account = cls.env["account.account"]

        def account(name, code, kind, reconcile=False):
            return Account.create({"name": name, "code": code, "account_type": kind, "reconcile": reconcile})

        # The suspense account is deliberately NOT reconcilable, as in production:
        # it can only be balanced, never matched.
        cls.suspense = account("Bank Suspense", "CLRSUS", "asset_current")
        cls.mdr = account("MDR Expense", "CLRMDR", "expense")
        cls.ar = account("Trade Receivable", "CLRAR", "asset_receivable", reconcile=True)
        cls.sweep = account("Main Bank", "CLRSWP", "asset_cash")
        cls.charge = account("Bank Charges", "CLRCHG", "expense")
        cls.tender_a = account("POS Debit Card", "CLRT01", "asset_receivable", reconcile=True)
        cls.tender_b = account("POS Credit Card", "CLRT02", "asset_receivable", reconcile=True)
        cls.tender_c = account("POS Cash", "CLRT03", "asset_receivable", reconcile=True)
        cls.tenders = cls.tender_a + cls.tender_b + cls.tender_c

        plan = cls.env["account.analytic.plan"].create({"name": "Clearing OU"})
        cls.store_one = cls.env["account.analytic.account"].create({"name": "STORE ONE", "plan_id": plan.id})
        cls.store_two = cls.env["account.analytic.account"].create({"name": "STORE TWO", "plan_id": plan.id})

        cls.gljv = cls.env["account.journal"].create({"name": "Clearing Journal", "code": "TGLJ", "type": "general"})
        cls.bank = cls.env["account.journal"].create(
            {
                "name": "BCA test",
                "code": "TBCA",
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
                    "name": "Store one debit",
                    "company_id": cls.company.id,
                    "journal_id": cls.bank.id,
                    "match_type": "mid",
                    "key": MID_ONE,
                    "channel": "debit",
                    "analytic_account_id": cls.store_one.id,
                },
                {
                    "name": "Store two debit",
                    "company_id": cls.company.id,
                    "journal_id": cls.bank.id,
                    "match_type": "mid",
                    "key": MID_TWO,
                    "channel": "debit",
                    "analytic_account_id": cls.store_two.id,
                },
            ]
        )

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------
    @classmethod
    def _posrec(cls, account, analytic, when, amount):
        """A posted POS receivable debit, as a POS session would leave it."""
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
            {
                "journal_id": cls.bank.id,
                "date": when,
                "amount": amount,
                "payment_ref": payment_ref,
            }
        )
        # Odoo 19 already posts the statement line's move on create.
        if line.move_id.state == "draft":
            line.move_id.action_post()
        return line

    @classmethod
    def _settlement_ref(cls, mid, gross, mdr, trans_day=None):
        stamp = " TANGGAL :%02d/%02d" % (trans_day.day, trans_day.month) if trans_day else ""
        return "KR OTOMATIS%s MID : %s LEVIS TEST TGH: %.2f DDR: %.2f" % (stamp, mid, gross, mdr)

    def _run(self, **overrides):
        vals = {
            "company_id": self.company.id,
            "date_from": date(2026, 7, 1),
            "date_to": date(2026, 7, 31),
            "journal_id": self.gljv.id,
            "bank_journal_ids": [Command.set(self.bank.ids)],
        }
        vals.update(overrides)
        return self.env["levis.pos.clearing"].create(vals)

    # ------------------------------------------------------------------
    # Stage 1 must not write anything
    # ------------------------------------------------------------------
    def test_compute_creates_no_accounting(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        statement = self._statement(date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0))
        before = self.env["account.move"].search_count([("company_id", "=", self.company.id)])

        run = self._run()
        run.action_compute()

        self.assertEqual(run.state, "computed")
        self.assertEqual(
            self.env["account.move"].search_count([("company_id", "=", self.company.id)]),
            before,
            "computing a summary must not create a journal entry",
        )
        self.assertFalse(statement.levis_clearing_run_id, "a preview must not claim the statement line")
        self.assertFalse(run.move_ids)
        line = run.line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.gross, 1_000_000.0)
        self.assertEqual(line.mdr, 10_000.0)
        self.assertEqual(line.cash_in, 990_000.0)
        self.assertEqual(line.allocated, 1_000_000.0)
        self.assertEqual(line.short_amount, 0.0)
        self.assertEqual(line.analytic_account_id, self.store_one)
        self.assertEqual(line.state, "ok")

    def test_tender_split_is_discovered_from_open_lines(self):
        """The narrative cannot say which tender; the open debits can."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 500_000.0)
        self._posrec(self.tender_b, self.store_one, day, 300_000.0)
        self._posrec(self.tender_c, self.store_one, day, 200_000.0)
        self._statement(date(2026, 7, 9), 891_000.0, self._settlement_ref(MID_ONE, 900_000.0, 9_000.0, trans_day=day))

        run = self._run()
        run.action_compute()
        allocs = run.line_ids.alloc_ids
        by_account = {alloc.account_id: alloc.amount for alloc in allocs}
        # Largest residual first: 500k, then 300k, then 100k of the last 200k.
        self.assertEqual(by_account[self.tender_a], 500_000.0)
        self.assertEqual(by_account[self.tender_b], 300_000.0)
        self.assertEqual(by_account[self.tender_c], 100_000.0)
        self.assertEqual(run.line_ids.short_amount, 0.0)

    def test_shortfall_is_reported_and_mdr_prorated(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 400_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )

        run = self._run(ar_fallback=False)
        run.action_compute()
        line = run.line_ids
        self.assertEqual(line.allocated, 400_000.0)
        self.assertEqual(line.short_amount, 600_000.0)
        self.assertEqual(line.state, "short")
        # Only the fee earned on what was settled: 10 000 * 400/1000.
        self.assertEqual(line.mdr_booked, 4_000.0)
        self.assertTrue(run.diag_ids.filtered(lambda d: d.kind == "short"))
        self.assertEqual(run.short_count, 1)

    def test_unmapped_mid_blocks_generation(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._settlement_ref("885004609999", 1_000_000.0, 10_000.0))

        run = self._run()
        run.action_compute()
        self.assertEqual(run.line_ids.state, "unmapped")
        self.assertEqual(run.unmapped_count, 1)
        self.assertTrue(run.diag_ids.filtered(lambda d: d.kind == "unmapped_mid"))
        with self.assertRaises(UserError):
            run.action_generate_moves()
        self.assertFalse(run.move_ids)

    def test_unparsed_line_is_visible_and_books_nothing(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0))
        self._statement(date(2026, 7, 9), 12_345.0, "SOMETHING NOBODY TAUGHT US")

        run = self._run()
        run.action_compute()
        self.assertEqual(run.unparsed_count, 1)
        self.assertEqual(run.unparsed_amount, 12_345.0)
        with self.assertRaises(UserError):
            run.action_generate_moves()

        run.ignore_warnings = True
        run.action_generate_moves()
        planned = run.leg_ids.filtered(lambda leg: leg.account_id == self.tender_a)
        self.assertEqual(sum(planned.mapped("balance")), -1_000_000.0, "the unparsed amount must not be booked")
        self.assertFalse(
            run.leg_ids.statement_line_id.filtered(lambda st: st.payment_ref == "SOMETHING NOBODY TAUGHT US"),
            "the unparsed line gets no legs at all",
        )

    def test_amount_mismatch_is_a_finding(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        # Narrative says 990 000 net; the bank moved 900 000.
        self._statement(date(2026, 7, 9), 900_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0))

        run = self._run()
        run.action_compute()
        self.assertEqual(run.line_ids.state, "mismatch")
        self.assertEqual(run.line_ids.mismatch_amount, -90_000.0)
        self.assertEqual(run.mismatch_count, 1)
        self.assertTrue(run.diag_ids.filtered(lambda d: d.kind == "amount_mismatch"))

    # ------------------------------------------------------------------
    # Stage 2
    # ------------------------------------------------------------------
    def test_generate_plans_balanced_legs_with_the_store_analytic(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        settlement = self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        charge = self._statement(date(2026, 7, 15), -30_000.0, "BIAYA ADM")
        before = self.env["account.move"].search_count([("company_id", "=", self.company.id)])

        run = self._run()
        run.action_compute()
        run.action_generate_moves()

        self.assertEqual(run.state, "generated")
        self.assertFalse(run.move_ids, "preparing must not create an entry of its own")
        self.assertEqual(
            self.env["account.move"].search_count([("company_id", "=", self.company.id)]),
            before,
            "preparing must not create a journal entry at all",
        )
        for st_line in (settlement, charge):
            _liq, suspense, other = st_line._seek_for_lines()
            self.assertTrue(suspense, "the statement line is untouched until posting")
            self.assertFalse(other)

        # Block A: the legs replace a 990 000 credit on suspense, so they total
        # -990 000 — the gross receivable plus the fee the acquirer kept.
        settlement_legs = run.leg_ids.filtered(lambda leg: leg.statement_line_id == settlement)
        self.assertAlmostEqual(sum(settlement_legs.mapped("balance")), -990_000.0, places=2)
        expected = {str(self.store_one.id): 100.0}
        for leg in settlement_legs:
            self.assertEqual(leg.analytic_distribution, expected, "every leg carries the OU")
        by_account = {leg.account_id: leg.balance for leg in settlement_legs}
        self.assertEqual(by_account[self.mdr], 10_000.0)
        self.assertEqual(by_account[self.tender_a], -1_000_000.0)
        self.assertNotIn(self.suspense, by_account, "nothing is left unexplained, so no suspense leg")

        charge_legs = run.leg_ids.filtered(lambda leg: leg.statement_line_id == charge)
        self.assertEqual(charge_legs.account_id, self.charge)
        self.assertEqual(charge_legs.balance, 30_000.0)
        self.assertFalse(charge_legs.analytic_distribution)

    def test_statement_lines_are_claimed_only_at_generation(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        statement = self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )

        run = self._run()
        run.action_compute()
        self.assertFalse(statement.levis_clearing_run_id)
        run.action_generate_moves()
        self.assertEqual(statement.levis_clearing_run_id, run)

        # A second run over the same period must find nothing left to spend.
        other = self._run()
        other.action_compute()
        self.assertEqual(other.line_ids.state, "skipped")
        self.assertTrue(other.diag_ids.filtered(lambda d: d.kind == "consumed"))
        with self.assertRaises(UserError):
            other.action_generate_moves()

    def test_generating_twice_is_refused(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        run.action_generate_moves()
        with self.assertRaises(UserError):
            run.action_generate_moves()
        with self.assertRaises(UserError):
            run.action_compute()

    def test_locked_period_is_refused_and_never_lifted(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        # Set through SQL on purpose. Core refuses an ORM write of a lock date while
        # unreconciled statement lines exist in the period — and because the bank
        # suspense account is not reconcilable, they never stop being unreconciled.
        # What is under test here is our guard, not core's validator.
        self.env.cr.execute(
            "UPDATE res_company SET fiscalyear_lock_date = %s WHERE id = %s",
            (date(2026, 7, 31), self.company.id),
        )
        self.company.invalidate_recordset(["fiscalyear_lock_date"])
        self.assertEqual(run._lock_date(), date(2026, 7, 31))

        with self.assertRaises(UserError):
            run.action_generate_moves()
        self.assertFalse(run.move_ids)
        self.assertEqual(self.company.fiscalyear_lock_date, date(2026, 7, 31), "the lock must not be touched")

    # ------------------------------------------------------------------
    # Stage 3
    # ------------------------------------------------------------------
    def test_post_reconciles_the_exact_pair_and_leaves_others_readable(self):
        """A short store must not be covered by another store's excess.

        Both stores use ``tender_a``. Store one is settled in full; store two is
        settled for half. A per-account reconcile would net them together and hide
        store two's remaining 500 000.
        """
        day = date(2026, 7, 8)
        one = self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        two = self._posrec(self.tender_a, self.store_two, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        self._statement(date(2026, 7, 9), 495_000.0, self._settlement_ref(MID_TWO, 500_000.0, 5_000.0, trans_day=day))

        run = self._run(ar_fallback=False)
        run.action_compute()
        run.action_generate_moves()
        run.action_post()

        self.assertEqual(run.state, "posted")
        self.assertEqual(set(run.move_ids.mapped("state")), {"posted"})
        # Every allocation must know the leg that pays it, or stage 3 could only
        # fall back to a blanket per-account reconcile.
        self.assertTrue(all(run.line_ids.alloc_ids.mapped("move_line_id")))
        self.assertTrue(one.reconciled, "store one was settled in full")
        self.assertFalse(two.reconciled)
        self.assertEqual(two.amount_residual, 500_000.0, "store two keeps its own residual")

    def test_posting_leaves_the_statement_line_reconciled(self):
        """The whole point of writing onto the statement line.

        July 2026 booked the counterpart in its own entry, which left every
        statement line sitting on suspense with ``is_reconciled = False`` — and
        Odoo then refuses a lock date over the period. A fully explained
        settlement must come out the other side with no suspense leg at all.
        """
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        settlement = self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        charge = self._statement(date(2026, 7, 15), -30_000.0, "BIAYA ADM")

        run = self._run()
        run.action_compute()
        run.action_generate_moves()
        run.action_post()

        for st_line in (settlement, charge):
            _liq, suspense, _other = st_line._seek_for_lines()
            self.assertFalse(suspense, "the suspense leg must be gone, not matched")
            self.assertTrue(st_line.is_reconciled, "%s stayed open" % st_line.payment_ref)
            self.assertEqual(st_line.move_id.state, "posted", "the bank entry stays posted throughout")
            self.assertAlmostEqual(
                sum(st_line.move_id.line_ids.mapped("debit")),
                sum(st_line.move_id.line_ids.mapped("credit")),
                places=2,
            )
        # The bank leg itself is untouched: clearing explains the money, it does
        # not restate what the bank did.
        liquidity, _s, _o = settlement._seek_for_lines()
        self.assertEqual(liquidity.balance, 990_000.0)
        self.assertEqual(
            {aml.account_id for aml in settlement.move_id.line_ids},
            {self.bank.default_account_id, self.mdr, self.tender_a},
        )

    def test_a_short_settlement_keeps_the_gap_on_suspense_and_stays_open(self):
        """Being short is not a reason to pretend the line is done."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 400_000.0)
        settlement = self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )

        run = self._run(ar_fallback=False)
        run.action_compute()
        run.action_generate_moves()
        # 600 000 of gross receivable went unmatched...
        self.assertEqual(run.line_ids.short_amount, 600_000.0)
        run.action_post()

        _liq, suspense, _other = settlement._seek_for_lines()
        self.assertTrue(suspense, "the unexplained part must stay visible on suspense")
        # ...but the bank only ever paid net, and the fee is prorated to what was
        # matched (4 000 of 10 000). So the money left unexplained is 594 000, not
        # the 600 000 gross: the missing 6 000 is a fee on a settlement that,
        # as far as the open receivables go, did not happen.
        self.assertAlmostEqual(sum(suspense.mapped("balance")), -594_000.0, places=2)
        self.assertEqual(run.line_ids.mdr_booked, 4_000.0)
        self.assertFalse(settlement.is_reconciled, "a short line is not a cleared line")

    def test_post_refuses_a_statement_line_someone_else_reconciled(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        settlement = self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )

        run = self._run()
        run.action_compute()
        run.action_generate_moves()

        # Somebody reconciles it by hand in the meantime.
        _liq, suspense, _other = settlement._seek_for_lines()
        settlement.with_context(force_delete=True, skip_readonly_check=True).write(
            {"line_ids": [(1, suspense.id, {"account_id": self.charge.id})]}
        )
        with self.assertRaises(UserError):
            run.action_post()

    def test_post_refuses_if_a_promised_receivable_moved(self):
        day = date(2026, 7, 8)
        aml = self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run(ar_fallback=False)
        run.action_compute()
        run.action_generate_moves()

        # Somebody reconciles it while the drafts wait.
        counter = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.gljv.id,
                "date": date(2026, 7, 20),
                "line_ids": [
                    Command.create({"account_id": self.tender_a.id, "credit": 1_000_000.0, "debit": 0.0}),
                    Command.create({"account_id": self.suspense.id, "debit": 1_000_000.0, "credit": 0.0}),
                ],
            }
        )
        counter.action_post()
        (aml + counter.line_ids.filtered(lambda l: l.account_id == self.tender_a)).reconcile()

        with self.assertRaises(UserError):
            run.action_post()
        self.assertFalse(run.move_ids, "a refused post books nothing")
        self.assertTrue(run.leg_ids, "the reviewed plan survives so it can be recomputed")

    def test_balances_before_after_simulated_and_actual_agree(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run(ar_fallback=False)
        run.action_compute()
        self.assertEqual(run.bal_suspense_after_sim, run.bal_suspense_before + 990_000.0)
        self.assertEqual(run.bal_mdr_after_sim, run.bal_mdr_before + 10_000.0)
        self.assertEqual(run.posrec_open_after_sim, run.posrec_open_before - 1_000_000.0)

        run.action_generate_moves()
        run.action_post()
        self.assertEqual(run.bal_suspense_after_actual, run.bal_suspense_after_sim)
        self.assertEqual(run.bal_mdr_after_actual, run.bal_mdr_after_sim)
        self.assertEqual(run.posrec_open_after_actual, run.posrec_open_after_sim)
        self.assertFalse(run.warning_text, "no drift means nothing to warn about")

    # ------------------------------------------------------------------
    # Cancel, diagnostics, prior-month AR
    # ------------------------------------------------------------------
    def test_cancel_releases_the_plan_and_markers_but_not_a_posted_run(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        statement = self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run(ar_fallback=False)
        run.action_compute()
        run.action_generate_moves()
        run.action_cancel()
        self.assertEqual(run.state, "cancel")
        self.assertFalse(run.move_ids)
        self.assertFalse(run.leg_ids)
        self.assertFalse(statement.levis_clearing_run_id)
        _liq, suspense, _other = statement._seek_for_lines()
        self.assertTrue(suspense, "cancelling before posting leaves the bank entry alone")

        again = self._run(ar_fallback=False)
        again.action_compute()
        again.action_generate_moves()
        again.action_post()
        with self.assertRaises(UserError):
            again.action_cancel()

    def test_prior_month_ar_absorbs_what_pos_cannot(self):
        """A settlement with no open POS receivable collects an older invoice."""
        self._posrec(self.ar, self.store_one, date(2026, 5, 20), 800_000.0)
        self._statement(date(2026, 7, 9), 792_000.0, self._settlement_ref(MID_ONE, 800_000.0, 8_000.0))
        run = self._run(ar_fallback=True)
        run.action_compute()
        line = run.line_ids
        self.assertEqual(line.block, "b", "nothing of this month's POS receivable was open")
        self.assertEqual(line.allocated, 800_000.0)
        self.assertEqual(line.alloc_ids.account_id, self.ar)
        self.assertEqual(run.block_b_total, 800_000.0)

    def test_receivable_without_an_operating_unit_is_reported_not_patched(self):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.gljv.id,
                "date": date(2026, 7, 8),
                "line_ids": [
                    Command.create({"account_id": self.tender_a.id, "debit": 700_000.0, "credit": 0.0}),
                    Command.create(
                        {
                            "account_id": self.company_data["default_account_revenue"].id,
                            "debit": 0.0,
                            "credit": 700_000.0,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        orphan = move.line_ids.filtered(lambda aml: aml.account_id == self.tender_a)

        run = self._run()
        run.action_compute()
        finding = run.diag_ids.filtered(lambda d: d.kind == "no_analytic")
        self.assertTrue(finding)
        self.assertEqual(finding.res_id, orphan.id)
        self.assertFalse(orphan.analytic_distribution, "the finding must not modify the line")
        self.assertEqual(run.no_analytic_count, 1)

    def test_interior_statement_gap_is_flagged(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 100.0)
        self._statement(date(2026, 7, 9), 99.0, self._settlement_ref(MID_ONE, 100.0, 1.0, trans_day=day))
        self._statement(date(2026, 7, 11), -30_000.0, "BIAYA ADM")
        run = self._run(ar_fallback=False)
        run.action_compute()
        gaps = run.diag_ids.filtered(lambda d: d.kind == "missing_day")
        self.assertEqual(gaps.mapped("date"), [date(2026, 7, 10)])

    def test_prior_month_trading_day_is_reachable(self):
        """A BRI-style settlement whose trading day precedes the period."""
        self.bank.levis_clearing_format = "bri"
        self.env["levis.bank.mid.map"].create(
            {
                "name": "Store one terminal",
                "company_id": self.company.id,
                "journal_id": self.bank.id,
                "match_type": "tid",
                "key": "001999600001",
                "analytic_account_id": self.store_one.id,
            }
        )
        self._posrec(self.tender_a, self.store_one, date(2026, 6, 30), 1_000_900.0)
        self._statement(
            date(2026, 7, 1),
            999_399.0,
            "OnUs 1 260630 001999600001 LEVIS TEST AMT:1.000.900,00MDR:1.501,00",
        )
        run = self._run(ar_fallback=False)
        run.action_compute()
        line = run.line_ids
        self.assertEqual(line.trans_date, date(2026, 6, 30))
        self.assertFalse(line.trans_date_is_derived)
        self.assertEqual(line.allocated, 1_000_900.0)
        self.assertEqual(line.alloc_ids.source_date, date(2026, 6, 30))

    def test_period_ref_shapes(self):
        whole = self._run()
        self.assertEqual(whole.period_ref, "POSCLR-2026-07")
        partial = self._run(date_from=date(2026, 7, 5), date_to=date(2026, 7, 20))
        self.assertEqual(partial.period_ref, "POSCLR-20260705-20260720")

    def test_unmapped_is_not_counted_as_a_shortfall(self):
        """ "We don't know the store" and "the store had nothing open" differ."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        self._statement(date(2026, 7, 9), 495_000.0, self._settlement_ref("885004609999", 500_000.0, 5_000.0))
        run = self._run(ar_fallback=False)
        run.action_compute()
        self.assertEqual(run.unmapped_count, 1)
        self.assertEqual(run.unmapped_amount, 495_000.0)
        self.assertEqual(run.total_short, 0.0, "an unmapped line is reported as unmapped, not short")
        self.assertEqual(run.short_count, 0)

    def test_wizard_proposes_one_rule_per_terminal(self):
        """The same shop reaches us as three feeds and two printed MIDs.

        BCA prints ``885004600003`` on the debit feed and ``004600003`` on the
        credit-card feed, and the debit MID also carries QRIS. One store, so one
        proposal — otherwise the rules collide on their uniqueness constraint.
        """
        day = date(2026, 7, 8)
        self._statement(date(2026, 7, 9), 99_000.0, self._settlement_ref("885004600003", 100_000.0, 1_000.0))
        self._statement(
            date(2026, 7, 9),
            50_000.0,
            "KARTU KREDIT MID:004600003 LEVIS TEST TGH:00000050500.00 ADM:00000000500.00",
        )
        self._statement(
            date(2026, 7, 9),
            20_000.0,
            "KR OTOMATIS TANGGAL :%02d/%02d MID : 885004600003 LEVIS TEST QR : 20000.00 DDR: 0.00"
            % (day.day, day.month),
        )

        wizard = self.env["levis.bank.mid.map.wizard"].create(
            {
                "company_id": self.company.id,
                "date_from": date(2026, 7, 1),
                "date_to": date(2026, 7, 31),
                "journal_ids": [Command.set(self.bank.ids)],
            }
        )
        wizard.action_scan()
        proposals = wizard.line_ids.filtered(lambda line: "600003" in (line.key or ""))
        self.assertEqual(len(proposals), 1, "one terminal, one proposal")
        self.assertEqual(proposals.line_count, 3, "all three feeds counted together")
        self.assertEqual(proposals.match_type, "mid")

        proposals.analytic_account_id = self.store_one
        wizard.action_apply()
        rule = self.env["levis.bank.mid.map"].search([("key", "like", "%600003%")])
        self.assertEqual(len(rule), 1)
        # And the shorter printed form still resolves against it.
        parsed = {"mid": "004600003", "tid": None, "keyword": None, "raw": ""}
        self.assertEqual(
            self.env["levis.bank.mid.map"]._resolve(self.company, self.bank, parsed, date(2026, 7, 9)),
            rule,
        )

    def test_cash_deposit_only_clears_the_cash_receivable(self):
        """A cash deposit must not clear a card receivable.

        Both are open for the same store on the same day and the card one is
        larger, so the old largest-residual-first rule would have taken it —
        clearing Visa with cash takings and leaving the real cash receivable open.
        """
        day = date(2026, 7, 8)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code", self.tender_c.code
        )
        card = self._posrec(self.tender_b, self.store_one, day, 900_000.0)
        cash = self._posrec(self.tender_c, self.store_one, day, 400_000.0)
        self.env["levis.bank.mid.map"].create(
            {
                "name": "Cash deposits store one",
                "company_id": self.company.id,
                "match_type": "keyword",
                "key": "SETORAN SATU",
                "channel": "cash",
                "analytic_account_id": self.store_one.id,
            }
        )
        self._statement(
            date(2026, 7, 9),
            400_000.0,
            "TRSF E-BANKING CR 0107/FTSCY/WS95031 400000.00 SETORAN SATU",
        )

        run = self._run(ar_fallback=False)
        run.action_compute()
        line = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(len(line), 1)
        self.assertEqual(line.alloc_ids.account_id, self.tender_c, "cash must settle the CASH receivable")
        self.assertEqual(line.allocated, 400_000.0)
        self.assertEqual(line.short_amount, 0.0)
        self.assertFalse(card.reconciled)
        self.assertEqual(card.amount_residual, 900_000.0, "the card receivable must be untouched")
        self.assertEqual(cash.amount_residual, 400_000.0)

    def test_cash_deposit_reports_a_shortfall_rather_than_taking_a_card_line(self):
        """With no cash receivable open, the deposit is short — not reassigned."""
        day = date(2026, 7, 8)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code", self.tender_c.code
        )
        card = self._posrec(self.tender_b, self.store_one, day, 900_000.0)
        self.env["levis.bank.mid.map"].create(
            {
                "name": "Cash deposits store one",
                "company_id": self.company.id,
                "match_type": "keyword",
                "key": "SETORAN SATU",
                "channel": "cash",
                "analytic_account_id": self.store_one.id,
            }
        )
        self._statement(
            date(2026, 7, 9),
            400_000.0,
            "TRSF E-BANKING CR 0107/FTSCY/WS95031 400000.00 SETORAN SATU",
        )

        run = self._run(ar_fallback=False)
        run.action_compute()
        line = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertFalse(line.alloc_ids, "nothing eligible, so nothing allocated")
        self.assertEqual(line.short_amount, 400_000.0)
        self.assertEqual(line.state, "short")
        self.assertEqual(card.amount_residual, 900_000.0, "the card receivable must be untouched")

    def test_card_settlement_still_spans_every_tender(self):
        """The restriction must not leak onto cards, where the split is discovered."""
        day = date(2026, 7, 8)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code", self.tender_c.code
        )
        self._posrec(self.tender_a, self.store_one, day, 500_000.0)
        self._posrec(self.tender_b, self.store_one, day, 300_000.0)
        self._statement(date(2026, 7, 9), 792_000.0, self._settlement_ref(MID_ONE, 800_000.0, 8_000.0, trans_day=day))

        run = self._run(ar_fallback=False)
        run.action_compute()
        line = run.line_ids.filtered(lambda line: line.kind == "settlement")
        self.assertEqual(set(line.alloc_ids.account_id.ids), {self.tender_a.id, self.tender_b.id})
        self.assertEqual(line.allocated, 800_000.0)

    def test_card_settlement_may_not_clear_the_cash_receivable(self):
        """Card money settling the CASH account clears one the customer never used.

        It also hides a real cash shortfall behind a card over-clear, which is the
        mirror of the defect the cash restriction fixes.
        """
        day = date(2026, 7, 8)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code", self.tender_c.code
        )
        card = self._posrec(self.tender_a, self.store_one, day, 300_000.0)
        self._posrec(self.tender_c, self.store_one, day, 500_000.0)
        self._statement(date(2026, 7, 9), 792_000.0, self._settlement_ref(MID_ONE, 800_000.0, 8_000.0, trans_day=day))

        run = self._run(ar_fallback=False)
        run.action_compute()
        line = run.line_ids.filtered(lambda line: line.kind == "settlement")
        self.assertEqual(set(line.alloc_ids.account_id.ids), {self.tender_a.id})
        self.assertEqual(line.allocated, 300_000.0)
        self.assertEqual(line.state, "short", "the rest is a finding, not the cash account's problem")
        self.assertEqual(line.alloc_ids.source_aml_id, card)

    def test_an_unreadable_narrative_is_not_narrowed_on_a_guess(self):
        """Channel "other" means we do not know; the old unrestricted pool stands."""
        day = date(2026, 7, 8)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code", self.tender_c.code
        )
        run = self._run()
        pool = run._pool_accounts_for_channel({"kind": "settlement", "channel": "other"}, self.tender_c)
        self.assertFalse(pool, "an unread narrative must not be restricted")
        pool = run._pool_accounts_for_channel({"kind": "settlement", "channel": "qris"}, self.tender_c)
        self.assertEqual(set(pool.ids), set(self.tenders.ids) - {self.tender_c.id})

    def test_the_bank_entry_number_is_readable_on_the_settlement(self):
        """The number to quote in the ledger, without opening the statement line."""
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        statement = self._statement(date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0))
        run = self._run()
        run.action_compute()
        self.assertEqual(run.line_ids.move_name, statement.move_id.name)

    def test_receipt_numbers_stay_empty_without_the_staged_rows(self):
        """The receipt list is a courtesy, never a precondition for clearing.

        ``custom_retail_import`` is not a dependency: on a database without it —
        or before X70D was ever staged — the settlement must still compute, and
        say nothing rather than guess.
        """
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0))
        run = self._run()
        run.action_compute()
        line = run.line_ids
        self.assertTrue(line.alloc_ids)
        self.assertFalse(line.x24_trans_refs)
        self.assertEqual(line.x24_trans_count, 0)
        self.assertEqual(line.x24_match, "none")
        self.assertFalse(line.x24_tender)
        self.assertFalse(line.x24_tender_mismatch)

    def test_the_tender_is_read_off_the_receivable_account_name(self):
        Alloc = self.env["levis.pos.clearing.alloc"]
        cash = self.env["account.account"].create(
            {
                "name": "POS Receivable - CASH",
                "code": "CLRT99",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        self.assertEqual(Alloc._x24_tender_of_account(cash), "CASH")
        self.assertIsNone(
            Alloc._x24_tender_of_account(self.config.mdr_account_id),
            "an account that is not a per-tender receivable names no tender",
        )

    def test_receipts_are_named_only_when_the_money_names_them(self):
        """The whole point of the rewrite: a partial settlement claims nothing.

        A day holding 16.865.300 across ten card transactions can compose 250.900
        many ways. Listing that day's receipts made a 250.900 line read as though
        it had paid millions — so unless one transaction, or one tender's whole
        day, equals the settlement exactly, nothing is named.
        """
        Alloc = self.env["levis.pos.clearing.alloc"]
        day = [
            ("OFFLINE_DOMESTIC_CARD", "80433-1-3066", 3_749_600.0),
            ("OFFLINE_DOMESTIC_CARD", "80433-1-3076", 349_900.0),
            ("OFFLINE_VISA", "80433-1-3122", 250_900.0),
            ("OFFLINE_OTHER_CREDITCARD", "80433-1-3074", 600_900.0),
            ("OFFLINE_OTHER_CREDITCARD", "80433-1-3094", 449_900.0),
        ]

        state, tender, refs = Alloc._x24_identify(day, 250_900.0)
        self.assertEqual((state, tender, refs), ("exact", "OFFLINE_VISA", ["80433-1-3122"]))

        # One tender's whole trading day: 600.900 + 449.900.
        state, tender, refs = Alloc._x24_identify(day, 1_050_800.0)
        self.assertEqual(state, "batch")
        self.assertEqual(tender, "OFFLINE_OTHER_CREDITCARD")
        self.assertEqual(sorted(refs), ["80433-1-3074", "80433-1-3094"])

        # 4.099.500 is 3.749.600 + 349.900 — a real subset, and still not claimed,
        # because a subset that adds up is not the same as evidence.
        self.assertEqual(Alloc._x24_identify(day, 3_000_000.0), ("none", False, []))

        twins = [("OFFLINE_VISA", "80433-1-1", 500.0), ("OFFLINE_JCB", "80433-1-2", 500.0)]
        state, tender, refs = Alloc._x24_identify(twins, 500.0)
        self.assertEqual(state, "ambiguous")
        self.assertFalse(tender, "two tenders could have paid it — name neither")
        self.assertEqual(sorted(refs), ["80433-1-1", "80433-1-2"])

    def test_a_long_receipt_list_states_the_count_instead_of_being_cut(self):
        Alloc = self.env["levis.pos.clearing.alloc"]
        refs = ["80431-1-%s" % n for n in range(1, 11)]
        self.assertEqual(Alloc._x24_format_refs(refs, 20), ", ".join(refs))
        spelled = Alloc._x24_format_refs(refs, 3)
        self.assertTrue(spelled.startswith("80431-1-1, 80431-1-2, 80431-1-3"))
        self.assertIn("7", spelled, "the seven it does not spell out must still be stated")
        self.assertFalse(Alloc._x24_format_refs([], 3))

    def _receipt(self, line, ref, amount, tender="OFFLINE_VISA", matched=False):
        return self.env["levis.pos.clearing.receipt"].create(
            {
                "line_id": line.id,
                "ref": ref,
                "tender": tender,
                "trans_date": line.trans_date or line.settlement_date,
                "amount": amount,
                "matched": matched,
            }
        )

    def _two_settlements(self):
        """Two bank lines on the same store and trading day — the case that bites."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 2_000_000.0)
        self._statement(date(2026, 7, 9), 495_000.0, self._settlement_ref(MID_ONE, 500_000.0, 5_000.0, trans_day=day))
        self._statement(date(2026, 7, 9), 297_000.0, self._settlement_ref(MID_ONE, 300_000.0, 3_000.0, trans_day=day))
        run = self._run()
        run.action_compute()
        return run, run.line_ids.sorted("gross")

    def test_a_ticked_receipt_leaves_every_other_bank_line(self):
        """One transaction is paid once — so it stops being offered elsewhere."""
        run, (smaller, larger) = self._two_settlements()
        here = self._receipt(larger, "80435-1-3089", 500_000.0)
        there = self._receipt(smaller, "80435-1-3089", 500_000.0)

        here.matched = True

        self.assertFalse(there.exists(), "the same transaction may not stay on offer elsewhere")
        self.assertEqual(larger.x24_trans_refs, "80435-1-3089")
        self.assertEqual(larger.matched_total, 500_000.0)
        self.assertEqual(larger.match_gap, 0.0)
        self.assertEqual(smaller.matched_total, 0.0)
        self.assertEqual(smaller.match_gap, 300_000.0, "and the other line is still short of an answer")

    def test_matching_one_transaction_to_two_bank_lines_is_refused(self):
        run, (smaller, larger) = self._two_settlements()
        self._receipt(larger, "80435-1-3089", 500_000.0, matched=True)
        with self.assertRaises(UserError):
            self._receipt(smaller, "80435-1-3089", 500_000.0, matched=True)

    def test_unticking_returns_the_transaction_to_the_pool(self):
        run, (smaller, larger) = self._two_settlements()
        receipt = self._receipt(larger, "80435-1-3089", 500_000.0, matched=True)

        receipt.action_unmatch()

        self.assertFalse(receipt.exists() and receipt.matched)
        self.assertFalse(larger.x24_trans_refs)
        self.assertEqual(larger.match_gap, larger.gross)
        # Free again: the other line may now claim it.
        self._receipt(smaller, "80435-1-3089", 500_000.0, matched=True)
        self.assertEqual(smaller.matched_total, 500_000.0)

    def test_the_gap_is_what_is_left_to_explain(self):
        run, (smaller, larger) = self._two_settlements()
        self._receipt(larger, "80435-1-3089", 300_000.0, matched=True)
        self.assertEqual(larger.matched_total, 300_000.0)
        self.assertEqual(larger.match_gap, 200_000.0)
        self._receipt(larger, "80435-1-3093", 200_000.0, matched=True)
        self.assertEqual(larger.x24_trans_count, 2)
        self.assertEqual(larger.match_gap, 0.0)

    def test_suggesting_needs_a_computed_run(self):
        run, (smaller, _larger) = self._two_settlements()
        run.action_cancel()
        with self.assertRaises(UserError):
            smaller.action_suggest_receipts()

    def test_suggesting_leaves_the_ticks_alone(self):
        """Refreshing a line's offer must never undo an answer already given."""
        run, (_smaller, larger) = self._two_settlements()
        kept = self._receipt(larger, "80435-1-3089", 500_000.0, matched=True)
        loose = self._receipt(larger, "80435-1-3093", 120_000.0)

        larger.action_suggest_receipts()

        self.assertTrue(kept.exists(), "a matched receipt survives a refresh")
        self.assertFalse(loose.exists(), "an unticked suggestion is rebuilt, not kept")
        self.assertEqual(larger.x24_trans_refs, "80435-1-3089")

    def test_incomplete_configuration_says_what_is_missing(self):
        self.config.mdr_account_id = False
        run = self._run()
        with self.assertRaises(UserError):
            run.action_compute()

    # ------------------------------------------------------------------
    # Searching the settlements, and reading the mapping wizard's totals
    # ------------------------------------------------------------------
    def test_settlements_can_be_searched_away_from_the_run(self):
        """The run's own state must be searchable from the settlement records.

        The Settlements tab is a one2many, which has no search panel, so the
        filters live on a normal action over the lines. Every field those filters
        name has to be stored — a filter on a non-stored one silently returns
        nothing rather than failing.
        """
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0))
        run = self._run()
        run.action_compute()

        Line = self.env["levis.pos.clearing.line"]
        self.assertEqual(run.line_ids.run_state, "computed")
        self.assertEqual(run.line_ids.run_period_ref, run.period_ref)
        self.assertEqual(
            Line.search([("run_state", "not in", ("posted", "cancel")), ("run_id", "=", run.id)]),
            run.line_ids,
        )
        # The search view's headline filters, exercised as domains.
        self.assertEqual(Line.search([("analytic_account_id", "=", self.store_one.id)]), run.line_ids)
        self.assertTrue(Line.search([("payment_ref", "ilike", MID_ONE)]))
        self.assertTrue(Line.search([("mid_key", "ilike", MID_ONE[-6:])]))

        action = run.action_view_lines()
        self.assertEqual(action["res_model"], "levis.pos.clearing.line")
        self.assertEqual(action["domain"], [("run_id", "=", run.id)])

    def test_unmapped_totals_can_be_tied_back_to_the_mutation(self):
        """A proposal's amount is a sum over many lines; it must prove itself.

        The sample narrative belongs to one statement line while Bank Amount adds
        up all of them, so on its own the figure looks as though it disagreed with
        the account mutation. Gross and MDR beside it, and the lines behind it,
        are what make it checkable.
        """
        first = self._statement(date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_UNMAPPED, 1_000_000.0, 10_000.0))
        second = self._statement(date(2026, 7, 10), 495_000.0, self._settlement_ref(MID_UNMAPPED, 500_000.0, 5_000.0))

        wizard = self.env["levis.bank.mid.map.wizard"].create(
            {
                "company_id": self.company.id,
                "date_from": date(2026, 7, 1),
                "date_to": date(2026, 7, 31),
                "journal_ids": [Command.set(self.bank.ids)],
            }
        )
        wizard.action_scan()
        proposal = wizard.line_ids.filtered(lambda line: MID_UNMAPPED[-6:] in (line.key or ""))
        self.assertEqual(len(proposal), 1)

        self.assertEqual(proposal.line_count, 2)
        self.assertEqual(proposal.total_amount, 1_485_000.0, "the mutation, net of the fee")
        self.assertEqual(proposal.gross_total, 1_500_000.0, "what the narratives claim")
        self.assertEqual(proposal.mdr_total, 15_000.0)
        self.assertEqual(proposal.narrative_gap, 0.0, "gross minus MDR is the money that moved")
        self.assertEqual(proposal.statement_line_ids, first | second)

        self.assertEqual(wizard.unmapped_total, sum(wizard.line_ids.mapped("total_amount")))
        self.assertEqual(wizard.unmapped_gross, sum(wizard.line_ids.mapped("gross_total")))

        action = proposal.action_open_statement_lines()
        self.assertEqual(action["res_model"], "account.bank.statement.line")
        self.assertEqual(sorted(action["domain"][0][2]), sorted((first | second).ids))

    def test_mapping_wizard_opens_as_a_page_not_a_dialog(self):
        run = self._run()
        self.assertEqual(run.action_open_mapping_wizard()["target"], "current")
