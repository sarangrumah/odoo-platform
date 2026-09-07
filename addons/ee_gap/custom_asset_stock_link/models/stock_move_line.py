# -*- coding: utf-8 -*-
from odoo import models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _action_done(self):
        """Single choke point for asset position tracking.

        Pickings, internal transfers, rental pickup/return and inventory
        adjustments (``stock.quant._apply_inventory``) all end up here, so one
        override keeps every asset's physical location current.
        """
        res = super()._action_done()
        if self.env.context.get("skip_asset_stock_sync"):
            return res
        lot_ids = self.exists().lot_id.ids
        if lot_ids:
            self.env["custom.fixed.asset"].sudo()._sync_stock_from_lots(lot_ids)
        return res
