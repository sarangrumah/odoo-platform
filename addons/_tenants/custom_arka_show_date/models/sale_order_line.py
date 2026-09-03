# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Re-declares the EXACT core @api.depends list (verified against
    # sale/models/sale_order_line.py@19.0) PLUS the four order fields the event
    # block is built from, so editing the event data refreshes the descriptions
    # that were derived from it. The field stays readonly=False, so a manually
    # typed description survives until one of these dependencies changes.
    @api.depends(
        "product_id",
        "linked_line_id",
        "linked_line_ids",
        "order_id.x_custom_event_name",
        "order_id.x_custom_event_location",
        "order_id.x_custom_show_date",
        "order_id.x_custom_dp_note",
    )
    def _compute_name(self):
        super()._compute_name()
        for line in self:
            # Down-payment lines carry their own wording, built by
            # _get_downpayment_description() below — leave them alone here.
            if not line.product_id or line.is_downpayment:
                continue
            event = line.order_id._custom_event_description()
            if not event:
                continue
            # super() has just rebuilt `name` from the product, so the first
            # line is the product description and the block below is ours.
            line.name = "%s\n%s" % ((line.name or "").strip(), event)

    def _get_downpayment_description(self):
        """Relabel the down-payment line the customer sees on the *pelunasan*.

        Core writes "Down Payment (ref: INV/… on 08/14/2026)" here, and that one
        string reaches three places: the "Down Payments" section of the order,
        the final invoice PDF, and — because ``custom_coretax_export`` exports
        every ``display_type == 'product'`` line — the Faktur Pajak "Nama Barang
        Jasa" cell of the settlement invoice. ARKA bills a show, so the same
        product + event wording used on the down-payment invoice leads here too,
        with the core reference kept as the trailing marker so Finance can still
        reconcile the deduction against the down-payment invoice::

            Jasa Drone Show 1000 Unit, Event Soekarno Cup, Lokasi Stadion
            Gelora Bung Tomo Surabaya, 24.08.26 (Uang Muka ref:
            INV/ARKA/2026/08/002 tgl 14/08/2026)

        Section lines ("Down Payments") and non-flagged companies keep the core
        wording untouched.
        """
        self.ensure_one()
        if self.display_type or not self.order_id.company_id.x_custom_show_date_enabled:
            return super()._get_downpayment_description()
        description = self.order_id._custom_down_payment_description(self._custom_down_payment_marker())
        return description or super()._get_downpayment_description()

    def _custom_down_payment_marker(self):
        """Trailing "(Uang Muka …)" marker, mirroring the core state wording.

        Dates are formatted dd/mm/YYYY explicitly rather than through
        ``format_date``: the string also lands in the coretax import file, which
        is read by the tax team in Indonesian format whatever the user's locale.
        """
        self.ensure_one()
        dp_state = self._get_downpayment_state()
        if dp_state == "draft":
            return "(Uang Muka Draft %s)" % self.create_date.date().strftime("%d/%m/%Y")
        if dp_state == "cancel":
            return "(Uang Muka Dibatalkan)"
        invoice = (
            self._get_invoice_lines()
            .filtered(lambda aml: aml.quantity >= 0)
            .move_id.filtered(lambda move: move.move_type == "out_invoice")
        )
        if len(invoice) == 1 and invoice.payment_reference and invoice.invoice_date:
            return "(Uang Muka ref: %s tgl %s)" % (
                invoice.payment_reference,
                invoice.invoice_date.strftime("%d/%m/%Y"),
            )
        return "(Uang Muka)"
