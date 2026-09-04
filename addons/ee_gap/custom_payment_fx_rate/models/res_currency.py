# -*- coding: utf-8 -*-
"""Let a caller pin the conversion rate for one currency pair.

``res.currency._convert`` -- and therefore every amount Odoo derives from a
foreign-currency payment -- goes through ``_get_conversion_rate``. Putting the
override here means the manual rate reaches the wizard's proposed amount, the
payment's journal entry and the write-off lines through a single seam, instead
of each of them having to recompute balances by hand.

The context payload is ``{'currency_id': <id>, 'rate': <company units per one
unit of that currency>}`` -- the direction a user quotes ("1 USD = 16,200 IDR"),
which is the inverse of the ``res.currency.rate`` stored by Odoo.
"""

from __future__ import annotations

from odoo import api, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @api.model
    def _get_conversion_rate(self, from_currency, to_currency, company=None, date=None):
        forced = self.env.context.get("manual_fx_rate")
        if forced:
            currency_id = forced.get("currency_id")
            rate = forced.get("rate")
            company = company or self.env.company
            company_currency = company.currency_id
            if currency_id and rate and from_currency != to_currency:
                if from_currency.id == currency_id and to_currency == company_currency:
                    return rate
                if to_currency.id == currency_id and from_currency == company_currency:
                    return 1.0 / rate
        return super()._get_conversion_rate(from_currency, to_currency, company=company, date=date)
