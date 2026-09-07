# -*- coding: utf-8 -*-
"""Give an all-service order its receipt.

``purchase_stock._create_picking`` only enters its loop for an order that has at
least one goods line. A mixed order therefore already builds the receipt, and the
line-level override adds the service moves to it -- but an order made only of
services is skipped outright, and that is the common shape for the case this
module exists for (subcontracted work, manpower, venue, insurance).
"""

from odoo import models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _create_picking(self):
        res = super()._create_picking()
        for order in self.filtered(lambda po: po.state == "purchase"):
            if any(product.type == "consu" for product in order.order_line.product_id):
                # Core built the receipt; the service moves rode along with it.
                continue
            lines = order.order_line.filtered(lambda line: line._is_service_receipt_line())
            if not lines:
                continue
            order = order.with_company(order.company_id)
            known_pickings = order.picking_ids
            lines._create_or_update_picking()
            new_pickings = order.picking_ids - known_pickings
            order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")).action_confirm()
            for picking in new_pickings:
                picking.message_post_with_source(
                    "mail.message_origin_link",
                    render_values={"self": picking, "origin": order},
                    subtype_xmlid="mail.mt_note",
                )
        return res
