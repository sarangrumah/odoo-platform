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
    # The three fields below feed the order-line description block (see
    # sale_order_line.py). They are captured once per order because a show is
    # one event: every line of the order belongs to the same event.
    x_custom_event_name = fields.Char(
        string="Event",
        copy=True,
        tracking=True,
        help='Event name printed in the line description, e.g. "Danone".',
    )
    x_custom_event_location = fields.Char(
        string="Lokasi Event",
        copy=True,
        tracking=True,
        help='Venue printed in the line description, e.g. "Taman Bhagawan Bali".',
    )
    x_custom_dp_note = fields.Char(
        string="Keterangan DP / Pelunasan",
        copy=True,
        tracking=True,
        help='Free text closing the line description, e.g. "DP 50%" or "PELUNASAN 50%". Left out when empty.',
    )

    def _custom_event_description(self):
        """The event line appended to each product line's description.

        Returns "" when the company gate is off or nothing has been captured,
        so the caller can leave the core description untouched.
        """
        self.ensure_one()
        if not self.company_id.x_custom_show_date_enabled:
            return ""
        parts = []
        if self.x_custom_event_name:
            parts.append("Event %s" % self.x_custom_event_name)
        if self.x_custom_event_location:
            parts.append("Lokasi %s" % self.x_custom_event_location)
        if self.x_custom_show_date:
            # dd.mm.yy — the format the client writes in their own samples.
            parts.append(self.x_custom_show_date.strftime("%d.%m.%y"))
        if self.x_custom_dp_note:
            parts.append(self.x_custom_dp_note)
        return ", ".join(parts)

    @api.depends("company_id", "company_id.x_custom_show_date_enabled")
    def _compute_x_custom_show_date_required(self):
        for order in self:
            order.x_custom_show_date_required = bool(order.company_id.x_custom_show_date_enabled)

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
