# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class AgedReceivableWizard(models.TransientModel):
    _name = "custom.report.aged.receivable.wizard"
    _inherit = "custom.report.wizard.mixin"
    _description = "Aged Receivable Wizard"
    _report_code = "aged_receivable"

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
    detail_mode = fields.Selection(
        [
            ("summary", "Summary (per partner)"),
            ("detail", "Detail (per document)"),
        ],
        string="Detail Level",
        default="detail",
        required=True,
        help="Detail = one row per open document, with its invoice number and "
        "receivable account (the PDF always prints the per-partner summary).",
    )

    def _report_context_extra(self):
        return {"aging_detail": self.detail_mode == "detail"}

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

    def action_export_xlsx(self):
        self.ensure_one()
        options = {
            **self._build_filters(),
            "date_from": date(1970, 1, 1).isoformat(),
            "date_to": self.date_to.isoformat(),
        }
        filename = "Aged_Receivable_%s.xlsx" % self.date_to
        report = self.env["custom.report.aged.receivable"].with_context(
            aging_detail=self.detail_mode == "detail",
        )
        return report._xlsx_action(options, filename)

    # ------------------------------------------------------------------
    # AR Aging Export
    # ------------------------------------------------------------------
    # Finance's per-document collection worklist. It reuses this wizard's
    # filters rather than shipping a TransientModel of its own: this addon is
    # installed on every tenant, and a new transient table would force an
    # ``-u`` across all of them. The menu points here with
    # ``ar_aging_export`` in the context, which is what swaps the buttons.
    _AR_AGING_CODE = "ar_aging_export"

    def _ar_aging_options(self):
        return {
            **self._build_filters(),
            "date_from": date(1970, 1, 1).isoformat(),
            "date_to": self.date_to.isoformat(),
        }

    def action_view_ar_aging(self):
        self.ensure_one()
        title = self.env["custom.report.ar.aging.export"]._report_title
        return {
            "type": "ir.actions.client",
            "tag": "custom_report_table",
            "name": title,
            "params": {
                "report_code": self._AR_AGING_CODE,
                "options": self._ar_aging_options(),
                "context_extra": {},
                "title": title,
            },
        }

    def action_print_ar_aging(self):
        self.ensure_one()
        data = {
            "report_code": self._AR_AGING_CODE,
            "doc_model": self._name,
            "options": self._ar_aging_options(),
        }
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)

    def action_export_ar_aging_xlsx(self):
        self.ensure_one()
        filename = "AR_Aging_Export_%s.xlsx" % self.date_to
        return self.env["custom.report.ar.aging.export"]._xlsx_action(self._ar_aging_options(), filename)
