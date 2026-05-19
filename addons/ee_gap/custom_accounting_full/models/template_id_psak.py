# -*- coding: utf-8 -*-
"""Indonesian PSAK-aligned chart template (Odoo 19 @template pattern).

Migrated from Odoo 16/17 XML-based ``account.chart.template`` records.
The 5-digit code structure is preserved per PSAK convention:

  1xxxx  Aset (Assets)
  2xxxx  Kewajiban (Liabilities)
  3xxxx  Ekuitas (Equity)
  4xxxx  Pendapatan (Revenue)
  5xxxx  Harga Pokok Penjualan (COGS)
  6xxxx  Beban Operasi (Operating Expenses)
  7xxxx  Pendapatan / Beban Lain (Other Income/Expense)
  8xxxx  Pajak Penghasilan (Income Tax)
"""
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template("id_psak")
    def _get_id_psak_template_data(self):
        return {
            "name": "Indonesia (PSAK) — Custom Platform",
            "code_digits": "5",
            "use_anglo_saxon": False,
            "property_account_receivable_id": "account_id_psak_11100",
            "property_account_payable_id": "account_id_psak_21100",
            "property_account_expense_categ_id": "account_id_psak_52000",
            "property_account_income_categ_id": "account_id_psak_41000",
            "country_id": "base.id",
        }

    @template("id_psak", "res.company")
    def _get_id_psak_res_company(self):
        return {
            self.env.company.id: {
                "anglo_saxon_accounting": False,
                "account_fiscal_country_id": "base.id",
                "bank_account_code_prefix": "11020",
                "cash_account_code_prefix": "11010",
                "transfer_account_code_prefix": "11030",
                "account_default_pos_receivable_account_id": "account_id_psak_11200",
                "income_currency_exchange_account_id": "account_id_psak_71100",
                "expense_currency_exchange_account_id": "account_id_psak_72100",
                "account_journal_suspense_account_id": "account_id_psak_11200",
                "default_cash_difference_income_account_id": "account_id_psak_71000",
                "default_cash_difference_expense_account_id": "account_id_psak_68000",
                "account_sale_tax_id": "account_id_psak_tax_ppn_keluaran_11",
                "account_purchase_tax_id": "account_id_psak_tax_ppn_masukan_11",
            },
        }
