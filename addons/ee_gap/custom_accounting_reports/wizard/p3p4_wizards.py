# -*- coding: utf-8 -*-
"""Wizards for the P3/P4 tax-team reports.

They all share the same parameter set (masa + company + posted_only), so the
common fields and the print / xlsx actions live on an AbstractModel mixin;
each concrete wizard just declares which report model/code it drives.
"""

from datetime import date

from odoo import fields, models


class TaxReportWizardMixin(models.AbstractModel):
    _name = "custom.report.tax.wizard.mixin"
    _description = "Common tax report wizard (masa + company)"

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
    company_ids = fields.Many2many("res.company", default=lambda self: self.env.companies)
    posted_only = fields.Boolean(default=True)

    # Subclasses set these three.
    _report_code = None
    _report_model = None
    _filename_prefix = "Report"

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "posted_only": self.posted_only,
        }

    def _options(self):
        return {
            **self._build_filters(),
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
        }

    def action_print(self):
        self.ensure_one()
        data = {"report_code": self._report_code, "doc_model": self._name, "options": self._options()}
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)

    def action_export_xlsx(self):
        self.ensure_one()
        filename = "%s_%s_%s.xlsx" % (self._filename_prefix, self.date_from, self.date_to)
        return self.env[self._report_model]._xlsx_action(self._options(), filename)


class DppNilaiLainWizard(models.TransientModel):
    _name = "custom.report.dpp.nilai.lain.wizard"
    _inherit = "custom.report.tax.wizard.mixin"
    _description = "DPP Nilai Lain Wizard"
    _report_code = "dpp_nilai_lain"
    _report_model = "custom.report.dpp.nilai.lain"
    _filename_prefix = "DPP_Nilai_Lain"


class FakturPenggantiWizard(models.TransientModel):
    _name = "custom.report.faktur.pengganti.wizard"
    _inherit = "custom.report.tax.wizard.mixin"
    _description = "Faktur Pengganti Wizard"
    _report_code = "faktur_pengganti"
    _report_model = "custom.report.faktur.pengganti"
    _filename_prefix = "Faktur_Pengganti"


class EkualisasiOmzetWizard(models.TransientModel):
    _name = "custom.report.ekualisasi.omzet.wizard"
    _inherit = "custom.report.tax.wizard.mixin"
    _description = "Ekualisasi Omzet Wizard"
    _report_code = "ekualisasi_omzet"
    _report_model = "custom.report.ekualisasi.omzet"
    _filename_prefix = "Ekualisasi_Omzet"


class PphEqualisasiWizard(models.TransientModel):
    _name = "custom.report.pph.equalisasi.wizard"
    _inherit = "custom.report.tax.wizard.mixin"
    _description = "Ekualisasi PPh Wizard"
    _report_code = "pph_equalisasi"
    _report_model = "custom.report.pph.equalisasi"
    _filename_prefix = "Ekualisasi_PPh"


class CoretaxSubmissionWizard(models.TransientModel):
    _name = "custom.report.coretax.submission.wizard"
    _inherit = "custom.report.tax.wizard.mixin"
    _description = "Coretax Submission Monitoring Wizard"
    _report_code = "coretax_submission"
    _report_model = "custom.report.coretax.submission"
    _filename_prefix = "Monitoring_Submission_Coretax"


class PajakkuUsageWizard(models.TransientModel):
    _name = "custom.report.pajakku.usage.wizard"
    _inherit = "custom.report.tax.wizard.mixin"
    _description = "Pajakku Usage Wizard"
    _report_code = "pajakku_usage"
    _report_model = "custom.report.pajakku.usage"
    _filename_prefix = "Usage_Pajakku"
