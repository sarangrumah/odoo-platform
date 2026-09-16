# -*- coding: utf-8 -*-
"""AR Aging Export — the per-document aging layout Finance exports to Excel.

One row per open receivable line, carrying the commercial trail (customer PO /
SO / DO), the tax split (DPP / PPN), the settlement figures (original / paid /
outstanding) and the outstanding amount dropped into one of fifteen overdue
buckets — day-by-day for the first week, then widening.

This is deliberately *not* ``custom.report.aged.receivable``: that report
answers "how old is my AR" in seven wide buckets; this one is the operational
collection worklist, and its bucket edges are set by Finance's own workbook.

The report reads its extras defensively (``_opt``, model presence checks) so it
still renders on tenants without ``sale``, ``stock`` or ``custom_coretax``.
"""

from odoo import models


# code, label, lower bound, upper bound — bounds are *overdue days*, i.e.
# ``as_of - due_date``. ``None`` = open-ended.
BUCKETS = (
    ("od_le_0", "OD : <= 0 Days", None, 0),
    ("od_1", "OD : 1 Days", 1, 1),
    ("od_2", "OD : 2 Days", 2, 2),
    ("od_3", "OD : 3 Days", 3, 3),
    ("od_4", "OD : 4 Days", 4, 4),
    ("od_5", "OD : 5 Days", 5, 5),
    ("od_6", "OD : 6 Days", 6, 6),
    ("od_7", "OD : 7 Days", 7, 7),
    ("od_8_14", "OD : 8-14 Days", 8, 14),
    ("od_15_30", "OD : 15-30 Days", 15, 30),
    ("od_31_60", "OD : 31-60 Days", 31, 60),
    ("od_61_90", "OD : 61-90 Days", 61, 90),
    ("od_91_120", "OD : 91-120 Days", 91, 120),
    ("od_121_360", "OD : 121-360 Days", 121, 360),
    ("od_gt_360", "OD : > 360 Days", 361, None),
)

BUCKET_CODES = [code for code, _label, _lo, _hi in BUCKETS]

# Columns carrying the "Amount Summary" band in Finance's workbook.
SUMMARY_FIELDS = ("original_amount", "paid_amount", "outstanding_amount")


class CustomReportArAgingExport(models.AbstractModel):
    _name = "custom.report.ar.aging.export"
    _inherit = "custom.report.aged.receivable"
    _description = "AR Aging Export"

    _report_code = "ar_aging_export"
    _report_title = "AR Aging Export"

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------
    def _base_columns(self):
        return [
            {"header": "Customer Name", "field": "partner_name", "kind": "text", "width": 32},
            {"header": "No Invoice", "field": "doc_no", "kind": "text", "width": 26},
            {"header": "No. PO", "field": "po_no", "kind": "text", "width": 18},
            {"header": "No. SO", "field": "so_no", "kind": "text", "width": 18},
            {"header": "No. DO", "field": "do_no", "kind": "text", "width": 26},
            {"header": "Invoice Date", "field": "invoice_date", "kind": "text", "width": 12},
            {"header": "Receive Date", "field": "receive_date", "kind": "text", "width": 12},
            {"header": "Payment Term", "field": "payment_term", "kind": "text", "width": 26},
            {"header": "Due Date", "field": "due_date", "kind": "text", "width": 12},
            {"header": "Tax No", "field": "tax_no", "kind": "text", "width": 20},
            {"header": "DPP", "field": "dpp", "kind": "number", "width": 16},
            {"header": "PPN", "field": "ppn", "kind": "number", "width": 14},
            {"header": "Full Amount", "field": "full_amount", "kind": "number", "width": 16},
            {"header": "Payment Date", "field": "payment_date", "kind": "text", "width": 12},
            # Day counts, not money — kept textual so they print as ``-6`` /
            # ``4`` instead of the engine's ``#,##0.00`` money format.
            {"header": "Overdue", "field": "overdue", "kind": "text", "width": 9},
            {"header": "Aging Days", "field": "aging_days", "kind": "text", "width": 10},
            {"header": "Original Amount", "field": "original_amount", "kind": "number", "width": 16},
            {"header": "Paid Amount", "field": "paid_amount", "kind": "number", "width": 16},
            {"header": "Outstanding Amount", "field": "outstanding_amount", "kind": "number", "width": 18},
        ]

    def _xlsx_columns(self):
        cols = self._base_columns()
        for code, label, _lo, _hi in BUCKETS:
            cols.append({"header": label, "field": code, "kind": "number", "width": 15})
        return cols

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def _classify_bucket(self, due_date, as_of):
        """Bucket by *overdue days*, not by the seven-bucket aged-AR ladder."""
        if not due_date:
            return "od_le_0"
        days = (as_of - due_date).days
        return self._bucket_for_days(days)

    def _bucket_for_days(self, days):
        if days <= 0:
            return "od_le_0"
        for code, _label, lower, upper in BUCKETS:
            if lower is None:
                continue
            if upper is None:
                if days >= lower:
                    return code
            elif lower <= days <= upper:
                return code
        return "od_gt_360"

    # ------------------------------------------------------------------
    # Commercial trail (sale / stock / coretax are all optional)
    # ------------------------------------------------------------------
    def _sale_orders(self, move):
        """The sale orders behind an invoice — via the invoice lines when
        ``sale`` is installed, else by matching ``invoice_origin`` on name."""
        if "sale.order" not in self.env:
            return None
        orders = self.env["sale.order"].browse()
        if "sale_line_ids" in self.env["account.move.line"]._fields:
            orders = move.invoice_line_ids.sale_line_ids.order_id
        if not orders and move.invoice_origin:
            names = [part.strip() for part in move.invoice_origin.split(",") if part.strip()]
            if names:
                orders = self.env["sale.order"].search([("name", "in", names)])
        return orders

    def _commercial_refs(self, move):
        """``(po_no, so_no, do_no, receive_date)`` for one invoice."""
        # ``ref`` is the customer's own reference on an invoice, but on a plain
        # journal entry it is the bookkeeper's narration ("Saldo Awal ...") —
        # not a PO number, so don't pass it off as one.
        po_no = (move.ref or "") if move.is_invoice(include_receipts=True) else ""
        so_no = ""
        do_no = ""
        receive_date = False
        orders = self._sale_orders(move)
        if orders:
            so_no = ", ".join(o.name for o in orders if o.name)
            client_refs = [o.client_order_ref for o in orders if o.client_order_ref]
            if client_refs:
                po_no = ", ".join(client_refs)
            pickings = orders.picking_ids if "picking_ids" in orders._fields else orders.browse()
            done = pickings.filtered(lambda p: p.state == "done")
            pickings = done or pickings
            if pickings:
                do_no = ", ".join(p.name for p in pickings if p.name)
                dates = [p.date_done for p in pickings if p.date_done]
                if dates:
                    receive_date = max(dates).date()
        if not so_no:
            so_no = move.invoice_origin or ""
        return po_no, so_no, do_no, receive_date

    def _payment_date(self, line, as_of=None):
        """Latest date on which something was matched against this line, on or
        before ``as_of`` — a match made after the cut-off did not exist yet in
        the period being reported."""
        dates = []
        for partial in line.matched_credit_ids | line.matched_debit_ids:
            if partial.max_date and (not as_of or partial.max_date <= as_of):
                dates.append(partial.max_date)
        return max(dates) if dates else False

    def _tax_split(self, move, balance):
        """``(dpp, ppn, full)`` in company currency.

        Invoices carry their own signed totals; plain journal entries (opening
        balances, accruals) have none, so the whole line is DPP.
        """
        if move and move.is_invoice(include_receipts=True):
            return (
                move.amount_untaxed_signed,
                move.amount_tax_signed,
                move.amount_total_signed,
            )
        return balance, 0.0, balance

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------
    def _build_lines(self, filters):
        as_of = filters["date_to"]
        rows = []
        lines = self._open_lines(filters)
        matched = self._matched_as_of(lines, as_of)
        for line in lines:
            residual = self._residual_as_of(line, matched)
            if not residual:
                continue
            move = line.move_id
            due = line.date_maturity or line.date
            doc_date = move.invoice_date or line.date
            po_no, so_no, do_no, receive_date = self._commercial_refs(move)
            dpp, ppn, full = self._tax_split(move, line.balance)
            payment_date = self._payment_date(line, as_of)
            row = {
                "partner_name": line.partner_id.display_name or "No Partner",
                "doc_no": move.name or "",
                "po_no": po_no,
                "so_no": so_no,
                "do_no": do_no,
                "invoice_date": self._format_date_id(doc_date),
                "receive_date": self._format_date_id(receive_date or doc_date),
                "payment_term": move.invoice_payment_term_id.display_name or "",
                "due_date": self._format_date_id(due),
                "tax_no": self._opt(move, "x_custom_nsfp"),
                "dpp": dpp,
                "ppn": ppn,
                "full_amount": full,
                "payment_date": self._format_date_id(payment_date),
                "overdue": str((as_of - due).days) if due else "",
                "aging_days": str((as_of - doc_date).days) if doc_date else "",
                "original_amount": line.balance,
                "paid_amount": line.balance - residual,
                "outstanding_amount": residual,
                "_sort_due": due,
                **{code: 0.0 for code in BUCKET_CODES},
            }
            row[self._classify_bucket(due, as_of)] = residual
            rows.append(row)

        rows.sort(key=lambda r: ((r["partner_name"] or "").lower(), r["_sort_due"] or as_of, r["doc_no"]))
        for row in rows:
            row.pop("_sort_due", None)

        total = {
            "type": "grand_total",
            "partner_name": "Grand Total",
            "dpp": 0.0,
            "ppn": 0.0,
            "full_amount": 0.0,
            "original_amount": 0.0,
            "paid_amount": 0.0,
            "outstanding_amount": 0.0,
            # Blank, not zero: a summed "overdue day" is meaningless.
            "overdue": "",
            "aging_days": "",
            **{code: 0.0 for code in BUCKET_CODES},
        }
        for row in rows:
            for field in ("dpp", "ppn", "full_amount") + SUMMARY_FIELDS:
                total[field] += row[field]
            for code in BUCKET_CODES:
                total[code] += row[code]

        return rows + [total]

    # ------------------------------------------------------------------
    # Screen / Excel
    # ------------------------------------------------------------------
    def _flatten_for_screen(self, lines, columns):
        """``_build_lines`` returns a flat list of row dicts here, so the
        engine's pass-through flattener is what we want — but the parent
        ``custom.report.aged.receivable`` overrode it to walk its partner
        groups, so restore the default rather than inherit that walk."""
        first_text = self._first_text_field(columns)
        return [self._screen_row(line, columns, first_text) for line in lines if line.get("type") != "coverage"]

    def _xlsx_body(self, sheet, ctx, columns, fmts, start_row):
        """Flat table, preceded by the merged ``Amount Summary`` band that
        spans the Original / Paid / Outstanding columns in the source
        workbook.

        The rows are written here rather than delegated to ``super()``: the
        parent aged-AR body renders the partner/bucket matrix, not a flat
        table.
        """
        index_by_field = {col["field"]: idx for idx, col in enumerate(columns)}
        first = index_by_field.get(SUMMARY_FIELDS[0])
        last = index_by_field.get(SUMMARY_FIELDS[-1])
        row = start_row
        # The engine's banner prints a from/to period; an aging report has no
        # meaningful start date, so restate it the way the workbook does.
        sheet.merge_range(
            row,
            0,
            row,
            max(len(columns) - 1, 0),
            "AR Aging Export at %s" % (ctx.get("date_to_id") or ""),
            fmts["meta"],
        )
        row += 1
        if first is not None and last is not None and last > first:
            sheet.merge_range(row, first, row, last, "Amount Summary", fmts["header"])
        row += 1

        for col_idx, col in enumerate(columns):
            sheet.write(row, col_idx, col.get("header", ""), fmts["header"])
        sheet.freeze_panes(row + 1, 2)
        row += 1

        for line in ctx.get("lines", []):
            if line.get("type") == "coverage":
                continue
            is_total = line.get("type") in ("grand_total", "total", "subtotal")
            for col_idx, col in enumerate(columns):
                value = line.get(col["field"])
                if col.get("kind") == "number":
                    fmt = fmts["total_num"] if is_total else fmts["num"]
                    if value in (None, False, ""):
                        sheet.write(row, col_idx, "", fmt)
                    else:
                        sheet.write_number(row, col_idx, float(value), fmt)
                    continue
                sheet.write(row, col_idx, value or "", fmts["total_text"] if is_total else fmts["text"])
            row += 1
        return row
