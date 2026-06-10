# -*- coding: utf-8 -*-
"""Balance Sheet: Asset / Liability / Equity grouped by account_type.

Uses Odoo 19 native ``account.account.account_type`` selection. PSAK
mapping happens implicitly because Indonesian CoA modules emit the
right selection values for each Indonesian account.
"""

from datetime import date as date_cls

from odoo import models


ASSET_TYPES = (
    "asset_receivable",
    "asset_cash",
    "asset_current",
    "asset_non_current",
    "asset_prepayments",
    "asset_fixed",
)
LIABILITY_TYPES = (
    "liability_payable",
    "liability_credit_card",
    "liability_current",
    "liability_non_current",
)
EQUITY_TYPES = (
    "equity",
    "equity_unaffected",
)


class CustomReportBalanceSheet(models.AbstractModel):
    _name = "custom.report.balance.sheet"
    _inherit = "custom.report.engine"
    _description = "Custom Balance Sheet"

    _report_code = "balance_sheet"
    _report_title = "Balance Sheet"

    def _xlsx_columns(self):
        return [
            {"header": "Code", "field": "account_code", "kind": "text", "width": 16},
            {"header": "Account", "field": "account_name", "kind": "text", "width": 46},
            {"header": "Balance", "field": "signed_balance", "kind": "number", "width": 20},
        ]

    def _xlsx_body(self, sheet, ctx, columns, fmts, start_row):
        lines = ctx.get("lines", [])
        has_comp = any(line.get("comparison") is not None for line in lines)
        last_col = 3 if has_comp else 2
        row = start_row

        sheet.write(row, 0, "Code", fmts["header"])
        sheet.write(row, 1, "Account", fmts["header"])
        sheet.write(row, 2, "Balance", fmts["header"])
        if has_comp:
            sheet.set_column(3, 3, 20)
            sheet.write(row, 3, "Prior Period", fmts["header"])
        sheet.freeze_panes(row + 1, 0)
        row += 1

        for line in lines:
            ltype = line.get("type")
            if ltype == "header":
                sheet.merge_range(row, 0, row, last_col, line.get("label") or "", fmts["section"])
                row += 1
            elif ltype == "section":
                for acc in line.get("accounts", []):
                    sheet.write(row, 0, acc.get("account_code") or "", fmts["text"])
                    sheet.write(row, 1, acc.get("account_name") or "", fmts["text"])
                    sheet.write_number(row, 2, float(acc.get("signed_balance") or 0.0), fmts["num"])
                    if has_comp:
                        sheet.write(row, 3, "", fmts["text"])
                    row += 1
            elif ltype in ("total", "grand_total", "check"):
                sheet.merge_range(row, 0, row, 1, line.get("label") or "", fmts["total_text"])
                sheet.write_number(row, 2, float(line.get("signed_balance") or 0.0), fmts["total_num"])
                if has_comp:
                    comp = line.get("comparison")
                    if comp is None:
                        sheet.write(row, 3, "", fmts["total_text"])
                    else:
                        sheet.write_number(row, 3, float(comp), fmts["total_num"])
                row += 1
        return row

    def _default_filters(self):
        filters = super()._default_filters()
        # Balance Sheet is cumulative — pin date_from far back.
        filters["date_from"] = date_cls(1970, 1, 1)
        return filters

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
        return accounts, subtotal

    def _build_lines(self, filters):
        # Always cumulative; ignore caller's date_from.
        filters = dict(filters)
        filters["date_from"] = date_cls(1970, 1, 1)

        balances = self._get_account_balances(filters)

        # Comparison period (prior year same date_to) — optional.
        comparison = {}
        if filters.get("comparison_date_to"):
            comp_filters = dict(
                filters,
                date_from=date_cls(1970, 1, 1),
                date_to=filters["comparison_date_to"],
            )
            comparison = self._get_account_balances(comp_filters)

        def comp_section(type_codes, flip_sign):
            if not comparison:
                return None
            subtotal = 0.0
            for row in comparison.values():
                if row["account_type"] not in type_codes:
                    continue
                signed = -row["balance"] if flip_sign else row["balance"]
                subtotal += signed
            return subtotal

        lines = []
        # ASSETS
        lines.append({"type": "header", "label": "ASSETS"})
        asset_accounts, total_assets = self._section(
            "ASSETS",
            ASSET_TYPES,
            balances,
            flip_sign=False,
        )
        lines.append(
            {
                "type": "section",
                "label": "Assets",
                "accounts": asset_accounts,
                "subtotal": total_assets,
                "comparison": comp_section(ASSET_TYPES, False),
            }
        )
        lines.append(
            {
                "type": "total",
                "label": "Total Assets",
                "signed_balance": total_assets,
                "comparison": comp_section(ASSET_TYPES, False),
            }
        )

        # LIABILITIES
        lines.append({"type": "header", "label": "LIABILITIES"})
        liab_accounts, total_liab = self._section(
            "LIABILITIES",
            LIABILITY_TYPES,
            balances,
            flip_sign=True,
        )
        lines.append(
            {
                "type": "section",
                "label": "Liabilities",
                "accounts": liab_accounts,
                "subtotal": total_liab,
                "comparison": comp_section(LIABILITY_TYPES, True),
            }
        )
        lines.append(
            {
                "type": "total",
                "label": "Total Liabilities",
                "signed_balance": total_liab,
                "comparison": comp_section(LIABILITY_TYPES, True),
            }
        )

        # EQUITY
        lines.append({"type": "header", "label": "EQUITY"})
        eq_accounts, total_eq = self._section(
            "EQUITY",
            EQUITY_TYPES,
            balances,
            flip_sign=True,
        )
        lines.append(
            {
                "type": "section",
                "label": "Equity",
                "accounts": eq_accounts,
                "subtotal": total_eq,
                "comparison": comp_section(EQUITY_TYPES, True),
            }
        )
        lines.append(
            {
                "type": "total",
                "label": "Total Equity",
                "signed_balance": total_eq,
                "comparison": comp_section(EQUITY_TYPES, True),
            }
        )

        lines.append(
            {
                "type": "grand_total",
                "label": "Total Liabilities + Equity",
                "signed_balance": total_liab + total_eq,
            }
        )
        imbalance = total_assets - (total_liab + total_eq)
        lines.append(
            {
                "type": "check",
                "label": "Imbalance (should be zero)",
                "signed_balance": imbalance,
            }
        )
        return lines
