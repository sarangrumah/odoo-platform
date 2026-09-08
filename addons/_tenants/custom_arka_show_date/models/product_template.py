# -*- coding: utf-8 -*-
"""What ARKA sells is not what ARKA buys.

The client keeps two catalogues for the same show. The customer order carries
the *Jasa* product — the service ARKA sells — while the purchase order raised on
the sister company carries the matching *Sewa* product, the rental AIM invoices
back::

    Jasa Drone Show 250 Unit   (sold to the customer)
    Sewa Drone Show 250 Unit   (bought from AIM)

Without somewhere to record that pairing, the purchase order generated from a
sale carried the *Jasa* line, and the buyer had to swap the product by hand on
every order — which is the retyping this whole feature exists to remove.

Odoo has no native sale→purchase substitution: ``product.supplierinfo`` prices a
product from a vendor, it does not replace it. Hence this one field.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_custom_ic_purchase_product_id = fields.Many2one(
        "product.product",
        string="Purchased As",
        copy=False,
        index="btree_not_null",
        domain="[('purchase_ok', '=', True)]",
        help="The product to buy when this one is sold. Used by 'Buat PO ke "
        "Sister Company' on the sales order: the customer line's product is "
        "replaced by this one on the purchase order. Leave empty to buy exactly "
        "what was sold.",
    )

    @api.constrains("x_custom_ic_purchase_product_id")
    def _check_x_custom_ic_purchase_product_id(self):
        for template in self:
            substitute = template.x_custom_ic_purchase_product_id
            if substitute and substitute.product_tmpl_id == template:
                raise ValidationError(_("'%s' cannot be purchased as itself.", template.display_name))


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _custom_ic_purchase_product(self):
        """The product to put on the purchase order in place of this one.

        Resolved ONE hop only, deliberately: a chain would walk the buyer to a
        product nobody chose, and a cycle would hang. Falls back to this very
        variant — not the template's default one — when no pairing is recorded,
        so a variant sold is the variant bought.
        """
        self.ensure_one()
        return self.x_custom_ic_purchase_product_id or self
