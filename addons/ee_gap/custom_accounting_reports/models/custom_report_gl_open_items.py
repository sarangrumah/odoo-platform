# -*- coding: utf-8 -*-
"""GL Open Items / Outstanding Balance.

Every unsettled line on a reconcilable account **as of** a cut-off date,
grouped per account. Covers AR and AP but also the clearing accounts that
neither aged report reaches — GR/IR, advances, intercompany suspense — which is
what "GL open items" means to Finance.

Deliberately different from Aged Receivable/Payable: those read the *current*
``amount_residual``, so a line settled after the cut-off already appears
reduced. Here the residual is rebuilt from the reconciliations that had actually
happened by ``date_to`` (``account.partial.reconcile.max_date``), which is the
only version that ties to the ledger at period end.

The ledger alone is not enough, though. On the clearing accounts this report
exists for, most matching never runs through ``account.partial.reconcile`` at
all: GR/IR is settled by the vendor bill journal, POS suspense by the daily
clearing entry. Those debits and credits cancel to the rupiah yet stay
``reconciled = False``, so a literal reading of the ledger printed 258 lines
netting to zero on POS Suspense Clearing and 54,966 on GR/IR textile. After the
as-of residual is known, the remaining debits and credits of each
account/partner/currency are therefore offset FIFO — oldest against oldest — and
only what is left over is printed. Rows carrying no partner at all also offset
across partners of the same account, because GR/IR books its credits without one
and its debits against the vendor. What Finance asked for is what is still owed,
not every entry that ever touched the account.

``Debit``/``Kredit`` stay at their original ledger amounts so each row can still
be traced back to its journal entry; ``Outstanding`` is the part that survives
both the reconciliations and the netting, and it is what the subtotals add up.

Even after the netting, an account like GR/IR still leaves a four-digit number of
rows, which is a wall, not a report. So the wizard picks a ``layout``: ``summary``
(one row per account), ``summary_partner`` (one row per account/counterparty) or
``detail`` (every open line). On screen the summary rows are clickable and walk
down the same chain — account → counterparty → lines — each step re-running the
report narrowed to what was clicked, so the figures cannot drift from the level
above. Narrowing by account is safe because netting never crosses accounts;
narrowing by counterparty is applied *after* the netting for exactly the opposite
reason — partnerless rows do offset across partners, so filtering the query first
would print a different, larger remainder than the summary promised.
"""

from __future__ import annotations

from odoo import _, models
from odoo.exceptions import UserError


class CustomReportGlOpenItems(models.AbstractModel):
    _name = "custom.report.gl.open.items"
    _inherit = "custom.report.engine"
    _description = "GL Open Items / Outstanding Balance"

    _report_code = "gl_open_items"
    _report_title = "GL Open Items / Outstanding Balance"

    _LAYOUTS = ("summary", "summary_partner", "detail")

    def _layout(self, filters=None):
        """Which level this run prints: account / account+partner / lines.

        Read from the caller's options first (that is what the wizard, the PDF
        and the drill-down all pass) and from the context second, because
        ``_xlsx_columns`` is called without the filters and only the context
        reaches it — see ``_with_layout``.
        """
        layout = (filters or {}).get("layout") or self.env.context.get("open_items_layout")
        return layout if layout in self._LAYOUTS else "detail"

    def _with_layout(self, filters=None):
        """Self, with the run's layout pinned in the context so the column
        spec (which never sees the filters) matches the rows."""
        return self.with_context(open_items_layout=self._layout(filters))

    def get_report_table(self, options=None, context_extra=None):
        return super(CustomReportGlOpenItems, self._with_layout(options)).get_report_table(options, context_extra)

    def _xlsx_export(self, filters=None):
        return super(CustomReportGlOpenItems, self._with_layout(filters))._xlsx_export(filters)

    def _xlsx_columns(self):
        layout = self._layout()
        if layout != "detail":
            columns = [{"header": "Akun", "field": "account", "kind": "text", "width": 40}]
            if layout == "summary_partner":
                columns.append({"header": "Lawan Transaksi", "field": "partner", "kind": "text", "width": 30})
            return columns + [
                {"header": "Jml Baris", "field": "item_count", "kind": "number", "width": 11},
                {"header": "Tertua", "field": "date", "kind": "date", "width": 12},
                {"header": "Umur Terlama (hari)", "field": "age", "kind": "number", "width": 16},
                {"header": "Debit", "field": "debit", "kind": "number", "width": 16},
                {"header": "Kredit", "field": "credit", "kind": "number", "width": 16},
                {"header": "Outstanding", "field": "outstanding", "kind": "number", "width": 18},
            ]
        return [
            {"header": "Akun", "field": "account", "kind": "text", "width": 34},
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "No. Dokumen", "field": "doc_no", "kind": "text", "width": 20},
            {"header": "Referensi", "field": "reference", "kind": "text", "width": 20},
            {"header": "Lawan Transaksi", "field": "partner", "kind": "text", "width": 28},
            {"header": "Jatuh Tempo", "field": "due_date", "kind": "date", "width": 12},
            {"header": "Umur (hari)", "field": "age", "kind": "number", "width": 11},
            {"header": "Debit", "field": "debit", "kind": "number", "width": 16},
            {"header": "Kredit", "field": "credit", "kind": "number", "width": 16},
            {"header": "Outstanding", "field": "outstanding", "kind": "number", "width": 18},
        ]

    # ------------------------------------------------------------------
    # As-of residual
    # ------------------------------------------------------------------
    def _settled_by(self, lines, date_to):
        """How much of each line was already reconciled on/before ``date_to``.

        Returns ``{line_id: signed_amount_settled}`` in company currency, signed
        the same way as ``balance`` so it can simply be subtracted. A line
        appearing on the debit side of a partial had that much of its debit
        cleared; on the credit side, its credit.

        The counterpart is judged on the ledger, not on the report filters: a
        line narrowed away by "Dari Tanggal", a partner or an account filter is
        still a real settlement, and ignoring it would report the surviving side
        as open. What is required of the counterpart is that it be **posted** —
        prd_levis_begbal carries a partial reconcile (Rp75,405,550) against a
        move that is still draft, and crediting the posted side for it would
        report the line as settled against something that is not in the books.
        Treating it as still open is both correct and what makes the total tie.
        """
        if not lines:
            return {}
        Partial = self.env["account.partial.reconcile"].sudo()
        partials = Partial.search(
            [
                "&",
                ("max_date", "<=", date_to),
                "|",
                ("debit_move_id", "in", lines.ids),
                ("credit_move_id", "in", lines.ids),
            ]
        )
        wanted = set(lines.ids)
        settled = {}
        for p in partials:
            debit_line = p.debit_move_id
            credit_line = p.credit_move_id
            if debit_line.parent_state != "posted" or credit_line.parent_state != "posted":
                continue
            amount = p.amount or 0.0
            if debit_line.id in wanted:
                settled[debit_line.id] = settled.get(debit_line.id, 0.0) + amount
            if credit_line.id in wanted:
                settled[credit_line.id] = settled.get(credit_line.id, 0.0) - amount
        return settled

    def _candidate_lines(self, filters):
        """Posted lines on reconcilable accounts, dated up to the cut-off.

        Reconciled lines are NOT filtered out here: one settled *after* the
        cut-off was still open then, and dropping it would understate the
        balance — the whole reason this report exists.
        """
        domain = [
            ("company_id", "in", list(filters["company_ids"])),
            ("account_id.reconcile", "=", True),
            ("parent_state", "=", "posted"),
            ("date", "<=", filters["date_to"]),
        ]
        if filters.get("date_from"):
            domain.append(("date", ">=", filters["date_from"]))
        if filters.get("partner_ids"):
            domain.append(("partner_id", "in", filters["partner_ids"]))
        if filters.get("account_ids"):
            domain.append(("account_id", "in", filters["account_ids"]))
        if filters.get("account_types"):
            domain.append(("account_id.account_type", "in", filters["account_types"]))
        return self.env["account.move.line"].search(domain, order="account_id, date, id")

    # ------------------------------------------------------------------
    # Netting
    # ------------------------------------------------------------------
    def _fifo(self, debits, credits, currency):
        """Consume the oldest debit against the oldest credit, in place.

        Both lists must already be in date order. Two pointers, so a 28,000-line
        GR/IR account costs one pass, not a cross product.
        """
        d_i = c_i = 0
        while d_i < len(debits) and c_i < len(credits):
            debit = debits[d_i]
            credit = credits[c_i]
            taken = min(debit["outstanding"], -credit["outstanding"])
            debit["outstanding"] -= taken
            credit["outstanding"] += taken
            if currency.is_zero(debit["outstanding"]):
                debit["outstanding"] = 0.0
                d_i += 1
            if currency.is_zero(credit["outstanding"]):
                credit["outstanding"] = 0.0
                c_i += 1

    def _net_offsetting(self, groups, currency):
        """Offset what the ledger left standing, oldest against oldest.

        ``groups`` maps ``(account, partner, currency)`` to its surviving rows,
        each carrying a signed ``outstanding``. Netting runs twice:

        1. inside one account/partner/currency, where a debit and a credit
           really do settle each other;
        2. across partners of the same account, but only for rows that carry
           **no** partner at all. GR/IR is exactly that case — in
           prd_levis_begbal the 28,348 goods-receipt credits have no partner
           while the 26,618 bill debits are booked against the vendor, so pass 1
           alone still printed 53,406 lines of a pair that cancels. A line
           without a partner makes no claim about who owes it, so there is
           nothing to protect by keeping it apart; two lines that both name a
           partner are never netted against each other.

        Returns ``{account_id: [rows]}`` holding only what is still owed.
        """
        for entries in groups.values():
            self._fifo(
                [e for e in entries if e["outstanding"] > 0.0],
                [e for e in entries if e["outstanding"] < 0.0],
                currency,
            )

        by_currency = {}
        for (account_id, _partner_id, currency_id), entries in groups.items():
            by_currency.setdefault((account_id, currency_id), []).extend(
                e for e in entries if not currency.is_zero(e["outstanding"])
            )

        per_account = {}
        for (account_id, _currency_id), entries in by_currency.items():
            entries.sort(key=lambda r: (r["date"], r["sequence"]))
            anonymous = [e for e in entries if not e["partner_id"]]
            if anonymous:
                self._fifo(
                    [e for e in anonymous if e["outstanding"] > 0.0],
                    [e for e in entries if e["outstanding"] < 0.0],
                    currency,
                )
                self._fifo(
                    [e for e in entries if e["outstanding"] > 0.0],
                    [e for e in anonymous if e["outstanding"] < 0.0],
                    currency,
                )
            surviving = [e for e in entries if not currency.is_zero(e["outstanding"])]
            if surviving:
                # An account that nets away entirely drops out with its
                # subtotal; printing "Subtotal ... 0" over no rows at all is
                # just the old noise in a shorter form.
                per_account.setdefault(account_id, []).extend(surviving)
        return per_account

    def _build_lines(self, filters):
        date_to = filters["date_to"]
        currency = self.env.company.currency_id
        lines = self._candidate_lines(filters)
        settled = self._settled_by(lines, date_to)

        # Collect per account/partner/currency first: netting may only happen
        # between entries that would actually settle each other.
        groups = {}
        accounts = {}
        for ml in lines:
            outstanding = (ml.balance or 0.0) - settled.get(ml.id, 0.0)
            if currency.is_zero(outstanding):
                continue
            acc = ml.account_id
            accounts.setdefault(acc.id, ("%s %s" % (self._account_code(acc), acc.name or "")).strip())
            due = ml.date_maturity or ml.date
            groups.setdefault((acc.id, ml.partner_id.id, ml.currency_id.id), []).append(
                {
                    "account": accounts[acc.id],
                    "date": ml.date,
                    "doc_no": ml.move_id.name or "",
                    "reference": ml.ref or ml.move_id.ref or "",
                    "partner": (ml.partner_id.display_name or ""),
                    "partner_id": ml.partner_id.id,
                    "due_date": ml.date_maturity,
                    "age": (date_to - due).days if due else 0,
                    "debit": ml.debit or 0.0,
                    "credit": ml.credit or 0.0,
                    "outstanding": outstanding,
                    "sequence": ml.id,
                }
            )

        per_account = self._net_offsetting(groups, currency)
        per_account = self._focus_partner(per_account, filters)

        layout = self._layout(filters)
        if layout != "detail":
            return self._summary_lines(per_account, accounts, layout)

        rows = []
        grand = 0.0
        for acc_id in sorted(per_account, key=lambda a: accounts[a]):
            block = sorted(per_account[acc_id], key=lambda r: (r["date"], r["sequence"]))
            subtotal = 0.0
            for row in block:
                rows.append(row)
                subtotal += row["outstanding"]
            rows.append(
                {
                    "type": "subtotal",
                    "account": _("Subtotal %s", accounts[acc_id]),
                    "outstanding": subtotal,
                }
            )
            grand += subtotal

        return self._close_lines(rows, grand)

    # ------------------------------------------------------------------
    # Summary levels
    # ------------------------------------------------------------------
    def _focus_partner(self, per_account, filters):
        """Keep only one counterparty's rows — *after* the netting.

        The drill-down from the account/partner summary passes
        ``focus_partner_id`` (an id, or ``"none"`` for the rows that carry no
        partner). It cannot be pushed into ``_candidate_lines``: partnerless
        rows offset across partners, so a query narrowed to one partner would
        skip that pass and print more than the summary said was open.
        """
        focus = filters.get("focus_partner_id")
        if focus in (None, False, ""):
            return per_account
        wants_none = focus in ("none", 0, "0")
        partner_id = None if wants_none else int(focus)

        def wanted(entry):
            return not entry["partner_id"] if wants_none else entry["partner_id"] == partner_id

        kept = {}
        for account_id, entries in per_account.items():
            rows = [e for e in entries if wanted(e)]
            if rows:
                kept[account_id] = rows
        return kept

    def _summary_lines(self, per_account, accounts, layout):
        """Collapse the surviving rows to one line per account, or per
        account/counterparty, each carrying what it takes to open the level
        below it (``drilldown_params``)."""
        rows = []
        grand = 0.0
        for acc_id in sorted(per_account, key=lambda a: accounts[a]):
            entries = per_account[acc_id]
            if layout == "summary":
                buckets = {False: entries}
            else:
                buckets = {}
                for entry in entries:
                    buckets.setdefault(entry["partner_id"], []).append(entry)
            subtotal = 0.0
            for partner_id in sorted(buckets, key=lambda p: (buckets[p][0]["partner"] or "").lower()):
                bucket = buckets[partner_id]
                row = {
                    "account": accounts[acc_id],
                    "item_count": len(bucket),
                    "date": min(e["date"] for e in bucket),
                    "age": max(e["age"] for e in bucket),
                    "debit": sum(e["debit"] for e in bucket),
                    "credit": sum(e["credit"] for e in bucket),
                    "outstanding": sum(e["outstanding"] for e in bucket),
                    "drilldown_params": {"account_id": acc_id},
                }
                if layout == "summary_partner":
                    row["partner"] = bucket[0]["partner"] or _("(Tanpa Lawan Transaksi)")
                    row["drilldown_params"]["focus_partner_id"] = partner_id or "none"
                rows.append(row)
                subtotal += row["outstanding"]
            if layout == "summary_partner" and len(buckets) > 1:
                rows.append(
                    {
                        "type": "subtotal",
                        "account": _("Subtotal %s", accounts[acc_id]),
                        "outstanding": subtotal,
                    }
                )
            grand += subtotal

        return self._close_lines(rows, grand)

    def _close_lines(self, rows, grand):
        if not rows:
            rows.append({"type": "note", "account": _("Tidak ada open item pada tanggal tersebut.")})
        rows.append({"type": "grand_total", "account": _("TOTAL OUTSTANDING"), "outstanding": grand})
        return rows

    # ------------------------------------------------------------------
    # Drill-down: account summary -> counterparty summary -> open lines
    # ------------------------------------------------------------------
    _NEXT_LAYOUT = {"summary": "summary_partner", "summary_partner": "detail"}

    def _report_drilldown_action(self, options, params):
        """Re-run this same report one level deeper, narrowed to the row
        that was clicked. Same report = same netting, so each level still
        adds up to the one above it."""
        options = dict(options or {})
        params = params or {}
        layout = self._NEXT_LAYOUT.get(self._layout(options))
        if not layout:
            raise UserError(_("This row is already the detail level."))
        account = self.env["account.account"].browse(params.get("account_id")).exists()
        if not account:
            raise UserError(_("This row is not linked to an account."))
        options["layout"] = layout
        options["account_ids"] = account.ids
        if params.get("focus_partner_id"):
            options["focus_partner_id"] = params["focus_partner_id"]
        title = _("GL Open Items — %(code)s %(name)s") % {
            "code": self._account_code(account),
            "name": account.name or "",
        }
        return {
            "type": "ir.actions.client",
            "tag": "custom_report_table",
            "name": title,
            "params": {
                "report_code": self._report_code,
                "options": options,
                "context_extra": {"open_items_layout": layout},
                "title": title,
            },
        }
