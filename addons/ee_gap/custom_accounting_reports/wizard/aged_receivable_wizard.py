# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class AgedReceivableWizard(models.TransientModel):
    _name = "custom.report.aged.receivable.wizard"
    _description = "Aged Receivable Wizard"

    date_to = fields.Date(
        string="As Of",
        required=True,
        default=lambda self: date.today(),
    )
    company_ids = fields.Many2many(
        "res.company",
        default=lambda self: self.env.companies,
    )
    partner_ids = fields.Many2many("res.partner")

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_to": self.date_to,
            "date_from": date(1970, 1, 1),
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "partner_ids": self.partner_ids.ids,
            "posted_only": True,
        }

    def action_print(self):
        self.ensure_one()
        data = {
            "report_code": "aged_receivable",
            "doc_model": self._name,
            "options": {
                **self._build_filters(),
                "date_from": date(1970, 1, 1).isoformat(),
                "date_to": self.date_to.isoformat(),
            },
        }
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)
