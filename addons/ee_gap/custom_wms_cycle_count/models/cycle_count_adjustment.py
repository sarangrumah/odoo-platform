# -*- coding: utf-8 -*-
"""Cycle-count adjustment — the variance-posting record."""

from __future__ import annotations

from odoo import _, fields, models
from odoo.exceptions import UserError


class CycleCountAdjustment(models.Model):
    _name = "custom.cycle.count.adjustment"
    _description = "Cycle Count Adjustment"
    _inherit = ["mail.thread", "pdp.audited.mixin"]
    _order = "create_date desc, id desc"

    line_id = fields.Many2one(
        "custom.cycle.count.line", required=True, ondelete="cascade", index=True
    )
    stock_move_id = fields.Many2one("stock.move", string="Stock Move", ondelete="set null")
    approved_by_id = fields.Many2one("res.users")
    approved_at = fields.Datetime()
    posted = fields.Boolean(default=False, tracking=True)

    def action_post(self):
        for rec in self:
            if rec.posted:
                continue
            line = rec.line_id
            if not line or not line.location_id or not line.product_id:
                raise UserError(_("Cannot post adjustment without product + location."))
            # Create a stock.move documenting the variance against the inventory loss location.
            warehouse = line.session_id.warehouse_id
            inv_loc = self.env.ref("stock.location_inventory", raise_if_not_found=False)
            if not inv_loc:
                inv_loc = self.env["stock.location"].search(
                    [("usage", "=", "inventory")], limit=1
                )
            if not inv_loc:
                raise UserError(_("Inventory adjustment location not found."))
            qty = line.variance_qty or 0.0
            if qty == 0.0:
                rec.posted = True
                continue
            src, dst = (line.location_id, inv_loc) if qty < 0 else (inv_loc, line.location_id)
            move = self.env["stock.move"].create({
                "name": _("Cycle count adjustment %s") % line.session_id.name,
                "product_id": line.product_id.id,
                "product_uom": line.product_id.uom_id.id,
                "product_uom_qty": abs(qty),
                "location_id": src.id,
                "location_dest_id": dst.id,
                "company_id": (warehouse.company_id or self.env.company).id,
            })
            rec.stock_move_id = move.id
            rec.posted = True
