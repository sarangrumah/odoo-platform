# -*- coding: utf-8 -*-
"""The cash-deposit document, and the claim it makes on a bank credit.

The point of this model is to replace a guess with evidence, so most of these
tests are about the moments it must refuse: validating without a slip, claiming a
bank credit that another deposit already claimed, and — the one that matters most
— declining to name a store when two deposits fit the same credit equally well.
"""

from datetime import date, timedelta

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install")
class TestStoreCashDeposit(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.bank_journal = cls.company_data["default_journal_bank"]
        plan = cls.env["account.analytic.plan"].create({"name": "OU Deposit Test"})
        cls.analytic = cls.env["account.analytic.account"].create(
            {"name": "Sunter", "plan_id": plan.id, "company_id": cls.company.id}
        )
        cls.warehouse = cls.env["stock.warehouse"].create(
            {
                "name": "Levi's Sunter Dep",
                "code": "LSDP",
                "company_id": cls.company.id,
                "l10n_store_code": "DEP001",
                "l10n_ou_analytic_id": cls.analytic.id,
            }
        )
        cls.trading = date(2026, 7, 20)
        cls.banked = date(2026, 7, 21)

    def _deposit(self, amount=1_000_000.0, **kwargs):
        vals = {
            "warehouse_id": self.warehouse.id,
            "deposit_date": self.banked,
            "trading_date_from": self.trading,
            "trading_date_to": self.trading,
            "amount": amount,
            "bank_journal_id": self.bank_journal.id,
        }
        vals.update(kwargs)
        return self.env["levis.store.cash.deposit"].create(vals)

    def _evidence(self, deposit):
        attachment = self.env["ir.attachment"].create(
            {"name": "slip.pdf", "raw": b"slip", "res_model": deposit._name, "res_id": deposit.id}
        )
        deposit.attachment_ids = [(4, attachment.id)]
        return attachment

    def _validated(self, **kwargs):
        deposit = self._deposit(**kwargs)
        self._evidence(deposit)
        deposit.action_submit()
        deposit.action_validate()
        return deposit

    def _statement_line(self, amount=1_000_000.0, when=None, journal=None):
        statement = self.env["account.bank.statement.line"].create(
            {
                "journal_id": (journal or self.bank_journal).id,
                "payment_ref": "SETORAN TUNAI",
                "amount": amount,
                "date": when or self.banked,
            }
        )
        return statement

    # ------------------------------------------------------------------
    # Numbering and the transfer reference
    # ------------------------------------------------------------------
    def test_a_deposit_is_numbered_on_creation(self):
        deposit = self._deposit()
        self.assertNotEqual(deposit.name, "/")
        self.assertTrue(deposit.name.startswith("SETOR/"))

    def test_the_transfer_reference_carries_the_store_code(self):
        deposit = self._deposit()
        self.assertTrue(deposit.berita_acara_ref)
        self.assertIn("DEP001", deposit.berita_acara_ref)
        self.assertIn("20260721", deposit.berita_acara_ref)

    def test_a_store_with_no_code_gets_no_transfer_reference(self):
        # Better an empty field than a reference that names no store.
        self.warehouse.l10n_store_code = False
        deposit = self._deposit()
        self.assertFalse(deposit.berita_acara_ref)

    # ------------------------------------------------------------------
    # The workflow, and what it refuses
    # ------------------------------------------------------------------
    def test_the_states_run_draft_submitted_validated(self):
        deposit = self._deposit()
        self.assertEqual(deposit.state, "draft")
        deposit.action_submit()
        self.assertEqual(deposit.state, "submitted")
        self._evidence(deposit)
        deposit.action_validate()
        self.assertEqual(deposit.state, "validated")
        self.assertEqual(deposit.validated_uid, self.env.user)

    def test_a_deposit_cannot_be_validated_without_evidence(self):
        deposit = self._deposit()
        deposit.action_submit()
        with self.assertRaises(UserError):
            deposit.action_validate()

    def test_a_draft_deposit_cannot_skip_straight_to_validated(self):
        deposit = self._deposit()
        self._evidence(deposit)
        with self.assertRaises(UserError):
            deposit.action_validate()

    def test_a_store_without_an_operating_unit_cannot_be_validated(self):
        self.warehouse.l10n_ou_analytic_id = False
        deposit = self._deposit()
        self._evidence(deposit)
        deposit.action_submit()
        with self.assertRaises(UserError):
            deposit.action_validate()

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    def test_a_deposit_must_be_positive(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self._deposit(amount=0.0)
                self.env.flush_all()

    def test_money_cannot_be_banked_before_it_is_taken(self):
        with self.assertRaises(ValidationError):
            self._deposit(
                trading_date_from=self.banked + timedelta(days=1),
                trading_date_to=self.banked + timedelta(days=1),
            )

    def test_the_takings_period_cannot_run_backwards(self):
        with self.assertRaises(ValidationError):
            self._deposit(
                trading_date_from=self.trading,
                trading_date_to=self.trading - timedelta(days=2),
            )

    def test_one_bank_credit_cannot_be_claimed_twice(self):
        line = self._statement_line()
        first = self._validated()
        second = self._validated()
        first._claim(line)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                second._claim(line)
                self.env.flush_all()

    def test_many_deposits_may_await_a_bank_credit(self):
        # NULL statement_line_id must stay distinct, or a second unmatched
        # deposit could never be keyed.
        self._validated()
        self._validated()
        self.env.flush_all()

    def test_a_matched_deposit_may_not_be_rekeyed(self):
        deposit = self._validated()
        deposit._claim(self._statement_line())
        with self.assertRaises(UserError):
            deposit.amount = 999.0

    def test_unmatching_releases_the_credit(self):
        deposit = self._validated()
        deposit._claim(self._statement_line())
        self.assertEqual(deposit.state, "matched")
        deposit.action_unmatch()
        self.assertEqual(deposit.state, "validated")
        self.assertFalse(deposit.statement_line_id)
        deposit.amount = 999.0  # rekeying is allowed again

    # ------------------------------------------------------------------
    # Matching — the ladder's third rung
    # ------------------------------------------------------------------
    def test_one_fitting_deposit_names_the_store(self):
        deposit = self._validated(amount=1_234_500.0)
        line = self._statement_line(amount=1_234_500.0)
        found = self.env["levis.store.cash.deposit"]._find_for_statement_line(line)
        self.assertEqual(found, deposit)

    def test_two_equally_good_deposits_name_neither(self):
        # Two stores, one bank, one identical float. This is a real situation and
        # it is not evidence for either store.
        self._validated(amount=500_000.0)
        self._validated(amount=500_000.0)
        line = self._statement_line(amount=500_000.0)
        found = self.env["levis.store.cash.deposit"]._find_for_statement_line(line)
        self.assertFalse(found)

    def test_a_deposit_that_is_not_validated_is_not_offered(self):
        deposit = self._deposit(amount=700_000.0)
        deposit.action_submit()
        line = self._statement_line(amount=700_000.0)
        self.assertFalse(self.env["levis.store.cash.deposit"]._find_for_statement_line(line))

    def test_a_cancelled_deposit_is_not_offered(self):
        deposit = self._validated(amount=800_000.0)
        deposit.action_cancel()
        line = self._statement_line(amount=800_000.0)
        self.assertFalse(self.env["levis.store.cash.deposit"]._find_for_statement_line(line))

    def test_an_already_matched_deposit_is_not_offered_again(self):
        deposit = self._validated(amount=900_000.0)
        deposit._claim(self._statement_line(amount=900_000.0))
        another = self._statement_line(amount=900_000.0)
        self.assertFalse(self.env["levis.store.cash.deposit"]._find_for_statement_line(another))

    def test_a_deposit_outside_the_window_is_not_offered(self):
        self._validated(amount=1_100_000.0)
        late = self._statement_line(amount=1_100_000.0, when=self.banked + timedelta(days=30))
        found = self.env["levis.store.cash.deposit"]._find_for_statement_line(late, window_days=3)
        self.assertFalse(found)

    def test_a_deposit_dated_after_the_credit_is_not_offered(self):
        # Money cannot be paid in after it has already landed.
        self._validated(amount=1_300_000.0)
        early = self._statement_line(amount=1_300_000.0, when=self.banked - timedelta(days=1))
        self.assertFalse(self.env["levis.store.cash.deposit"]._find_for_statement_line(early))

    def test_a_near_miss_needs_the_tolerance_to_be_offered(self):
        self._validated(amount=1_000_000.0)
        line = self._statement_line(amount=999_000.0)
        self.assertFalse(self.env["levis.store.cash.deposit"]._find_for_statement_line(line))
        found = self.env["levis.store.cash.deposit"]._find_for_statement_line(line, tolerance=5_000.0)
        self.assertTrue(found)

    def test_a_credit_on_another_bank_is_not_offered(self):
        other_journal = self.env["account.journal"].create(
            {"name": "Other Bank", "type": "bank", "code": "OBNK", "company_id": self.company.id}
        )
        self._validated(amount=1_500_000.0)
        # Created on the other journal rather than reassigned: a statement line's
        # journal drives its move, and writing it after the fact is not a thing
        # the ORM supports.
        line = self._statement_line(amount=1_500_000.0, journal=other_journal)
        self.assertFalse(self.env["levis.store.cash.deposit"]._find_for_statement_line(line))

    # ------------------------------------------------------------------
    # Expectation from the tills
    # ------------------------------------------------------------------
    def test_no_linked_session_is_not_a_shortfall(self):
        # "Nobody measured" must not read as "the store was short".
        deposit = self._deposit(amount=1_000_000.0)
        self.assertEqual(deposit.expected_amount, 0.0)
        self.assertEqual(deposit.variance, 0.0)
