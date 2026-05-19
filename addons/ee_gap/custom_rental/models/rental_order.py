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

    # Late-fee accrual
    late_fee_rate = fields.Float(
        string="Late Fee Rate (% / day)",
        default=lambda s: float(s.env["ir.config_parameter"].sudo().get_param(
            "custom_rental.default_late_fee_rate", "10.0")),
        help="Percentage of rental subtotal charged per overdue day.",
    )
    late_fee_total = fields.Monetary(
        currency_field="currency_id", readonly=True, copy=False,
        help="Cumulative late fee accrued by the daily cron.",
    )
    late_fee_line_ids = fields.One2many(
        "custom.rental.late.fee.line", "order_id", string="Late Fee Accruals",
    )

    # BAST documents (custom_bast module; install will succeed when both modules present)
    bast_pickup_id = fields.Many2one(
        "custom.bast.document", string="BAST Pickup", copy=False,
        domain="[('kind', '=', 'pickup')]",
    )
    bast_return_id = fields.Many2one(
        "custom.bast.document", string="BAST Return", copy=False,
        domain="[('kind', '=', 'return')]",
    )

    # E-signature capture (data URL bytes, base64 decoded)
    customer_signature = fields.Binary(string="Customer Signature", copy=False)
    customer_signed_by = fields.Char(copy=False)
    customer_signed_at = fields.Datetime(readonly=True, copy=False)

    # Stock picking integration
    pickup_picking_id = fields.Many2one("stock.picking", copy=False, readonly=True)
    return_picking_id = fields.Many2one("stock.picking", copy=False, readonly=True)

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
            # 50% surcharge on late days (legacy compute, distinct from
            # cron-driven late_fee_total which represents post-due accrual).
            rec.late_penalty = rec.daily_rate * late_days * 0.5
            rec.total_due = rec.rental_fee + rec.late_penalty + (rec.late_fee_total or 0.0)

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
                    "Asset %(asset)s is already booked %(start)s -> %(end)s (order %(name)s).",
                    asset=rec.asset_id.name,
                    start=overlap.pickup_dt, end=overlap.return_dt_expected, name=overlap.name,
                ))

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft orders can be confirmed."))
            rec.write({"state": "confirmed"})
            rec._pdp_audit_write("rental_confirm", rec.id, None)
            rec._create_stock_picking("outgoing")

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
            rec._create_stock_picking("incoming")

    def action_cancel(self):
        for rec in self:
            if rec.state == "returned":
                raise UserError(_("Cannot cancel a returned order."))
            if rec.state == "picked_up":
                rec.asset_id.sudo().write({"state": "available"})
            rec.write({"state": "cancelled"})
            rec._pdp_audit_write("rental_cancel", rec.id, None)

    # ------------------------------------------------------------------
    # Stock picking integration
    # ------------------------------------------------------------------
    def _stock_integration_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "custom_rental.config_stock_integration", "True"
        ) in ("True", "true", "1", True)

    def _create_stock_picking(self, direction):
        """direction: 'outgoing' (confirm) or 'incoming' (return)."""
        self.ensure_one()
        if not self._stock_integration_enabled():
            return False
        if not self.asset_id.product_id:
            return False
        Picking = self.env["stock.picking"]
        # Pick the first matching picking type in this company.
        ptype = self.env["stock.picking.type"].search([
            ("code", "=", direction),
            ("company_id", "in", (False, self.company_id.id)),
        ], limit=1)
        if not ptype:
            return False
        loc_src = ptype.default_location_src_id or ptype.warehouse_id.lot_stock_id
        loc_dst = ptype.default_location_dest_id
        if not (loc_src and loc_dst):
            return False
        product = self.asset_id.product_id
        vals = {
            "picking_type_id": ptype.id,
            "partner_id": self.partner_id.id,
            "location_id": loc_src.id,
            "location_dest_id": loc_dst.id,
            "origin": self.name,
            "company_id": self.company_id.id,
            "move_ids": [(0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "product_uom_qty": 1.0,
                "product_uom": product.uom_id.id,
                "location_id": loc_src.id,
                "location_dest_id": loc_dst.id,
                "company_id": self.company_id.id,
            })],
        }
        picking = Picking.sudo().create(vals)
        if direction == "outgoing":
            self.pickup_picking_id = picking.id
        else:
            self.return_picking_id = picking.id
        return picking

    # ------------------------------------------------------------------
    # BAST generation
    # ------------------------------------------------------------------
    def _ensure_bast_module(self):
        if "custom.bast.document" not in self.env:
            raise UserError(_(
                "Module 'custom_bast' is not installed. Install it before "
                "generating BAST documents."))

    def action_generate_bast_pickup(self):
        for rec in self:
            rec._ensure_bast_module()
            if rec.bast_pickup_id:
                raise UserError(_("BAST Pickup already exists for %s.") % rec.name)
            doc = rec.env["custom.bast.document"].sudo().create({
                "name": "BAST-PICKUP/%s" % rec.name,
                "kind": "pickup",
                "partner_id": rec.partner_id.id,
                "company_id": rec.company_id.id,
                "origin": rec.name,
                "origin_model": "rental.order",
                "origin_res_id": rec.id,
            })
            rec.bast_pickup_id = doc.id
        return True

    def action_generate_bast_return(self):
        for rec in self:
            rec._ensure_bast_module()
            if rec.bast_return_id:
                raise UserError(_("BAST Return already exists for %s.") % rec.name)
            doc = rec.env["custom.bast.document"].sudo().create({
                "name": "BAST-RETURN/%s" % rec.name,
                "kind": "return",
                "partner_id": rec.partner_id.id,
                "company_id": rec.company_id.id,
                "origin": rec.name,
                "origin_model": "rental.order",
                "origin_res_id": rec.id,
            })
            rec.bast_return_id = doc.id
        return True

    # ------------------------------------------------------------------
    # Late-fee cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_accrue_late_fees(self):
        """Daily cron: for every picked_up order past expected return, accrue
        late fee = days_overdue * (rate/100) * rental_fee_subtotal."""
        Line = self.env["custom.rental.late.fee.line"]
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        overdue = self.search([
            ("state", "=", "picked_up"),
            ("return_dt_expected", "<", now),
        ])
        for rec in overdue:
            if Line.search_count([("order_id", "=", rec.id), ("accrued_on", "=", today)]):
                continue
            delta_days = (now - rec.return_dt_expected).total_seconds() / 86400.0
            if delta_days <= 0:
                continue
            subtotal = rec.rental_fee or (rec.daily_rate * (rec.days_planned or 1.0))
            fee = subtotal * (rec.late_fee_rate or 0.0) / 100.0
            if fee <= 0:
                continue
            Line.sudo().create({
                "order_id": rec.id,
                "accrued_on": today,
                "days_overdue": delta_days,
                "rate": rec.late_fee_rate or 0.0,
                "base_amount": subtotal,
                "fee_amount": fee,
                "currency_id": rec.currency_id.id,
                "note": "Auto cron accrual",
            })
            rec.sudo().write({"late_fee_total": (rec.late_fee_total or 0.0) + fee})
            rec.message_post(
                body=_("Late fee accrued: %(fee)s (overdue %(days).1f days).",
                       fee=fee, days=delta_days),
                message_type="notification",
            )
        return True

    # ------------------------------------------------------------------
    # Signature
    # ------------------------------------------------------------------
    def action_capture_signature(self, signature_b64=None, signed_by=None):
        self.ensure_one()
        if not signature_b64:
            raise UserError(_("Empty signature."))
        self.write({
            "customer_signature": signature_b64,
            "customer_signed_by": signed_by or self.env.user.name,
            "customer_signed_at": fields.Datetime.now(),
        })
        return True
