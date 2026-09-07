# -*- coding: utf-8 -*-
"""Push flagged service lines onto the purchase order's receipt.

``purchase_stock`` gates every picking path on ``product_id.type == 'consu'``:
``_compute_qty_received_method``, ``_prepare_stock_moves`` and
``_create_or_update_picking`` all step over a service. Each is reopened here for
the lines whose product carries ``receive_on_gr``.

A service has no procurement chain and is never reserved -- ``stock.move``
bypasses reservation for anything that is not storable -- so the goods branches
collapse to a single move that is available the moment it is confirmed.
"""

from odoo import _, api, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _is_service_receipt_line(self):
        """True for an orderable line whose service is flagged to be received."""
        self.ensure_one()
        return not self.display_type and self.product_id and self.product_id._is_service_receipt_product()

    # ------------------------------------------------------------------
    # Received quantity
    # ------------------------------------------------------------------
    # Re-declaring @api.depends REPLACES the inherited set, so the base triggers
    # are relisted here alongside the flag that now feeds the same compute.
    @api.depends(
        "product_id",
        "product_id.type",
        "product_id.receive_on_gr",
        "order_id.state",
        "move_ids",
    )
    def _compute_qty_received_method(self):
        super()._compute_qty_received_method()
        for line in self:
            if not line._is_service_receipt_line():
                continue
            # Only take the received quantity over where a receipt can actually
            # supply it. Flagging a product recomputes every line that ever used
            # it, confirmed orders included -- and a line confirmed before the
            # flag existed has no receipt and can never be given one, because
            # core only builds them at confirmation. Switching it would zero a
            # quantity somebody typed, leaving the order unbillable, or
            # bill-negative where it was already invoiced. Core takes the same
            # care: purchase_stock's own install hook recomputes every order
            # EXCEPT the confirmed ones.
            if line.order_id.state in ("draft", "sent") or line.move_ids:
                line.qty_received_method = "stock_moves"

    # ------------------------------------------------------------------
    # Receipt
    # ------------------------------------------------------------------
    def _prepare_stock_moves(self, picking):
        self.ensure_one()
        if not self._is_service_receipt_line():
            return super()._prepare_stock_moves(picking)

        # Core's goods branch splits the quantity between moves that answer a
        # downstream demand and the rest. A service is bought for itself, never
        # pulled by a procurement, so only "the rest" is ever left -- whatever is
        # ordered and not already on a receipt.
        qty_to_push = self.product_qty - self._get_qty_procurement()
        if self.product_uom_id.is_zero(qty_to_push):
            return []
        product_uom_qty, product_uom = self.product_uom_id._adjust_uom_quantities(qty_to_push, self.product_id.uom_id)
        vals = self._prepare_stock_move_vals(picking, self._get_stock_move_price_unit(), product_uom_qty, product_uom)
        vals["move_dest_ids"] = False
        return [vals]

    def _create_or_update_picking(self):
        service_lines = self.filtered(lambda line: line._is_service_receipt_line())
        super(PurchaseOrderLine, self - service_lines)._create_or_update_picking()
        for line in service_lines:
            line._service_receipt_create_or_update_picking()

    def _service_receipt_create_or_update_picking(self):
        """Core's ``_create_or_update_picking`` body, for one service line."""
        self.ensure_one()
        if self.product_uom_id.compare(self.product_qty, self.qty_invoiced) < 0 and self.invoice_lines:
            # Ordering less than has been billed needs a refund, same as a good.
            self.invoice_lines[0].move_id.activity_schedule(
                "mail.mail_activity_data_warning",
                note=_("The quantities on your purchase order indicate less than billed. You should ask for a refund."),
                user_id=self.env.uid,
            )

        picking = self._service_receipt_picking()
        if not picking:
            if self.product_qty <= self.qty_received:
                return
            picking = self.env["stock.picking"].create(self.order_id._prepare_picking())

        moves = self._create_stock_moves(picking)
        moves._action_confirm()._action_assign()

    def _service_receipt_picking(self):
        """The open receipt this line should join, if there is one.

        Its own moves' transfer wins over any other open transfer on the order,
        which is how core picks one for a good.
        """
        self.ensure_one()

        def is_open_incoming(picking):
            return picking.state not in ("done", "cancel") and picking.location_dest_id.usage in (
                "internal",
                "transit",
                "customer",
            )

        line_pickings = self.move_ids.picking_id.filtered(is_open_incoming)
        if line_pickings:
            return line_pickings[0]
        return self.order_id.picking_ids.filtered(is_open_incoming)[:1]
