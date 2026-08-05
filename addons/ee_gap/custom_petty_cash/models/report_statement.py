# -*- coding: utf-8 -*-
"""Kartu Uang Muka — per-employee cash advance statement.

Outstanding answers *how much* and Aging answers *how old*; neither shows the
movement that produced the balance. This report is the ledger card: every
disbursement, realization, bill payment, return, top-up and exchange
difference for an employee, in date order, with a running balance.

It inherits ``custom.report.partner.card.base`` rather than the plain report
engine because that base already knows the nested per-entity block shape — it
supplies ``_flatten_for_screen`` (without which the on-screen table renders one
blank row per entity, the bug that once made Kartu Utang look empty) and an
``_xlsx_body`` that writes a heading, an opening row and a Total per entity.
The base keys those off the literal names ``partner_name`` and
``running_balance``, so the blocks below use them for the *employee* — only
``_xlsx_columns`` and ``_build_lines`` are overridden.
"""

from __future__ import annotations

from datetime import date as date_cls, timedelta

from odoo import _, models


class PettyCashReportStatement(models.AbstractModel):
    _name = "petty.cash.report.statement"
    _inherit = "custom.report.partner.card.base"
    _description = "Kartu Uang Muka (Cash Advance Statement)"

    _report_code = "petty_cash_statement"
    _report_title = "Kartu Uang Muka"

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------
    def _xlsx_columns(self):
        return [
            {"header": "Date", "field": "date", "kind": "date", "width": 12},
            {"header": "Document", "field": "doc_no", "kind": "text", "width": 18},
            {"header": "Movement", "field": "movement", "kind": "text", "width": 22},
            {"header": "Request", "field": "request_ref", "kind": "text", "width": 16},
            {"header": "Type", "field": "type_name", "kind": "text", "width": 14},
            {"header": "Description", "field": "label", "kind": "text", "width": 34},
            {"header": "Disbursement", "field": "debit", "kind": "number", "width": 16},
            {"header": "Realization / Return", "field": "credit", "kind": "number", "width": 18},
            {"header": "Balance", "field": "running_balance", "kind": "number", "width": 16},
            {"header": "Amount (Doc Curr.)", "field": "amount_currency", "kind": "number", "width": 16},
            {"header": "Doc Curr.", "field": "currency", "kind": "text", "width": 9},
            {"header": "Due", "field": "deadline", "kind": "date", "width": 12},
            {"header": "Status", "field": "status", "kind": "text", "width": 12},
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pc_advance_accounts(self, company_ids):
        """Every account that can carry an advance across ``company_ids``.

        Both layers of the resolution chain contribute: the per-type accounts
        and the company-wide fallback.
        """
        companies = self.env["res.company"].browse(list(company_ids))
        types = self.env["petty.cash.type"].sudo().search([("company_id", "in", list(company_ids))])
        return types.advance_account_id | companies.mapped("petty_cash_advance_account_id")

    def _pc_statement_domain(self, filters, accounts):
        domain = [
            ("account_id", "in", accounts.ids),
            ("move_id.petty_cash_request_id", "!=", False),
        ]
        if filters.get("employee_ids"):
            domain.append(("move_id.petty_cash_request_id.employee_id", "in", list(filters["employee_ids"])))
        if filters.get("advance_type_ids"):
            domain.append(("move_id.petty_cash_request_id.advance_type_id", "in", list(filters["advance_type_ids"])))
        return domain

    def _pc_movement_label(self, move_line, request):
        """Name what this journal item *is* — the point of the card."""
        move = move_line.move_id
        if request and move == request.disburse_move_id:
            return _("Pencairan / Disbursement")
        if move.petty_cash_realization_id:
            if move.move_type == "in_invoice":
                return _("Tagihan Pihak Ketiga / Vendor Bill")
            # Odoo 19 renamed account.move.payment_id -> origin_payment_id.
            if move.origin_payment_id:
                return _("Pembayaran Tagihan / Bill Payment")
            return _("Realisasi / Realization")
        if move.journal_id == move.company_id.currency_exchange_journal_id:
            return _("Selisih Kurs / Exchange Difference")
        return _("Top-up / Reimbursement") if move_line.debit else _("Pengembalian / Return")

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------
    def _build_lines(self, filters):
        AML = self.env["account.move.line"]
        accounts = self._pc_advance_accounts(filters["company_ids"])
        if not accounts:
            return [
                {
                    "type": "grand_total",
                    "label": "Grand Total",
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                    "closing": 0.0,
                }
            ]

        base = self._pc_statement_domain(filters, accounts)

        opening_filters = dict(
            filters,
            date_from=date_cls(1970, 1, 1),
            date_to=filters["date_from"] - timedelta(days=1),
        )
        opening_lines = AML.search(self._base_move_line_domain(opening_filters) + base)
        opening_by_employee = {}
        for line in opening_lines:
            employee = line.move_id.petty_cash_request_id.employee_id
            opening_by_employee[employee.id] = opening_by_employee.get(employee.id, 0.0) + line.debit - line.credit

        period_lines = AML.search(self._base_move_line_domain(filters) + base)
        # One prefetch, then sort in Python: ordering on a nested many2one path
        # is not something search() can express, and the card must read as
        # consecutive request blocks inside each employee.
        period_lines.move_id.mapped("petty_cash_request_id")
        period_lines = period_lines.sorted(
            key=lambda ml: (
                (ml.move_id.petty_cash_request_id.employee_id.name or "").lower(),
                ml.move_id.petty_cash_request_id.request_date or date_cls(1970, 1, 1),
                ml.move_id.petty_cash_request_id.id,
                ml.date,
                ml.id,
            )
        )

        employees = {}
        for line in period_lines:
            request = line.move_id.petty_cash_request_id
            employee = request.employee_id
            entry = employees.setdefault(
                employee.id,
                {
                    "type": "partner",
                    "employee_id": employee.id,
                    "partner_name": employee.name or "— No Employee —",
                    "opening": opening_by_employee.get(employee.id, 0.0),
                    "lines": [],
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                },
            )
            entry["total_debit"] += line.debit
            entry["total_credit"] += line.credit
            running = entry["opening"] + entry["total_debit"] - entry["total_credit"]
            entry["lines"].append(
                {
                    "date": line.date,
                    "doc_no": line.move_id.name or "",
                    "movement": self._pc_movement_label(line, request),
                    "request_ref": request.name or "",
                    "type_name": request.advance_type_id.name or "",
                    "label": line.name or line.move_id.ref or "",
                    "debit": line.debit,
                    "credit": line.credit,
                    "running_balance": running,
                    "amount_currency": line.amount_currency or 0.0,
                    "currency": line.currency_id.name or "",
                    "deadline": request.realization_deadline,
                    "status": dict(request._fields["state"].selection).get(request.state, ""),
                }
            )

        # Employees whose balance is entirely brought forward still belong on
        # the card — an advance that saw no movement this period is exactly the
        # one Finance is chasing.
        for employee_id, opening in opening_by_employee.items():
            if employee_id in employees or not opening:
                continue
            employee = self.env["hr.employee"].browse(employee_id)
            employees[employee_id] = {
                "type": "partner",
                "employee_id": employee_id,
                "partner_name": employee.name or "— No Employee —",
                "opening": opening,
                "lines": [],
                "total_debit": 0.0,
                "total_credit": 0.0,
            }

        lines = []
        total_debit = total_credit = total_closing = 0.0
        for entry in sorted(employees.values(), key=lambda r: (r["partner_name"] or "").lower()):
            closing = entry["opening"] + entry["total_debit"] - entry["total_credit"]
            entry["closing"] = closing
            lines.append(entry)
            total_debit += entry["total_debit"]
            total_credit += entry["total_credit"]
            total_closing += closing

        lines.append(
            {
                "type": "grand_total",
                "label": "Grand Total",
                "total_debit": total_debit,
                "total_credit": total_credit,
                "closing": total_closing,
            }
        )
        return lines
