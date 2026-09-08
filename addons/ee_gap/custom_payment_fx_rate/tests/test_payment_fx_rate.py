# -*- coding: utf-8 -*-
"""Manual exchange rate on payments.

The fixture currency of ``AccountTestInvoicingCommon`` is quoted 2 foreign per 1
company unit from 2017-01-01, i.e. the rate of the day in the direction this
module uses (company units per foreign unit) is 0.5.
"""

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged

RATE_OF_THE_DAY = 0.5
DEALT_RATE = 0.8
PAYMENT_DATE = "2017-06-15"


@tagged("post_install", "-at_install")
class TestPaymentFxRate(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company_currency = cls.company.currency_id
        cls.foreign_currency = cls.setup_other_currency("EUR")
        cls.bank_journal = cls.company_data["default_journal_bank"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _new_payment(self, currency, amount=100.0):
        return self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.partner_a.id,
                "amount": amount,
                "currency_id": currency.id,
                "date": PAYMENT_DATE,
                "journal_id": self.bank_journal.id,
            }
        )

    def _new_foreign_bill(self, amount=100.0):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": PAYMENT_DATE,
                "date": PAYMENT_DATE,
                "currency_id": self.foreign_currency.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Imported goods",
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _open_wizard(self, bill, **values):
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create({"payment_date": PAYMENT_DATE, **values})
        )
        return wizard

    # ------------------------------------------------------------------
    # Payment form
    # ------------------------------------------------------------------
    def test_default_rate_is_the_rate_of_the_day(self):
        payment = self._new_payment(self.foreign_currency)
        self.assertTrue(payment.fx_show_rate)
        self.assertEqual(payment.fx_foreign_currency_id, self.foreign_currency)
        self.assertAlmostEqual(payment.manual_currency_rate, RATE_OF_THE_DAY)
        self.assertAlmostEqual(payment.fx_expected_rate, RATE_OF_THE_DAY)

    def test_company_currency_payment_has_no_rate(self):
        payment = self._new_payment(self.company_currency)
        self.assertFalse(payment.fx_show_rate)
        self.assertFalse(payment.fx_foreign_currency_id)
        self.assertFalse(payment.manual_currency_rate)
        self.assertFalse(payment._manual_fx_context())

    def test_untouched_rate_books_the_rate_of_the_day(self):
        payment = self._new_payment(self.foreign_currency)
        payment.action_post()
        liquidity = payment.move_id.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id)
        self.assertAlmostEqual(sum(liquidity.mapped("balance")), -100.0 * RATE_OF_THE_DAY)
        self.assertAlmostEqual(sum(liquidity.mapped("amount_currency")), -100.0)

    def test_manual_rate_values_the_journal_entry(self):
        payment = self._new_payment(self.foreign_currency)
        payment.manual_currency_rate = DEALT_RATE
        payment.action_post()

        move = payment.move_id
        self.assertAlmostEqual(sum(move.line_ids.mapped("balance")), 0.0, msg="the entry must stay balanced")
        liquidity = move.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id)
        counterpart = move.line_ids - liquidity
        # 100 foreign at 0.8 instead of the 0.5 of the day.
        self.assertAlmostEqual(sum(liquidity.mapped("balance")), -100.0 * DEALT_RATE)
        self.assertAlmostEqual(sum(liquidity.mapped("amount_currency")), -100.0)
        self.assertAlmostEqual(sum(counterpart.mapped("balance")), 100.0 * DEALT_RATE)

    def test_rate_must_be_positive(self):
        payment = self._new_payment(self.foreign_currency)
        with self.assertRaises(ValidationError):
            payment.manual_currency_rate = 0.0

    # ------------------------------------------------------------------
    # Register Payment wizard
    # ------------------------------------------------------------------
    def test_wizard_defaults_to_the_rate_of_the_day(self):
        wizard = self._open_wizard(self._new_foreign_bill())
        self.assertTrue(wizard.fx_show_rate)
        self.assertEqual(wizard.fx_foreign_currency_id, self.foreign_currency)
        self.assertAlmostEqual(wizard.manual_currency_rate, RATE_OF_THE_DAY)

    def test_wizard_rate_drives_the_company_currency_amount(self):
        """An IDR bank account paying a USD bill: the rate sets the rupiah proposed."""
        bill = self._new_foreign_bill()
        wizard = self._open_wizard(bill, currency_id=self.company_currency.id)
        self.assertAlmostEqual(wizard.amount, 100.0 * RATE_OF_THE_DAY)

        wizard.manual_currency_rate = DEALT_RATE
        wizard._onchange_manual_currency_rate()
        self.assertAlmostEqual(wizard.amount, 100.0 * DEALT_RATE)

        wizard._create_payments()
        self.assertAlmostEqual(bill.amount_residual, 0.0, msg="the bill must still reconcile in full")

    def test_wizard_carries_the_rate_onto_a_foreign_payment(self):
        bill = self._new_foreign_bill()
        wizard = self._open_wizard(bill)
        wizard.manual_currency_rate = DEALT_RATE
        payments = wizard._create_payments()

        self.assertEqual(len(payments), 1)
        self.assertEqual(payments.currency_id, self.foreign_currency)
        self.assertAlmostEqual(payments.manual_currency_rate, DEALT_RATE)
        liquidity = payments.move_id.line_ids.filtered(lambda line: line.account_id == payments.outstanding_account_id)
        self.assertAlmostEqual(sum(liquidity.mapped("balance")), -100.0 * DEALT_RATE)

    def test_wizard_leaves_a_company_currency_payment_alone(self):
        bill = self.init_invoice("in_invoice", partner=self.partner_a, amounts=[100.0], post=True)
        wizard = self._open_wizard(bill)
        self.assertFalse(wizard.fx_show_rate)
        self.assertFalse(wizard._manual_fx_context())
        self.assertAlmostEqual(wizard.amount, bill.amount_total)
