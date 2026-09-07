# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "custom.arka.event.mixin"]

    x_custom_show_date = fields.Date(
        string="Show Date",
        copy=False,
        help="Show date carried from the sales order. For companies with Show "
        "Date enabled, the customer-invoice payment-term due dates are anchored "
        "to this date instead of the invoice date.",
    )
    x_custom_event_name = fields.Char(
        string="Event",
        copy=False,
        help="Event this document belongs to. Filled automatically from the "
        "sales order or the purchase order; set it by hand on a bill that has "
        "neither, then use 'Tag Event' to book it to the event.",
    )
    x_custom_event_location = fields.Char(
        string="Lokasi Event",
        copy=False,
        help="Venue of the event this document belongs to.",
    )
    x_custom_event_visible = fields.Boolean(
        compute="_compute_x_custom_event_visible",
        help="Technical helper: True when this company captures event data.",
    )

    @api.depends(
        "company_id",
        "company_id.x_custom_show_date_enabled",
        "company_id.x_custom_event_tracking_enabled",
    )
    def _compute_x_custom_event_visible(self):
        for move in self:
            company = move.company_id
            move.x_custom_event_visible = bool(
                company.x_custom_show_date_enabled or company.x_custom_event_tracking_enabled
            )

    def _custom_event_taggable_lines(self):
        """Only the costed/earning lines — never tax or payment-term lines.

        A journal entry carries the payable/receivable and tax lines too;
        putting analytic on them would double the event's result.
        """
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line.display_type == "product")

    # Re-declares the EXACT core @api.depends list (verified against
    # account/models/account_move.py@19.0) PLUS the two new triggers. Omitting
    # any of the original five silently breaks recompute on that field.
    @api.depends(
        "invoice_payment_term_id",
        "invoice_date",
        "currency_id",
        "amount_total_in_currency_signed",
        "invoice_date_due",
        "x_custom_show_date",
        "company_id.x_custom_show_date_enabled",
    )
    def _compute_needed_terms(self):
        # Anchored = flagged-company customer invoices that carry a show date.
        anchored = self.filtered(
            lambda m: m.company_id.x_custom_show_date_enabled and m.move_type == "out_invoice" and m.x_custom_show_date
        )
        rest = self - anchored

        if rest:
            super(AccountMove, rest)._compute_needed_terms()

        # Per-record: the anchor is move-specific, so each must call super with
        # its own context. account.payment.term._compute_terms consumes the key.
        for move in anchored:
            super(
                AccountMove,
                move.with_context(arka_show_date_ref=move.x_custom_show_date),
            )._compute_needed_terms()
