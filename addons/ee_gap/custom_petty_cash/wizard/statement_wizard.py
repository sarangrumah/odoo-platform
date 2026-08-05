# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class PettyCashStatementWizard(models.TransientModel):
    _name = "petty.cash.statement.wizard"
    _inherit = "custom.report.wizard.mixin"
    _description = "Kartu Uang Muka Wizard"
    _report_code = "petty_cash_statement"

    date_from = fields.Date(required=True, default=lambda self: date.today().replace(month=1, day=1))
    date_to = fields.Date(string="As Of", required=True, default=lambda self: date.today())
    company_ids = fields.Many2many("res.company", default=lambda self: self.env.companies)
    employee_ids = fields.Many2many("hr.employee", string="Employees")
    advance_type_ids = fields.Many2many("petty.cash.type", string="Advance Types")

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "employee_ids": self.employee_ids.ids,
            "advance_type_ids": self.advance_type_ids.ids,
            "posted_only": True,
        }

    def _iso_options(self):
        return {
            **self._build_filters(),
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
        }

    def action_print(self):
        self.ensure_one()
        data = {
            "report_code": self._report_code,
            "doc_model": self._name,
            "options": self._iso_options(),
        }
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)

    def action_export_xlsx(self):
        self.ensure_one()
        filename = "Kartu_Uang_Muka_%s.xlsx" % self.date_to
        return self.env["petty.cash.report.statement"]._xlsx_action(self._iso_options(), filename)
