# -*- coding: utf-8 -*-
from odoo import fields, models


class CustomFixedAssetDepreciationLine(models.Model):
    _name = "custom.fixed.asset.depreciation.line"
    _description = "Custom Fixed Asset Depreciation Line"
    _order = "asset_id, sequence, date"

    asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="asset_id.company_id",
        store=True,
    )
    currency_id = fields.Many2one(
        related="asset_id.currency_id",
        store=True,
    )
    sequence = fields.Integer(required=True)
    date = fields.Date(required=True)
    amount = fields.Monetary(
        required=True,
        currency_field="currency_id",
    )
    posted = fields.Boolean(
        default=False,
        copy=False,
        help="Set once the journal entry has been booked to the GL.",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
    )

    def action_post_now(self):
        """Manual posting override — usable when an accountant needs to
        post a single line ahead of the cron schedule.
        """
        for line in self:
            if line.posted:
                continue
            line.asset_id._post_due_depreciation(as_of=line.date)
