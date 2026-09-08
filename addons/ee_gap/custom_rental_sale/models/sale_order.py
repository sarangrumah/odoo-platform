# -*- coding: utf-8 -*-
"""The sales order stays the commercial document; it just also knows what shipped.

Everything a seller does here is unchanged. The fields below are Ops' side of the
same event: which units go out, when they go, and where they sit while they are
gone. They are all optional -- an order that names no deployment product behaves
exactly as it did before this module existed.
"""

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    deployment_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Deployment Product",
        copy=True,
        help="The unit or bundle physically dispatched for this order. Where it "
        "carries a phantom BOM, the dispatch explodes into its components -- one "
        "stock move per drone, battery and controller.",
    )
    deployment_qty = fields.Integer(
        string="Deployment Qty",
        default=1,
        copy=True,
        help="Number of bundles dispatched. A 1,500-drone show is normally one bundle of 1,500, not 1,500 bundles.",
    )
    deployment_spare_qty = fields.Integer(
        string="Spare Bundles",
        default=0,
        copy=True,
        help="Spares shipped alongside. Never invoiced, and must come back in full.",
    )
    deployment_start = fields.Datetime(string="Dispatch On", copy=False)
    deployment_end = fields.Datetime(string="Expected Back", copy=False)
    deployment_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="On-Deployment Location",
        domain="[('usage', '=', 'internal')]",
        copy=False,
        help="Leave empty to use the company's configured on-deployment location.",
    )
    deployment_ids = fields.One2many(
        comodel_name="rental.order",
        inverse_name="sale_order_id",
        string="Deployments",
    )
    deployment_count = fields.Integer(compute="_compute_deployment_count")

    @api.depends("deployment_ids")
    def _compute_deployment_count(self):
        counts = {}
        if self.ids:
            groups = self.env["rental.order"]._read_group(
                domain=[("sale_order_id", "in", self.ids)],
                groupby=["sale_order_id"],
                aggregates=["__count"],
            )
            counts = {order.id: count for order, count in groups}
        for order in self:
            order.deployment_count = counts.get(order.id, 0)

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------
    def _default_deployment_window(self):
        """Dispatch the day before the show, expect the units back the day after.

        ``x_custom_show_date`` is already captured on every ARKA-AIM quotation, so
        Ops should not have to retype the one date the order revolves around.
        Falls back to the commitment date, then to today.
        """
        self.ensure_one()
        show_date = self.env.context.get("show_date")
        if not show_date and "x_custom_show_date" in self._fields:
            show_date = self.x_custom_show_date
        if show_date:
            start = fields.Datetime.to_datetime(show_date) - relativedelta(days=1)
            return start, start + relativedelta(days=2)
        anchor = self.commitment_date or fields.Datetime.now()
        anchor = fields.Datetime.to_datetime(anchor)
        return anchor, anchor + relativedelta(days=1)

    # ------------------------------------------------------------------
    # Creating the dispatch document
    # ------------------------------------------------------------------
    def _deployment_location(self):
        self.ensure_one()
        return self.deployment_location_id or self.company_id.deployment_location_id

    def _prepare_deployment_vals(self):
        self.ensure_one()
        start = self.deployment_start
        end = self.deployment_end
        if not start or not end:
            start, end = self._default_deployment_window()
        return {
            "partner_id": self.partner_id.id,
            "product_id": self.deployment_product_id.id,
            "qty": max(self.deployment_qty or 1, 1),
            "loan_qty": max(self.deployment_spare_qty or 0, 0),
            "pickup_dt": start,
            "return_dt_expected": end,
            # Zero on purpose. The sales order carries the money; a second
            # document that could also bill for it is a liability.
            "daily_rate": 0.0,
            "deposit_amount": 0.0,
            "is_internal_loan": True,
            "on_loan_location_id": self._deployment_location().id,
            "sale_order_id": self.id,
            "company_id": self.company_id.id,
            "notes": _("Dispatch for %(order)s", order=self.name),
        }

    def action_create_deployment(self):
        self.ensure_one()
        if not self.deployment_product_id:
            raise UserError(_("Set a deployment product on %s before dispatching units for it.", self.name))
        if not self._deployment_location():
            raise UserError(
                _("No on-deployment location configured. Set one under Sales Settings > Deployments, or on this order.")
            )
        deployment = self.env["rental.order"].create(self._prepare_deployment_vals())
        self.message_post(
            body=_(
                "Deployment %(name)s created for %(qty)s x %(product)s.",
                name=deployment.name,
                qty=deployment.qty,
                product=self.deployment_product_id.display_name,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Deployment"),
            "res_model": "rental.order",
            "res_id": deployment.id,
            "view_mode": "form",
        }

    def action_view_deployments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Deployments for %s", self.name),
            "res_model": "rental.order",
            "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            if not order.company_id.deployment_auto_create:
                continue
            if not order.deployment_product_id or order.deployment_ids:
                continue
            if not order._deployment_location():
                # A missing location must not block the sale. Say so on the order
                # and let Ops raise the dispatch by hand.
                order.message_post(
                    body=_(
                        "No on-deployment location is configured, so no dispatch "
                        "document was created. Configure one and use Create Deployment."
                    )
                )
                continue
            order.action_create_deployment()
        return res
