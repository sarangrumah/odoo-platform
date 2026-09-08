# -*- coding: utf-8 -*-
from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _asset_conversion_mode(self):
        self.ensure_one()
        return self.product_tmpl_id._asset_conversion_mode()

    def _can_be_fixed_asset(self):
        """Whether this product can become a ``custom.fixed.asset`` at all.

        A service cannot: the register is a subledger of things, counted or
        identified, and a depreciation schedule needs something that was
        acquired. Services normally never reach the wizard because they never
        reach a receipt -- but ``custom_service_receipt`` puts flagged ones on
        one, so the register has to say no for itself.
        """
        self.ensure_one()
        return self.type != "service"
