# -*- coding: utf-8 -*-
"""Repair channel: who does the work and who pays for it.

``custom_repairs`` already tracks SLA, labour and material cost and bridges each
repair to a ``maintenance.request``. What it does not say is whether the job is
done in-house, sent to a vendor, or claimed under warranty -- three routes with
different paperwork and, crucially, different cost consequences. Core
``repair.order`` carries ``under_warranty`` and ``partner_id``; this keeps those
in step with an explicit channel rather than leaving two independent flags that
can disagree.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

CHANNELS = [
    ("in_house", "In-House"),
    ("third_party", "Third Party"),
    ("warranty", "Warranty Claim"),
]


class RepairOrder(models.Model):
    _inherit = "repair.order"

    x_fixed_asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        string="Fixed Asset",
        index=True,
        help="Register entry of the unit under repair.",
    )
    x_repair_channel = fields.Selection(
        selection=CHANNELS,
        string="Repair Channel",
        default="in_house",
        required=True,
        tracking=True,
    )
    x_repair_vendor_id = fields.Many2one(
        comodel_name="res.partner",
        string="Repair Vendor",
        help="Third party carrying out the work.",
    )
    x_warranty_claim_ref = fields.Char(string="Warranty Claim Ref.")
    x_warranty_claim_date = fields.Date(string="Warranty Claim Date")
    x_warranty_expiry_date = fields.Date(
        string="Warranty Expires",
        help="Warranty end date of the unit, for reference when raising a claim.",
    )
    x_is_warranty = fields.Boolean(
        compute="_compute_is_warranty",
        store=True,
        string="Under Warranty Claim",
    )

    @api.depends("x_repair_channel")
    def _compute_is_warranty(self):
        for repair in self:
            repair.x_is_warranty = repair.x_repair_channel == "warranty"

    @api.onchange("x_repair_channel")
    def _onchange_x_repair_channel(self):
        for repair in self:
            repair.under_warranty = repair.x_repair_channel == "warranty"
            if repair.x_repair_channel == "in_house":
                repair.x_repair_vendor_id = False

    @api.constrains("x_repair_channel", "x_repair_vendor_id", "x_warranty_claim_ref")
    def _check_repair_channel(self):
        for repair in self:
            if repair.x_repair_channel == "third_party" and not repair.x_repair_vendor_id:
                raise UserError(_("Repair %s is routed to a third party, so a repair vendor is required.", repair.name))
            if repair.x_repair_channel == "warranty" and not repair.x_warranty_claim_ref:
                raise UserError(_("Repair %s is a warranty claim, so a claim reference is required.", repair.name))

    # ------------------------------------------------------------------
    # Keep the asset's condition in step with the repair
    # ------------------------------------------------------------------
    def _sync_asset_condition(self):
        """Move the linked asset between ``in_repair`` and ``damaged``/``ok``.

        Deliberately does NOT set the asset back to ``ok`` when the repair is
        done: the unit is still physically in the damage warehouse at that
        point. Returning it to service is an explicit act on the asset, because
        it involves a stock move somebody has to actually perform.
        """
        for repair in self:
            asset = repair.x_fixed_asset_id
            if not asset:
                continue
            if repair.state in ("confirmed", "under_repair") and asset.condition == "damaged":
                asset._log_condition_event(
                    "repair_start",
                    condition_to="in_repair",
                    description=_(
                        "Sent for repair (%(channel)s) on order %(name)s.",
                        channel=dict(CHANNELS).get(repair.x_repair_channel, ""),
                        name=repair.name,
                    ),
                    reference=repair.x_warranty_claim_ref,
                    repair_order_id=repair.id,
                )
            elif repair.state == "done" and asset.condition == "in_repair":
                asset._log_condition_event(
                    "repair_done",
                    condition_to="repaired",
                    description=_(
                        "Repair %(name)s completed. Cost borne by company: %(cost)s.",
                        name=repair.name,
                        cost=0.0 if repair.x_is_warranty else repair.x_total_repair_cost,
                    ),
                    reference=repair.x_warranty_claim_ref,
                    repair_order_id=repair.id,
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # The onchange only fires in the form. Anything created in code --
            # the damage wizard, an import, a test -- would otherwise leave the
            # core warranty flag disagreeing with the channel.
            if vals.get("x_repair_channel"):
                vals["under_warranty"] = vals["x_repair_channel"] == "warranty"
        repairs = super().create(vals_list)
        repairs._sync_asset_condition()
        return repairs

    def write(self, vals):
        if "x_repair_channel" in vals and "under_warranty" not in vals:
            vals = dict(vals, under_warranty=vals["x_repair_channel"] == "warranty")
        res = super().write(vals)
        if "state" in vals:
            self._sync_asset_condition()
        return res
