# -*- coding: utf-8 -*-
"""The store-day proof, and the narrowed run it lets through.

A settlement cannot be checked against a receivable one at a time. The bank's
channels (debit, credit, QRIS) and the POS tenders (ten accounts) are two
different partitions of the same money, so the only honest question is whether
a store's whole trading day ties to that store's whole open receivable for the
day. These tests are that question and its four refusals.

The assertions that matter most are the negative ones: that a rupiah of
difference proves nothing, that a proven day never spends outside itself, that
an unreadable line poisons every store sharing its bank day, and that a
narrowed run leaves everything it did not prove exactly as it found it.
"""

from datetime import date, timedelta

from odoo.tests import tagged

from .test_pos_clearing import MID_ONE, MID_TWO, MID_UNMAPPED, TestPosClearing

TRADING_DAY = date(2026, 7, 8)
SETTLED_ON = date(2026, 7, 9)


@tagged("post_install", "-at_install")
class TestAutoClearing(TestPosClearing):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The proof refuses to weigh anything until it knows which receivable
        # holds the till, because excluding cash is the whole defence. The
        # fixture's cash tender carries a test code, so point the parameter at
        # it the way a tenant points it at 1106000101.
        cls.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code",
            cls.tender_c.with_company(cls.company).code,
        )

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------
    @classmethod
    def _qris_ref(cls, mid, gross, mdr, trans_day):
        """BCA's QRIS row: the gross is marked ``QR :``, and the fee is real."""
        return "KR OTOMATIS TANGGAL :%02d/%02d MID : %s LEVIS TEST QR : %.2f DDR: %.2f" % (
            trans_day.day,
            trans_day.month,
            mid,
            gross,
            mdr,
        )

    def _pim2(self):
        """3 September 2026 at Pondok Indah Mall 2, moved into the test period.

        The bank paid a debit settlement of 17.605.500 and a QRIS settlement of
        65.499.000; the POS had booked 69.099.900 on one tender and 14.004.600
        on another. Same total, 83.104.500, and no member of either side is a
        subset of the other. This is the shape the whole design exists for.
        """
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 69_099_900.0)
        self._posrec(self.tender_b, self.store_one, TRADING_DAY, 14_004_600.0)
        debit = self._statement(
            SETTLED_ON,
            17_605_500.0 - 26_408.0,
            self._settlement_ref(MID_ONE, 17_605_500.0, 26_408.0, TRADING_DAY),
        )
        qris = self._statement(SETTLED_ON, 65_499_000.0, self._qris_ref(MID_ONE, 65_499_000.0, 0.0, TRADING_DAY))
        return debit, qris

    def _proof_states(self, run):
        return set(run.line_ids.filtered("proof_state").mapped("proof_state"))

    # ------------------------------------------------------------------
    # The tie
    # ------------------------------------------------------------------
    def test_a_store_day_that_ties_is_proven_though_no_single_line_matches(self):
        self._pim2()
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"exact"})
        for line in run.line_ids:
            self.assertEqual(line.proof_ledger_total, 83_104_500.0)
            self.assertEqual(line.short_amount, 0.0)
        # Neither settlement equals either receivable, which is the point.
        self.assertNotIn(17_605_500.0, (69_099_900.0, 14_004_600.0))
        self.assertNotIn(65_499_000.0, (69_099_900.0, 14_004_600.0))

    def test_the_fee_booked_is_the_fee_the_bank_printed(self):
        self._pim2()
        run = self._run()
        run.action_compute()

        by_gross = {line.gross: line for line in run.line_ids}
        self.assertEqual(by_gross[17_605_500.0].mdr_booked, 26_408.0)
        # QRIS settles gross here, and a zero fee is a real zero — never a rate
        # to look up.
        self.assertEqual(by_gross[65_499_000.0].mdr_booked, 0.0)

    def test_a_proven_day_carries_its_verdict_up_to_the_store_screen(self):
        self._pim2()
        run = self._run()
        run.action_compute()

        store_day = run.store_day_ids.filtered(lambda row: row.analytic_account_id == self.store_one)
        self.assertEqual(len(store_day), 1)
        self.assertEqual(store_day.proof_state, "exact")
        self.assertEqual(store_day.ledger_open_total, 83_104_500.0)
        self.assertEqual(store_day.proof_variance, 0.0)

    # ------------------------------------------------------------------
    # The four refusals
    # ------------------------------------------------------------------
    def test_one_rupiah_short_proves_nothing(self):
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 1_000_001.0)
        self._statement(SETTLED_ON, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY))
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"under"})
        self.assertTrue(run.diag_ids.filtered(lambda d: d.kind == "store_day_under"))

    def test_one_rupiah_over_proves_nothing(self):
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 999_999.0)
        self._statement(SETTLED_ON, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY))
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"over"})
        self.assertTrue(run.diag_ids.filtered(lambda d: d.kind == "store_day_over"))

    def test_a_day_whose_sales_never_arrived_is_named_not_cleared(self):
        self._statement(SETTLED_ON, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY))
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"no_sales"})
        diag = run.diag_ids.filtered(lambda d: d.kind == "store_day_no_sales")
        self.assertTrue(diag, "a missing sales feed must be named, not read as a difference")
        self.assertIn("never sold in Odoo", diag.message)

    def test_an_unreadable_money_in_line_blocks_every_store_on_its_bank_day(self):
        self._pim2()
        # Another store's takings, on the same bank day, that nothing can read.
        self._statement(SETTLED_ON, 5_000_000.0, "SOMETHING NOBODY PARSES")
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"blocked"})
        self.assertTrue(run.diag_ids.filtered(lambda d: d.kind == "store_day_blocked"))

    def test_an_unmapped_settlement_blocks_its_bank_day_too(self):
        self._pim2()
        self._statement(SETTLED_ON, 5_000_000.0, self._settlement_ref(MID_UNMAPPED, 5_000_000.0, 0.0, TRADING_DAY))
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"blocked"})

    def test_a_narrative_that_disagrees_with_the_money_blocks_its_own_group(self):
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 1_000_000.0)
        # The bank moved 900.000 while the narrative claims 1.000.000 less a
        # 10.000 fee. One of the two is wrong and neither may be assumed.
        self._statement(SETTLED_ON, 900_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY))
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"blocked"})

    def test_a_money_out_line_blocks_nothing(self):
        self._pim2()
        # A sweep to the pooling account on the same day: money leaving, never a
        # shop's takings.
        self._statement(SETTLED_ON, -3_000_000.0, "TRSF E-BANKING DB 0907/SWBCA/WS95431 6865 ERA BUSANA")
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"exact"})

    # ------------------------------------------------------------------
    # A proven day is spent on itself
    # ------------------------------------------------------------------
    def _tempting_neighbour(self):
        """Yesterday holds a receivable of exactly today's settlement gross.

        The most tempting thing a greedy largest-first search could reach, and
        taking it would break yesterday's own tie after it had been measured.
        """
        tempting = self._posrec(self.tender_b, self.store_one, TRADING_DAY - timedelta(days=1), 1_000_000.0)
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(SETTLED_ON, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY))
        return tempting

    def test_a_proven_day_spends_only_its_own_receivable(self):
        """The regression guard for the pinned day ladder."""
        tempting = self._tempting_neighbour()
        run = self._run(auto_only=True)
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"exact"})
        self.assertNotIn(
            tempting.id,
            run.line_ids.alloc_ids.mapped("source_aml_id").ids,
            "a proven day that spends yesterday's receivable breaks yesterday's tie",
        )

    def _a_thief_and_a_proven_day(self):
        """A settlement whose own day sold nothing, reaching into a proven one.

        The thief settles a day earlier, so it allocates first, and its ladder
        walks outward until it finds money — which is the old behaviour, and
        correct for a run that books on the old terms. The day it reaches is a
        day that ties to the rupiah.
        """
        owned = self._posrec(self.tender_a, self.store_one, TRADING_DAY, 1_000_000.0)
        thief = self._statement(
            TRADING_DAY,
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY - timedelta(days=1)),
        )
        owner = self._statement(
            SETTLED_ON, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY)
        )
        return owned, thief, owner

    def test_a_wide_run_allocates_exactly_what_it_always_did(self):
        """The inertness guard: the verdict is recorded and binds nothing."""
        owned, thief, owner = self._a_thief_and_a_proven_day()
        run = self._run()
        run.action_compute()

        taken = run.line_ids.filtered(lambda line: line.statement_line_id == thief)
        kept = run.line_ids.filtered(lambda line: line.statement_line_id == owner)
        self.assertEqual(kept.proof_state, "exact", "the verdict is recorded on a wide run too")
        self.assertIn(owned.id, taken.alloc_ids.mapped("source_aml_id").ids)
        self.assertEqual(kept.short_amount, 1_000_000.0, "a wide run books on the old terms, proof or no proof")

    def test_a_narrowed_run_keeps_a_proven_day_for_the_day_that_earned_it(self):
        owned, thief, owner = self._a_thief_and_a_proven_day()
        run = self._run(auto_only=True)
        run.action_compute()

        taken = run.line_ids.filtered(lambda line: line.statement_line_id == thief)
        kept = run.line_ids.filtered(lambda line: line.statement_line_id == owner)
        self.assertEqual(taken.state, "skipped")
        self.assertFalse(taken.alloc_ids, "a day that sold nothing may not spend a day that did")
        self.assertEqual(kept.proof_state, "exact")
        self.assertEqual(kept.allocated, 1_000_000.0)
        self.assertEqual(kept.short_amount, 0.0)

    # ------------------------------------------------------------------
    # Cash is weighed on neither side — the shop-floor scenarios
    # ------------------------------------------------------------------
    def test_a_late_cash_deposit_cannot_disturb_the_card_proof(self):
        """The till banked days late, because the bank was shut."""
        self._pim2()
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 7_500_000.0)
        self._statement(SETTLED_ON, 7_500_000.0, "TRSF E-BANKING CR 0907/FTSCY/WS95271 7500000.00 M RIZKI H")
        run = self._run()
        run.action_compute()

        card = run.line_ids.filtered(lambda line: line.channel in ("debit", "qris"))
        self.assertEqual(set(card.mapped("proof_state")), {"exact"})
        deposit = run.line_ids.filtered(lambda line: line.kind == "cash_deposit")
        self.assertFalse(deposit.proof_state, "a cash deposit is never weighed by the proof")

    def test_cash_banked_for_a_sale_that_never_reached_xstore_leaves_the_card_proof_alone(self):
        """Money in with no receivable behind it at all."""
        self._pim2()
        self._statement(SETTLED_ON, 2_400_000.0, "SETORAN TUNAI 0907 TOKO")
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"exact"})

    # ------------------------------------------------------------------
    # The narrowed run
    # ------------------------------------------------------------------
    def test_a_narrowed_run_books_what_it_proved(self):
        debit, qris = self._pim2()
        run = self._run(auto_only=True)
        run.action_compute()
        run.action_generate_moves()

        self.assertEqual(run.state, "generated")
        self.assertTrue(run.leg_ids)
        self.assertEqual(debit.levis_clearing_run_id, run)
        self.assertEqual(qris.levis_clearing_run_id, run)

    def test_a_narrowed_run_leaves_what_it_could_not_prove_untouched(self):
        self._pim2()
        # A second store whose day does not tie.
        self._posrec(self.tender_a, self.store_two, TRADING_DAY, 5_000_000.0)
        stranded = self._statement(
            SETTLED_ON, 990_000.0, self._settlement_ref(MID_TWO, 1_000_000.0, 10_000.0, TRADING_DAY)
        )
        run = self._run(auto_only=True)
        run.action_compute()

        line = run.line_ids.filtered(lambda row: row.statement_line_id == stranded)
        self.assertEqual(line.state, "skipped")
        self.assertFalse(line.block)
        self.assertFalse(line.alloc_ids, "an unproven line must not spend the pool")

        run.action_generate_moves()
        self.assertFalse(
            stranded.levis_clearing_run_id,
            "a line this run did not book must stay free for the run that will",
        )

    def test_a_narrowed_run_still_books_the_bank_s_own_movements(self):
        self._statement(SETTLED_ON, -3_000_000.0, "TRSF E-BANKING DB 0907/SWBCA/WS95431 6865 ERA BUSANA")
        run = self._run(auto_only=True)
        run.action_compute()
        run.action_generate_moves()

        sweep = run.line_ids.filtered(lambda line: line.kind == "sweep")
        self.assertEqual(sweep.block, "c")
        self.assertTrue(sweep.leg_ids, "a sweep is the bank's own movement and needs no proof")

    def test_a_wide_run_is_unchanged_by_all_of_this(self):
        """The inertness claim: off, nothing behaves differently."""
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 5_000_000.0)
        self._statement(SETTLED_ON, 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, TRADING_DAY))
        run = self._run()
        run.action_compute()

        line = run.line_ids
        self.assertEqual(line.state, "ok")
        self.assertEqual(line.allocated, 1_000_000.0)
        self.assertEqual(line.block, "a")
        self.assertEqual(line.proof_state, "under", "the verdict is recorded even where it gates nothing")

    # ------------------------------------------------------------------
    # The second tier: a nameable part of a bigger day
    # ------------------------------------------------------------------
    def _partial_day(self):
        """A day holding 920.000 against a settlement of 620.000.

        Exactly one combination of the three open items makes the gross, so the
        subset search has an answer and the greedy order has nothing to decide.
        """
        big = self._posrec(self.tender_a, self.store_one, TRADING_DAY, 500_000.0)
        small = self._posrec(self.tender_b, self.store_one, TRADING_DAY, 120_000.0)
        spare = self._posrec(self.tender_a, self.store_one, TRADING_DAY, 300_000.0)
        self._statement(SETTLED_ON, 613_800.0, self._settlement_ref(MID_ONE, 620_000.0, 6_200.0, TRADING_DAY))
        return big, small, spare

    def test_the_subset_tier_is_off_unless_advanced_matching_is_set(self):
        self._partial_day()
        run = self._run()
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"under"})
        self.assertFalse(self.config.advanced_matching, "the switch must ship off")

    def test_the_subset_tier_takes_the_combination_it_proved_and_nothing_else(self):
        big, small, spare = self._partial_day()
        self.config.advanced_matching = True
        run = self._run(auto_only=True)
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"subset"})
        taken = set(run.line_ids.alloc_ids.mapped("source_aml_id").ids)
        self.assertEqual(taken, {big.id, small.id})
        self.assertNotIn(spare.id, taken, "the spare item was never part of the proof")

    def test_two_ways_to_compose_the_gross_prove_neither(self):
        # 300+200 and 250+250 both make 500.000, and no single item does.
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 300_000.0)
        self._posrec(self.tender_b, self.store_one, TRADING_DAY, 200_000.0)
        self._posrec(self.tender_a, self.store_one, TRADING_DAY, 250_000.0)
        self._posrec(self.tender_b, self.store_one, TRADING_DAY, 250_000.0)
        self._statement(SETTLED_ON, 495_000.0, self._settlement_ref(MID_ONE, 500_000.0, 5_000.0, TRADING_DAY))
        self.config.advanced_matching = True
        run = self._run(auto_only=True)
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"under"}, "two ways to make a number is evidence for neither")

    def test_a_lone_item_equal_to_the_gross_is_taken(self):
        """The matcher's own contract, and the standard already used elsewhere.

        A single open item equal to the settlement is what
        `_get_auto_match_candidate` has always treated as a match. The subset
        search short-circuits on it in the same way, so a day holding one
        500.000 item alongside 300+200 takes the 500.000 rather than reporting
        ambiguity. It is the *compositions* that have to be unique.
        """
        exact = self._posrec(self.tender_a, self.store_one, TRADING_DAY, 500_000.0)
        self._posrec(self.tender_b, self.store_one, TRADING_DAY, 300_000.0)
        self._posrec(self.tender_b, self.store_one, TRADING_DAY, 200_000.0)
        self._statement(SETTLED_ON, 495_000.0, self._settlement_ref(MID_ONE, 500_000.0, 5_000.0, TRADING_DAY))
        self.config.advanced_matching = True
        run = self._run(auto_only=True)
        run.action_compute()

        self.assertEqual(self._proof_states(run), {"subset"})
        self.assertEqual(set(run.line_ids.alloc_ids.mapped("source_aml_id").ids), {exact.id})

    def test_nothing_is_proven_until_the_cash_receivable_is_known(self):
        """Excluding cash is the defence; without it there is no proof to give."""
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code", "NO-SUCH-CODE"
        )
        self._pim2()
        run = self._run()
        run.action_compute()

        self.assertFalse(self._proof_states(run))
        self.assertTrue(run.diag_ids.filtered(lambda d: d.kind == "no_cash_account"))
