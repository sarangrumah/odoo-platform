# -*- coding: utf-8 -*-
"""Aged Receivable: open AR per partner bucketed by overdue days."""

from odoo import models


BUCKETS = (
    ("not_due", "Not Due", None, 0),
    ("d_0_30", "0-30", 0, 30),
    ("d_31_60", "31-60", 31, 60),
    ("d_61_90", "61-90", 61, 90),
    ("d_91_180", "91-180", 91, 180),
    ("d_181_365", "181-365", 181, 365),
    ("d_over_365", "365+", 366, None),
)


class CustomReportAgedReceivable(models.AbstractModel):
    _name = "custom.report.aged.receivable"
    _inherit = "custom.report.engine"
    _description = "Custom Aged Receivable"

    _report_code = "aged_receivable"
    _report_title = "Aged Receivable"

    def _xlsx_columns(self):
        cols = [{"header": "Partner", "field": "partner_name", "kind": "text", "width": 36}]
        for code, label, _lower, _upper in BUCKETS:
            cols.append({"header": label, "field": code, "kind": "number", "width": 13})
        cols.append({"header": "Total", "field": "total", "kind": "number", "width": 16})
        return cols

    def _xlsx_body(self, sheet, ctx, columns, fmts, start_row):
        data = ctx.get("lines") or {}
        rows = data.get("rows", [])
        buckets = data.get("buckets", [])
        grand = data.get("grand_total", {})
        ncol = len(buckets) + 2  # partner + buckets + total
        row = start_row

        for col_idx, col in enumerate(columns):
            sheet.write(row, col_idx, col["header"], fmts["header"])
        sheet.freeze_panes(row + 1, 1)
        row += 1

        for r in rows:
            sheet.write(row, 0, r.get("partner_name") or "", fmts["text"])
            for i, b in enumerate(buckets):
                sheet.write_number(row, 1 + i, float(r.get(b["code"]) or 0.0), fmts["num"])
            sheet.write_number(row, ncol - 1, float(r.get("total") or 0.0), fmts["num"])
            row += 1

        sheet.write(row, 0, "Grand Total", fmts["total_text"])
        for i, b in enumerate(buckets):
            sheet.write_number(row, 1 + i, float(grand.get(b["code"]) or 0.0), fmts["total_num"])
        sheet.write_number(row, ncol - 1, float(grand.get("total") or 0.0), fmts["total_num"])
        return row + 1

    def _account_type(self):
        return "asset_receivable"

    def _classify_bucket(self, due_date, as_of):
        if not due_date or due_date >= as_of:
            return "not_due"
        days = (as_of - due_date).days
        if days <= 0:
            return "not_due"
        for code, _label, lower, upper in BUCKETS:
            if lower is None:
                continue
            if upper is None:
                if days >= lower:
                    return code
            elif lower <= days <= upper:
                return code
        return "d_over_365"

    def _build_lines(self, filters):
        as_of = filters["date_to"]
        AccountMoveLine = self.env["account.move.line"]
        domain = [
            ("company_id", "in", filters["company_ids"]),
            ("account_id.account_type", "=", self._account_type()),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("date", "<=", as_of),
        ]
        if filters.get("partner_ids"):
            domain.append(("partner_id", "in", filters["partner_ids"]))
        ml = AccountMoveLine.search(domain)

        per_partner = {}
        for line in ml:
            residual = line.amount_residual
            if not residual:
                continue
            pid = line.partner_id.id or 0
            row = per_partner.setdefault(
                pid,
                {
                    "partner_id": pid,
                    "partner_name": (line.partner_id.display_name or "No Partner"),
                    "total": 0.0,
                    **{code: 0.0 for code, _, _, _ in BUCKETS},
                },
            )
            bucket = self._classify_bucket(
                line.date_maturity or line.date,
                as_of,
            )
            row[bucket] += residual
            row["total"] += residual

        partners = sorted(
            per_partner.values(),
            key=lambda r: (r["partner_name"] or "").lower(),
        )
        grand_total = {c: 0.0 for c, _, _, _ in BUCKETS}
        grand_total["total"] = 0.0
        for row in partners:
            for code, _, _, _ in BUCKETS:
                grand_total[code] += row[code]
            grand_total["total"] += row["total"]

        return {
            "type": "aging",
            "buckets": [{"code": c, "label": label} for c, label, _, _ in BUCKETS],
            "rows": partners,
            "grand_total": grand_total,
        }
