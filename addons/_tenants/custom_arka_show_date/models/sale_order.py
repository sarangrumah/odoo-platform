# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "custom.arka.event.mixin"]

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

    def _custom_event_description(self, include_dp_note=True):
        """The event line appended to each product line's description.

        ``include_dp_note`` is turned off by the down-payment line, which already
        states the down payment in its own trailing marker ("(Uang Muka 50%)");
        repeating the free-text note there would print "DP 50% (Uang Muka 50%)".

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
        if include_dp_note and self.x_custom_dp_note:
            parts.append(self.x_custom_dp_note)
        return ", ".join(parts)

    def _custom_down_payment_description(self, dp_marker=""):
        """Description printed on the down-payment invoice line.

        Core labels that line "Down payment of 50.00%", and that wording reaches
        both the invoice PDF and the Faktur Pajak "Nama Barang Jasa" cell — the
        coretax exporter reads ``line.product_id.name or line.name`` and a DP
        line carries no product, so it falls through to the name. ARKA bills the
        customer for the show, so the products being down-paid lead, the event
        block follows, and the down payment itself is reduced to a trailing
        marker::

            Jasa Drone Show 250 Unit, Event Danone, Lokasi Taman Bhagawan Bali,
            07.08.26 (Uang Muka 50%)

        Deliberately a SINGLE line: the same string lands in one cell of the
        coretax import file, where an embedded newline is not safe. The invoice
        PDF wraps it to the column width instead.

        Returns "" when the company gate is off or the order has no product
        line, so the caller keeps the core wording.
        """
        self.ensure_one()
        if not self.company_id.x_custom_show_date_enabled:
            return ""
        names = []
        for line in self.order_line:
            if line.display_type or line.is_downpayment:
                continue
            # First line only: sale_order_line.py appends the event block to
            # every product line, and taking it from each of them would repeat
            # the same event once per product. It is added below, once.
            label = (line.name or line.product_id.name or "").split("\n")[0].strip()
            if label and label not in names:
                names.append(label)
        if not names:
            return ""
        parts = [", ".join(names)]
        # The event detail must reach the DP printouts too — the invoice PDF and
        # the Faktur Pajak both read this one string.
        event = self._custom_event_description(include_dp_note=False)
        if event:
            parts.append(event)
        description = ", ".join(parts)
        return "%s %s" % (description, dp_marker) if dp_marker else description

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
        # The event travels with the invoice so a bill/invoice raised without a
        # source document can still be matched to its event by hand.
        values["x_custom_event_name"] = self.x_custom_event_name
        values["x_custom_event_location"] = self.x_custom_event_location
        return values

    # ------------------------------------------------------------------
    # Analytic (event) tagging
    # ------------------------------------------------------------------
    def _custom_event_taggable_lines(self):
        self.ensure_one()
        # Down-payment lines are excluded: the down-payment invoice and the
        # deduction line on the settlement net to zero, and they post to a
        # liability account, not to the event's revenue.
        return self.order_line.filtered(lambda line: not line.display_type and not line.is_downpayment)

    def action_confirm(self):
        # BEFORE super(), not after: prd_arkaaim runs with "Auto Lock Confirmed
        # Sales Orders" on, so by the time super() returns the order is locked
        # and core refuses any write to its lines ("It is forbidden to modify
        # the following fields in a locked order"). Tagging while the order is
        # still a draft avoids that entirely.
        for order in self:
            order._custom_event_apply_analytic()
        return super().action_confirm()

    # ------------------------------------------------------------------
    # Intercompany purchase order raised from this sale (ARKA -> AIM)
    # ------------------------------------------------------------------
    x_custom_event_po_ids = fields.One2many(
        "purchase.order",
        "x_custom_event_source_so_id",
        string="Purchase Orders",
        readonly=True,
    )
    x_custom_event_po_count = fields.Integer(compute="_compute_x_custom_event_po_count")
    x_custom_ic_purchase_available = fields.Boolean(
        compute="_compute_x_custom_ic_purchase_available",
        help="Technical helper: True when an intercompany rule lets this "
        "company raise a purchase order on its sister company. Drives the "
        "visibility of the 'Buat PO ke Sister Company' button.",
    )

    @api.depends("x_custom_event_po_ids")
    def _compute_x_custom_event_po_count(self):
        for order in self:
            order.x_custom_event_po_count = len(order.x_custom_event_po_ids)

    @api.depends("company_id")
    def _compute_x_custom_ic_purchase_available(self):
        for order in self:
            order.x_custom_ic_purchase_available = bool(order._custom_ic_purchase_rule())

    def _custom_ic_purchase_rule(self):
        """The intercompany rule that says who this company buys the show from.

        Reuses ``custom_intercompany_procurement``'s rule rather than adding a
        second piece of configuration: the rule that already mirrors ARKA's PO
        into an AIM sales order is exactly the one that names the supplier.
        """
        self.ensure_one()
        if not self.company_id:
            return self.env["account.intercompany.rule"]
        return (
            self.env["account.intercompany.rule"]
            .sudo()
            .search(
                [
                    ("active", "=", True),
                    ("mirror_purchase_order", "=", True),
                    ("company_from_id", "=", self.company_id.id),
                ],
                limit=1,
            )
        )

    def action_custom_create_ic_purchase_order(self):
        """Raise the purchase order on the sister company from this sale.

        The buyer used to retype the event into a fresh PO's header note, which
        is where "OPERRATIONAL DRONE SHOW - DANONE BALI" came from. Here the
        event, the show date and the ordered lines come straight off the sale,
        so ARKA's sale, ARKA's purchase and AIM's mirrored sale all say the
        same thing.

        The PO is left in DRAFT on purpose: prices towards the sister company
        are not the customer's prices, so a buyer still reviews them. Confirming
        it then triggers the existing intercompany mirror into AIM.
        """
        self.ensure_one()
        rule = self._custom_ic_purchase_rule()
        if not rule:
            raise UserError(
                _(
                    "No intercompany rule lets %s raise a purchase order on a "
                    "sister company. Configure one under Accounting ▸ "
                    "Intercompany Rules with 'Mirror Purchase Order' ticked.",
                    self.company_id.display_name,
                )
            )
        vendor = rule.company_to_id.partner_id
        if not vendor:
            raise UserError(_("The sister company %s has no contact record.", rule.company_to_id.display_name))

        order_lines = []
        for line in self.order_line:
            if line.is_downpayment:
                # A down payment is a payment schedule, not something to buy.
                continue
            if line.display_type:
                order_lines.append(
                    (
                        0,
                        0,
                        {
                            "display_type": line.display_type,
                            "name": line.name,
                            "sequence": line.sequence,
                            "product_qty": 0.0,
                            "price_unit": 0.0,
                        },
                    )
                )
                continue
            if not line.product_id:
                continue
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": line.product_id.id,
                        "product_qty": line.product_uom_qty,
                        "product_uom_id": line.product_uom_id.id,
                        "sequence": line.sequence,
                        # name / price_unit / taxes / date_planned are left to
                        # the core computes, which read the vendor's own
                        # pricelist and supplier info. Copying the customer
                        # price here would book AIM's cost at ARKA's margin.
                    },
                )
            )
        if not any(vals[2].get("product_id") for vals in order_lines):
            raise UserError(_("This order has no product line to purchase."))

        purchase = (
            self.env["purchase.order"]
            .with_company(self.company_id)
            .create(
                {
                    "partner_id": vendor.id,
                    "company_id": self.company_id.id,
                    "origin": self.name,
                    "x_custom_event_source_so_id": self.id,
                    "x_custom_show_date": self.x_custom_show_date,
                    "x_custom_event_name": self.x_custom_event_name,
                    "x_custom_event_location": self.x_custom_event_location,
                    "order_line": order_lines,
                }
            )
        )
        purchase._custom_event_apply_analytic()
        purchase._custom_warn_products_the_sister_cannot_sell(rule.company_to_id)
        self.message_post(body=_("Purchase order %s raised on %s for this event.", purchase.name, vendor.display_name))
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Order"),
            "res_model": "purchase.order",
            "res_id": purchase.id,
            "view_mode": "form",
        }

    def action_custom_view_event_purchase_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Orders"),
            "res_model": "purchase.order",
            "domain": [("id", "in", self.x_custom_event_po_ids.ids)],
            "view_mode": "list,form",
        }
