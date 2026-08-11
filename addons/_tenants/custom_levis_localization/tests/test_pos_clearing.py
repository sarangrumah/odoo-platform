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
        booked = run.move_ids.line_ids.filtered(lambda aml: aml.account_id == self.suspense)
        self.assertEqual(sum(booked.mapped("debit")), 990_000.0, "the unparsed amount must not be booked")

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
    def test_generate_creates_balanced_drafts_with_the_store_analytic(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        self._statement(date(2026, 7, 15), -30_000.0, "BIAYA ADM")

        run = self._run()
        run.action_compute()
        run.action_generate_moves()

        self.assertEqual(run.state, "generated")
        self.assertEqual(set(run.move_ids.mapped("state")), {"draft"})
        self.assertEqual(len(run.move_ids), 2, "one entry per block and date")
        for move in run.move_ids:
            self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit")), places=2)
            self.assertTrue(move.ref.startswith(run.period_ref))

        settlement_move = run.move_ids.filtered(lambda m: "-A-" in m.ref)
        expected = {str(self.store_one.id): 100.0}
        for aml in settlement_move.line_ids:
            self.assertEqual(aml.analytic_distribution, expected, "every leg carries the OU")
        legs = {aml.account_id: aml.balance for aml in settlement_move.line_ids}
        self.assertEqual(legs[self.suspense], 990_000.0)
        self.assertEqual(legs[self.mdr], 10_000.0)
        self.assertEqual(legs[self.tender_a], -1_000_000.0)

        charge_move = run.move_ids.filtered(lambda m: "-C-" in m.ref)
        charge_legs = {aml.account_id: aml.balance for aml in charge_move.line_ids}
        # The statement debited suspense by 30 000, so clearing credits it back.
        self.assertEqual(charge_legs[self.suspense], -30_000.0)
        self.assertEqual(charge_legs[self.charge], 30_000.0)
        self.assertFalse(charge_move.line_ids.mapped("analytic_distribution")[0])

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
        # The counters drive the header buttons, so they must follow the state.
        self.assertEqual(run.posted_move_count, run.move_count)
        self.assertEqual(run.draft_move_count, 0)
        # Every allocation must know the leg that pays it, or stage 3 could only
        # fall back to a blanket per-account reconcile.
        self.assertTrue(all(run.line_ids.alloc_ids.mapped("move_line_id")))
        self.assertTrue(one.reconciled, "store one was settled in full")
        self.assertFalse(two.reconciled)
        self.assertEqual(two.amount_residual, 500_000.0, "store two keeps its own residual")

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
        self.assertEqual(set(run.move_ids.mapped("state")), {"draft"})

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
    def test_cancel_releases_drafts_and_markers_but_not_posted(self):
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
        self.assertFalse(statement.levis_clearing_run_id)

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

    def test_incomplete_configuration_says_what_is_missing(self):
        self.config.mdr_account_id = False
        run = self._run()
        with self.assertRaises(UserError):
            run.action_compute()
