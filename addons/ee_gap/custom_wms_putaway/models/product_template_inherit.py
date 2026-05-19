# -*- coding: utf-8 -*-
"""product.template extension — ABC velocity classification."""

from __future__ import annotations

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    abc_class = fields.Selection(
        [("A", "A"), ("B", "B"), ("C", "C")],
        string="ABC Class",
        default="B",
        help="Velocity-based ABC classification: A=fast, B=medium, C=slow.",
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    abc_class = fields.Selection(related="product_tmpl_id.abc_class", store=True, readonly=False)
