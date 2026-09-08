# -*- coding: utf-8 -*-
"""Manual exchange rate on a foreign-currency payment.

Odoo 19 lets a user type the rate on a bill (``account.move.invoice_currency_
rate``) but gives a payment no such field: its journal entry is always valued at
whatever ``res.currency.rate`` says on the payment date. Treasury reality is the
opposite -- the bank advice carries the rate that was actually dealt, and that is
the number that has to hit the books.

This adds the missing field, quoted in the direction a user reads
("1 USD = 16,200 IDR"), and pins it onto the conversion that builds the journal
entry. Nothing else changes: the difference against the rate on the bill still
lands on the exchange-difference account through the normal reconciliation, so a
manual rate produces a realised FX gain/loss, never a silent re-valuation.
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

FX_RATE_DIGITS = (16, 6)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    fx_foreign_currency_id = fields.Many2one(
        "res.currency",
        string="Foreign Currency",
        compute="_compute_fx_foreign_currency_id",
        help="The payment currency, when it differs from the company currency.",
    )
    fx_show_rate = fields.Boolean(compute="_compute_fx_foreign_currency_id")
    fx_expected_rate = fields.Float(
        string="Rate of the Day",
        compute="_compute_fx_expected_rate",
        digits=FX_RATE_DIGITS,
        help="The rate Odoo would apply on the payment date, from res.currency.rate.",
    )
    manual_currency_rate = fields.Float(
        string="Exchange Rate",
        compute="_compute_manual_currency_rate",
        store=True,
        readonly=False,
        copy=False,
        digits=FX_RATE_DIGITS,
        help="How many units of the company currency one unit of the payment currency "
        "is worth, i.e. the rate actually dealt with the bank. Defaults to the rate of "
        "the payment date and can be overridden while the payment is a draft.",
    )
    fx_rate_hint = fields.Char(compute="_compute_fx_rate_hint")

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends("currency_id", "company_currency_id")
    def _compute_fx_foreign_currency_id(self):
        for payment in self:
            foreign = (
                payment.currency_id
                if payment.currency_id and payment.currency_id != payment.company_currency_id
                else self.env["res.currency"]
            )
            payment.fx_foreign_currency_id = foreign
            payment.fx_show_rate = bool(foreign)

    @api.depends("fx_foreign_currency_id", "company_id", "date")
    def _compute_fx_expected_rate(self):
        for payment in self:
            payment.fx_expected_rate = payment._fx_rate_of_the_day()

    @api.depends("currency_id", "company_id", "date")
    def _compute_manual_currency_rate(self):
        for payment in self:
            payment.manual_currency_rate = payment._fx_rate_of_the_day()

    @api.depends("fx_foreign_currency_id", "company_currency_id")
    def _compute_fx_rate_hint(self):
        for payment in self:
            if payment.fx_foreign_currency_id:
                payment.fx_rate_hint = _(
                    "per 1 %(foreign_currency)s",
                    foreign_currency=payment.fx_foreign_currency_id.name,
                )
            else:
                payment.fx_rate_hint = False

    @api.constrains("manual_currency_rate", "currency_id", "company_id")
    def _check_manual_currency_rate(self):
        for payment in self:
            if payment.fx_show_rate and payment.manual_currency_rate <= 0:
                raise ValidationError(_("The exchange rate of a foreign-currency payment must be strictly positive."))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fx_rate_of_the_day(self):
        """Company-currency units per one unit of the payment currency, per res.currency.rate."""
        self.ensure_one()
        if not self.fx_foreign_currency_id:
            return 0.0
        return (
            self.env["res.currency"]
            .with_context(manual_fx_rate=False)
            ._get_conversion_rate(
                from_currency=self.fx_foreign_currency_id,
                to_currency=self.company_currency_id,
                company=self.company_id or self.env.company,
                date=self.date or fields.Date.context_today(self),
            )
        )

    def _manual_fx_context(self):
        """Payload for ``res.currency._get_conversion_rate``; empty when inapplicable."""
        self.ensure_one()
        if not self.fx_show_rate or not self.manual_currency_rate:
            return {}
        return {"manual_fx_rate": {"currency_id": self.currency_id.id, "rate": self.manual_currency_rate}}

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------
    def _prepare_move_lines_per_type(self, *args, **kwargs):
        """Value the journal entry at the dealt rate rather than the rate of the day."""
        self.ensure_one()
        fx_context = self._manual_fx_context()
        if fx_context:
            return super(AccountPayment, self.with_context(**fx_context))._prepare_move_lines_per_type(*args, **kwargs)
        return super()._prepare_move_lines_per_type(*args, **kwargs)

    @api.depends(
        "move_id.amount_total_signed",
        "amount",
        "payment_type",
        "currency_id",
        "date",
        "company_id",
        "company_currency_id",
        "manual_currency_rate",
    )
    def _compute_amount_company_currency_signed(self):
        """Same figure as the journal entry, so the form never contradicts the books."""
        for payment in self:
            fx_context = payment._manual_fx_context()
            super(AccountPayment, payment.with_context(**fx_context))._compute_amount_company_currency_signed()
