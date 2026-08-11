# -*- coding: utf-8 -*-
"""Operating Unit on purchase and sales orders, and onto the invoices they make."""

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(compute="_compute_operating_unit_id", store=True, readonly=False)

    @api.depends("picking_type_id.warehouse_id")
    def _compute_operating_unit_id(self):
        index = self.env["operating.unit"]._warehouse_index()
        default_unit = self.env.user.default_operating_unit_id
        for order in self:
            if order.operating_unit_id:
                continue
            order.operating_unit_id = index.get(order.picking_type_id.warehouse_id.id) or default_unit.id or False

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.operating_unit_id:
            vals["operating_unit_id"] = self.operating_unit_id.id
        return vals


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(compute="_compute_operating_unit_id", store=True, readonly=False)

    @api.depends("warehouse_id")
    def _compute_operating_unit_id(self):
        index = self.env["operating.unit"]._warehouse_index()
        default_unit = self.env.user.default_operating_unit_id
        for order in self:
            if order.operating_unit_id:
                continue
            order.operating_unit_id = index.get(order.warehouse_id.id) or default_unit.id or False

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.operating_unit_id:
            vals["operating_unit_id"] = self.operating_unit_id.id
        return vals
