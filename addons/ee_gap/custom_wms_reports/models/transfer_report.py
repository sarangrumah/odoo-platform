# -*- coding: utf-8 -*-
"""Transfer Report — read-only SQL view over stock moves that belong to a
picking (receipts / deliveries / internal transfers, including the moves
materialised by the WMS Transfer Order engine). Grouped in the views by
operation type, source/destination and product.
"""

from odoo import fields, models, tools


TRANSFER_KIND = [
    ("incoming", "Receipt"),
    ("outgoing", "Delivery"),
    ("internal", "Internal Transfer"),
]

MOVE_STATE = [
    ("draft", "Draft"),
    ("waiting", "Waiting Another Operation"),
    ("confirmed", "Waiting"),
    ("partially_available", "Partially Available"),
    ("assigned", "Ready"),
    ("done", "Done"),
    ("cancel", "Cancelled"),
]


class WmsTransferReport(models.Model):
    _name = "custom.wms.transfer.report"
    _description = "Transfer Report"
    _auto = False
    _rec_name = "reference"
    _order = "date desc, id desc"

    date = fields.Datetime(readonly=True)
    reference = fields.Char(readonly=True)
    origin = fields.Char(string="Source Document", readonly=True)
    picking_id = fields.Many2one("stock.picking", readonly=True)
    picking_type_id = fields.Many2one("stock.picking.type", string="Operation Type", readonly=True)
    transfer_kind = fields.Selection(TRANSFER_KIND, string="Kind", readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True)
    location_id = fields.Many2one("stock.location", string="From", readonly=True)
    location_dest_id = fields.Many2one("stock.location", string="To", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    default_code = fields.Char(string="SKU", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    demand_qty = fields.Float(string="Demand", readonly=True)
    done_qty = fields.Float(string="Done", readonly=True)
    state = fields.Selection(MOVE_STATE, readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    m.id AS id,
                    m.date AS date,
                    m.reference AS reference,
                    m.origin AS origin,
                    m.picking_id AS picking_id,
                    m.picking_type_id AS picking_type_id,
                    spt.code AS transfer_kind,
                    pick.partner_id AS partner_id,
                    m.location_id AS location_id,
                    m.location_dest_id AS location_dest_id,
                    m.product_id AS product_id,
                    pp.default_code AS default_code,
                    pt.categ_id AS categ_id,
                    m.product_uom_qty AS demand_qty,
                    CASE WHEN m.state = 'done' THEN m.quantity ELSE 0.0 END AS done_qty,
                    m.state AS state,
                    m.company_id AS company_id
                FROM stock_move m
                JOIN stock_picking_type spt ON spt.id = m.picking_type_id
                JOIN product_product pp ON pp.id = m.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN stock_picking pick ON pick.id = m.picking_id
                WHERE m.state != 'cancel'
            )
            """
        )
