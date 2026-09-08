# -*- coding: utf-8 -*-
"""Operating Unit on stock documents — always derived from the warehouse."""

from odoo import api, fields, models


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(compute="_compute_operating_unit_id", store=True, readonly=False)

    @api.depends("picking_type_id.warehouse_id")
    def _compute_operating_unit_id(self):
        index = self.env["operating.unit"]._warehouse_index()
        for picking in self:
            if picking.operating_unit_id:
                continue
            picking.operating_unit_id = index.get(picking.picking_type_id.warehouse_id.id) or False


class StockMove(models.Model):
    _name = "stock.move"
    _inherit = ["stock.move", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(compute="_compute_operating_unit_id", store=True, readonly=False)

    @api.depends("picking_id.operating_unit_id", "picking_type_id.warehouse_id")
    def _compute_operating_unit_id(self):
        index = self.env["operating.unit"]._warehouse_index()
        for move in self:
            if move.operating_unit_id:
                continue
            move.operating_unit_id = (
                move.picking_id.operating_unit_id.id or index.get(move.picking_type_id.warehouse_id.id) or False
            )


class StockQuant(models.Model):
    _name = "stock.quant"
    _inherit = ["stock.quant", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(compute="_compute_operating_unit_id", store=True, readonly=False)

    @api.depends("location_id.warehouse_id")
    def _compute_operating_unit_id(self):
        index = self.env["operating.unit"]._warehouse_index()
        for quant in self:
            # Quants are rewritten constantly by the stock engine; recomputing
            # from the location every time is correct and cheap (cached index).
            quant.operating_unit_id = index.get(quant.location_id.warehouse_id.id) or False
