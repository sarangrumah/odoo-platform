# -*- coding: utf-8 -*-
"""stock.move.line hook — on incoming validate, auto-propose putaway."""

from __future__ import annotations

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _is_incoming(self) -> bool:
        self.ensure_one()
        ptype = self.picking_id.picking_type_id
        return bool(ptype and ptype.code == "incoming")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        engine = self.env["custom.putaway.engine"]
        for rec in records:
            try:
                if rec._is_incoming():
                    engine.apply_top_proposal(rec)
            except Exception as exc:  # pragma: no cover - never block create
                _logger.warning("putaway auto-propose failed for ml=%s: %s", rec.id, exc)
        return records
