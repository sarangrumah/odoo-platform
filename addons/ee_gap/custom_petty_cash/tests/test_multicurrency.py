# -*- coding: utf-8 -*-
"""Foreign-currency advances.

Before 0.5.0 every generated line carried only debit/credit, so a USD 1,000
advance booked 1,000 IDR. These tests pin the fix: one conversion per pair,
currency_id on every line, doc-currency vs company-currency balances kept
apart, and settlement through the exchange-difference journal.
"""

from odoo import Command
from odoo.tests import tagged

from .common import PettyCashCommon

RATE = 16_000.0


@tagged("post_install", "-at_install")
class TestAdvanceMultiCurrency(PettyCashCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.foreign = cls.env["res.currency"].create(
            {"name": "TCU", "symbol": "T$", "rounding": 0.01, "decimal_places": 2}
        )
        cls.env["res.currency.rate"].create(
            {
                "name": "2020-01-01",
                "currency_id": cls.foreign.id,
                "company_id": cls.company.id,
                # company currency per 1 foreign unit -> inverse_company_rate
                "inverse_company_rate": RATE,
            }
        )
        if not cls.company.currency_exchange_journal_id:
            cls.company.currency_exchange_journal_id = cls.env["account.journal"].create(
                {"name": "CA Exchange", "type": "general", "code": "CAEX"}
            )

    def test_same_currency_still_stamps_currency_id(self):
        """currency_id must be set even when it equals the company currency —
        Odoo stores it there too, and a blank leaves amount_currency at 0."""
        request = self._full_cycle(1000.0)
        advance_line = request.disburse_move_id.line_ids.filtered(lambda line: line.account_id == self.advance_ca)
        self.assertTrue(advance_line.currency_id)
        self.assertEqual(advance_line.currency_id, self.company.currency_id)
        self.assertAlmostEqual(advance_line.amount_currency, advance_line.debit, 2)

    def test_disbursement_books_counter_value(self):
        request = self._new_request(1000.0, currency=self.foreign)
        request.action_submit()
        request.action_approve()
        request.action_disburse()

        move = request.disburse_move_id
        advance_line = move.line_ids.filtered(lambda line: line.account_id == self.advance_ca)
        bank_line = move.line_ids.filtered(lambda line: line.account_id == self.bank_acc)

        self.assertEqual(advance_line.currency_id, self.foreign)
        self.assertAlmostEqual(advance_line.amount_currency, 1000.0, 2)
        self.assertAlmostEqual(advance_line.debit, 1000.0 * RATE, 2)
        self.assertAlmostEqual(bank_line.amount_currency, -1000.0, 2)
        self.assertAlmostEqual(bank_line.credit, 1000.0 * RATE, 2)
        self.assertAlmostEqual(sum(move.line_ids.mapped("balance")), 0.0, 2)

        # Doc currency and company currency are reported separately.
        self.assertAlmostEqual(request.amount_outstanding, 1000.0, 2)
        self.assertAlmostEqual(request.amount_outstanding_company, 1000.0 * RATE, 2)

    def test_expense_realization_in_foreign_currency(self):
        request = self._new_request(1000.0, currency=self.foreign)
        request.action_submit()
        request.action_approve()
        request.action_disburse()

        realization = self.env["petty.cash.realization"].create(
            {
                "request_id": request.id,
                "line_ids": [
                    Command.create(
                        {
                            "line_type": "expense",
                            "name": "Hotel",
                            "account_id": self.expense.id,
                            "price_unit": 400.0,
                        }
                    ),
                    Command.create(
                        {
                            "line_type": "expense",
                            "name": "Taxi",
                            "account_id": self.expense.id,
                            "price_unit": 200.0,
                        }
                    ),
                ],
            }
        )
        realization.action_post()

        entry = realization.bill_ids.filtered(lambda m: m.move_type == "entry")
        self.assertTrue(entry)
        self.assertAlmostEqual(sum(entry.line_ids.mapped("balance")), 0.0, 2)
        self.assertAlmostEqual(sum(entry.line_ids.mapped("amount_currency")), 0.0, 2)
        advance_line = entry.line_ids.filtered(lambda line: line.account_id == self.advance_ca)
        self.assertAlmostEqual(advance_line.amount_currency, -600.0, 2)
        self.assertAlmostEqual(request.amount_outstanding, 400.0, 2)
        self.assertAlmostEqual(request.amount_outstanding_company, 400.0 * RATE, 2)

    def test_settle_reconciles_and_tags_exchange_move(self):
        request = self._new_request(1000.0, currency=self.foreign)
        request.action_submit()
        request.action_approve()
        request.action_disburse()

        realization = self.env["petty.cash.realization"].create(
            {
                "request_id": request.id,
                "line_ids": [
                    Command.create(
                        {
                            "line_type": "expense",
                            "name": "Hotel",
                            "account_id": self.expense.id,
                            "price_unit": 600.0,
                        }
                    )
                ],
            }
        )
        realization.action_post()

        # Rate moves before the leftover comes back.
        self.env["res.currency.rate"].create(
            {
                "name": "2030-01-01",
                "currency_id": self.foreign.id,
                "company_id": self.company.id,
                "inverse_company_rate": RATE * 1.1,
            }
        )
        request.action_return_balance()
        self.assertAlmostEqual(request.amount_outstanding, 0.0, 2)

        request.action_settle()
        self.assertEqual(request.state, "settled")
        advance_lines = request._advance_move_lines(posted_only=True)
        self.assertTrue(all(line.reconciled for line in advance_lines))
        # Any FX entry reconcile() spun up is tagged, so it shows on the
        # smart button and on the Kartu Uang Muka.
        exchange = request.move_ids.filtered(lambda m: m.journal_id == self.company.currency_exchange_journal_id)
        for move in exchange:
            self.assertEqual(move.petty_cash_request_id, request)
