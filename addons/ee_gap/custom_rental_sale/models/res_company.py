# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    deployment_auto_create = fields.Boolean(
        string="Create Deployments From Sales Orders",
        default=False,
        help="Confirming a sales order that names a deployment product also creates "
        "the dispatch document for the units behind it. Off by default: a company "
        "whose warehouse is not ready for it carries on exactly as before.",
    )
    deployment_source_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Deployment Source Location",
        domain="[('usage', 'in', ('internal', 'view'))]",
        help="Where the dispatched units are picked from. Leave empty to use the "
        "stock location of the on-deployment location's warehouse. Set it to the "
        "location the fleet actually lives in -- picking from the wrong one books "
        "negative quants and leaves the units where they were.",
    )
    deployment_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="On-Deployment Location",
        domain="[('usage', '=', 'internal')]",
        help="Internal location the units sit in while they are out at an event. "
        "Internal on purpose: the units never leave the company, so no stock "
        "valuation can reach the ledger.",
    )
