# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.repair_order import CHANNELS


class AssetReportDamageWizard(models.TransientModel):
    _name = "custom.asset.report.damage.wizard"
    _description = "Report Asset Damage"
    _inherit = ["custom.asset.condition.wizard.mixin"]

    damage_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Damage Location",
        domain="[('usage', '=', 'internal')]",
        default=lambda self: self.env.company.asset_damage_location_id,
        help="Leave empty to use the company's configured damage location.",
    )
    create_repair = fields.Boolean(
        string="Open Repair Order",
        default=True,
        help="Raise one repair order per unit and, through custom_repairs, a "
        "corrective maintenance request on its equipment card.",
    )
    repair_channel = fields.Selection(
        selection=CHANNELS,
        string="Repair Channel",
        default="in_house",
    )
    repair_vendor_id = fields.Many2one(comodel_name="res.partner", string="Repair Vendor")
    warranty_claim_ref = fields.Char(string="Warranty Claim Ref.")
    promised_date = fields.Date(string="Promised Completion")

    @api.onchange("repair_channel")
    def _onchange_repair_channel(self):
        if self.repair_channel != "third_party":
            self.repair_vendor_id = False
        if self.repair_channel != "warranty":
            self.warranty_claim_ref = False

    def _destination_location(self, asset):
        location = self.damage_location_id or asset.company_id.asset_damage_location_id
        if self.move_serial and asset.lot_id and not location:
            raise UserError(
                _(
                    "No damage location set. Configure it under Accounting Settings "
                    "> Asset Lifecycle, or untick Move Serial."
                )
            )
        return location

    def action_report_damage(self):
        self.ensure_one()
        self._validate_assets(("damaged", "in_repair", "missing", "written_off"))
        if self.create_repair:
            if self.repair_channel == "third_party" and not self.repair_vendor_id:
                raise UserError(_("A repair vendor is required for a third-party repair."))
            if self.repair_channel == "warranty" and not self.warranty_claim_ref:
                raise UserError(_("A claim reference is required for a warranty repair."))

        logs = self._apply("damage", "damaged")
        if self.create_repair:
            self._create_repairs()
        return self._open_logs(logs)

    def _create_repairs(self):
        """One repair order per unit, pre-pointed at its serial.

        Equipment cards are provisioned on the fly: without one, the
        ``custom_repairs`` bridge has nothing to raise a maintenance request
        against, and the failure history the whole feature exists for would
        never accumulate.
        """
        self.ensure_one()
        Repair = self.env["repair.order"]
        repairs = Repair.browse()
        for asset in self.asset_ids:
            asset._ensure_equipment()
            vals = {
                "x_fixed_asset_id": asset.id,
                "x_repair_channel": self.repair_channel,
                "x_repair_vendor_id": self.repair_vendor_id.id,
                "x_warranty_claim_ref": self.warranty_claim_ref,
                "x_warranty_claim_date": self.event_date if self.repair_channel == "warranty" else False,
                "x_equipment_id": asset.equipment_id.id,
                "x_id_complaint": self.description,
                "x_promised_completion_date": self.promised_date,
                "x_requesting_user_id": self.env.user.id,
                "under_warranty": self.repair_channel == "warranty",
                "company_id": asset.company_id.id,
                "internal_notes": _("Asset %(code)s - %(name)s", code=asset.code, name=asset.name),
            }
            if asset.product_id:
                vals["product_id"] = asset.product_id.id
                vals["product_uom"] = asset.product_id.uom_id.id
            if asset.lot_id:
                vals["lot_id"] = asset.lot_id.id
            if self.repair_channel == "third_party":
                vals["partner_id"] = self.repair_vendor_id.id
            repair = Repair.create(vals)
            repairs |= repair
            asset.message_post(
                body=_(
                    "Repair order %(name)s opened (%(channel)s).",
                    name=repair.name,
                    channel=dict(CHANNELS).get(self.repair_channel, ""),
                )
            )
        return repairs
