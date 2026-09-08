# -*- coding: utf-8 -*-
from odoo import api, fields, models

CONDITIONS = [
    ("ok", "Serviceable"),
    ("damaged", "Damaged"),
    ("in_repair", "Under Repair"),
    ("repaired", "Repaired - Awaiting Return"),
    ("missing", "Missing"),
    ("written_off", "Written Off"),
]

EVENTS = [
    ("damage", "Damage Reported"),
    ("missing", "Missing Reported"),
    ("repair_start", "Sent For Repair"),
    ("repair_done", "Repair Completed"),
    ("return_service", "Returned To Service"),
    ("write_off", "Written Off"),
    ("replaced", "Replaced By New Unit"),
    ("found", "Found Again"),
]


class CustomAssetConditionLog(models.Model):
    """One immutable row per condition event on one asset.

    The asset carries the serial number, so this is by construction the repair
    and incident history of a physical unit -- which is what Ops asked for. Kept
    as its own model rather than as chatter messages so it can be grouped,
    filtered and reported on.
    """

    _name = "custom.asset.condition.log"
    _description = "Fixed Asset Condition Event"
    _order = "event_date desc, id desc"

    asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        required=True,
        ondelete="cascade",
        index=True,
    )
    asset_code = fields.Char(related="asset_id.code", store=True, string="Asset Code")
    serial_number = fields.Char(related="asset_id.serial_number", store=True, readonly=True)
    lot_id = fields.Many2one(related="asset_id.lot_id", store=True, readonly=True, string="Stock Serial/Lot")
    company_id = fields.Many2one(related="asset_id.company_id", store=True, readonly=True)

    event_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    event_type = fields.Selection(selection=EVENTS, required=True, index=True)
    condition_from = fields.Selection(selection=CONDITIONS)
    condition_to = fields.Selection(selection=CONDITIONS)

    description = fields.Text()
    reference = fields.Char(
        string="Document Reference",
        help="BAP / incident report / claim number backing this event.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Reported By",
        default=lambda self: self.env.user,
    )
    repair_order_id = fields.Many2one(comodel_name="repair.order", ondelete="set null")
    maintenance_request_id = fields.Many2one(comodel_name="maintenance.request", ondelete="set null")
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Stock Transfer",
        ondelete="set null",
        help="Internal transfer that moved the serial as part of this event.",
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Moved To",
        ondelete="set null",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Journal Entry",
        ondelete="set null",
    )
    replacement_asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        string="Replacement Unit",
        ondelete="set null",
    )

    @api.depends("asset_code", "event_type")
    def _compute_display_name(self):
        labels = dict(EVENTS)
        for log in self:
            log.display_name = "%s - %s" % (log.asset_code or "?", labels.get(log.event_type, ""))
