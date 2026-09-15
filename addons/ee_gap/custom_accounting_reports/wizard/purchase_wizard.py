# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, fields, models


class PurchaseWizard(models.TransientModel):
    _name = "custom.report.purchase.wizard"
    _inherit = "custom.report.wizard.mixin"
    _description = "Purchase Report Wizard"
    _report_code = "purchase"

    date_from = fields.Date(
        required=True,
        default=lambda self: date.today().replace(month=1, day=1),
    )
    date_to = fields.Date(
        required=True,
        default=lambda self: date.today(),
    )
    company_ids = fields.Many2many(
        "res.company",
        default=lambda self: self.env.companies,
    )
    partner_ids = fields.Many2many("res.partner", string="Vendors")
    group_by = fields.Selection(
        [
            ("none", "No grouping"),
            ("vendor", "By Vendor"),
            ("product", "By Product"),
            ("month", "By Month"),
            ("purchase_type", "By Trade / Non-Trade"),
        ],
        string="Group By",
        default="none",
        required=True,
    )
    posted_only = fields.Boolean(default=True)

    # Levi's sheet #25/#30: the register is pulled per receiving period, so the
    # goods-receipt date drives the window by default. Lines with no purchase
    # order behind them (services, non-trade) fall back to their bill date.
    date_basis = fields.Selection(
        [
            ("gr", "Tanggal GR (Goods Receipt)"),
            ("bill", "Tanggal Bill"),
        ],
        string="Periode Berdasarkan",
        default="gr",
        required=True,
        help="Tanggal GR: baris ditarik menurut penerimaan barang pertama dari "
        "baris PO-nya. Baris tanpa PO (jasa, non-trade) tetap memakai tanggal bill.",
    )
    show_gr = fields.Boolean(compute="_compute_show_gr")

    @api.depends_context("uid")
    def _compute_show_gr(self):
        available = self.env["custom.report.purchase"]._gr_available()
        for wizard in self:
            wizard.show_gr = available

    # Trade / Non-Trade stream (Levi's feature #9). The underlying
    # ``account.move.l10n_purchase_type`` comes from the tenant module
    # custom_levis_localization; on databases without it the filter is hidden
    # and the report keeps its previous shape.
    purchase_type = fields.Selection(
        [
            ("all", "All"),
            ("trade", "Trade"),
            ("non_trade", "Non-Trade"),
            ("unclassified", "Unclassified"),
        ],
        string="Purchase Type",
        default="all",
        required=True,
        help="Restrict the register to one purchase stream. Bills without a "
        "stream fall back to the reversed entry and the source purchase order "
        "before being reported as Unclassified.",
    )
    show_purchase_type = fields.Boolean(compute="_compute_show_purchase_type")

    @api.depends_context("uid")
    def _compute_show_purchase_type(self):
        available = "l10n_purchase_type" in self.env["account.move"]._fields
        for wizard in self:
            wizard.show_purchase_type = available

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "partner_ids": self.partner_ids.ids,
            "group_by": self.group_by,
            "posted_only": self.posted_only,
            "purchase_type": self.purchase_type,
            "date_basis": self.date_basis if self.show_gr else "bill",
        }

    def action_print(self):
        self.ensure_one()
        data = {
            "report_code": "purchase",
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
        suffix = {"trade": "_Trade", "non_trade": "_NonTrade", "unclassified": "_Unclassified"}.get(
            self.purchase_type, ""
        )
        filename = "Purchase_Report%s_%s_%s.xlsx" % (suffix, self.date_from, self.date_to)
        return self.env["custom.report.purchase"]._xlsx_action(options, filename)
