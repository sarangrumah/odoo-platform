# -*- coding: utf-8 -*-
from odoo import _, fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    fixed_asset_ids = fields.One2many(
        comodel_name="custom.fixed.asset",
        inverse_name="lot_id",
        string="Fixed Asset",
    )

    def action_view_fixed_asset(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Fixed Asset"),
            "res_model": "custom.fixed.asset",
            "view_mode": "form" if len(self.fixed_asset_ids) == 1 else "list,form",
            "res_id": self.fixed_asset_ids[:1].id if len(self.fixed_asset_ids) == 1 else False,
            "domain": [("id", "in", self.fixed_asset_ids.ids)],
        }
