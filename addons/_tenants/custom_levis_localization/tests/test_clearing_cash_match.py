# -*- coding: utf-8 -*-
"""Cash: the till on one side, the deposit that banks it on the other.

Two claims are tested here, and they are separate claims.

**The card difference is the card difference.** ``variance_bank`` used to weigh
the whole statement against the whole X70D, cash included, which on a store-day
whose card side was perfect to the rupiah reported Rp -1.161.572: an acquirer
fee of 161.672 and an unbanked till of 999.900 added together under a label that
named neither. Each side is now weighed against its own population.

**A deposit that names no store can still be placed.** Not by guessing: by being
the one credit that fits the one store-day, with nothing else in the run wanting
either. Everything the arithmetic refuses is listed instead, for the screen that
lets a person answer it.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_clearing_store_day import STORE_CODE, STORE_CODE_TWO, TestClearingStoreDay
from .test_pos_clearing import MID_ONE

CASH_REF = "SETORAN TUNAI"


@tagged("post_install", "-at_install")
class TestClearingCashMatch(TestClearingStoreDay):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The CASH receivable has to be nameable before a deposit can be bound to
        # it; without this the engine says so and matches nothing, which is a
        # different test.
        cls.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code", cls.tender_c.code
        )
        cls.tender_c.name = "POS Receivable - CASH"

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def _card_day_with_cash(self, cash=999_900.0, day=date(2026, 7, 8)):
        """A store-day whose card side ties exactly and whose till is still out."""
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_VISA", "0001", 1_000_000.0)
        self._x70d(STORE_CODE, day, "CASH", "0002", cash)
        self._statement(
            day + self._one_day(),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )

    @staticmethod
    def _one_day():
        from datetime import timedelta

        return timedelta(days=1)

    # ------------------------------------------------------------------
    # The difference that was reported wrong
    # ------------------------------------------------------------------
    def test_the_bank_difference_is_the_fee_not_the_fee_plus_the_till(self):
        """The reported defect, in the shape it was reported in.

        Card money 990.000 against card tenders 1.000.000 is the 10.000 fee. The
        till of 999.900 is not in it — nothing banked it, and the bank never
        settles one.
        """
        self._card_day_with_cash()
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        self.assertAlmostEqual(row.variance_bank, -10_000.0, places=2)
        self.assertAlmostEqual(row.cash_variance, 999_900.0, places=2)
        self.assertAlmostEqual(row.variance, -999_900.0, places=2, msg="the total still carries both")

    def test_the_card_statement_is_stated_apart_from_the_money_in(self):
        self._card_day_with_cash()
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        self.assertAlmostEqual(row.statement_card_total, 990_000.0, places=2)
        self.assertAlmostEqual(row.statement_total, 990_000.0, places=2)

    def test_a_day_with_no_cash_at_all_reads_exactly_as_before(self):
        run = self._one_store_day()
        row = run.store_day_ids
        self.assertAlmostEqual(row.variance_bank, -10_000.0, places=2)
        self.assertAlmostEqual(row.cash_variance, 0.0, places=2)

    # ------------------------------------------------------------------
    # The matcher ships inert
    # ------------------------------------------------------------------
    def test_an_unattributed_deposit_stays_unattributed_while_the_switch_is_off(self):
        """Default behaviour is the old behaviour, to the letter."""
        self.assertFalse(self.config.cash_auto_match)
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        run = self._run()
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(deposit.state, "unmapped")
        self.assertFalse(deposit.analytic_account_id)
        self.assertFalse(deposit.cash_auto_matched)

    # ------------------------------------------------------------------
    # What the arithmetic may decide
    # ------------------------------------------------------------------
    def _switched_on(self):
        self.config.cash_auto_match = True
        self.config.cash_match_lookback_days = 3

    def test_one_till_one_deposit_is_matched_by_amount(self):
        self._switched_on()
        self._card_day_with_cash()
        cash = self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        run = self._run()
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(deposit.analytic_account_id, self.store_one)
        self.assertEqual(deposit.trans_date, date(2026, 7, 8), "the day is part of the match, not the lag")
        self.assertTrue(deposit.cash_auto_matched)
        self.assertEqual(deposit.state, "ok")
        self.assertEqual(deposit.alloc_ids.source_aml_id, cash, "a deposit settles the CASH receivable")

    def test_a_matched_deposit_closes_the_cash_difference_on_the_store_day(self):
        self._switched_on()
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        run = self._run()
        run.action_compute()
        row = run.store_day_ids.filtered(lambda day: day.trading_date == date(2026, 7, 8))
        self.assertAlmostEqual(row.cash_deposit_total, 999_900.0, places=2)
        self.assertAlmostEqual(row.cash_variance, 0.0, places=2)
        self.assertAlmostEqual(row.variance_bank, -10_000.0, places=2, msg="the card side is untouched")

    def test_the_match_is_reported_as_a_finding_rather_than_done_quietly(self):
        self._switched_on()
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        run = self._run()
        run.action_compute()
        self.assertTrue(run.diag_ids.filtered(lambda diag: diag.kind == "cash_matched"))

    def test_a_till_banked_three_days_later_is_still_found(self):
        self._switched_on()
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        self._statement(date(2026, 7, 11), 999_900.0, CASH_REF)
        run = self._run()
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(deposit.trans_date, date(2026, 7, 8))

    def test_a_till_banked_outside_the_window_is_left_alone(self):
        self._switched_on()
        self.config.cash_match_lookback_days = 1
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        self._statement(date(2026, 7, 12), 999_900.0, CASH_REF)
        run = self._run()
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertFalse(deposit.analytic_account_id)

    # ------------------------------------------------------------------
    # What the arithmetic must refuse
    # ------------------------------------------------------------------
    def test_two_stores_with_the_same_till_are_not_guessed_between(self):
        """Two shops banking the same round float is real, and it proves nothing."""
        self._switched_on()
        day = date(2026, 7, 8)
        self._x70d(STORE_CODE, day, "CASH", "0001", 500_000.0)
        self._x70d(STORE_CODE_TWO, day, "CASH", "0002", 500_000.0)
        self._posrec(self.tender_c, self.store_one, day, 500_000.0)
        self._posrec(self.tender_c, self.store_two, day, 500_000.0)
        self._statement(date(2026, 7, 9), 500_000.0, CASH_REF)
        run = self._run()
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertFalse(deposit.analytic_account_id)
        self.assertTrue(run.diag_ids.filtered(lambda diag: diag.kind == "cash_ambiguous"))

    def test_two_deposits_fitting_one_till_take_neither(self):
        """Being the only fit is not enough — it has to be the only claimant."""
        self._switched_on()
        day = date(2026, 7, 8)
        self._x70d(STORE_CODE, day, "CASH", "0001", 500_000.0)
        self._posrec(self.tender_c, self.store_one, day, 1_000_000.0)
        self._statement(date(2026, 7, 9), 500_000.0, CASH_REF)
        self._statement(date(2026, 7, 9), 500_000.0, CASH_REF + " CDM")
        run = self._run()
        run.action_compute()
        deposits = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(len(deposits), 2)
        self.assertFalse(deposits.mapped("analytic_account_id"))

    def test_a_till_a_mapped_deposit_already_pays_is_not_claimed_twice(self):
        """The narrative got there first, so the same takings cannot be sold twice."""
        self._switched_on()
        day = date(2026, 7, 8)
        self.env["levis.bank.mid.map"].create(
            {
                "name": "Store one cash",
                "company_id": self.company.id,
                "journal_id": self.bank.id,
                "match_type": "keyword",
                "key": "SETORAN SATU",
                "channel": "cash",
                "analytic_account_id": self.store_one.id,
            }
        )
        self._x70d(STORE_CODE, day, "CASH", "0001", 500_000.0)
        self._posrec(self.tender_c, self.store_one, day, 1_000_000.0)
        self._statement(date(2026, 7, 9), 500_000.0, "TRSF E-BANKING CR 0907/FTSCY/WS9 500000.00 SETORAN SATU")
        self._statement(date(2026, 7, 9), 500_000.0, CASH_REF)
        run = self._run()
        run.action_compute()
        named = run.line_ids.filtered(lambda line: line.kind == "cash_deposit" and line.analytic_account_id)
        self.assertEqual(len(named), 1, "only the deposit the narrative placed")
        self.assertFalse(named.cash_auto_matched)

    def test_a_deposit_the_narrative_places_is_never_overruled(self):
        self._switched_on()
        day = date(2026, 7, 8)
        self.env["levis.bank.mid.map"].create(
            {
                "name": "Store two cash",
                "company_id": self.company.id,
                "journal_id": self.bank.id,
                "match_type": "keyword",
                "key": "SETORAN DUA",
                "channel": "cash",
                "analytic_account_id": self.store_two.id,
            }
        )
        # The amount fits store one's till exactly; the narrative says store two.
        self._x70d(STORE_CODE, day, "CASH", "0001", 500_000.0)
        self._posrec(self.tender_c, self.store_two, day, 500_000.0)
        self._statement(date(2026, 7, 9), 500_000.0, "TRSF E-BANKING CR 0907/FTSCY/WS9 500000.00 SETORAN DUA")
        run = self._run()
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(deposit.analytic_account_id, self.store_two)
        self.assertFalse(deposit.cash_auto_matched)

    # ------------------------------------------------------------------
    # The screen a person answers on
    # ------------------------------------------------------------------
    def _unmatched_day(self):
        """A till of 999.900 and a deposit of it that the matcher will not take."""
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        # Two days' cash banked at once: nothing sums to it, so nothing is matched.
        self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        self._x70d(STORE_CODE_TWO, date(2026, 7, 8), "CASH", "0009", 999_900.0)
        run = self._run()
        run.action_compute()
        return run

    def test_the_screen_offers_the_deposits_that_belong_to_nobody(self):
        self._switched_on()
        run = self._unmatched_day()
        row = run.store_day_ids.filtered(
            lambda day: day.analytic_account_id == self.store_one and day.trading_date == date(2026, 7, 8)
        )
        wizard = self.env["levis.clearing.cash.match"]._build_for(row)
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertAlmostEqual(wizard.outstanding, 999_900.0, places=2)

    def test_answering_on_the_screen_books_the_deposit(self):
        self._switched_on()
        run = self._unmatched_day()
        row = run.store_day_ids.filtered(
            lambda day: day.analytic_account_id == self.store_one and day.trading_date == date(2026, 7, 8)
        )
        wizard = self.env["levis.clearing.cash.match"]._build_for(row)
        wizard.line_ids.selected = True
        wizard.action_apply()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(deposit.analytic_account_id, self.store_one)
        self.assertEqual(deposit.trans_date, date(2026, 7, 8))
        self.assertEqual(deposit.state, "ok")
        self.assertFalse(deposit.cash_auto_matched, "a person's answer is not an arithmetic one")

    def test_the_answer_survives_the_next_recompute(self):
        self._switched_on()
        run = self._unmatched_day()
        row = run.store_day_ids.filtered(
            lambda day: day.analytic_account_id == self.store_one and day.trading_date == date(2026, 7, 8)
        )
        wizard = self.env["levis.clearing.cash.match"]._build_for(row)
        wizard.line_ids.selected = True
        wizard.action_apply()
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(deposit.analytic_account_id, self.store_one)

    # ------------------------------------------------------------------
    # What counts as banked
    # ------------------------------------------------------------------
    def test_a_deposit_an_auto_only_run_skipped_still_counts_as_banked(self):
        """The column is about the money, not about what this run chose to clear.

        A narrowed run skips every cash deposit — cash carries no store-day
        proof, so it is never *proven* — and reading that as "the till is still
        in the safe" would report every shop in the run as short of its own cash.
        """
        self._switched_on()
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        run = self._run(auto_only=True)
        run.action_compute()
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertEqual(deposit.state, "skipped", "a narrowed run books no cash")
        self.assertEqual(deposit.analytic_account_id, self.store_one)
        row = run.store_day_ids.filtered(lambda day: day.trading_date == date(2026, 7, 8))
        self.assertAlmostEqual(row.cash_deposit_total, 999_900.0, places=2)
        self.assertAlmostEqual(row.cash_variance, 0.0, places=2)

    def test_the_same_deposit_imported_twice_banks_the_till_once(self):
        """Cumulative statement re-imports are deliberate here; double counting is not."""
        self._switched_on()
        self._card_day_with_cash()
        self._posrec(self.tender_c, self.store_one, date(2026, 7, 8), 999_900.0)
        first = self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        copy = self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        # The discriminator is *when the row was written*, not its wording: two
        # rows an hour or more apart cannot have come from one file. The fixture
        # writes both in the same instant, so the copy is aged by hand.
        self.env.cr.execute(
            "UPDATE account_bank_statement_line SET create_date = create_date + interval '2 hours' WHERE id = %s",
            (copy.id,),
        )
        copy.invalidate_recordset()
        run = self._run()
        run.action_compute()
        duplicate = run.line_ids.filtered(lambda line: line.duplicate_of_id)
        self.assertEqual(len(duplicate), 1, "the second import is recognised as a copy")
        self.assertEqual(duplicate.statement_line_id, copy)
        row = run.store_day_ids.filtered(lambda day: day.trading_date == date(2026, 7, 8))
        self.assertAlmostEqual(row.cash_deposit_total, 999_900.0, places=2, msg="the till is banked once")
        self.assertAlmostEqual(row.cash_variance, 0.0, places=2)

    # ------------------------------------------------------------------
    # Surviving its own recompute
    # ------------------------------------------------------------------
    def test_the_screen_survives_the_recompute_it_asks_for(self):
        """Reported from prd_levis_begbal, 22 Sep 2026.

        Applying recomputes the run, and a recompute deletes every store-day and
        every clearing line it holds. While this wizard hung off those records
        with ``ondelete="cascade"``, the answer succeeded and then deleted the
        screen that gave it: the operator was left on a dead form, and pressing
        again reported "record deleted" for work that had already been done.
        """
        self._switched_on()
        run = self._unmatched_day()
        row = run.store_day_ids.filtered(
            lambda day: day.analytic_account_id == self.store_one and day.trading_date == date(2026, 7, 8)
        )
        wizard = self.env["levis.clearing.cash.match"]._build_for(row)
        wizard.line_ids.selected = True
        wizard.action_apply()
        self.assertTrue(wizard.exists(), "the screen must outlive the recompute it triggers")
        self.assertTrue(wizard.line_ids.exists(), "its candidate rows too")
        self.assertTrue(wizard.applied)
        self.assertEqual(wizard.analytic_account_id, self.store_one, "identity is snapshotted, not borrowed")

    def test_pressing_apply_again_shows_the_result_rather_than_redoing_it(self):
        """The second press is a person who was given no sign the first worked."""
        self._switched_on()
        run = self._unmatched_day()
        row = run.store_day_ids.filtered(
            lambda day: day.analytic_account_id == self.store_one and day.trading_date == date(2026, 7, 8)
        )
        wizard = self.env["levis.clearing.cash.match"]._build_for(row)
        wizard.line_ids.selected = True
        first = wizard.action_apply()
        self.assertEqual(first["res_model"], "levis.pos.clearing.store.day")
        again = wizard.action_apply()
        self.assertEqual(
            again["res_id"],
            first["res_id"],
            "a second press must not rebuild the projection — same row, not a new one",
        )

    def test_the_action_it_returns_points_at_the_rebuilt_row(self):
        self._switched_on()
        run = self._unmatched_day()
        row = run.store_day_ids.filtered(
            lambda day: day.analytic_account_id == self.store_one and day.trading_date == date(2026, 7, 8)
        )
        wizard = self.env["levis.clearing.cash.match"]._build_for(row)
        wizard.line_ids.selected = True
        action = wizard.action_apply()
        self.assertFalse(row.exists(), "the row it was opened from is gone — rebuilt, not patched")
        rebuilt = self.env["levis.pos.clearing.store.day"].browse(action["res_id"])
        self.assertTrue(rebuilt.exists())
        self.assertEqual(rebuilt.analytic_account_id, self.store_one)
        self.assertEqual(rebuilt.settlement_date, date(2026, 7, 9))
        self.assertTrue(action.get("views"), "an act_window without resolved views lands on a blank screen")

    def test_the_screen_refuses_a_deposit_bigger_than_the_till_it_claims(self):
        self._switched_on()
        self._card_day_with_cash(cash=100_000.0)
        self._statement(date(2026, 7, 9), 999_900.0, CASH_REF)
        self._x70d(STORE_CODE_TWO, date(2026, 7, 8), "CASH", "0009", 999_900.0)
        run = self._run()
        run.action_compute()
        row = run.store_day_ids.filtered(
            lambda day: day.analytic_account_id == self.store_one and day.trading_date == date(2026, 7, 8)
        )
        wizard = self.env["levis.clearing.cash.match"]._build_for(row)
        wizard.line_ids.selected = True
        with self.assertRaises(UserError):
            wizard.action_apply()
