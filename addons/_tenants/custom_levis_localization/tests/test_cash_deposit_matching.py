# -*- coding: utf-8 -*-
"""The berita acara as the thing that names a cash deposit's store.

A cash narrative is free text somebody typed into a transfer form. Measured on
prd_levis_begbal for September 2026: of the 70 deposits no rule could place, 44
named no store at all — only the depositor, a date, or nothing beyond "SETORAN
TUNAI". No keyword rule can ever place those, and inventing one that tries would
be guessing whose money it is.

A counted, signed and attached deposit slip can. These tests are about the
moments it must refuse to: two slips that fit equally well, a slip outside the
window, and a slip that has already been spent.
"""

from datetime import date, timedelta

from odoo import Command
from odoo.tests import tagged

from .test_pos_clearing import TestPosClearing

TRADING_DAY = date(2026, 7, 8)
BANKED_ON = date(2026, 7, 9)
CASH_REF = "TRSF E-BANKING CR 0907/FTSCY/WS95271 setoran DEWI INTAN SARI"


@tagged("post_install", "-at_install")
class TestCashDepositMatching(TestPosClearing):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.pos_cash_receivable_code",
            cls.tender_c.with_company(cls.company).code,
        )
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.warehouse.l10n_ou_analytic_id = cls.store_one.id

    # ------------------------------------------------------------------
    def _slip(self, amount, banked=BANKED_ON, warehouse=None, validate=True):
        deposit = self.env["levis.store.cash.deposit"].create(
            {
                "warehouse_id": (warehouse or self.warehouse).id,
                "deposit_date": banked,
                "trading_date_from": TRADING_DAY,
                "trading_date_to": TRADING_DAY,
                "amount": amount,
                "bank_journal_id": self.bank.id,
            }
        )
        if not validate:
            return deposit
        attachment = self.env["ir.attachment"].create(
            {"name": "slip.pdf", "raw": b"slip", "res_model": deposit._name, "res_id": deposit.id}
        )
        deposit.attachment_ids = [Command.link(attachment.id)]
        deposit.action_submit()
        deposit.action_validate()
        return deposit

    def _cash_line(self, run):
        return run.line_ids.filtered(lambda line: line.kind == "cash_deposit")

    # ------------------------------------------------------------------
    # What it makes possible
    # ------------------------------------------------------------------
    def test_a_slip_names_the_store_no_narrative_could(self):
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        slip = self._slip(1_000_000.0)

        run = self._run()
        run.action_compute()

        line = self._cash_line(run)
        self.assertEqual(line.cash_deposit_id, slip)
        self.assertEqual(line.analytic_account_id, self.store_one, "the slip placed what the narrative could not")
        self.assertEqual(line.allocated, 1_000_000.0)
        self.assertFalse(line.trans_date_is_derived, "the slip states the day; it is not a lag guess")

    def test_without_a_slip_the_same_line_stays_unmapped(self):
        """The control: the narrative alone names nobody."""
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)

        run = self._run()
        run.action_compute()

        line = self._cash_line(run)
        self.assertEqual(line.state, "unmapped")
        self.assertFalse(line.cash_deposit_id)
        self.assertFalse(line.analytic_account_id)

    # ------------------------------------------------------------------
    # The refusals
    # ------------------------------------------------------------------
    def test_two_slips_that_fit_equally_well_name_neither(self):
        """Two shops, one bank, one flat float — a real situation, not evidence."""
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        other = self.env["stock.warehouse"].create(
            {"name": "Store Two WH", "code": "ST2", "company_id": self.company.id}
        )
        other.l10n_ou_analytic_id = self.store_two.id
        self._slip(1_000_000.0)
        self._slip(1_000_000.0, warehouse=other)

        run = self._run()
        run.action_compute()

        line = self._cash_line(run)
        self.assertFalse(line.cash_deposit_id)
        self.assertEqual(line.state, "unmapped", "an ambiguous pair must place nobody")

    def test_a_slip_for_a_different_amount_is_not_this_deposit(self):
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        self._slip(999_999.0)

        run = self._run()
        run.action_compute()

        self.assertFalse(self._cash_line(run).cash_deposit_id, "a rupiah out is a different deposit")

    def test_a_slip_banked_after_the_money_landed_is_not_it(self):
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        self._slip(1_000_000.0, banked=BANKED_ON + timedelta(days=1))

        run = self._run()
        run.action_compute()

        self.assertFalse(self._cash_line(run).cash_deposit_id, "money is paid in on or before the day it lands")

    def test_an_unvalidated_slip_vouches_for_nothing(self):
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        self._slip(1_000_000.0, validate=False)

        run = self._run()
        run.action_compute()

        self.assertFalse(self._cash_line(run).cash_deposit_id, "validation is the moment someone vouches")

    # ------------------------------------------------------------------
    # The slip is spent when the money is, not before
    # ------------------------------------------------------------------
    def test_computing_does_not_claim_the_slip(self):
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        slip = self._slip(1_000_000.0)

        run = self._run()
        run.action_compute()

        self.assertEqual(slip.state, "validated", "a proposal may be recomputed; it may not spend a slip")
        self.assertFalse(slip.statement_line_id)

    def test_posting_claims_the_slip(self):
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        statement = self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        slip = self._slip(1_000_000.0)

        run = self._run()
        run.action_compute()
        run.action_generate_moves()
        run.action_post()

        self.assertEqual(slip.state, "matched")
        self.assertEqual(slip.statement_line_id, statement)

    def test_a_cash_deposit_is_still_never_proven(self):
        """The store-day proof keeps cash out of both sides, slip or no slip."""
        self._posrec(self.tender_c, self.store_one, TRADING_DAY, 1_000_000.0)
        self._statement(BANKED_ON, 1_000_000.0, CASH_REF)
        self._slip(1_000_000.0)

        run = self._run()
        run.action_compute()

        self.assertFalse(self._cash_line(run).proof_state, "a slip places the store; it does not prove a day")
