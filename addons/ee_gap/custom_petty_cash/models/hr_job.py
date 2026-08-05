# -*- coding: utf-8 -*-
"""Per-position advance ceiling.

Sits between the employee-specific limit and the type-wide one, so Finance can
say "a Supervisor may hold 10jt" once instead of on every employee record.
"""

from __future__ import annotations

from odoo import fields, models


class HrJob(models.Model):
    _inherit = "hr.job"

    pc_advance_limit = fields.Monetary(
        string="Cash Advance Ceiling",
        currency_field="pc_currency_id",
        help="Maximum total open advances an employee in this position may "
        "hold, in company currency. 0 = no position-level limit (the type's "
        "ceiling applies instead).",
    )
    # Not a `related` on company_id.currency_id: hr.job.company_id is optional,
    # and a Monetary whose currency is empty renders blank.
    pc_currency_id = fields.Many2one("res.currency", compute="_compute_pc_currency_id")

    def _compute_pc_currency_id(self):
        for rec in self:
            rec.pc_currency_id = rec.company_id.currency_id or self.env.company.currency_id
