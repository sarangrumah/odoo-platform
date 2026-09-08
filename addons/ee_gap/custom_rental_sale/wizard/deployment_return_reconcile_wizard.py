# -*- coding: utf-8 -*-
"""What happened to the units that did not come back the way they went out.

The wizard deliberately lists **discrepancies only**, not the whole dispatch. A
drone show sends 1,500 serials out; asking an operator to tick 1,500 boxes to say
"all fine" would guarantee the feature goes unused. The serials that returned
normally need no decision, so they get none.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

OUTCOMES = [
    ("missing", "Missing"),
    ("damaged", "Returned Damaged"),
    ("ignore", "Leave For Now"),
]


class DeploymentReturnReconcileLine(models.TransientModel):
    _name = "custom.rental.return.reconcile.line"
    _description = "Deployment Return Reconciliation Line"

    wizard_id = fields.Many2one(
        comodel_name="custom.rental.return.reconcile.wizard",
        required=True,
        ondelete="cascade",
    )
    lot_id = fields.Many2one(comodel_name="stock.lot", string="Serial", required=True)
    asset_id = fields.Many2one(comodel_name="custom.fixed.asset", string="Asset", readonly=True)
    asset_code = fields.Char(related="asset_id.code", readonly=True, string="Asset Code")
    serial_number = fields.Char(related="asset_id.serial_number", readonly=True)
    net_book_value = fields.Monetary(related="asset_id.net_book_value", readonly=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="asset_id.currency_id", readonly=True)
    outcome = fields.Selection(selection=OUTCOMES, required=True, default="missing")
    note = fields.Char(string="Note")


class DeploymentReturnReconcileWizard(models.TransientModel):
    _name = "custom.rental.return.reconcile.wizard"
    _description = "Reconcile A Deployment Return"

    rental_order_id = fields.Many2one(
        comodel_name="rental.order",
        required=True,
        readonly=True,
    )
    sale_order_id = fields.Many2one(related="rental_order_id.sale_order_id", readonly=True, string="Sales Order")
    event_date = fields.Datetime(related="rental_order_id.return_dt_actual", readonly=True)
    reference = fields.Char(
        string="Report Reference (BAP)",
        required=True,
        help="Incident report backing the loss. One reference covers every unit "
        "reconciled here -- they were lost or broken at the same event.",
    )
    description = fields.Text(
        required=True,
        help="What happened at the event. Copied onto every unit's history.",
    )
    line_ids = fields.One2many(
        comodel_name="custom.rental.return.reconcile.line",
        inverse_name="wizard_id",
        string="Units To Account For",
    )
    unexpected_lot_ids = fields.Many2many(
        comodel_name="stock.lot",
        string="Came Back Unexpectedly",
        readonly=True,
        help="Serials in the return that never went out. Not something this "
        "wizard can book -- it is a dispatch or scanning error to chase.",
    )
    damaged_lot_ids = fields.Many2many(
        comodel_name="stock.lot",
        relation="custom_rental_reconcile_damaged_lot_rel",
        string="Returned But Damaged",
        help="Units that did come back, but broken. They are already home, so "
        "reporting them here moves them on to the damage warehouse.",
    )
    open_repair = fields.Boolean(
        string="Open Repair Orders",
        default=True,
        help="Raise a repair order per damaged unit.",
    )
    repair_channel = fields.Selection(
        selection=[("in_house", "In-House"), ("third_party", "Third Party"), ("warranty", "Warranty Claim")],
        default="in_house",
    )
    missing_count = fields.Integer(compute="_compute_counts")
    damaged_count = fields.Integer(compute="_compute_counts")
    missing_value = fields.Monetary(compute="_compute_counts", currency_field="currency_id")
    currency_id = fields.Many2one(related="rental_order_id.currency_id", readonly=True)

    @api.depends("line_ids.outcome", "line_ids.asset_id", "damaged_lot_ids")
    def _compute_counts(self):
        for wizard in self:
            missing = wizard.line_ids.filtered(lambda line: line.outcome == "missing")
            wizard.missing_count = len(missing)
            wizard.missing_value = sum(missing.mapped("asset_id.net_book_value"))
            wizard.damaged_count = len(wizard.line_ids.filtered(lambda line: line.outcome == "damaged")) + len(
                wizard.damaged_lot_ids
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env["rental.order"].browse(
            res.get("rental_order_id") or self.env.context.get("default_rental_order_id")
        )
        if not order:
            return res
        missing, unexpected = order._returned_serial_discrepancy()
        assets = {
            asset.lot_id.id: asset
            for asset in self.env["custom.fixed.asset"].sudo().search([("lot_id", "in", missing.ids)])
        }
        res["line_ids"] = [
            (
                0,
                0,
                {
                    "lot_id": lot.id,
                    "asset_id": assets.get(lot.id).id if assets.get(lot.id) else False,
                    "outcome": "missing",
                },
            )
            for lot in missing
        ]
        res["unexpected_lot_ids"] = [(6, 0, unexpected.ids)]
        res.setdefault(
            "description",
            _("Not accounted for on return of deployment %s.", order.name),
        )
        return res

    # ------------------------------------------------------------------
    def _assets_for(self, lots):
        return self.env["custom.fixed.asset"].sudo().search([("lot_id", "in", lots.ids)])

    def action_reconcile(self):
        self.ensure_one()
        order = self.rental_order_id
        undecided = self.line_ids.filtered(lambda line: line.outcome == "ignore")

        missing_assets = self.line_ids.filtered(lambda line: line.outcome == "missing" and line.asset_id).asset_id
        damaged_assets = self.line_ids.filtered(lambda line: line.outcome == "damaged" and line.asset_id).asset_id
        damaged_assets |= self._assets_for(self.damaged_lot_ids)

        if not missing_assets and not damaged_assets:
            raise UserError(_("Nothing to book -- every unit is left for now."))

        if missing_assets:
            self.env["custom.asset.report.missing.wizard"].create(
                {
                    "asset_ids": [(6, 0, missing_assets.ids)],
                    "event_date": fields.Date.context_today(self),
                    "description": self.description,
                    "reference": self.reference,
                    "move_serial": True,
                }
            ).action_report_missing()

        if damaged_assets:
            self.env["custom.asset.report.damage.wizard"].create(
                {
                    "asset_ids": [(6, 0, damaged_assets.ids)],
                    "event_date": fields.Date.context_today(self),
                    "description": self.description,
                    "reference": self.reference,
                    "move_serial": True,
                    "create_repair": self.open_repair,
                    "repair_channel": self.repair_channel,
                }
            ).action_report_damage()

        order.message_post(
            body=_(
                "Return reconciled against %(ref)s: %(missing)s missing, %(damaged)s damaged, %(left)s left open.",
                ref=self.reference,
                missing=len(missing_assets),
                damaged=len(damaged_assets),
                left=len(undecided),
            )
        )
        if self.sale_order_id:
            self.sale_order_id.message_post(
                body=_(
                    "Deployment %(name)s came back short: %(missing)s unit(s) missing, "
                    "%(damaged)s damaged. Report ref %(ref)s.",
                    name=order.name,
                    missing=len(missing_assets),
                    damaged=len(damaged_assets),
                    ref=self.reference,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Condition Events"),
            "res_model": "custom.asset.condition.log",
            "view_mode": "list,form",
            "domain": [("asset_id", "in", (missing_assets | damaged_assets).ids)],
            "context": {"create": False},
        }
