# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    asset_damage_location_id = fields.Many2one(related="company_id.asset_damage_location_id", readonly=False)
    asset_missing_location_id = fields.Many2one(related="company_id.asset_missing_location_id", readonly=False)
    asset_loss_account_id = fields.Many2one(related="company_id.asset_loss_account_id", readonly=False)
    asset_compensation_income_account_id = fields.Many2one(
        related="company_id.asset_compensation_income_account_id", readonly=False
    )
    asset_replacement_journal_id = fields.Many2one(related="company_id.asset_replacement_journal_id", readonly=False)
    asset_equipment_category_id = fields.Many2one(related="company_id.asset_equipment_category_id", readonly=False)
