# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class AgedPayableWizard(models.TransientModel):
    _name = "custom.report.aged.payable.wizard"
    _inherit = "custom.report.wizard.mixin"
    _description = "Aged Payable Wizard"
    _report_code = "aged_payable"

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
        help="Detail = one row per open document, with its bill number, vendor "
        "reference and payable account (the PDF always prints the per-partner "
        "summary).",
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
            "report_code": "aged_payable",
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
        filename = "Aged_Payable_%s.xlsx" % self.date_to
        report = self.env["custom.report.aged.payable"].with_context(
            aging_detail=self.detail_mode == "detail",
        )
        return report._xlsx_action(options, filename)

    # ------------------------------------------------------------------
    # AP Aging Export
    # ------------------------------------------------------------------
    # The payable twin of ``action_*_ar_aging`` on the receivable wizard, and
    # reusing this wizard for the same reason: a new TransientModel would force
    # a schema change on all thirteen databases that carry this addon. The menu
    # points here with ``ap_aging_export`` in the context, which swaps the
    # footer buttons and hides ``detail_mode`` (the export is always per
    # document).
    _AP_AGING_CODE = "ap_aging_export"

    def _ap_aging_options(self):
        return {
            **self._build_filters(),
            "date_from": date(1970, 1, 1).isoformat(),
            "date_to": self.date_to.isoformat(),
        }

    def action_view_ap_aging(self):
        self.ensure_one()
        title = self.env["custom.report.ap.aging.export"]._report_title
        return {
            "type": "ir.actions.client",
            "tag": "custom_report_table",
            "name": title,
            "params": {
                "report_code": self._AP_AGING_CODE,
                "options": self._ap_aging_options(),
                "context_extra": {},
                "title": title,
            },
        }

    def action_print_ap_aging(self):
        self.ensure_one()
        data = {
            "report_code": self._AP_AGING_CODE,
            "doc_model": self._name,
            "options": self._ap_aging_options(),
        }
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)

    def action_export_ap_aging_xlsx(self):
        self.ensure_one()
        filename = "AP_Aging_Export_%s.xlsx" % self.date_to
        return self.env["custom.report.ap.aging.export"]._xlsx_action(self._ap_aging_options(), filename)
