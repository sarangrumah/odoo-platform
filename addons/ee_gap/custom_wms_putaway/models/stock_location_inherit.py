# -*- coding: utf-8 -*-
"""stock.location extension — volumetric capacity tracking."""

from __future__ import annotations

from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    volume_capacity_m3 = fields.Float(string="Volume Capacity (m3)", default=0.0)
    volume_used_m3 = fields.Float(
        string="Volume Used (m3)",
        compute="_compute_volume_used",
        store=False,
    )

    @api.depends("quant_ids", "quant_ids.quantity", "quant_ids.product_id")
    def _compute_volume_used(self):
        for rec in self:
            total = 0.0
            for q in rec.quant_ids:
                vol = (q.product_id.volume or 0.0) * (q.quantity or 0.0)
                total += vol
            rec.volume_used_m3 = total
