# -*- coding: utf-8 -*-
"""Warranty matrix lookup for product warranty terms."""

from __future__ import annotations

from odoo import fields, models


class WarrantyMatrix(models.Model):
    _name = "custom.repairs.warranty.matrix"
    _description = "Repair Warranty Matrix"
    _order = "product_id, id"

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    warranty_months = fields.Integer(
        string="Warranty (months)",
        required=True,
        default=12,
    )
    warranty_terms = fields.Text(
        string="Warranty Terms",
        help="Terms and conditions for warranty coverage of this product.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "warranty_months_positive",
            "CHECK (warranty_months >= 0)",
            "Warranty months must be zero or positive.",
        ),
    ]
