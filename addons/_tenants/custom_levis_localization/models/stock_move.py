# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _is_levis_goods_receipt(self):
        """A vendor goods receipt: stock entering from a supplier location.

        This deliberately excludes internal transfers, manufacturing receipts
        and customer returns — only true vendor receipts skip GL posting.
        """
        self.ensure_one()
        return self.location_id.usage == "supplier"

    def _should_create_account_move(self):
        # Requirement 3: no inventory journal on Goods Receipt confirm.
        # The stock valuation layer is still produced by stock_account (so
        # on-hand value/qty remain correct); we only stop the account.move.
        self.ensure_one()
        if self._is_levis_goods_receipt():
            return False
        return super()._should_create_account_move()
