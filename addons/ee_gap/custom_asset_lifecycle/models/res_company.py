# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    asset_damage_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Asset Damage Location",
        domain="[('usage', '=', 'internal')]",
        help="Where a serial goes when its unit is reported damaged.",
    )
    asset_missing_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Asset Lost/Missing Location",
        domain="[('usage', '=', 'internal')]",
        help="Where a serial goes when its unit is reported missing, so it stops "
        "counting as available on-hand stock while the loss is investigated.",
    )
    asset_loss_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Asset Loss Account",
        help="Expense account debited for the net book value of a written-off unit.",
    )
    asset_compensation_income_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Asset Compensation Income Account",
        help="Income account credited at fair value when a client hands over a "
        "replacement unit that becomes company property.",
    )
    asset_replacement_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Asset Replacement Journal",
        domain="[('type', '=', 'general')]",
        help="Journal used for the acquisition entry of a replacement unit. "
        "Falls back to the asset's own depreciation journal.",
    )
    asset_equipment_category_id = fields.Many2one(
        comodel_name="maintenance.equipment.category",
        string="Asset Equipment Category",
        help="Default maintenance category for equipment cards created from the register.",
    )
