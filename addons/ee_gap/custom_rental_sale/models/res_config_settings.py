# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    deployment_auto_create = fields.Boolean(related="company_id.deployment_auto_create", readonly=False)
    deployment_location_id = fields.Many2one(related="company_id.deployment_location_id", readonly=False)
    deployment_source_location_id = fields.Many2one(related="company_id.deployment_source_location_id", readonly=False)
