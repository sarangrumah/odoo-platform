# -*- coding: utf-8 -*-
"""Gate ``sale.order.action_confirm`` on approval state."""

from __future__ import annotations

from odoo import models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "approval.mixin"]

    def action_confirm(self):
        for order in self:
            order._approval_check_required()
        return super().action_confirm()
