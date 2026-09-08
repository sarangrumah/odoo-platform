# -*- coding: utf-8 -*-
"""Bulk-create the maintenance equipment cards a register never had.

The ARKA-AIM register carries 3,590 units and, before this, zero
``maintenance.equipment`` records -- so the chain asset -> rental unit ->
equipment -> failure history was broken at the third link and no repair history
could accumulate anywhere. This wizard closes it in one pass, and is idempotent:
assets that already carry an equipment card are skipped.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AssetEquipmentProvisionWizard(models.TransientModel):
    _name = "custom.asset.equipment.provision.wizard"
    _description = "Provision Maintenance Equipment For Assets"

    asset_ids = fields.Many2many(
        comodel_name="custom.fixed.asset",
        string="Assets",
        required=True,
    )
    category_id = fields.Many2one(
        comodel_name="maintenance.equipment.category",
        string="Equipment Category",
        default=lambda self: self.env.company.asset_equipment_category_id,
    )
    pending_count = fields.Integer(compute="_compute_counts")
    existing_count = fields.Integer(compute="_compute_counts")

    @api.depends("asset_ids.equipment_id")
    def _compute_counts(self):
        for wizard in self:
            existing = wizard.asset_ids.filtered("equipment_id")
            wizard.existing_count = len(existing)
            wizard.pending_count = len(wizard.asset_ids) - len(existing)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("active_model") == "custom.fixed.asset":
            res["asset_ids"] = [(6, 0, self.env.context.get("active_ids", []))]
        return res

    def action_provision(self):
        self.ensure_one()
        pending = self.asset_ids.filtered(lambda a: not a.equipment_id)
        if not pending:
            raise UserError(_("Every selected asset already has an equipment card."))
        created = pending._ensure_equipment(category=self.category_id)
        return {
            "type": "ir.actions.act_window",
            "name": _("Equipment Cards"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }
