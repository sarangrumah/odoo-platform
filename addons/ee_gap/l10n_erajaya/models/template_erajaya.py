# -*- coding: utf-8 -*-
"""Erajaya chart template (code ``erajaya``).

Bulk data (accounts, account groups, tax groups, taxes) is shipped as CSV under
``data/template/*-erajaya.csv`` and loaded by the chart-template engine. This
module supplies the root metadata, company defaults, journals and fiscal
positions in Python.
"""
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template("erajaya")
    def _get_erajaya_template_data(self):
        return {
            "name": "Indonesia - Erajaya",
            "code_digits": "10",
            "country_id": "base.id",
            "use_storno_accounting": False,
            "property_account_receivable_id": "erajaya_1106000001",
            "property_account_payable_id": "erajaya_2103100001",
            "property_account_income_categ_id": "erajaya_5199000000",
            "property_account_expense_categ_id": "erajaya_6199000000",
        }

    @template("erajaya", "res.company")
    def _get_erajaya_res_company(self):
        return {
            self.env.company.id: {
                "anglo_saxon_accounting": True,
                "account_fiscal_country_id": "base.id",
                "bank_account_code_prefix": "1103",
                "cash_account_code_prefix": "1102",
                "transfer_account_code_prefix": "1101",
                "income_currency_exchange_account_id": "erajaya_7607000000",
                "expense_currency_exchange_account_id": "erajaya_7704000000",
                "account_sale_tax_id": "erajaya_tax_12_non_luxury_good_sale",
                "account_purchase_tax_id": "erajaya_tax_12_non_luxury_good_purchase",
            },
        }

    @template("erajaya", "account.journal")
    def _get_erajaya_account_journal(self):
        # Override the standard journals the base `account` template creates
        # (keys: sale/purchase/general/bank/cash) rather than adding new ones,
        # which would duplicate journals and collide on mail aliases.
        return {
            "sale": {"name": "Penjualan", "default_account_id": "erajaya_5199000000"},
            "purchase": {"name": "Pembelian", "default_account_id": "erajaya_6199000000"},
        }

    @template("erajaya", "account.fiscal.position")
    def _get_erajaya_account_fiscal_position(self):
        return {
            "erajaya_fpos_domestic": {
                "name": "Domestik",
                "auto_apply": True,
                "country_id": "base.id",
            },
            "erajaya_fpos_foreign": {
                "name": "Luar Negeri / Ekspor",
                "auto_apply": False,
            },
        }
