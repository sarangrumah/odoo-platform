# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class VatReportWizard(models.TransientModel):
    _name = "custom.report.vat.wizard"
    _inherit = "custom.report.wizard.mixin"
    _description = "Report VAT Wizard"
    _report_code = "report_vat"

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
    vat_side = fields.Selection(
        [
            ("both", "VAT In + VAT Out"),
            ("masukan", "VAT In (PPN Masukan)"),
            ("keluaran", "VAT Out (PPN Keluaran)"),
        ],
        string="Sisi PPN",
        default="both",
        required=True,
        help="The reference pull carries both sides in one sheet; narrow it here when only one account is wanted.",
    )
    account_ids = fields.Many2many(
        "account.account",
        string="Akun (opsional)",
        help="Leave empty for every VAT account. A selection here narrows that set, it never adds a non-VAT account.",
    )
    partner_ids = fields.Many2many("res.partner", string="Lawan Transaksi")
    posted_only = fields.Boolean(default=True)

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "vat_side": self.vat_side,
            "account_ids": self.account_ids.ids,
            "partner_ids": self.partner_ids.ids,
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
        data = {
            "report_code": "report_vat",
            "doc_model": self._name,
            "options": self._options(),
        }
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)

    def action_export_xlsx(self):
        self.ensure_one()
        filename = "Report_VAT_%s_%s.xlsx" % (self.date_from, self.date_to)
        return self.env["custom.report.vat"]._xlsx_action(self._options(), filename)

    def action_view_source(self):
        """Open the underlying move lines, so a figure can be traced without
        leaving Odoo."""
        self.ensure_one()
        company_ids = self.company_ids.ids or self.env.companies.ids
        vat_ids = self.env["custom.report.vat"]._vat_account_ids(company_ids, self.vat_side)
        if self.account_ids:
            vat_ids = [aid for aid in vat_ids if aid in set(self.account_ids.ids)]
        domain = [
            ("company_id", "in", company_ids),
            ("account_id", "in", vat_ids),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.posted_only:
            domain.append(("parent_state", "=", "posted"))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        return {
            "type": "ir.actions.act_window",
            "name": "Jurnal PPN",
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": domain,
            "target": "current",
        }
