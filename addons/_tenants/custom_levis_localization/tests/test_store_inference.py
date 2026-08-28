# -*- coding: utf-8 -*-
"""The store-inference ladder, and the line it must not cross.

The ladder exists to remove the manual *searching*. It must not remove the
manual *deciding* — so the tests that matter most here are the ones asserting
that a resemblance produces a suggestion and nothing else, and that a run
refuses to book while any suggestion is unconfirmed.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_pos_clearing import MID_ONE, TestPosClearing


@tagged("post_install", "-at_install")
class TestStoreInference(TestPosClearing):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["levis.clearing.config"]._get(cls.company)
        cls.config.advanced_matching = True

    # A BCA settlement needs BOTH a gross and a MID to parse at all, so an
    # unmappable line is one carrying a MID nobody has mapped — not one with no
    # MID, which is simply unreadable and never reaches the ladder.
    UNMAPPED_MID = "885004609999"

    def _unmapped_ref(self, gross=1_000_000.0, mdr=10_000.0, text="TOKO TANPA ATURAN"):
        return "KR OTOMATIS MID : %s %s TGH: %.2f DDR: %.2f" % (
            self.UNMAPPED_MID,
            text,
            gross,
            mdr,
        )

    # ------------------------------------------------------------------
    # Rung 1 still wins, and still refuses to guess past an unmapped MID
    # ------------------------------------------------------------------
    def test_a_mapped_mid_is_still_the_first_answer(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9), 990_000.0, self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day)
        )
        run = self._run()
        run.action_compute()
        self.assertEqual(run.line_ids.store_method, "mid")
        self.assertEqual(run.line_ids.store_confidence, "exact")
        self.assertEqual(run.line_ids.analytic_account_id, self.store_one)

    # ------------------------------------------------------------------
    # Rung 2 — the store code the berita acara puts on the transfer
    # ------------------------------------------------------------------
    def test_a_store_code_in_the_narrative_names_the_store(self):
        warehouse = self.env["stock.warehouse"].create(
            {
                "name": "Inference Store",
                "code": "INFW",
                "company_id": self.company.id,
                "l10n_store_code": "SNC77",
                "l10n_ou_analytic_id": self.store_one.id,
            }
        )
        self.assertTrue(warehouse)
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 500_000.0)
        self._statement(date(2026, 7, 9), 500_000.0, "TRSF E-BANKING CR SETOR SNC77 HARIAN")
        run = self._run()
        run.action_compute()
        self.assertEqual(run.line_ids.store_method, "store_code")
        self.assertEqual(run.line_ids.store_confidence, "exact")
        self.assertEqual(run.line_ids.analytic_account_id, self.store_one)

    def test_a_store_code_must_be_a_whole_token(self):
        # "SNC77" inside an account number is not a store naming itself.
        self.env["stock.warehouse"].create(
            {
                "name": "Inference Store 2",
                "code": "INFX",
                "company_id": self.company.id,
                "l10n_store_code": "SNC77",
                "l10n_ou_analytic_id": self.store_one.id,
            }
        )
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 500_000.0)
        self._statement(date(2026, 7, 9), 500_000.0, "TRSF E-BANKING CR REK 998SNC7712 SETORAN")
        run = self._run()
        run.action_compute()
        self.assertNotEqual(run.line_ids.store_method, "store_code")

    # ------------------------------------------------------------------
    # Rung 3 — a validated deposit, the deterministic answer for cash
    # ------------------------------------------------------------------
    def test_a_validated_deposit_names_a_store_no_keyword_could(self):
        warehouse = self.env["stock.warehouse"].create(
            {
                "name": "Deposit Store",
                "code": "DEPW",
                "company_id": self.company.id,
                "l10n_store_code": "DEP99",
                "l10n_ou_analytic_id": self.store_one.id,
            }
        )
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 750_000.0)
        deposit = self.env["levis.store.cash.deposit"].create(
            {
                "warehouse_id": warehouse.id,
                "deposit_date": date(2026, 7, 9),
                "trading_date_from": date(2026, 7, 8),
                "trading_date_to": date(2026, 7, 8),
                "amount": 750_000.0,
                "bank_journal_id": self.bank.id,
            }
        )
        attachment = self.env["ir.attachment"].create(
            {"name": "slip.pdf", "raw": b"x", "res_model": deposit._name, "res_id": deposit.id}
        )
        deposit.attachment_ids = [(4, attachment.id)]
        deposit.action_submit()
        deposit.action_validate()

        # Narrative names no store at all — only the deposit can answer.
        self._statement(date(2026, 7, 9), 750_000.0, "TRSF E-BANKING CR 0107/FTSCY/WS95031")
        run = self._run()
        run.action_compute()
        self.assertEqual(run.line_ids.store_method, "deposit")
        self.assertEqual(run.line_ids.analytic_account_id, self.store_one)

    # ------------------------------------------------------------------
    # The line the ladder must not cross
    # ------------------------------------------------------------------
    def test_a_weak_inference_is_a_suggestion_not_an_attribution(self):
        # Only one store has anything open, so rung 5 can reach an answer — and
        # must still refuse to book it.
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._unmapped_ref())
        run = self._run()
        run.action_compute()
        line = run.line_ids
        self.assertEqual(line.store_confidence, "weak")
        self.assertEqual(line.suggested_analytic_account_id, self.store_one)
        self.assertFalse(line.analytic_account_id, "a suggestion may not attribute money")
        self.assertEqual(line.state, "unmapped")
        self.assertFalse(line.alloc_ids, "nothing may be allocated on a resemblance")

    def test_generation_refuses_while_a_store_is_only_suggested(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._unmapped_ref())
        run = self._run()
        run.action_compute()
        with self.assertRaises(UserError):
            run.action_generate_moves()

    def test_two_possible_stores_produce_no_suggestion_at_all(self):
        # Both stores could have produced the figure. Ambiguity is not weaker
        # evidence; it is none.
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._posrec(self.tender_a, self.store_two, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._unmapped_ref())
        run = self._run()
        run.action_compute()
        self.assertFalse(run.line_ids.suggested_analytic_account_id)
        self.assertFalse(run.line_ids.store_confidence)

    def test_confirming_a_store_makes_the_line_bookable(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._unmapped_ref())
        run = self._run()
        run.action_compute()
        run.line_ids.action_confirm_store()
        self.assertEqual(run.line_ids.analytic_account_id, self.store_one)
        self.assertTrue(run.line_ids.store_confirmed)
        run._assert_unconfirmed_stores()  # no longer refuses

    def test_confirming_teaches_the_wording_for_next_time(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._unmapped_ref())
        run = self._run()
        run.action_compute()
        run.line_ids.action_confirm_store()
        hint = self.env["levis.bank.narrative.hint"].search(
            [("company_id", "=", self.company.id), ("analytic_account_id", "=", self.store_one.id)]
        )
        self.assertTrue(hint, "the decision has to be remembered, or it is made again next month")
        self.assertEqual(hint.source, "manual")

    def test_ignore_warnings_still_lets_an_accountant_through(self):
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._unmapped_ref())
        run = self._run(ignore_warnings=True)
        run.action_compute()
        run._assert_unconfirmed_stores()

    # ------------------------------------------------------------------
    # Off by default
    # ------------------------------------------------------------------
    def test_with_advanced_matching_off_nothing_is_inferred(self):
        self.config.advanced_matching = False
        self._posrec(self.tender_a, self.store_one, date(2026, 7, 8), 1_000_000.0)
        self._statement(date(2026, 7, 9), 990_000.0, self._unmapped_ref())
        run = self._run()
        run.action_compute()
        self.assertFalse(run.line_ids.suggested_analytic_account_id)
        self.assertFalse(run.line_ids.store_method)
        self.assertEqual(run.line_ids.state, "unmapped")
