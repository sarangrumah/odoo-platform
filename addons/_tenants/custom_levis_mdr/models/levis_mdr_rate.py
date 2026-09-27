# -*- coding: utf-8 -*-
"""The merchant discount rate a bank charges, per tender type, over time.

The key is the ``PAYMENT`` label exactly as the store's X70D export writes it --
"BCA - QRIS", "MANDIRI - DEBIT MANDIRI/MANDIRI GPN". It is not parsed into an
acquirer and a product, because the file is the only authority on what the label
looks like and a parser would have to be corrected every time the client adds a
card scheme. ``acquirer`` is kept as a plain informational column for grouping.

Rates are **effective-dated, never overwritten**. A renegotiated rate is a new
row with a later ``date_from``; editing the old row would silently restate every
reconciliation already done at the old rate.

``percent`` is stored the way the rate is negotiated and spoken about -- 0.15
means 0,15%, not 15%. The arithmetic divides by 100 in exactly one place, the
``levis.mdr.txn`` view.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LevisMdrRate(models.Model):
    _name = "levis.mdr.rate"
    _description = "Levi's Card MDR Rate"
    _order = "payment, date_from desc, id desc"
    _rec_name = "payment"

    payment = fields.Char(
        required=True,
        index=True,
        string="Tender Type",
        help="The PAYMENT label as the store's X70D export writes it, e.g. 'BCA - QRIS'. "
        "Matched case-insensitively and trimmed, but otherwise verbatim.",
    )
    acquirer = fields.Char(
        index=True,
        help="Informational: the bank whose EDC or QR the transaction went through. "
        "Grouping only -- the rate is resolved on the full label.",
    )
    percent = fields.Float(
        digits=(16, 4),
        help="Merchant discount rate in percent: 0.15 means 0,15%. A genuine 0 is "
        "meaningful (QRIS at BCA, BNI and BRI is 0%) and is not the same as no rate "
        "on file, which is the absence of a row.",
    )
    fixed_fee = fields.Monetary(
        currency_field="currency_id",
        help="Flat fee per transaction, where an acquirer charges one on top of the "
        "percentage. Zero for every rate on file today.",
    )
    date_from = fields.Date(
        help="First trading day this rate applies to. Empty means it has applied for "
        "as long as there is data -- which is how the first load ships, because the "
        "rate card the client supplied carries no effective date. Set it once Finance "
        "confirms from when these rates were agreed.",
    )
    date_to = fields.Date(help="Last trading day this rate applies to. Empty means still current.")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda s: s.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    active = fields.Boolean(default=True)
    note = fields.Char()

    @api.constrains("percent", "fixed_fee")
    def _check_signs(self):
        for rate in self:
            if rate.percent < 0 or rate.fixed_fee < 0:
                raise ValidationError(
                    _("MDR is a deduction, so it is recorded positive. %s has a negative rate or fee.")
                    % (rate.payment or "?")
                )
            if rate.percent > 100:
                raise ValidationError(
                    _(
                        "%(label)s has a rate of %(pct)s. The rate is a percentage: "
                        "0.15 means 0,15%%. A value above 100 is a unit mistake.",
                        label=rate.payment or "?",
                        pct=rate.percent,
                    )
                )

    @api.constrains("date_from", "date_to")
    def _check_period(self):
        for rate in self:
            if rate.date_from and rate.date_to and rate.date_to < rate.date_from:
                raise ValidationError(
                    _("%s ends before it starts.") % (rate.payment or "?"),
                )
