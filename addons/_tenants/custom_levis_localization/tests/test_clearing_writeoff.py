# -*- coding: utf-8 -*-
"""Sending an identified residual somewhere other than suspense.

Reuses the clearing fixtures wholesale — the point of these tests is the
residual leg and nothing else.

The first test is the one that matters: with no write-off chosen, every figure
must be exactly what it was before this feature existed. If that ever fails, the
default is not really a default and the rest of the suite is being protected by
an accident.
"""

from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_pos_clearing import MID_ONE, TestPosClearing


@tagged("post_install", "-at_install")
class TestClearingWriteoff(TestPosClearing):
    def _short_run(self, generate=True):
        """A settlement 600 000 short of the receivables it claims to pay."""
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 400_000.0)
        settlement = self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        run = self._run(ar_fallback=False)
        run.action_compute()
        if generate:
            run.action_generate_moves()
        return run, settlement

    def _wizard(self, lines, **vals):
        base = {"line_ids": [Command.set(lines.ids)], "company_id": self.company.id}
        base.update(vals)
        return self.env["levis.clearing.writeoff.wizard"].create(base)

    # ------------------------------------------------------------------
    # The default must be indistinguishable from not having the feature
    # ------------------------------------------------------------------
    def test_without_a_write_off_the_residual_still_lands_on_suspense(self):
        run, settlement = self._short_run()
        short_legs = run.leg_ids.filtered(lambda leg: leg.role == "short")
        self.assertEqual(len(short_legs), 1)
        self.assertEqual(short_legs.account_id, self.suspense)
        self.assertFalse(run.leg_ids.filtered(lambda leg: leg.role == "writeoff"))
        run.action_post()
        _liq, suspense, _other = settlement._seek_for_lines()
        self.assertAlmostEqual(sum(suspense.mapped("balance")), -594_000.0, places=2)
        self.assertFalse(settlement.is_reconciled)

    def test_choosing_leave_on_suspense_changes_nothing(self):
        run, _settlement = self._short_run()
        wizard = self._wizard(run.line_ids, mode="suspense")
        wizard.action_apply()
        self.assertFalse(run.line_ids.writeoff_account_id)
        self.assertEqual(run.leg_ids.filtered(lambda leg: leg.role == "short").account_id, self.suspense)

    # ------------------------------------------------------------------
    # Absorbing, before posting
    # ------------------------------------------------------------------
    def test_a_write_off_moves_only_the_residual_leg(self):
        run, _settlement = self._short_run()
        before = {leg.id: leg.balance for leg in run.leg_ids.filtered(lambda leg: leg.role != "short")}

        wizard = self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="admin_fee")
        wizard.action_apply()

        self.assertEqual(run.line_ids.writeoff_account_id, self.charge)
        self.assertFalse(run.leg_ids.filtered(lambda leg: leg.role == "short"))
        writeoff = run.leg_ids.filtered(lambda leg: leg.role == "writeoff")
        self.assertEqual(len(writeoff), 1)
        self.assertEqual(writeoff.account_id, self.charge)
        # Every other leg is untouched.
        after = {leg.id: leg.balance for leg in run.leg_ids.filtered(lambda leg: leg.role != "writeoff")}
        self.assertEqual(before, after)

    def test_the_entry_still_balances_after_a_write_off(self):
        run, settlement = self._short_run()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="rounding").action_apply()
        planned = sum(run.leg_ids.mapped("balance"))
        self.assertAlmostEqual(planned, -settlement.amount, places=2)
        run.action_post()  # _preflight enforces the same identity

    def test_a_written_off_line_closes_the_statement_line(self):
        run, settlement = self._short_run()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="admin_fee").action_apply()
        run.action_post()
        _liq, suspense, _other = settlement._seek_for_lines()
        self.assertFalse(suspense, "nothing should be left on suspense")
        self.assertTrue(settlement.is_reconciled)

    def test_the_write_off_records_who_decided_it(self):
        run, _settlement = self._short_run()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="short_deposit").action_apply()
        self.assertEqual(run.line_ids.writeoff_uid, self.env.user)
        self.assertEqual(run.line_ids.writeoff_reason, "short_deposit")

    # ------------------------------------------------------------------
    # What it refuses
    # ------------------------------------------------------------------
    def test_a_residual_may_not_be_hidden_back_on_suspense(self):
        run, _settlement = self._short_run()
        wizard = self._wizard(run.line_ids, mode="absorb", account_id=self.suspense.id, reason="other")
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_a_residual_may_not_be_hidden_in_a_pos_receivable(self):
        run, _settlement = self._short_run()
        wizard = self._wizard(run.line_ids, mode="absorb", account_id=self.tender_a.id, reason="other")
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_absorbing_needs_an_account(self):
        run, _settlement = self._short_run()
        wizard = self._wizard(run.line_ids, mode="absorb", reason="other")
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_a_settlement_with_no_residual_has_nothing_to_write_off(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_a, self.store_one, day, 1_000_000.0)
        self._statement(
            date(2026, 7, 9),
            990_000.0,
            self._settlement_ref(MID_ONE, 1_000_000.0, 10_000.0, trans_day=day),
        )
        run = self._run()
        run.action_compute()
        wizard = self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="other")
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_posting_refuses_a_write_off_over_the_limit(self):
        run, _settlement = self._short_run()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="other").action_apply()
        run.config_id.writeoff_limit_amount = 1_000.0
        with self.assertRaises(UserError):
            run.action_post()

    def test_a_write_off_inside_the_limit_still_posts(self):
        run, _settlement = self._short_run()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="other").action_apply()
        run.config_id.writeoff_limit_amount = 10_000_000.0
        run.action_post()
        self.assertEqual(run.state, "posted")

    def test_no_limit_means_no_cap(self):
        run, _settlement = self._short_run()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="other").action_apply()
        self.assertEqual(run.config_id.writeoff_limit_amount, 0.0)
        run.action_post()
        self.assertEqual(run.state, "posted")

    # ------------------------------------------------------------------
    # After posting
    # ------------------------------------------------------------------
    def test_a_residual_can_still_be_written_off_after_posting(self):
        run, settlement = self._short_run()
        run.action_post()
        _liq, suspense, _other = settlement._seek_for_lines()
        self.assertTrue(suspense)

        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="admin_fee").action_apply()

        _liq, suspense_after, _other = settlement._seek_for_lines()
        self.assertFalse(suspense_after, "the suspense item is replaced, not supplemented")
        self.assertTrue(settlement.is_reconciled)
        booked = settlement.move_id.line_ids.filtered(lambda aml: aml.account_id == self.charge)
        self.assertAlmostEqual(sum(booked.mapped("balance")), -594_000.0, places=2)

    def test_the_posted_write_off_carries_the_store(self):
        run, settlement = self._short_run()
        run.action_post()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="admin_fee").action_apply()
        booked = settlement.move_id.line_ids.filtered(lambda aml: aml.account_id == self.charge)
        self.assertEqual(booked.analytic_distribution, {str(self.store_one.id): 100.0})

    def test_a_posted_write_off_cannot_be_undone_by_clearing_a_field(self):
        run, _settlement = self._short_run()
        run.action_post()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="other").action_apply()
        wizard = self._wizard(run.line_ids, mode="suspense")
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_writing_off_twice_refuses_rather_than_doubling(self):
        run, _settlement = self._short_run()
        run.action_post()
        self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="other").action_apply()
        # Nothing on suspense any more, so a second attempt has nothing to move.
        wizard = self._wizard(run.line_ids, mode="absorb", account_id=self.charge.id, reason="other")
        with self.assertRaises(UserError):
            wizard.action_apply()
