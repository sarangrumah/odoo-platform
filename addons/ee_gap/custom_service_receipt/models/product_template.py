# -*- coding: utf-8 -*-
"""Opt a service product into the goods receipt.

The flag lives on the template because that is where the purchase control policy
it travels with lives. It is only read for ``type == 'service'``: goods already
go through a receipt, and setting it there changes nothing.
"""

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    receive_on_gr = fields.Boolean(
        string="Receive on Goods Receipt",
        help="Put this service on the purchase order's receipt, like a good. The "
        "received quantity then comes from the validated receipt instead of being "
        "typed on the order line, so the vendor bill is gated by an acceptance "
        "document. Ticking this also switches the control policy to 'On received "
        "quantities'. No stock is moved and nothing is valued: a service creates "
        "no quant and no journal entry.",
    )

    def _sync_receive_on_gr(self, vals):
        """Force *On received quantities* when the flag is switched on.

        A receipt that does not gate the bill is decoration, so the two settings
        are kept together -- unless the caller is setting the policy itself in the
        same write, which then wins.
        """
        if vals.get("receive_on_gr") and "purchase_method" not in vals:
            vals = dict(vals, purchase_method="receive")
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._sync_receive_on_gr(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._sync_receive_on_gr(vals))


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _is_service_receipt_product(self):
        """True for a service that its master says should arrive on a receipt."""
        self.ensure_one()
        return self.type == "service" and self.receive_on_gr
