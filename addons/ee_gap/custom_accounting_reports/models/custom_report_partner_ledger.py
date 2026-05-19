# -*- coding: utf-8 -*-
"""Partner Ledger: GL grouped by partner first, then chronological."""
from datetime import date as date_cls, timedelta

from odoo import models


class CustomReportPartnerLedger(models.AbstractModel):
    _name = "custom.report.partner.ledger"
    _inherit = "custom.report.engine"
    _description = "Custom Partner Ledger"

    _report_code = "partner_ledger"
    _report_title = "Partner Ledger"

    def _account_types(self, kind):
        if kind == "receivable":
            return ("asset_receivable",)
        if kind == "payable":
            return ("liability_payable",)
        return ("asset_receivable", "liability_payable")

    def _build_lines(self, filters):
        kind = filters.get("partner_kind") or "both"
        types = list(self._account_types(kind))

        # Opening per partner
        opening_filters = dict(
            filters,
            date_from=date_cls(1970, 1, 1),
            date_to=filters["date_from"] - timedelta(days=1),
        )
        AML = self.env["account.move.line"]
        opening_rows = AML._read_group(
            domain=self._base_move_line_domain(opening_filters) + [
                ("account_id.account_type", "in", types),
            ],
            groupby=["partner_id"],
            aggregates=["debit:sum", "credit:sum"],
        )
        opening_by_partner = {
            (p.id if p else 0): (d or 0.0) - (c or 0.0)
            for p, d, c in opening_rows
        }

        period_domain = self._base_move_line_domain(filters) + [
            ("account_id.account_type", "in", types),
        ]
        if filters.get("partner_ids"):
            period_domain.append(
                ("partner_id", "in", filters["partner_ids"])
            )
        period_lines = AML.search(
            period_domain, order="partner_id, date, id",
        )

        partners = {}
        for ml in period_lines:
            pid = ml.partner_id.id or 0
            entry = partners.setdefault(pid, {
                "type": "partner",
                "partner_id": pid,
                "partner_name": (
                    ml.partner_id.display_name or "— No Partner —"
                ),
                "opening": opening_by_partner.get(pid, 0.0),
                "lines": [],
                "total_debit": 0.0,
                "total_credit": 0.0,
            })
            entry["total_debit"] += ml.debit
            entry["total_credit"] += ml.credit
            running = (
                entry["opening"]
                + entry["total_debit"] - entry["total_credit"]
            )
            entry["lines"].append({
                "date": ml.date,
                "move_name": ml.move_id.name or ml.move_id.display_name,
                "account_code": ml.account_id.code,
                "label": ml.name or "",
                "debit": ml.debit,
                "credit": ml.credit,
                "running_balance": running,
            })

        # Include partners with only opening movements.
        for pid, opening in opening_by_partner.items():
            if pid in partners or not opening:
                continue
            partner = (
                self.env["res.partner"].browse(pid) if pid else None
            )
            partners[pid] = {
                "type": "partner",
                "partner_id": pid,
                "partner_name": (
                    partner.display_name if partner
                    else "— No Partner —"
                ),
                "opening": opening,
                "lines": [],
                "total_debit": 0.0,
                "total_credit": 0.0,
            }

        lines = []
        total_op = total_d = total_c = total_cl = 0.0
        for entry in sorted(
            partners.values(), key=lambda r: r["partner_name"],
        ):
            closing = (
                entry["opening"]
                + entry["total_debit"] - entry["total_credit"]
            )
            entry["closing"] = closing
            lines.append(entry)
            total_op += entry["opening"]
            total_d += entry["total_debit"]
            total_c += entry["total_credit"]
            total_cl += closing

        lines.append({
            "type": "grand_total",
            "label": "Grand Total",
            "opening": total_op,
            "total_debit": total_d,
            "total_credit": total_c,
            "closing": total_cl,
        })
        return lines
