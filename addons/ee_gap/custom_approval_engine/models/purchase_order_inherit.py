# -*- coding: utf-8 -*-
"""Gate ``purchase.order.button_confirm`` on approval state."""

from __future__ import annotations

from odoo import models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "approval.mixin"]

    def button_confirm(self):
        for order in self:
            order._approval_check_required()
        return super().button_confirm()
