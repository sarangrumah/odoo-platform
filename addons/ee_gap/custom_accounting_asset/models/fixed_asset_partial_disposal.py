# -*- coding: utf-8 -*-
from odoo import fields, models


class CustomFixedAssetPartialDisposal(models.Model):
    """History of units taken out of a pooled (quantity-managed) asset.

    One record per retirement event: how many units left, what they carried in
    cost and accumulated depreciation, what came back as proceeds, and the
    journal entry that booked it. The asset itself only keeps the running
    totals, so this is where the audit trail lives.
    """

    _name = "custom.fixed.asset.partial.disposal"
    _description = "Custom Fixed Asset Partial Retirement"
    _order = "disposal_date desc, id desc"

    name = fields.Char(string="Reference", readonly=True)
    asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="asset_id.company_id", store=True)
    currency_id = fields.Many2one(related="asset_id.currency_id", store=True)
    disposal_date = fields.Date(required=True)
    reason = fields.Selection(
        selection=[
            ("scrap", "Broken / scrapped"),
            ("sale", "Sold"),
            ("loss", "Lost / stolen"),
            ("transfer", "Transferred out"),
            ("other", "Other"),
        ],
        default="scrap",
        required=True,
    )
    quantity = fields.Float(
        string="Units Retired",
        required=True,
        digits="Product Unit of Measure",
    )
    quantity_before = fields.Float(
        string="Units Before",
        readonly=True,
        digits="Product Unit of Measure",
    )
    quantity_after = fields.Float(
        string="Units After",
        readonly=True,
        digits="Product Unit of Measure",
    )
    cost_removed = fields.Monetary(
        string="Cost Removed",
        currency_field="currency_id",
        readonly=True,
        help="Gross carrying amount (acquisition + revaluation) released from the asset account.",
    )
    accumulated_removed = fields.Monetary(
        string="Accum. Depreciation Removed",
        currency_field="currency_id",
        readonly=True,
    )
    net_book_value_removed = fields.Monetary(
        string="NBV Removed",
        currency_field="currency_id",
        readonly=True,
    )
    proceeds = fields.Monetary(
        string="Proceeds",
        currency_field="currency_id",
        readonly=True,
    )
    gain_loss = fields.Monetary(
        string="Gain / (Loss)",
        currency_field="currency_id",
        readonly=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
    )
    note = fields.Text()
