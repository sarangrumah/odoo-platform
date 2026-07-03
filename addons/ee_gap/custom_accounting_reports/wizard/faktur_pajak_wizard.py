# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class FakturPajakWizard(models.TransientModel):
    _name = "custom.report.faktur.pajak.wizard"
    _description = "Rekap Faktur Pajak Wizard"

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
    faktur_type = fields.Selection(
        [
            ("keluaran", "Faktur Keluaran (PPN Output)"),
            ("masukan", "Faktur Masukan (PPN Input)"),
        ],
        string="Jenis Faktur",
        default="keluaran",
        required=True,
    )
    partner_ids = fields.Many2many("res.partner", string="Lawan Transaksi")
    posted_only = fields.Boolean(default=True)

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "faktur_type": self.faktur_type,
            "partner_ids": self.partner_ids.ids,
            "posted_only": self.posted_only,
        }

    def action_print(self):
        self.ensure_one()
        data = {
            "report_code": "faktur_pajak",
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
        filename = "Rekap_Faktur_%s_%s_%s.xlsx" % (self.faktur_type, self.date_from, self.date_to)
        return self.env["custom.report.faktur.pajak"]._xlsx_action(options, filename)
