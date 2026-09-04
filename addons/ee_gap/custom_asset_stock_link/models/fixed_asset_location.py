# -*- coding: utf-8 -*-
from odoo import fields, models


class CustomFixedAssetLocation(models.Model):
    _inherit = "custom.fixed.asset.location"

    stock_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Stock Location",
        domain="[('usage', '=', 'internal')]",
        help="Warehouse location that physically represents this asset location. "
        "Used as the default destination when materialising assets into stock.",
    )
