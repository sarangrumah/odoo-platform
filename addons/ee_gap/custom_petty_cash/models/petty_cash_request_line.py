# -*- coding: utf-8 -*-
"""Detail lines of a petty cash request — what the money is asked for."""

from __future__ import annotations

from odoo import fields, models


class PettyCashRequestLine(models.Model):
    _name = "petty.cash.request.line"
    _description = "Petty Cash Request Detail Line"
    _order = "sequence, id"

    request_id = fields.Many2one(
        "petty.cash.request",
        string="Request",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Description", required=True)
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        help="Indicative expense/asset account for this spend.",
    )
    amount = fields.Monetary(string="Amount", currency_field="currency_id")
    currency_id = fields.Many2one(related="request_id.currency_id")
