# -*- coding: utf-8 -*-
from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _asset_conversion_mode(self):
        self.ensure_one()
        return self.product_tmpl_id._asset_conversion_mode()
