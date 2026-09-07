# -*- coding: utf-8 -*-
"""The event travels down the buying leg too.

Before this, the event lived on the purchase order only as free text in the
header note — "MERDEKA RUN - MONAS", "OPERRATIONAL DRONE SHOW - DANONE BALI",
typos and all. Nothing tied that note to the sales order it came from, nothing
carried it onto the vendor bill, and so the P&L per Show showed ARKA's revenue
against an almost empty cost side: of ARKA's vendor bills exactly one carried a
show date.

The same three fields the sales order captures are captured here, propagated to
the vendor bill through ``_prepare_invoice``, and handed to the sister company
by the intercompany PO → SO mirror.
"""

from odoo import _, api, fields, models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "custom.arka.event.mixin"]

    x_custom_show_date = fields.Date(
        string="Show Date",
        copy=True,
        tracking=True,
        help="Event/show date this purchase is for. Propagated to the vendor "
        "bill and to the sister company's mirrored sales order.",
    )
    x_custom_event_name = fields.Char(
        string="Event",
        copy=True,
        tracking=True,
        help='Event name, e.g. "Soekarno Cup".',
    )
    x_custom_event_location = fields.Char(
        string="Lokasi Event",
        copy=True,
        tracking=True,
        help='Venue, e.g. "Stadion Gelora Bung Tomo Surabaya".',
    )
    x_custom_event_source_so_id = fields.Many2one(
        "sale.order",
        string="Sumber SO Event",
        readonly=True,
        copy=False,
        index=True,
        help="The customer sales order this purchase order was generated from.",
    )
    x_custom_event_visible = fields.Boolean(
        compute="_compute_x_custom_event_visible",
        help="Technical helper: True when this company captures event data. Drives the form's invisible attributes.",
    )

    @api.depends(
        "company_id",
        "company_id.x_custom_show_date_enabled",
        "company_id.x_custom_event_tracking_enabled",
    )
    def _compute_x_custom_event_visible(self):
        for order in self:
            company = order.company_id
            order.x_custom_event_visible = bool(
                company.x_custom_show_date_enabled or company.x_custom_event_tracking_enabled
            )

    # ------------------------------------------------------------------
    # Event data out to the vendor bill and the sister company
    # ------------------------------------------------------------------
    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        # Unconditional: the fields simply carry over. Only the analytic
        # stamping and the due-date anchoring are gated on a company flag.
        values.update(
            {
                "x_custom_show_date": self.x_custom_show_date,
                "x_custom_event_name": self.x_custom_event_name,
                "x_custom_event_location": self.x_custom_event_location,
            }
        )
        return values

    def _custom_create_ic_mirror_so(self, rule):
        """Hand the event to the selling company as data, not as a note.

        ``custom_intercompany_procurement`` copies the header ``note`` and
        nothing else, which is why AIM has been reading the event out of free
        text. Writing the three fields onto the mirrored order is what lets AIM
        see — and report on — the same event ARKA sold.
        """
        order = super()._custom_create_ic_mirror_so(rule)
        if order and (self.x_custom_show_date or self.x_custom_event_name or self.x_custom_event_location):
            order.sudo().write(
                {
                    "x_custom_show_date": self.x_custom_show_date,
                    "x_custom_event_name": self.x_custom_event_name,
                    "x_custom_event_location": self.x_custom_event_location,
                }
            )
            # The mirror is a draft the seller will confirm later, but its
            # lines already feed AIM's customer invoice — tag them now so the
            # revenue side of the event is never missed.
            order.sudo()._custom_event_apply_analytic()
        return order

    def _custom_warn_products_the_sister_cannot_sell(self, target_company):
        """Say up front which lines will stop the mirror from being created.

        The mirror creates the sales order in the SISTER company, so a product
        restricted to the buying company cannot appear on it — Odoo rejects the
        line as a company crossover and ``custom_intercompany_procurement``
        catches that, logs it and posts to chatter. The buyer only finds out
        after confirming. In prd_arkaaim this is not hypothetical: every PO that
        mirrored used a company-less product, and "Jasa Drone Show 250 Unit"
        exists twice — once scoped to ARKA (id 14) and once shared (id 153).

        Non-blocking on purpose: the fix is in the product master, and the buyer
        may legitimately want the purchase order anyway.
        """
        self.ensure_one()
        blocked = self.order_line.product_id.filtered(
            lambda product: product.company_id and product.company_id != target_company
        )
        if not blocked:
            return False
        self.message_post(
            body=_(
                "These products belong to %(owner)s only, so %(sister)s cannot put them on the "
                "mirrored sales order and the intercompany mirror will fail on confirmation: "
                "%(products)s. Clear the Company field on the product (or use the shared "
                "duplicate) first.",
                owner=self.company_id.display_name,
                sister=target_company.display_name,
                products=", ".join(blocked.mapped("display_name")),
            )
        )
        return blocked

    # ------------------------------------------------------------------
    # Analytic
    # ------------------------------------------------------------------
    def _custom_event_taggable_lines(self):
        self.ensure_one()
        return self.order_line.filtered(lambda line: not line.display_type)

    def button_confirm(self):
        # Tagged before confirmation for the same reason the sale side is: a
        # confirmed document is the wrong moment to be writing to its lines.
        for order in self:
            order._custom_event_apply_analytic()
        return super().button_confirm()
