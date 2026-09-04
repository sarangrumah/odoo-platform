# -*- coding: utf-8 -*-
"""Manual exchange rate on the Register Payment wizard.

Two situations, one field:

* the wizard is denominated in a foreign currency -- the rate values the journal
  entry, exactly as on the payment form;
* the wizard is denominated in the company currency while the bills being
  settled are foreign (an IDR bank account paying a USD bill) -- the rate then
  drives the amount the wizard proposes, so the user types the rate off the bank
  advice instead of back-computing the rupiah figure by hand.
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

FX_RATE_DIGITS = (16, 6)


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    fx_foreign_currency_id = fields.Many2one(
        "res.currency",
        string="Foreign Currency",
        compute="_compute_fx_foreign_currency_id",
        help="The foreign currency this payment involves: the payment currency when it "
        "differs from the company currency, otherwise the currency of the documents paid.",
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
        digits=FX_RATE_DIGITS,
        help="How many units of the company currency one unit of the foreign currency is "
        "worth, i.e. the rate actually dealt with the bank. Defaults to the rate of the "
        "payment date.",
    )
    fx_rate_hint = fields.Char(compute="_compute_fx_rate_hint")

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends("currency_id", "source_currency_id", "company_currency_id")
    def _compute_fx_foreign_currency_id(self):
        for wizard in self:
            company_currency = wizard.company_currency_id
            foreign = self.env["res.currency"]
            if wizard.currency_id and wizard.currency_id != company_currency:
                foreign = wizard.currency_id
            elif wizard.source_currency_id and wizard.source_currency_id != company_currency:
                foreign = wizard.source_currency_id
            wizard.fx_foreign_currency_id = foreign
            wizard.fx_show_rate = bool(foreign)

    @api.depends("fx_foreign_currency_id", "company_id", "payment_date")
    def _compute_fx_expected_rate(self):
        for wizard in self:
            wizard.fx_expected_rate = wizard._fx_rate_of_the_day()

    @api.depends("currency_id", "source_currency_id", "company_id", "payment_date")
    def _compute_manual_currency_rate(self):
        for wizard in self:
            wizard.manual_currency_rate = wizard._fx_rate_of_the_day()

    @api.depends("fx_foreign_currency_id", "company_currency_id")
    def _compute_fx_rate_hint(self):
        for wizard in self:
            if wizard.fx_foreign_currency_id:
                wizard.fx_rate_hint = _(
                    "per 1 %(foreign_currency)s",
                    foreign_currency=wizard.fx_foreign_currency_id.name,
                )
            else:
                wizard.fx_rate_hint = False

    @api.onchange("manual_currency_rate")
    def _onchange_manual_currency_rate(self):
        """Re-propose the amount at the rate just typed, unless the user set one by hand."""
        if not self.fx_show_rate or self.custom_user_amount:
            return
        if not self.journal_id or not self.currency_id or not self.payment_date:
            return
        if self.manual_currency_rate <= 0:
            return
        self.amount = self._get_total_amounts_to_pay(self.batches)["amount_by_default"]

    @api.constrains("manual_currency_rate")
    def _check_manual_currency_rate(self):
        for wizard in self:
            if wizard.fx_show_rate and wizard.manual_currency_rate <= 0:
                raise ValidationError(_("The exchange rate of a foreign-currency payment must be strictly positive."))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fx_rate_of_the_day(self):
        """Company-currency units per one unit of the foreign currency, per res.currency.rate."""
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
                date=self.payment_date or fields.Date.context_today(self),
            )
        )

    def _manual_fx_context(self):
        """Payload for ``res.currency._get_conversion_rate``; empty when inapplicable."""
        self.ensure_one()
        if not self.fx_show_rate or self.manual_currency_rate <= 0:
            return {}
        return {
            "manual_fx_rate": {
                "currency_id": self.fx_foreign_currency_id.id,
                "rate": self.manual_currency_rate,
            }
        }

    def _with_manual_fx(self):
        fx_context = self._manual_fx_context()
        return self.with_context(**fx_context) if fx_context else self

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------
    def _convert_to_wizard_currency(self, installments):
        """Single seam for the amount the wizard proposes: every branch converts here."""
        self.ensure_one()
        fx_context = self._manual_fx_context()
        if not fx_context:
            return super()._convert_to_wizard_currency(installments)
        # The residuals are totalled per ``line.currency_id``, and a currency read off a
        # journal item carries that item's context, not the wizard's -- so the lines
        # have to be re-read under the manual rate for the conversion to see it. The
        # copies stay local: the caller keeps using the original installment dicts.
        installments = [
            dict(installment, line=installment["line"].with_context(**fx_context)) for installment in installments
        ]
        return super(AccountPaymentRegister, self.with_context(**fx_context))._convert_to_wizard_currency(installments)

    def _create_payment_vals_from_wizard(self, batch_result):
        fx_context = self._manual_fx_context()
        if fx_context:
            # Same trap as in _convert_to_wizard_currency: the early-payment-discount
            # branch converts through ``aml.currency_id``, so the batch lines have to
            # carry the context too. Same records, only re-read.
            batch_result = dict(batch_result, lines=batch_result["lines"].with_context(**fx_context))
        vals = super(AccountPaymentRegister, self._with_manual_fx())._create_payment_vals_from_wizard(batch_result)
        return self._add_manual_currency_rate(vals)

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super(AccountPaymentRegister, self._with_manual_fx())._create_payment_vals_from_batch(batch_result)
        return self._add_manual_currency_rate(vals)

    def _add_manual_currency_rate(self, vals):
        """Carry the rate onto the payment, but only when the payment itself is foreign.

        Paying a USD bill out of an IDR bank account creates an IDR payment: the
        rate shaped the amount proposed above and has nothing left to value.
        """
        self.ensure_one()
        if self._manual_fx_context() and vals.get("currency_id") == self.fx_foreign_currency_id.id:
            vals["manual_currency_rate"] = self.manual_currency_rate
        return vals
