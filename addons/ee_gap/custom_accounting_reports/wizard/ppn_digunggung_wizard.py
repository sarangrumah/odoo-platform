# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class PpnDigunggungWizard(models.TransientModel):
    _name = "custom.report.ppn.digunggung.wizard"
    _inherit = "custom.report.wizard.mixin"
    _description = "Rekap PPN Keluaran Digunggung Wizard"
    _report_code = "ppn_digunggung"

    date_from = fields.Date(
        string="Masa Dari",
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string="Masa Sampai",
        required=True,
        default=lambda self: date.today(),
    )
    company_ids = fields.Many2many(
        "res.company",
        default=lambda self: self.env.companies,
    )
    posted_only = fields.Boolean(default=True)

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "posted_only": self.posted_only,
        }

    def _report_code_for_view(self):
        """Recap by default; the per-transaction detail when the menu asks.

        Both menus drive this one wizard on purpose — the filters are
        identical, and a second ``TransientModel`` would force an ``-u`` on
        every tenant that has this addon installed.
        """
        return "ppn_digunggung_detail" if self.env.context.get("ppn_digunggung_detail") else "ppn_digunggung"

    def action_print(self):
        self.ensure_one()
        data = {
            "report_code": self._report_code_for_view(),
            "doc_model": self._name,
            "options": {
                **self._build_filters(),
                "date_from": self.date_from.isoformat(),
                "date_to": self.date_to.isoformat(),
            },
        }
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)

    def action_export_xlsx(self):
        self.ensure_one()
        options = {
            **self._build_filters(),
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
        }
        code = self._report_code_for_view()
        stem = "PPN_Digunggung_Detail" if code == "ppn_digunggung_detail" else "PPN_Digunggung"
        filename = "%s_%s_%s.xlsx" % (stem, self.date_from, self.date_to)
        report = self.env["report.custom_accounting_reports.report_dispatch"]._report_model(code)
        return report._xlsx_action(options, filename)

    def action_view_source(self):
        """The POS journal entries behind the recap, never the invoices."""
        self.ensure_one()
        domain = [
            ("company_id", "in", self.company_ids.ids or self.env.companies.ids),
            ("move_type", "not in", ("out_invoice", "out_refund")),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("line_ids.tax_line_id", "!=", False),
        ]
        if self.posted_only:
            domain.append(("state", "=", "posted"))
        return {
            "type": "ir.actions.act_window",
            "name": "Penyerahan Digunggung",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": domain,
            "target": "current",
        }
