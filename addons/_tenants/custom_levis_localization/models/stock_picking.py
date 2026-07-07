# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        # Requirement 2: on goods receipt the received (done) quantity of each
        # line must not exceed its demand (ordered) quantity.
        for picking in self:
            if picking.picking_type_code != "incoming":
                continue
            offending = []
            for move in picking.move_ids:
                rounding = move.product_uom.rounding
                if float_compare(move.quantity, move.product_uom_qty, precision_rounding=rounding) > 0:
                    offending.append(
                        _(
                            "- %(product)s: received %(done)s > demand %(demand)s",
                            product=move.product_id.display_name,
                            done=move.quantity,
                            demand=move.product_uom_qty,
                        )
                    )
            if offending:
                raise UserError(
                    _(
                        "Received quantity cannot exceed the demand quantity on a goods receipt.\n\n%(lines)s",
                        lines="\n".join(offending),
                    )
                )
        return super().button_validate()
