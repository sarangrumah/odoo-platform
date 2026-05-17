# -*- coding: utf-8 -*-
"""Gate ``account.move._post`` on approval state."""

from __future__ import annotations

from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "approval.mixin"]

    def _post(self, soft=True):
        for move in self:
            move._approval_check_required()
        return super()._post(soft=soft)
