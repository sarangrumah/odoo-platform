# -*- coding: utf-8 -*-
"""Profit & Loss: Revenue / COGS / Op Ex / Other / Tax with YTD."""
from datetime import date as date_cls

from odoo import models


REVENUE_TYPES = ("income", "income_other")
COGS_TYPES = ("expense_direct_cost",)
EXPENSE_TYPES = ("expense",)
OTHER_TYPES = ("expense_depreciation",)


class CustomReportProfitLoss(models.AbstractModel):
    _name = "custom.report.profit.loss"
    _inherit = "custom.report.engine"
    _description = "Custom Profit & Loss"

    _report_code = "profit_loss"
    _report_title = "Profit & Loss"

    def _section(self, label, type_codes, balances, flip_sign):
        accounts = []
        subtotal = 0.0
        for row in balances.values():
            if row["account_type"] not in type_codes:
                continue
            signed = -row["balance"] if flip_sign else row["balance"]
            accounts.append(dict(row, signed_balance=signed))
            subtotal += signed
        accounts.sort(key=lambda r: r["account_code"] or "")
        return {
            "type": "section",
            "label": label,
            "accounts": accounts,
            "subtotal": subtotal,
        }

    def _ytd_period(self, filters):
        """Year-to-Date period: from 1-Jan of date_to's year until
        date_to. Returns ``{account_id: balance}``.
        """
        ytd_start = date_cls(filters["date_to"].year, 1, 1)
        ytd_filters = dict(filters, date_from=ytd_start)
        return self._get_account_balances(ytd_filters)

    def _build_lines(self, filters):
        balances = self._get_account_balances(filters)
        ytd_balances = self._ytd_period(filters)

        lines = []
        revenue = self._section(
            "Revenue", REVENUE_TYPES, balances, flip_sign=True,
        )
        cogs = self._section(
            "Cost of Goods Sold", COGS_TYPES, balances, flip_sign=False,
        )
        op_ex = self._section(
            "Operating Expenses", EXPENSE_TYPES, balances, flip_sign=False,
        )
        other = self._section(
            "Other Expenses", OTHER_TYPES, balances, flip_sign=False,
        )

        gross_profit = revenue["subtotal"] - cogs["subtotal"]
        operating_profit = gross_profit - op_ex["subtotal"]
        net_profit = operating_profit - other["subtotal"]

        # YTD signed totals
        def ytd_sum(type_codes, flip):
            tot = 0.0
            for row in ytd_balances.values():
                if row["account_type"] in type_codes:
                    tot += -row["balance"] if flip else row["balance"]
            return tot

        ytd_revenue = ytd_sum(REVENUE_TYPES, True)
        ytd_cogs = ytd_sum(COGS_TYPES, False)
        ytd_opex = ytd_sum(EXPENSE_TYPES, False)
        ytd_other = ytd_sum(OTHER_TYPES, False)
        ytd_net = ytd_revenue - ytd_cogs - ytd_opex - ytd_other

        lines.append(revenue)
        lines.append({
            "type": "total", "label": "Total Revenue",
            "signed_balance": revenue["subtotal"],
            "ytd": ytd_revenue,
        })
        lines.append(cogs)
        lines.append({
            "type": "total", "label": "Total COGS",
            "signed_balance": cogs["subtotal"],
            "ytd": ytd_cogs,
        })
        lines.append({
            "type": "total", "label": "Gross Profit",
            "signed_balance": gross_profit,
            "ytd": ytd_revenue - ytd_cogs,
        })
        lines.append(op_ex)
        lines.append({
            "type": "total", "label": "Operating Profit",
            "signed_balance": operating_profit,
            "ytd": ytd_revenue - ytd_cogs - ytd_opex,
        })
        lines.append(other)
        lines.append({
            "type": "grand_total", "label": "Net Profit / (Loss)",
            "signed_balance": net_profit,
            "ytd": ytd_net,
        })
        return lines
