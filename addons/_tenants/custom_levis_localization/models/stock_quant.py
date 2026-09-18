# -*- coding: utf-8 -*-
"""A document number for inventory adjustments (sheet row #70).

Odoo 19 books an inventory adjustment as bare ``stock.move`` records with
``is_inventory = True`` and no picking, so there is no document to point at:
the Reference column falls back to a generic string and two unrelated counts on
the same day are indistinguishable. Accounting asked for ``STADJ/2026/09/00001``.

Odoo already has the hook — ``stock.move.inventory_name`` feeds
``_compute_reference``, and ``stock.quant._get_inventory_move_values`` reads it
off the context. So the whole change is to draw one sequence number per *apply*
(not per quant: one count is one document, however many lines it touches) and
let core carry it the rest of the way.
"""

from odoo import models

ADJUSTMENT_SEQUENCE = "levis.stock.adjustment"


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _apply_inventory(self, date=None):
        if self and not self.env.context.get("inventory_name"):
            reference = self.env["ir.sequence"].next_by_code(ADJUSTMENT_SEQUENCE)
            if reference:
                quants = self.with_context(inventory_name=reference)
                return super(StockQuant, quants)._apply_inventory(date=date)
        return super()._apply_inventory(date=date)
