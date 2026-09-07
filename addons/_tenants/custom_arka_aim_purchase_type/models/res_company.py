# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    x_nontrade_asset_group_id = fields.Many2one(
        "custom.fixed.asset.group",
        string="Non-Trade Asset Group",
        domain="[('company_id', 'in', [id, False])]",
        help="Asset group applied to assets created from a Non-Trade goods receipt "
        "when neither the wizard override nor the product carries one. Lets a plain "
        "opex product be capitalised from the receipt without editing its master.",
    )
