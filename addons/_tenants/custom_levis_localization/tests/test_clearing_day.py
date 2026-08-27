# -*- coding: utf-8 -*-
"""The settlement day, as a projection over the run.

Two claims carry this model and both are tested here:

* a day is green when its work is **finished** — nothing unexplained, nothing
  unmapped — and
* it is *not* gated on the H-1 tally, because a settlement may legitimately draw
  on more than one trading day and a red nobody can clear is a red nobody reads.

Everything else is arithmetic.
"""

from datetime import date

from odoo.tests import tagged

from .test_pos_clearing import MID_ONE, TestPosClearing


@tagged("post_install", "-at_install")
class TestClearingDay(TestPosClearing):
    def _clean_run(self):
        """One settlement that fully explains itself."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        settlement = self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        run = self._run()
        run.action_compute()
        return run, settlement

    def _short_run(self):
        """A settlement 600 000 short of what it claims to pay."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 400_000.0)
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        run = self._run(ar_fallback=False)
        run.action_compute()
        return run

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    def test_computing_a_run_produces_its_days(self):
        run, _settlement = self._clean_run()
        self.assertTrue(run.day_ids)
        self.assertEqual(run.day_ids.settlement_date, date(2026, 7, 9))

    def test_a_day_knows_the_trading_day_it_stands_for(self):
        run, _settlement = self._clean_run()
        # settlement_lag_days is 1 by default.
        self.assertEqual(run.day_ids.trading_date, date(2026, 7, 8))

    def test_every_line_is_attached_to_its_day(self):
        run, _settlement = self._clean_run()
        self.assertTrue(all(line.day_id for line in run.line_ids if line.settlement_date))

    def test_recomputing_does_not_double_the_days(self):
        run, _settlement = self._clean_run()
        first = run.day_ids.ids
        run.action_compute()
        self.assertEqual(len(run.day_ids), 1)
        self.assertNotEqual(run.day_ids.ids, first, "days are rebuilt, not patched")

    def test_two_settlement_dates_make_two_days(self):
        first = date(2026, 7, 8)
        second = date(2026, 7, 10)
        self._posrec(self.tender_a, self.store_one, first, 1_000_000.0)
        self._posrec(self.tender_a, self.store_one, second, 500_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=first)
        )
        self._statement(
            date(2026, 7, 11), 495_000.0, self._settlement_ref(MID_ONE, 500_000.0, 5_000.0, trans_day=second)
        )
        run = self._run()
        run.action_compute()
        self.assertEqual(len(run.day_ids), 2)

    # ------------------------------------------------------------------
    # The figures
    # ------------------------------------------------------------------
    def test_gross_is_the_bank_amount_plus_the_fee(self):
        run, _settlement = self._clean_run()
        day = run.day_ids
        self.assertAlmostEqual(day.bank_in_total, 990_000.0, places=2)
        self.assertAlmostEqual(day.mdr_total, 10_000.0, places=2)
        self.assertAlmostEqual(day.gross_total, 1_000_000.0, places=2)

    def test_sales_h1_is_read_from_the_ledger(self):
        run, _settlement = self._clean_run()
        self.assertAlmostEqual(run.day_ids.sales_h1_total, 1_000_000.0, places=2)

    def test_a_matching_day_tallies(self):
        run, _settlement = self._clean_run()
        self.assertAlmostEqual(run.day_ids.tally_variance, 0.0, places=2)

    # ------------------------------------------------------------------
    # Green, and what it is not
    # ------------------------------------------------------------------
    def test_a_fully_explained_day_is_green(self):
        run, _settlement = self._clean_run()
        day = run.day_ids
        self.assertTrue(day.is_balanced)
        self.assertEqual(day.state, "ok")
        self.assertEqual(day.kanban_color, 10)

    def test_a_short_day_is_not_green(self):
        run = self._short_run()
        day = run.day_ids
        self.assertFalse(day.is_balanced)
        self.assertGreater(day.unexplained_total, 0.0)
        self.assertNotEqual(day.kanban_color, 10)

    def test_a_tally_gap_alone_does_not_stop_a_day_going_green(self):
        """The load-bearing test of this model.

        The store sold 1 500 000 on the 8th but only 1 000 000 of it settled on
        the 9th — the rest lands later, which is normal. Every bank line present
        is fully explained, so the day's work IS finished and it must read as
        finished, while the tally still reports the gap for a supervisor.
        """
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._posrec(self.tender_b, self.store_one, day, 500_000.0)
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        run = self._run()
        run.action_compute()
        clearing_day = run.day_ids

        self.assertAlmostEqual(clearing_day.unexplained_total, 0.0, places=2)
        self.assertTrue(clearing_day.is_balanced, "the day's own work is done")
        self.assertEqual(clearing_day.state, "ok")
        # ...and the gap is still reported, just not as a blocker.
        self.assertAlmostEqual(clearing_day.tally_variance, -500_000.0, places=2)

    def test_an_unmapped_line_keeps_the_day_red(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            "KR OTOMATIS MID : 999999999999 UNKNOWN TGH: 1000000.00 DDR: 10000.00",
        )
        run = self._run()
        run.action_compute()
        clearing_day = run.day_ids
        self.assertGreaterEqual(clearing_day.unmapped_count, 1)
        self.assertFalse(clearing_day.is_balanced)
        self.assertEqual(clearing_day.kanban_color, 1)

    def test_a_written_off_residual_lets_the_day_go_green(self):
        run = self._short_run()
        self.assertFalse(run.day_ids.is_balanced)
        self.env["levis.clearing.writeoff.wizard"].create(
            {
                "line_ids": [(6, 0, run.line_ids.ids)],
                "company_id": self.company.id,
                "mode": "absorb",
                "account_id": self.charge.id,
                "reason": "admin_fee",
            }
        ).action_apply()
        run.day_ids._recompute_figures()
        self.assertAlmostEqual(run.day_ids.unexplained_total, 0.0, places=2)
        self.assertTrue(run.day_ids.is_balanced, "a decision taken is not an open item")
        self.assertGreater(run.day_ids.writeoff_total, 0.0)

    def test_a_day_is_compared_only_against_its_own_stores(self):
        """Found on real data, not in a fixture.

        A date can carry more than one bank feed. Measured on August production
        data, an IBNI feed holding a single Rp 1 line was being compared against
        the whole company's sales for the day and reported a variance of minus
        412 million. A comparison is only meaningful between the same population
        on both sides.
        """
        day = date(2026, 7, 8)
        # store_one sells and settles through the main bank...
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        # ...while store_two sells the same day and settles nowhere.
        self._posrec(self.tender_a, self.store_two, day, 5_000_000.0)

        run = self._run()
        run.action_compute()
        clearing_day = run.day_ids

        # The day only settled store_one, so only store_one's sales are its
        # yardstick. Counting store_two's 5 000 000 would report a variance of
        # minus five million against a day that did nothing wrong.
        self.assertAlmostEqual(clearing_day.sales_h1_total, 1_000_000.0, places=2)
        self.assertAlmostEqual(clearing_day.tally_variance, 0.0, places=2)

    def test_a_day_that_settled_no_store_compares_against_nothing(self):
        # A feed carrying only a bank charge has no store and therefore no
        # yardstick — zero, not "the entire company's sales".
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), -25_000.0, "BIAYA ADM")
        run = self._run()
        run.action_compute()
        self.assertTrue(run.day_ids)
        self.assertAlmostEqual(run.day_ids.sales_h1_total, 0.0, places=2)
        self.assertAlmostEqual(run.day_ids.tally_variance, 0.0, places=2)

    # ------------------------------------------------------------------
    # It is a projection, not accounting
    # ------------------------------------------------------------------
    def test_building_days_books_nothing(self):
        # Counted after the fixtures, not before: `_posrec` and `_statement` each
        # post a move of their own, and blaming those on the day builder is how a
        # test ends up asserting something it never measured.
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        run = self._run()
        before = self.env["account.move"].search_count([("company_id", "=", self.company.id)])

        run.action_compute()
        self.assertTrue(run.day_ids)
        run.day_ids._recompute_figures()

        after = self.env["account.move"].search_count([("company_id", "=", self.company.id)])
        self.assertEqual(before, after, "a projection may not create accounting")

    def test_deleting_a_day_leaves_the_lines_alone(self):
        run, _settlement = self._clean_run()
        lines = run.line_ids
        run.day_ids.unlink()
        self.assertTrue(all(line.exists() for line in lines))
        self.assertFalse(lines.day_id)
