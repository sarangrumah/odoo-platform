# -*- coding: utf-8 -*-
from odoo import _, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    # Not stored: ``custom.fixed.asset.equipment_id`` is the single source of
    # truth for the link, and a stored mirror here would have no field on this
    # model to depend on -- it would go stale the moment an asset were repointed.
    fixed_asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        string="Fixed Asset",
        compute="_compute_fixed_asset_id",
        search="_search_fixed_asset_id",
        help="Register entry this equipment card belongs to.",
    )

    def _compute_fixed_asset_id(self):
        Asset = self.env["custom.fixed.asset"]
        by_equipment = {}
        if self.ids:
            for asset in Asset.sudo().search([("equipment_id", "in", self.ids)]):
                by_equipment.setdefault(asset.equipment_id.id, asset)
        for equipment in self:
            equipment.fixed_asset_id = by_equipment.get(equipment.id, Asset)

    def _search_fixed_asset_id(self, operator, value):
        assets = (
            self.env["custom.fixed.asset"]
            .sudo()
            .search([("id", operator, value)] if isinstance(value, int) else [("display_name", operator, value)])
        )
        return [("id", "in", assets.equipment_id.ids)]

    def action_view_fixed_asset(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Fixed Asset"),
            "res_model": "custom.fixed.asset",
            "res_id": self.fixed_asset_id.id,
            "view_mode": "form",
        }
