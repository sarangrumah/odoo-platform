# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


STATES = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("picked_up", "Picked Up"),
    ("returned", "Returned"),
    ("cancelled", "Cancelled"),
]


class RentalOrder(models.Model):
    _name = "rental.order"
    _description = "Rental Order"
    _inherit = ["mail.thread", "mail.activity.mixin", "pdp.audited.mixin"]
    _order = "create_date desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    partner_id = fields.Many2one("res.partner", required=True, tracking=True)
    asset_id = fields.Many2one("rental.asset", required=True, tracking=True,
                               domain="[('state', '!=', 'retired')]")

    pickup_dt = fields.Datetime(required=True, tracking=True)
    return_dt_expected = fields.Datetime(required=True, tracking=True)
    return_dt_actual = fields.Datetime(readonly=True, tracking=True)

    daily_rate = fields.Monetary(currency_field="currency_id", required=True)
    deposit_amount = fields.Monetary(currency_field="currency_id")
    days_planned = fields.Float(compute="_compute_days", store=True)
    days_actual = fields.Float(compute="_compute_days", store=True)

    rental_fee = fields.Monetary(compute="_compute_fees", store=True, currency_field="currency_id")
    late_penalty = fields.Monetary(compute="_compute_fees", store=True, currency_field="currency_id")
    total_due = fields.Monetary(compute="_compute_fees", store=True, currency_field="currency_id")

    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.company.currency_id)
    state = fields.Selection(STATES, default="draft", required=True, tracking=True, index=True)
    notes = fields.Text()
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    def _pdp_audit_classification(self):
        return "financial"

    @api.depends("pickup_dt", "return_dt_expected", "return_dt_actual")
    def _compute_days(self):
        for rec in self:
            if rec.pickup_dt and rec.return_dt_expected:
                rec.days_planned = max(
                    1.0, (rec.return_dt_expected - rec.pickup_dt).total_seconds() / 86400.0,
                )
            else:
                rec.days_planned = 0.0
            if rec.pickup_dt and rec.return_dt_actual:
                rec.days_actual = max(
                    1.0, (rec.return_dt_actual - rec.pickup_dt).total_seconds() / 86400.0,
                )
            else:
                rec.days_actual = 0.0

    @api.depends("daily_rate", "days_planned", "days_actual")
    def _compute_fees(self):
        for rec in self:
            rec.rental_fee = rec.daily_rate * (rec.days_actual or rec.days_planned)
            late_days = max(0.0, (rec.days_actual or 0) - (rec.days_planned or 0))
            # 50% surcharge on late days
            rec.late_penalty = rec.daily_rate * late_days * 0.5
            rec.total_due = rec.rental_fee + rec.late_penalty

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("rental.order") or "RNT-???"
            if vals.get("asset_id") and not vals.get("daily_rate"):
                asset = self.env["rental.asset"].browse(vals["asset_id"])
                vals["daily_rate"] = asset.daily_rate
                if not vals.get("deposit_amount"):
                    vals["deposit_amount"] = asset.deposit_amount
        return super().create(vals_list)

    @api.constrains("pickup_dt", "return_dt_expected", "asset_id", "state")
    def _check_overlap(self):
        for rec in self:
            if rec.pickup_dt and rec.return_dt_expected and rec.pickup_dt >= rec.return_dt_expected:
                raise ValidationError(_("Expected return must be after pickup."))
            if rec.state in ("cancelled", "returned"):
                continue
            overlap = self.sudo().search([
                ("asset_id", "=", rec.asset_id.id),
                ("state", "in", ("confirmed", "picked_up")),
                ("id", "!=", rec.id),
                ("pickup_dt", "<", rec.return_dt_expected),
                ("return_dt_expected", ">", rec.pickup_dt),
            ], limit=1)
            if overlap:
                raise ValidationError(_(
                    "Asset %(asset)s is already booked %(start)s → %(end)s (order %(name)s).",
                    asset=rec.asset_id.name,
                    start=overlap.pickup_dt, end=overlap.return_dt_expected, name=overlap.name,
                ))

    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft orders can be confirmed."))
            rec.write({"state": "confirmed"})
            rec._pdp_audit_write("rental_confirm", rec.id, None)

    def action_pickup(self):
        for rec in self:
            if rec.state != "confirmed":
                raise UserError(_("Only confirmed orders can be picked up."))
            rec.write({"state": "picked_up"})
            rec.asset_id.sudo().write({"state": "on_rent"})
            rec._pdp_audit_write("rental_pickup", rec.id, None)

    def action_return(self):
        for rec in self:
            if rec.state != "picked_up":
                raise UserError(_("Only picked-up orders can be returned."))
            rec.write({"state": "returned", "return_dt_actual": fields.Datetime.now()})
            rec.asset_id.sudo().write({"state": "available"})
            rec._pdp_audit_write("rental_return", rec.id,
                                 {"total_due": float(rec.total_due or 0)})

    def action_cancel(self):
        for rec in self:
            if rec.state == "returned":
                raise UserError(_("Cannot cancel a returned order."))
            if rec.state == "picked_up":
                rec.asset_id.sudo().write({"state": "available"})
            rec.write({"state": "cancelled"})
            rec._pdp_audit_write("rental_cancel", rec.id, None)
