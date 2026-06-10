# -*- coding: utf-8 -*-
"""General Ledger: per-account list of moves for a period.

For every account that posted at least one line in the date range we
list opening balance, every posted move.line, running balance, total
debit/credit, and closing balance. Grouped output keyed by account
code in ascending order.
"""

from datetime import date as date_cls, timedelta

from odoo import models


class CustomReportGeneralLedger(models.AbstractModel):
    _name = "custom.report.general.ledger"
    _inherit = "custom.report.engine"
    _description = "Custom General Ledger"

    _report_code = "general_ledger"
    _report_title = "General Ledger"

    def _xlsx_columns(self):
        return [
            {"header": "Date", "field": "date", "kind": "text", "width": 12},
            {"header": "Entry", "field": "move_name", "kind": "text", "width": 18},
            {"header": "Partner", "field": "partner", "kind": "text", "width": 28},
            {"header": "Label", "field": "label", "kind": "text", "width": 34},
            {"header": "Debit", "field": "debit", "kind": "number", "width": 16},
            {"header": "Credit", "field": "credit", "kind": "number", "width": 16},
            {"header": "Balance", "field": "balance", "kind": "number", "width": 16},
        ]

    def _xlsx_body(self, sheet, ctx, columns, fmts, start_row):
        ncol = len(columns)
        row = start_row
        for col_idx, col in enumerate(columns):
            sheet.write(row, col_idx, col["header"], fmts["header"])
        sheet.freeze_panes(row + 1, 0)
        row += 1

        for line in ctx.get("lines", []):
            ltype = line.get("type")
            if ltype == "account":
                heading = "[%s] %s" % (
                    line.get("account_code") or "",
                    line.get("account_name") or "",
                )
                sheet.merge_range(row, 0, row, ncol - 2, heading, fmts["group_text"])
                sheet.write_number(
                    row, ncol - 1, float(line.get("opening") or 0.0), fmts["group_num"]
                )
                row += 1
                for ml in line.get("lines", []):
                    sheet.write(row, 0, self._format_date_id(ml.get("date")), fmts["text"])
                    sheet.write(row, 1, ml.get("move_name") or "", fmts["text"])
                    sheet.write(row, 2, ml.get("partner") or "", fmts["text"])
                    sheet.write(row, 3, ml.get("label") or "", fmts["text"])
                    sheet.write_number(row, 4, float(ml.get("debit") or 0.0), fmts["num"])
                    sheet.write_number(row, 5, float(ml.get("credit") or 0.0), fmts["num"])
                    sheet.write_number(row, 6, float(ml.get("balance") or 0.0), fmts["num"])
                    row += 1
                sheet.merge_range(
                    row, 0, row, 3,
                    "Total %s" % (line.get("account_code") or ""),
                    fmts["total_text"],
                )
                sheet.write_number(row, 4, float(line.get("total_debit") or 0.0), fmts["total_num"])
                sheet.write_number(row, 5, float(line.get("total_credit") or 0.0), fmts["total_num"])
                sheet.write_number(row, 6, float(line.get("closing") or 0.0), fmts["total_num"])
                row += 1
            elif ltype == "grand_total":
                sheet.merge_range(
                    row, 0, row, 3, line.get("label") or "Grand Total", fmts["total_text"]
                )
                sheet.write_number(row, 4, float(line.get("total_debit") or 0.0), fmts["total_num"])
                sheet.write_number(row, 5, float(line.get("total_credit") or 0.0), fmts["total_num"])
                sheet.write_number(row, 6, float(line.get("closing") or 0.0), fmts["total_num"])
                row += 1
        return row

    def _opening_balance_per_account(self, filters):
        """Cumulative balance per account *before* ``date_from``."""
        opening_filters = dict(
            filters,
            date_from=date_cls(1970, 1, 1),
            date_to=filters["date_from"] - timedelta(days=1),
        )
        per_account = self._get_account_balances(opening_filters)
        return {aid: row["balance"] for aid, row in per_account.items()}

    def _build_lines(self, filters):
        opening_by_account = self._opening_balance_per_account(filters)

        # Use the engine's SQL helper for the period lines.
        query, params = self._get_move_lines_query(filters)
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        # Resolve names in a single batched read.
        AccountAccount = self.env["account.account"]
        AccountMove = self.env["account.move"]
        ResPartner = self.env["res.partner"]
        account_ids = sorted({r["account_id"] for r in rows} | set(opening_by_account))
        move_ids = sorted({r["move_id"] for r in rows if r["move_id"]})
        partner_ids = sorted({r["partner_id"] for r in rows if r["partner_id"]})
        accounts = {a.id: a for a in AccountAccount.browse(account_ids)}
        moves = {m.id: m for m in AccountMove.browse(move_ids)}
        partners = {p.id: p for p in ResPartner.browse(partner_ids)}

        by_account = {}
        for row in rows:
            aid = row["account_id"]
            acc = accounts.get(aid)
            if not acc:
                continue
            bucket = by_account.setdefault(
                aid,
                {
                    "type": "account",
                    "account_id": aid,
                    "account_code": acc.code,
                    "account_name": acc.name,
                    "account_type": acc.account_type,
                    "opening": opening_by_account.get(aid, 0.0),
                    "lines": [],
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                },
            )
            move = moves.get(row["move_id"])
            partner = partners.get(row["partner_id"])
            bucket["lines"].append(
                {
                    "date": row["date"],
                    "ref": row["ref"] or (move.name if move else ""),
                    "move_name": (move.name if move else "") or "/",
                    "partner": partner.display_name if partner else "",
                    "label": row["name"] or "",
                    "debit": row["debit"] or 0.0,
                    "credit": row["credit"] or 0.0,
                }
            )
            bucket["total_debit"] += row["debit"] or 0.0
            bucket["total_credit"] += row["credit"] or 0.0

        # Accounts with opening but no movement still appear.
        for aid, opening in opening_by_account.items():
            if aid in by_account or not opening:
                continue
            acc = accounts.get(aid)
            if not acc:
                continue
            by_account[aid] = {
                "type": "account",
                "account_id": aid,
                "account_code": acc.code,
                "account_name": acc.name,
                "account_type": acc.account_type,
                "opening": opening,
                "lines": [],
                "total_debit": 0.0,
                "total_credit": 0.0,
            }

        result = {"accounts": [], "grand_total_debit": 0.0, "grand_total_credit": 0.0}
        flat_lines = []
        for aid in sorted(
            by_account,
            key=lambda a: by_account[a]["account_code"] or "",
        ):
            bucket = by_account[aid]
            running = bucket["opening"]
            for ln in bucket["lines"]:
                running += ln["debit"] - ln["credit"]
                ln["balance"] = running
            bucket["closing"] = running
            result["accounts"].append(bucket)
            result["grand_total_debit"] += bucket["total_debit"]
            result["grand_total_credit"] += bucket["total_credit"]
            flat_lines.append(bucket)

        flat_lines.append(
            {
                "type": "grand_total",
                "label": "Grand Total",
                "total_debit": result["grand_total_debit"],
                "total_credit": result["grand_total_credit"],
                "closing": (result["grand_total_debit"] - result["grand_total_credit"]),
            }
        )
        return flat_lines
