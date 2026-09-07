# -*- coding: utf-8 -*-
"""Let a flagged service be picked by hand on a transfer.

The moves that matter are created from the purchase order, but a warehouse user
adding or correcting a line on the receipt hits core's field-level domain --
``[('type', '=', 'consu')]`` on ``stock.move`` and ``[('type', '!=', 'service')]``
on ``stock.move.line``. Both are pure UI filters, so widening them by exactly the
flag is enough; nothing else in stock reads the product type to decide what it
may do with a move.
"""

from odoo import fields, models

_SERVICE_RECEIPT_DOMAIN = "['|', ('type', '=', 'consu'), '&', ('type', '=', 'service'), ('receive_on_gr', '=', True)]"


class StockMove(models.Model):
    _inherit = "stock.move"

    product_id = fields.Many2one(domain=_SERVICE_RECEIPT_DOMAIN)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    product_id = fields.Many2one(domain=_SERVICE_RECEIPT_DOMAIN)
