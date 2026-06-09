# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_custom_show_date = fields.Date(
        string="Show Date",
        copy=True,
        tracking=True,
        help="Event/show date for this order. Propagated to the customer "
        "invoice; when the company has Show Date enabled, the invoice "
        "payment-term due dates are anchored to this date.",
    )
    x_custom_show_date_required = fields.Boolean(
        string="Show Date Required",
        compute="_compute_x_custom_show_date_required",
        help="Technical helper: True when this order's company has Show Date "
        "enabled. Drives the form 'required'/'invisible' attributes.",
    )

    @api.depends("company_id", "company_id.x_custom_show_date_enabled")
    def _compute_x_custom_show_date_required(self):
        for order in self:
            order.x_custom_show_date_required = bool(
                order.company_id.x_custom_show_date_enabled
            )

    def _confirmation_error_message(self):
        # Preserve core confirmation checks first.
        msg = super()._confirmation_error_message()
        if msg:
            return msg
        if self.company_id.x_custom_show_date_enabled and not self.x_custom_show_date:
            return _("Please set the Show Date before confirming this order.")
        return False

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        # Harmless when the company flag is off: the field just carries over;
        # only the due-date anchoring (account.move) is gated on the flag.
        values["x_custom_show_date"] = self.x_custom_show_date
        return values
