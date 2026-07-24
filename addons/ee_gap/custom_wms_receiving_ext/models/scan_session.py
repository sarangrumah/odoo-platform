# -*- coding: utf-8 -*-
"""Post-apply enrichment of lots created/linked by the barcode scan flow.

``custom_barcode.action_apply_to_picking`` creates/links ``stock.lot``
records but drops the GS1 expiration date (AI 17) it already parsed, and
knows nothing about supplier batch references. Rather than fork the shared
addon, we run after it and enrich every lot the OK scan lines point at.
"""

from __future__ import annotations

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class CustomBarcodeScanSession(models.Model):
    _inherit = "custom.barcode.scan.session"

    def action_apply_to_picking(self):
        res = super().action_apply_to_picking()
        Lot = self.env["stock.lot"]
        for rec in self:
            if not rec.picking_id:
                continue
            for line in rec.line_ids.filtered(lambda l: l.status == "ok" and l.product_id):
                if line.product_id.tracking not in ("lot", "serial"):
                    continue
                gs1 = line.get_gs1_dict()
                lot = line.lot_id
                if not lot:
                    lot_name = gs1.get("lot") or line.raw_barcode
                    if not lot_name:
                        continue
                    lot = Lot.search(
                        [("name", "=", lot_name), ("product_id", "=", line.product_id.id)],
                        limit=1,
                    )
                if not lot:
                    continue
                vals = {}
                exp_date = gs1.get("exp_date")
                if exp_date:
                    # product_expiry pre-fills expiration_date from the
                    # product's expiration_time on lot creation; the explicit
                    # GS1 date from the physical label must override it.
                    exp = fields.Date.to_date(exp_date)
                    if exp:
                        vals["expiration_date"] = fields.Datetime.to_datetime(exp)
                batch_ref = line.supplier_batch_ref or gs1.get("lot")
                if batch_ref and not lot.supplier_batch_ref:
                    vals["supplier_batch_ref"] = batch_ref
                if vals:
                    lot.write(vals)
                    _logger.info(
                        "scan session %s: enriched lot %s with %s",
                        rec.name,
                        lot.name,
                        vals,
                    )
        return res
