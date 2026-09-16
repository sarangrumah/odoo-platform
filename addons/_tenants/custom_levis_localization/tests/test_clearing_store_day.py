# -*- coding: utf-8 -*-
"""One store's settlement day against the tenders it rang up.

The claims this model makes, and each one is tested here:

* a row exists per store per settlement date, and only where the store is known;
* money in counts takings only — a sweep to the main bank is the same money
  leaving again and must never be compared against sales;
* the sales side is every tender of the trading day, **cash included**, with
  cash split out so an undeposited till is not read as a missing settlement;
* the per-tender breakdown shows what the store rang up beside what the run
  credited, which is how a settlement booked to the wrong receivable is seen;
* and none of it depends on the retail import: with no staged row the screen
  says nothing rather than guessing.
"""

import json
from datetime import date

from odoo import Command
from odoo.tests import tagged

from .test_pos_clearing import MID_ONE, MID_TWO, TestPosClearing

STORE_CODE = "80440"
STORE_CODE_TWO = "80441"


@tagged("post_install", "-at_install")
class TestClearingStoreDay(TestPosClearing):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls._store_warehouse(STORE_CODE, cls.store_one)
        cls.warehouse_two = cls._store_warehouse(STORE_CODE_TWO, cls.store_two)
        cls.profile = (
            cls.env["retail.import.profile"]
            .sudo()
            .create(
                {
                    "name": "X70D test",
                    "code": "TESTX70D",
                    "file_type": "x70d",
                    "company_id": cls.company.id,
                }
            )
        )
        cls.log = (
            cls.env["retail.import.log"].sudo().create({"profile_id": cls.profile.id, "company_id": cls.company.id})
        )
        cls._row_number = 0

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------
    @classmethod
    def _store_warehouse(cls, code, analytic):
        """A warehouse carrying the operating unit, reachable by store code.

        The matcher walks store code → ``pos.config`` external id → warehouse →
        operating unit, so the fixture has to build that whole chain: it is the
        chain being tested.
        """
        warehouse = (
            cls.env["stock.warehouse"]
            .sudo()
            .create(
                {
                    "name": "Store %s" % code,
                    "code": code[-5:],
                    "company_id": cls.company.id,
                    "l10n_ou_analytic_id": analytic.id,
                }
            )
        )
        config = cls.env["pos.config"].sudo().create({"name": "POS %s" % code, "warehouse_id": warehouse.id})
        cls.env["ir.model.data"].sudo().create(
            {
                "module": "custom_retail_import",
                "name": "posconfig_%s" % code,
                "model": "pos.config",
                "res_id": config.id,
            }
        )
        return warehouse

    @classmethod
    def _x70d(cls, store_code, when, tender, transnum, amount):
        """One staged X70D tender row, exactly as the importer leaves it."""
        cls._row_number += 1
        return (
            cls.env["retail.import.line"]
            .sudo()
            .create(
                {
                    "log_id": cls.log.id,
                    "row_number": cls._row_number,
                    "raw_data_json": json.dumps(
                        {
                            "store_code": store_code,
                            "register": "1",
                            "transnum": transnum,
                            "trans_date": when.strftime("%Y-%m-%d"),
                            "tender_type": tender,
                            "tender_amount": "%.2f" % amount,
                        }
                    ),
                }
            )
        )

    def _one_store_day(self):
        """A card settlement of a day whose card tenders are exactly that much."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_VISA", "0001", 600_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_VISA", "0002", 400_000.0)
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        run = self._run()
        run.action_compute()
        return run

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    def test_computing_a_run_produces_its_store_days(self):
        run = self._one_store_day()
        self.assertEqual(len(run.store_day_ids), 1)
        row = run.store_day_ids
        self.assertEqual(row.analytic_account_id, self.store_one)
        self.assertEqual(row.settlement_date, date(2026, 7, 9))
        self.assertEqual(row.trading_date, date(2026, 7, 8))

    def test_every_settled_line_is_attached_to_its_store_day(self):
        run = self._one_store_day()
        self.assertEqual(run.line_ids.store_day_id, run.store_day_ids)

    def test_two_stores_on_one_date_are_two_rows(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._posrec(self.tender_a, self.store_two, day, 500_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        self._statement(date(2026, 7, 9), 495_000.0, self._settlement_ref(MID_TWO, 500_000.0, 5_000.0, trans_day=day))
        run = self._run()
        run.action_compute()
        self.assertEqual(len(run.store_day_ids), 2)
        self.assertEqual(
            set(run.store_day_ids.mapped("analytic_account_id").ids), {self.store_one.id, self.store_two.id}
        )

    def test_recomputing_rebuilds_rather_than_doubles(self):
        run = self._one_store_day()
        first = run.store_day_ids.ids
        run.action_compute()
        self.assertEqual(len(run.store_day_ids), 1)
        self.assertNotEqual(run.store_day_ids.ids, first, "store days are rebuilt, not patched")

    def test_a_settlement_with_no_store_makes_no_row(self):
        """An unmapped merchant id belongs to no shop, so it gets no store row."""
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            "KR OTOMATIS MID : 885004600009 LEVIS TEST TGH: 1000000.00 DDR: 10000.00",
        )
        run = self._run()
        run.action_compute()
        self.assertTrue(run.line_ids)
        self.assertFalse(run.store_day_ids)

    # ------------------------------------------------------------------
    # The two sides
    # ------------------------------------------------------------------
    def test_money_in_is_the_statement_the_fee_and_the_gross(self):
        row = self._one_store_day().store_day_ids
        self.assertAlmostEqual(row.statement_total, 990_000.0, places=2)
        self.assertAlmostEqual(row.mdr_total, 10_000.0, places=2)
        self.assertAlmostEqual(row.gross_total, 1_000_000.0, places=2)

    def test_the_sales_side_is_read_from_the_staged_x70d_rows(self):
        row = self._one_store_day().store_day_ids
        self.assertAlmostEqual(row.x70d_total, 1_000_000.0, places=2)
        self.assertEqual(row.x70d_count, 2)

    def test_a_matching_store_day_tallies(self):
        row = self._one_store_day().store_day_ids
        self.assertAlmostEqual(row.variance, 0.0, places=2)
        self.assertTrue(row.is_balanced)

    def test_the_bank_difference_is_the_fee_apart_from_the_gross_one(self):
        row = self._one_store_day().store_day_ids
        self.assertAlmostEqual(row.variance_bank, -10_000.0, places=2)

    def test_cash_is_counted_and_split_out(self):
        """Cash is in the total by instruction, and in its own column so a till
        left in the safe is never read as a settlement that failed to arrive."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_VISA", "0001", 1_000_000.0)
        self._x70d(STORE_CODE, day, "CASH", "0002", 250_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        self.assertAlmostEqual(row.x70d_cash_total, 250_000.0, places=2)
        self.assertAlmostEqual(row.x70d_card_total, 1_000_000.0, places=2)
        self.assertAlmostEqual(row.x70d_total, 1_250_000.0, places=2)
        self.assertAlmostEqual(row.variance, -250_000.0, places=2)
        self.assertFalse(row.is_balanced)

    def test_the_tender_fold_matches_the_matcher(self):
        """``OFFLINE_OTHER_CARD`` and ``OFFLINE_OTHER_CREDITCARD`` are one bucket."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_OTHER_CARD", "0001", 400_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_OTHER_CREDITCARD", "0002", 600_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        self.assertEqual(
            row.tender_ids.filtered(lambda t: t.x70d_amount).mapped("tender"), ["OFFLINE_OTHER_CREDITCARD"]
        )
        self.assertAlmostEqual(
            row.tender_ids.filtered(lambda t: t.tender == "OFFLINE_OTHER_CREDITCARD").x70d_amount,
            1_000_000.0,
            places=2,
        )

    def test_the_x70d_transactions_of_the_day_are_listed(self):
        row = self._one_store_day().store_day_ids
        self.assertEqual(len(row.x70d_txn_ids), 2)
        self.assertEqual(set(row.x70d_txn_ids.mapped("ref")), {"%s-1-0001" % STORE_CODE, "%s-1-0002" % STORE_CODE})
        self.assertAlmostEqual(sum(row.x70d_txn_ids.mapped("amount")), 1_000_000.0, places=2)

    def test_another_store_s_transactions_stay_out_of_this_row(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_VISA", "0001", 1_000_000.0)
        self._x70d(STORE_CODE_TWO, day, "OFFLINE_VISA", "0002", 750_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        self.assertAlmostEqual(row.x70d_total, 1_000_000.0, places=2)

    # ------------------------------------------------------------------
    # What money in is not
    # ------------------------------------------------------------------
    def test_a_sweep_belongs_to_no_store_and_is_never_compared(self):
        """A transfer to the pooling account is the same money leaving again.

        It carries no merchant id, so it names no store — and that is exactly
        why it can never reach a store's row and be subtracted from its sales.
        """
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_VISA", "0001", 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        sweep = self._statement(
            date(2026, 7, 9),
            -15_000_000_000.0,
            "TRSF E-BANKING DB 0107/SWBCA/WS95431 15000000000.00 ERA BUSANA RETAILI",
        )
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        swept = run.line_ids.filtered(lambda line: line.statement_line_id == sweep)
        self.assertEqual(swept.kind, "sweep")
        self.assertFalse(swept.store_day_id)
        self.assertAlmostEqual(row.gross_total, 1_000_000.0, places=2)
        self.assertAlmostEqual(row.variance, 0.0, places=2)

    # ------------------------------------------------------------------
    # Per tender
    # ------------------------------------------------------------------
    def test_the_breakdown_shows_what_was_rung_up_against_what_was_credited(self):
        row = self._one_store_day().store_day_ids
        breakdown = {tender.tender: tender for tender in row.tender_ids}
        self.assertIn("OFFLINE_VISA", breakdown)
        self.assertAlmostEqual(breakdown["OFFLINE_VISA"].x70d_amount, 1_000_000.0, places=2)
        # The fixture's receivable is named "POS Debit Card", which names no
        # tender, so nothing is credited to a tender bucket here.
        self.assertAlmostEqual(breakdown["OFFLINE_VISA"].booked_amount, 0.0, places=2)

    def test_a_settlement_credited_to_the_wrong_tender_shows_as_two_differences(self):
        """The 5.260.902 case: the day is right, the receivable is not.

        The allocation picks by residual and cannot see a tender, so a card
        settlement can end up crediting the wrong per-tender receivable. Read on
        the settlement alone that is invisible; on the store's day it is a pair
        of equal and opposite differences.
        """
        day = date(2026, 7, 8)
        visa = self.env["account.account"].create(
            {
                "name": "POS Receivable - OFFLINE_VISA",
                "code": "CLRTV1",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        other = self.env["account.account"].create(
            {
                "name": "POS Receivable - OFFLINE_OTHER_CREDITCARD",
                "code": "CLRTV2",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        self.config.pos_receivable_account_ids = [Command.set((self.tenders + visa + other).ids)]
        # The store rang the money up on Visa; the only open receivable large
        # enough is the other-credit one, so that is what the run will consume.
        self._posrec(other, self.store_one, day, 1_000_000.0)
        self._x70d(STORE_CODE, day, "OFFLINE_VISA", "0001", 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        breakdown = {tender.tender: tender for tender in row.tender_ids}
        self.assertAlmostEqual(breakdown["OFFLINE_VISA"].variance, 1_000_000.0, places=2)
        self.assertAlmostEqual(breakdown["OFFLINE_OTHER_CREDITCARD"].variance, -1_000_000.0, places=2)
        # The store's day still tallies: the money is right, only its bucket is not.
        self.assertAlmostEqual(row.variance, 0.0, places=2)

    # ------------------------------------------------------------------
    # Reaching the screen from a run that predates it
    # ------------------------------------------------------------------
    def test_the_button_builds_the_rows_without_recomputing_the_month(self):
        """A run computed before this screen existed must not have to be recomputed.

        Recomputing rebuilds the settlements from scratch and takes every
        receipt tick with them, so the button rebuilds the projection instead —
        it books nothing, and the ticks are untouched.
        """
        run = self._one_store_day()
        ticked = run.line_ids.receipt_ids.filtered("matched").mapped("ref")
        run.store_day_ids.unlink()
        self.assertFalse(run.store_day_ids)
        action = run.action_view_store_days()
        self.assertEqual(action["res_model"], "levis.pos.clearing.store.day")
        self.assertTrue(run.store_day_ids)
        self.assertEqual(run.line_ids.receipt_ids.filtered("matched").mapped("ref"), ticked)

    def test_the_settlement_list_button_builds_them_too(self):
        run = self._one_store_day()
        run.store_day_ids.unlink()
        action = run.line_ids.action_open_store_days()
        self.assertEqual(action["res_model"], "levis.pos.clearing.store.day")
        self.assertTrue(run.store_day_ids)

    # ------------------------------------------------------------------
    # Without the feed
    # ------------------------------------------------------------------
    def test_a_day_with_no_staged_rows_says_nothing_rather_than_guessing(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        row = run.store_day_ids
        self.assertEqual(row.x70d_count, 0)
        self.assertAlmostEqual(row.x70d_total, 0.0, places=2)
        self.assertAlmostEqual(row.variance, 1_000_000.0, places=2)
        self.assertFalse(row.is_balanced)
