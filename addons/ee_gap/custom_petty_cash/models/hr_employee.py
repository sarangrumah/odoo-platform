# -*- coding: utf-8 -*-
"""Per-employee analytic account so a single petty-cash account can be sliced
by employee (a dedicated "Employee" analytic plan, separate from the
"Operating Unit" plan), plus the employee-level advance ceiling."""

from __future__ import annotations

from odoo import fields, models

PC_EMPLOYEE_PLAN = "Employee"


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pc_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Petty Cash Analytic",
        copy=False,
        help="Analytic account (plan 'Employee') stamped on this employee's "
        "petty-cash journal items so the shared advance account can be "
        "reported per employee.",
    )
    pc_advance_limit = fields.Monetary(
        string="Cash Advance Ceiling",
        currency_field="pc_currency_id",
        help="Maximum total open advances this employee may hold, in company "
        "currency. 0 = fall through to the job position's ceiling, then the "
        "advance type's.",
    )
    pc_currency_id = fields.Many2one("res.currency", compute="_compute_pc_currency_id")

    def _compute_pc_currency_id(self):
        for rec in self:
            rec.pc_currency_id = rec.company_id.currency_id or self.env.company.currency_id

    def _pc_employee_plan(self):
        """Get-or-create the dedicated 'Employee' analytic plan.

        The plan name is configurable so a tenant whose analytic plans are
        already named differently does not end up with a second, near-duplicate
        plan.
        """
        plan_name = (
            self.env["ir.config_parameter"].sudo().get_param("custom_petty_cash.employee_plan_name") or PC_EMPLOYEE_PLAN
        )
        Plan = self.env["account.analytic.plan"].sudo()
        plan = Plan.search([("name", "=", plan_name)], limit=1)
        if not plan:
            plan = Plan.create({"name": plan_name})
        return plan

    def _pc_get_analytic_account(self):
        """Return this employee's analytic account, creating it on first use."""
        self.ensure_one()
        if self.pc_analytic_account_id:
            return self.pc_analytic_account_id
        plan = self._pc_employee_plan()
        account = (
            self.env["account.analytic.account"]
            .sudo()
            .create(
                {
                    "name": self.name,
                    "plan_id": plan.id,
                    "company_id": self.company_id.id or self.env.company.id,
                }
            )
        )
        self.sudo().pc_analytic_account_id = account.id
        return account
