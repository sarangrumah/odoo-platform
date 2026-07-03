# -*- coding: utf-8 -*-
"""General Ledger.

Two output layouts, selected by the wizard and carried on the context
key ``gl_layout``:

* ``grouped`` (default, used by the PDF) — per-account sections with
  opening balance, every posted move.line, running balance and an
  account total, ordered by account code.
* ``flat`` — one row per move.line with the account as a *column*
  (matching the legacy-ERP / SAP "GL line items" export), plus a set of
  optional display columns the user can toggle in the wizard. The list
  of enabled optional columns is carried on the context key
  ``gl_columns``.

Only the Excel export honours ``flat``; the PDF always renders grouped
(a 19-column flat table does not fit an A4 page).
"""

from datetime import date as date_cls, timedelta

from odoo import models


# Optional flat columns the wizard can toggle. Keys here must match the
# ``show_<key>`` booleans on ``custom.report.general.ledger.wizard`` and
# the entries in ``_flat_column_registry``.
GL_OPTIONAL_COLUMNS = (
    "doc_no",
    "reference",
    "tax",
    "clearing",
    "cost_center",
    "profit_center",
    "currency",
    "amount_currency",
    "due_date",
    "user",
)

# Render order for the flat layout. Core columns are always shown; the
# optional ones appear only when selected (see ``_xlsx_columns``).
_FLAT_ORDER = (
    "date",
    "journal",
    "account_code",
    "account_name",
    "partner",
    "label",
    "doc_no",
    "reference",
    "tax",
    "clearing",
    "cost_center",
    "profit_center",
    "currency",
    "amount_currency",
    "due_date",
    "user",
    "debit",
    "credit",
    "balance",
)
_FLAT_CORE = {
    "date",
    "journal",
    "account_code",
    "account_name",
    "partner",
    "label",
    "debit",
    "credit",
    "balance",
}


class CustomReportGeneralLedger(models.AbstractModel):
    _name = "custom.report.general.ledger"
    _inherit = "custom.report.engine"
    _description = "Custom General Ledger"

    _report_code = "general_ledger"
    _report_title = "General Ledger"

    # ------------------------------------------------------------------
    # Layout switch helpers
    # ------------------------------------------------------------------
    def _is_flat(self):
        return self.env.context.get("gl_layout") == "flat"

    def _flat_column_registry(self):
        """Full spec for every flat column, keyed by column key."""
        return {
            "date": {"header": "Date", "field": "date", "kind": "date", "width": 12},
            "journal": {"header": "Journal", "field": "journal_code", "kind": "text", "width": 10},
            "account_code": {"header": "Account", "field": "account_code", "kind": "text", "width": 14},
            "account_name": {"header": "Account Name", "field": "account_name", "kind": "text", "width": 30},
            "partner": {"header": "Partner", "field": "partner", "kind": "text", "width": 28},
            "label": {"header": "Label", "field": "label", "kind": "text", "width": 32},
            "doc_no": {"header": "Document No", "field": "doc_no", "kind": "text", "width": 18},
            "reference": {"header": "Reference", "field": "reference", "kind": "text", "width": 18},
            "tax": {"header": "Tax Code", "field": "tax_code", "kind": "text", "width": 12},
            "clearing": {"header": "Clearing Doc", "field": "clearing", "kind": "text", "width": 16},
            "cost_center": {"header": "Cost Center", "field": "cost_center", "kind": "text", "width": 18},
            "profit_center": {"header": "Profit Center", "field": "profit_center", "kind": "text", "width": 18},
            "currency": {"header": "Doc Currency", "field": "currency", "kind": "text", "width": 10},
            "amount_currency": {"header": "Amount (Doc Curr.)", "field": "amount_currency", "kind": "number", "width": 16},
            "due_date": {"header": "Due Date", "field": "due_date", "kind": "date", "width": 12},
            "user": {"header": "User", "field": "user", "kind": "text", "width": 18},
            "debit": {"header": "Debit", "field": "debit", "kind": "number", "width": 16},
            "credit": {"header": "Credit", "field": "credit", "kind": "number", "width": 16},
            "balance": {"header": "Balance", "field": "balance", "kind": "number", "width": 16},
        }

    # ------------------------------------------------------------------
    # XLSX columns
    # ------------------------------------------------------------------
    def _xlsx_columns(self):
        if not self._is_flat():
            return [
                {"header": "Date", "field": "date", "kind": "text", "width": 12},
                {"header": "Entry", "field": "move_name", "kind": "text", "width": 18},
                {"header": "Partner", "field": "partner", "kind": "text", "width": 28},
                {"header": "Label", "field": "label", "kind": "text", "width": 34},
                {"header": "Debit", "field": "debit", "kind": "number", "width": 16},
                {"header": "Credit", "field": "credit", "kind": "number", "width": 16},
                {"header": "Balance", "field": "balance", "kind": "number", "width": 16},
            ]
        registry = self._flat_column_registry()
        # ``gl_columns`` absent (None) = no wizard / programmatic export: show
        # every optional column. An explicit (possibly empty) list = honour the
        # user's exact selection, so unchecking all leaves the core columns.
        selected = self.env.context.get("gl_columns")
        selected = set(GL_OPTIONAL_COLUMNS) if selected is None else set(selected)
        keys = [k for k in _FLAT_ORDER if k in _FLAT_CORE or k in selected]
        return [registry[k] for k in keys]

    # ------------------------------------------------------------------
    # XLSX body
    # ------------------------------------------------------------------
    def _xlsx_body(self, sheet, ctx, columns, fmts, start_row):
        if self._is_flat():
            # Flat layout is a plain table — the engine's generic body
            # already renders it from ``columns`` + ``lines``.
            return super()._xlsx_body(sheet, ctx, columns, fmts, start_row)

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

    # ------------------------------------------------------------------
    # Line builders
    # ------------------------------------------------------------------
    def _build_lines(self, filters):
        if self._is_flat():
            return self._build_flat_lines(filters)
        return self._build_grouped_lines(filters)

    def _opening_balance_per_account(self, filters):
        """Cumulative balance per account *before* ``date_from``."""
        opening_filters = dict(
            filters,
            date_from=date_cls(1970, 1, 1),
            date_to=filters["date_from"] - timedelta(days=1),
        )
        per_account = self._get_account_balances(opening_filters)
        return {aid: row["balance"] for aid, row in per_account.items()}

    def _build_grouped_lines(self, filters):
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
                    "account_code": self._account_code(acc),
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
                "account_code": self._account_code(acc),
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

    # ------------------------------------------------------------------
    # Flat layout builder
    # ------------------------------------------------------------------
    def _flat_query(self, filters):
        """``(query, params)`` selecting the extended move-line columns the
        flat layout needs. Mirrors the WHERE clause of
        :py:meth:`custom.report.engine._get_move_lines_query`."""
        params = [
            filters["date_from"],
            filters["date_to"],
            tuple(filters["company_ids"]) or (0,),
        ]
        query = """
            SELECT aml.id, aml.date, aml.name AS label, aml.ref AS aml_ref,
                   aml.debit, aml.credit, aml.balance, aml.amount_currency,
                   aml.date_maturity, aml.account_id, aml.partner_id,
                   aml.currency_id, aml.full_reconcile_id, aml.tax_line_id,
                   aml.create_uid, aml.analytic_distribution,
                   aml.move_id, aml.journal_id
              FROM account_move_line aml
             WHERE aml.date >= %s
               AND aml.date <= %s
               AND aml.company_id IN %s
               AND aml.account_id IS NOT NULL
        """
        if filters.get("posted_only", True):
            query += " AND aml.parent_state = %s"
            params.append("posted")
        else:
            query += " AND aml.parent_state IN %s"
            params.append(("draft", "posted"))
        if filters.get("journal_ids"):
            query += " AND aml.journal_id IN %s"
            params.append(tuple(filters["journal_ids"]))
        if filters.get("account_ids"):
            query += " AND aml.account_id IN %s"
            params.append(tuple(filters["account_ids"]))
        if filters.get("partner_ids"):
            query += " AND aml.partner_id IN %s"
            params.append(tuple(filters["partner_ids"]))
        query += " ORDER BY aml.account_id, aml.date, aml.id"
        return query, tuple(params)

    def _split_analytic(self, distribution, analytic_map, plan_is_profit):
        """Split an ``analytic_distribution`` JSON dict into
        ``(cost_center_str, profit_center_str)`` by analytic-plan name."""
        if not distribution:
            return "", ""
        ids = set()
        for key in distribution.keys():
            for part in str(key).split(","):
                part = part.strip()
                if part.isdigit():
                    ids.add(int(part))
        cost, profit = [], []
        for aid in ids:
            acc = analytic_map.get(aid)
            if not acc:
                continue
            if plan_is_profit.get(acc.plan_id.id):
                profit.append(acc.name)
            else:
                cost.append(acc.name)
        return ", ".join(filter(None, cost)), ", ".join(filter(None, profit))

    def _build_flat_lines(self, filters):
        # The flat query reads ``parent_state`` (a stored related of
        # ``move_id.state``) via raw SQL. Flush pending ORM writes first so a
        # move posted earlier in the same transaction — e.g. post-then-export
        # in one server action, or a test — is visible to the SQL.
        self.env.flush_all()
        query, params = self._flat_query(filters)
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        # Batch-resolve every related label in one read per model.
        def _ids(key):
            return sorted({r[key] for r in rows if r.get(key)})

        accounts = {a.id: a for a in self.env["account.account"].browse(_ids("account_id"))}
        moves = {m.id: m for m in self.env["account.move"].browse(_ids("move_id"))}
        journals = {j.id: j for j in self.env["account.journal"].browse(_ids("journal_id"))}
        partners = {p.id: p for p in self.env["res.partner"].browse(_ids("partner_id"))}
        currencies = {c.id: c for c in self.env["res.currency"].browse(_ids("currency_id"))}
        users = {u.id: u for u in self.env["res.users"].browse(_ids("create_uid"))}
        taxes = {t.id: t for t in self.env["account.tax"].browse(_ids("tax_line_id"))}
        recs = {f.id: f for f in self.env["account.full.reconcile"].browse(_ids("full_reconcile_id"))}

        analytic_ids = set()
        for r in rows:
            for key in (r.get("analytic_distribution") or {}).keys():
                for part in str(key).split(","):
                    part = part.strip()
                    if part.isdigit():
                        analytic_ids.add(int(part))
        analytics = {
            a.id: a
            for a in self.env["account.analytic.account"].browse(sorted(analytic_ids))
        }
        plan_is_profit = {
            a.plan_id.id: "profit" in (a.plan_id.name or "").lower()
            for a in analytics.values()
        }

        lines = []
        total_d = total_c = total_b = 0.0
        for r in rows:
            acc = accounts.get(r["account_id"])
            move = moves.get(r["move_id"])
            journal = journals.get(r["journal_id"])
            partner = partners.get(r["partner_id"])
            currency = currencies.get(r["currency_id"])
            user = users.get(r["create_uid"])
            tax = taxes.get(r["tax_line_id"])
            rec = recs.get(r["full_reconcile_id"])
            cost, profit = self._split_analytic(
                r.get("analytic_distribution"), analytics, plan_is_profit
            )
            lines.append(
                {
                    "date": r["date"],
                    "journal_code": journal.code if journal else "",
                    "account_code": self._account_code(acc),
                    "account_name": acc.name if acc else "",
                    "partner": partner.display_name if partner else "",
                    "label": r["label"] or "",
                    "doc_no": (move.name if move else "") or "",
                    "reference": r["aml_ref"] or (move.ref if move else "") or "",
                    "tax_code": tax.name if tax else "",
                    "clearing": rec.name if rec else "",
                    "cost_center": cost,
                    "profit_center": profit,
                    "currency": currency.name if currency else "",
                    "amount_currency": r["amount_currency"] or 0.0,
                    "due_date": r["date_maturity"],
                    "user": user.name if user else "",
                    "debit": r["debit"] or 0.0,
                    "credit": r["credit"] or 0.0,
                    "balance": r["balance"] or 0.0,
                }
            )
            total_d += r["debit"] or 0.0
            total_c += r["credit"] or 0.0
            total_b += r["balance"] or 0.0

        lines.append(
            {
                "type": "grand_total",
                "account_name": "Grand Total",
                "debit": total_d,
                "credit": total_c,
                "balance": total_b,
            }
        )
        return lines
