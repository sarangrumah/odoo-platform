# -*- coding: utf-8 -*-
"""Glue between Odoo's ``ir.actions.report`` dispatcher and each
concrete ``custom.report.*`` AbstractModel.

We register a single ``report.custom_accounting_reports.report_dispatch``
service. Wizards push the desired ``report_code`` + filters via the
``data`` payload; the dispatcher looks up the right AbstractModel,
builds its context, then hands off to a router QWeb template that
in turn includes the per-report layout.
"""

from odoo import api, models


REPORT_MODEL_MAP = {
    "general_ledger": "custom.report.general.ledger",
    "trial_balance": "custom.report.trial.balance",
    "balance_sheet": "custom.report.balance.sheet",
    "profit_loss": "custom.report.profit.loss",
    "profit_loss_branch": "custom.report.profit.loss.branch",
    "cash_flow": "custom.report.cash.flow",
    "aged_receivable": "custom.report.aged.receivable",
    "aged_payable": "custom.report.aged.payable",
    "partner_ledger": "custom.report.partner.ledger",
    "payable_card": "custom.report.payable.card",
    "receivable_card": "custom.report.receivable.card",
    "advance": "custom.report.advance",
    "sales": "custom.report.sales",
    "tax": "custom.report.tax",
    "faktur_pajak": "custom.report.faktur.pajak",
    "bupot": "custom.report.bupot",
    "spt_ppn": "custom.report.spt.ppn",
    "pph_withholding": "custom.report.pph.withholding",
    "nsfp_monitoring": "custom.report.nsfp.monitoring",
    "npwp_quality": "custom.report.npwp.quality",
    "dpp_nilai_lain": "custom.report.dpp.nilai.lain",
    "faktur_pengganti": "custom.report.faktur.pengganti",
    "ekualisasi_omzet": "custom.report.ekualisasi.omzet",
    "pph_equalisasi": "custom.report.pph.equalisasi",
    "coretax_submission": "custom.report.coretax.submission",
    "pajakku_usage": "custom.report.pajakku.usage",
    "pph_reconciliation": "custom.report.pph.reconciliation",
    "pph25": "custom.report.pph25",
    "tax_audit": "custom.report.tax.audit",
    "day_book": "custom.report.day.book",
    "cash_book": "custom.report.cash.book",
    "bank_book": "custom.report.bank.book",
    "journal_audit": "custom.report.journal.audit",
    "financial": "custom.report.financial.renderer",
}


class CustomReportDispatch(models.AbstractModel):
    _name = "report.custom_accounting_reports.report_dispatch"
    _description = "Custom Financial Report Dispatcher"

    def _get_report_values(self, docids, data=None):
        data = data or {}
        report_code = data.get("report_code") or "trial_balance"
        model_name = REPORT_MODEL_MAP.get(
            report_code,
            "custom.report.trial.balance",
        )
        report = self.env[model_name]
        ctx = report._compute(data.get("options") or data.get("filters"))
        return {
            "doc_ids": docids,
            "doc_model": data.get("doc_model", ""),
            "docs": (self.env[data["doc_model"]].browse(docids) if data.get("doc_model") else []),
            "report_code": report_code,
            **ctx,
        }

    # ------------------------------------------------------------------
    # On-screen table / export entry points (called by the OWL client)
    # ------------------------------------------------------------------
    def _report_model(self, report_code):
        return self.env[REPORT_MODEL_MAP.get(report_code, "custom.report.trial.balance")]

    @api.model
    def get_report_table(self, report_code, options=None, context_extra=None):
        """Single JSON entry point for the OWL table client action.

        Resolves ``report_code`` via :data:`REPORT_MODEL_MAP` and returns
        the report's :py:meth:`~custom.report.engine.get_report_table`
        payload (columns + display rows)."""
        return self._report_model(report_code).get_report_table(options, context_extra)

    @api.model
    def run_xlsx(self, report_code, options=None, context_extra=None, filename=None):
        """Build the Excel download for ``report_code`` — mirrors the
        wizard's ``action_export_xlsx`` so the client's Export button is
        wizard-independent."""
        report = self._report_model(report_code).with_context(**(context_extra or {}))
        filename = filename or ("%s.xlsx" % report_code)
        return report._xlsx_action(options, filename)

    @api.model
    def run_pdf(self, report_code, options=None):
        """Build the QWeb-PDF download for ``report_code`` — mirrors the
        wizard's ``action_print``."""
        data = {"report_code": report_code, "options": options or {}}
        return self.env.ref(
            "custom_accounting_reports.action_report_custom_financial"
        ).report_action([], data=data)
