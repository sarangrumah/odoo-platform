# -*- coding: utf-8 -*-
from odoo import fields, models


class RentalAsset(models.Model):
    _inherit = "rental.asset"

    lot_id = fields.Many2one(
        related="fixed_asset_id.lot_id",
        string="Serial",
        store=True,
        readonly=True,
    )
    stock_location_id = fields.Many2one(
        related="fixed_asset_id.stock_location_id",
        string="Physical Location",
        store=True,
        readonly=True,
    )
    is_available_now = fields.Boolean(
        related="fixed_asset_id.is_rentable",
        string="Available Now",
        store=True,
        readonly=True,
    )
