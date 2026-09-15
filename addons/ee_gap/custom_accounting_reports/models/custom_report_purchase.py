# -*- coding: utf-8 -*-
"""Purchase register over posted vendor bills.

One row per bill product line (in_invoice / in_refund, refunds signed
negative), with an optional grouping (vendor / product / month) that adds
subtotal rows. The native Purchase Analysis pivot is left as-is; this is the
single curated template requested for the report menu — the vendor-bill mirror
of :mod:`custom_report_sales`.

Amounts use the document-currency ``price_subtotal`` / ``price_total`` (equal
to the company currency for single-currency books).
"""

from datetime import date as date_cls, datetime, time
from itertools import groupby

from odoo import fields, models

PTYPE_LABELS = {"trade": "Trade", "non_trade": "Non-Trade"}
UNCLASSIFIED = "Unclassified"


class CustomReportPurchase(models.AbstractModel):
    _name = "custom.report.purchase"
    _inherit = "custom.report.engine"
    _description = "Custom Purchase Register"

    _report_code = "purchase"
    _report_title = "Purchase Report"

    # ------------------------------------------------------------------
    # Goods-receipt basis (Levi's sheet #25 / #30)
    # ------------------------------------------------------------------
    # Accounting pulls the register per *receiving* period, not per billing
    # period: a July receipt billed in August belongs to July. The bill line is
    # still the row (that is where price, discount and tax live), but the
    # period filter, the leading date and the month grouping follow the first
    # done goods receipt of its purchase order line.
    #
    # Bill lines with no purchase order behind them — services, non-trade
    # expenses, manual bills — have no receipt at all. They keep the bill date
    # as their basis date so the register stays complete instead of silently
    # dropping every non-trade cost.
    def _gr_available(self):
        return "purchase_line_id" in self.env["account.move.line"]._fields and "stock.move" in self.env

    def _first_gr_dates(self, filters):
        """{purchase.order.line id: date of its first done receipt} up to date_to."""
        if not self._gr_available():
            return {}
        date_to = fields.Date.to_date(filters["date_to"])
        groups = (
            self.env["stock.move"]
            .sudo()
            ._read_group(
                domain=[
                    ("state", "=", "done"),
                    ("purchase_line_id", "!=", False),
                    ("company_id", "in", list(filters["company_ids"])),
                    ("date", "<=", datetime.combine(date_to, time.max)),
                ],
                groupby=["purchase_line_id"],
                aggregates=["date:min"],
            )
        )
        return {pol.id: dt.date() for pol, dt in groups if dt}

    def _gr_numbers(self, po_line_ids, filters):
        """{purchase.order.line id: "WH/IN/00012, WH/IN/00019"} for done receipts."""
        if not po_line_ids or not self._gr_available():
            return {}
        date_to = fields.Date.to_date(filters["date_to"])
        moves = (
            self.env["stock.move"]
            .sudo()
            .search_read(
                [
                    ("state", "=", "done"),
                    ("purchase_line_id", "in", list(po_line_ids)),
                    ("date", "<=", datetime.combine(date_to, time.max)),
                ],
                ["purchase_line_id", "picking_id"],
            )
        )
        names = {}
        for mv in moves:
            picking = mv.get("picking_id")
            if not picking:
                continue
            names.setdefault(mv["purchase_line_id"][0], set()).add(picking[1])
        return {pol: ", ".join(sorted(vals)) for pol, vals in names.items()}

    # ------------------------------------------------------------------
    # Trade / Non-Trade split (Levi's feature #9)
    # ------------------------------------------------------------------
    # ``account.move.l10n_purchase_type`` is added by the tenant module
    # custom_levis_localization. This addon is shared by every tenant DB on the
    # same container, so the Type column / filter only appears where the field
    # actually exists.
    def _purchase_type_available(self):
        return "l10n_purchase_type" in self.env["account.move"]._fields

    def _resolve_purchase_type(self, ml):
        """Trade / Non-Trade of one bill line, with fallbacks.

        The stream lives on the bill (carried from the PO at creation). Older /
        manual documents can miss it, so fall back to the reversed entry (credit
        notes created with "Reverse") and then to the source PO.
        """
        move = ml.move_id
        ptype = move.l10n_purchase_type
        if not ptype and move.reversed_entry_id:
            ptype = move.reversed_entry_id.l10n_purchase_type
        if not ptype and "purchase_line_id" in ml._fields and ml.purchase_line_id:
            ptype = ml.purchase_line_id.order_id.l10n_purchase_type
        return ptype or False

    def _xlsx_columns(self):
        cols = []
        show_gr = self._gr_available()
        if show_gr:
            cols += [
                {"header": "Tgl GR", "field": "gr_date", "kind": "date", "width": 12},
                {"header": "No. GR", "field": "gr_no", "kind": "text", "width": 20},
                {"header": "Tgl Bill", "field": "bill_date", "kind": "date", "width": 12},
            ]
        else:
            cols.append({"header": "Date", "field": "date", "kind": "date", "width": 12})
        cols.append({"header": "Bill No", "field": "invoice_no", "kind": "text", "width": 18})
        if self._purchase_type_available():
            cols.append({"header": "Type", "field": "ptype", "kind": "text", "width": 12})
        cols += [
            {"header": "Vendor", "field": "vendor", "kind": "text", "width": 28},
            {"header": "Item Code", "field": "item_code", "kind": "text", "width": 16},
            {"header": "Item Name", "field": "product", "kind": "text", "width": 30},
            {"header": "Description", "field": "label", "kind": "text", "width": 30},
            {"header": "Qty", "field": "quantity", "kind": "number", "width": 10},
            {"header": "Unit Price", "field": "price_unit", "kind": "number", "width": 14},
            {"header": "Disc %", "field": "discount", "kind": "number", "width": 9},
            {"header": "Untaxed", "field": "untaxed", "kind": "number", "width": 16},
            {"header": "Tax", "field": "tax", "kind": "number", "width": 14},
            {"header": "Total", "field": "total", "kind": "number", "width": 16},
        ]
        return cols

    # The engine's generic flat ``_xlsx_body`` already renders these lines
    # (subtotal / grand_total rows are emitted bold).

    def _compute(self, filters=None):
        """Expose the Trade / Non-Trade knobs to the PDF template."""
        ctx = super()._compute(filters)
        ctx["show_ptype"] = self._purchase_type_available()
        want = (ctx["filters"].get("purchase_type") or "all") if ctx["show_ptype"] else "all"
        ctx["purchase_type_label"] = {
            "trade": "Trade",
            "non_trade": "Non-Trade",
            "unclassified": UNCLASSIFIED,
        }.get(want, "")
        show_gr = self._gr_available()
        ctx["show_gr"] = show_gr
        basis = (ctx["filters"].get("date_basis") or "gr") if show_gr else "bill"
        ctx["date_basis_label"] = "Tanggal GR" if basis == "gr" else "Tanggal Bill"
        return ctx

    def _group_key(self, row, group_by):
        if group_by == "vendor":
            return row["vendor"] or "—"
        if group_by == "product":
            return row["product"] or "—"
        if group_by == "month":
            return row["date"].strftime("%Y-%m") if row["date"] else "—"
        if group_by == "purchase_type":
            return row.get("ptype") or UNCLASSIFIED
        return None

    def _build_lines(self, filters):
        group_by = filters.get("group_by") or "none"
        show_gr = self._gr_available()
        basis = (filters.get("date_basis") or "gr") if show_gr else "bill"
        domain = [
            ("company_id", "in", filters["company_ids"]),
            ("move_id.move_type", "in", ("in_invoice", "in_refund")),
            ("display_type", "=", "product"),
        ]
        first_gr = self._first_gr_dates(filters) if basis == "gr" else {}
        date_window = [
            ("date", ">=", filters["date_from"]),
            ("date", "<=", filters["date_to"]),
        ]
        if basis != "gr":
            domain += date_window
        if filters.get("posted_only", True):
            domain.append(("parent_state", "=", "posted"))
        else:
            domain.append(("parent_state", "in", ("draft", "posted")))
        if filters.get("partner_ids"):
            domain.append(("move_id.partner_id", "in", filters["partner_ids"]))

        has_ptype = self._purchase_type_available()
        if group_by == "purchase_type" and not has_ptype:
            group_by = "none"
        want_ptype = filters.get("purchase_type") or "all"
        if not has_ptype:
            want_ptype = "all"
        elif want_ptype in ("trade", "non_trade"):
            # Rows whose bill carries the other stream can never be reclassified
            # by the fallbacks, so keep them out of the search entirely; the
            # blanks still go through _resolve_purchase_type below.
            domain.append(("move_id.l10n_purchase_type", "in", (want_ptype, False)))

        AML = self.env["account.move.line"]
        if basis == "gr":
            date_from = fields.Date.to_date(filters["date_from"])
            date_to = fields.Date.to_date(filters["date_to"])
            in_window = [pol for pol, gr in first_gr.items() if date_from <= gr <= date_to]
            # Two populations make up a GR-basis pull: lines whose receipt lands
            # in the window, whatever month their bill carries — and lines that
            # have no receipt at all (services, non-trade, a bill keyed before
            # the goods arrived), which keep their bill date so no cost is ever
            # silently dropped by switching basis.
            received = AML.search(domain + [("purchase_line_id", "in", in_window)])
            unreceived = AML.search(domain + date_window).filtered(lambda ml: not first_gr.get(ml.purchase_line_id.id))
            move_lines = received | unreceived
        else:
            move_lines = AML.search(domain)
        gr_numbers = self._gr_numbers(move_lines.mapped("purchase_line_id").ids, filters) if show_gr else {}
        if show_gr and basis != "gr":
            first_gr = self._first_gr_dates(filters)

        rows = []
        for ml in move_lines:
            ptype = self._resolve_purchase_type(ml) if has_ptype else False
            if want_ptype == "unclassified":
                if ptype:
                    continue
            elif want_ptype != "all" and ptype != want_ptype:
                continue
            sign = -1.0 if ml.move_id.move_type == "in_refund" else 1.0
            untaxed = ml.price_subtotal * sign
            total = ml.price_total * sign
            pol_id = ml.purchase_line_id.id if show_gr else False
            gr_date = first_gr.get(pol_id) if pol_id else None
            rows.append(
                {
                    "date": (gr_date or ml.date) if basis == "gr" else ml.date,
                    "bill_date": ml.date,
                    "gr_date": gr_date,
                    "gr_no": gr_numbers.get(pol_id, "") if pol_id else "",
                    "invoice_no": ml.move_id.name or "",
                    "ptype": PTYPE_LABELS.get(ptype, UNCLASSIFIED if has_ptype else ""),
                    "vendor": ml.move_id.partner_id.display_name or "",
                    "item_code": ml.product_id.default_code or "",
                    "product": ml.product_id.name or "",
                    "label": ml.name or "",
                    "quantity": (ml.quantity or 0.0) * sign,
                    "price_unit": ml.price_unit or 0.0,
                    "discount": ml.discount or 0.0,
                    "untaxed": untaxed,
                    "tax": total - untaxed,
                    "total": total,
                }
            )

        lines = []
        g_qty = g_un = g_tx = g_tot = 0.0

        def _accumulate(r):
            nonlocal g_qty, g_un, g_tx, g_tot
            g_qty += r["quantity"]
            g_un += r["untaxed"]
            g_tx += r["tax"]
            g_tot += r["total"]

        if group_by == "none":
            for r in sorted(rows, key=lambda r: (r["date"] or date_cls.min, r["invoice_no"])):
                lines.append(r)
                _accumulate(r)
        else:
            label_field = {"vendor": "vendor", "product": "product", "purchase_type": "ptype"}.get(
                group_by, "invoice_no"
            )
            rows.sort(key=lambda r: (self._group_key(r, group_by), r["date"] or date_cls.min, r["invoice_no"]))
            for key, grp in groupby(rows, key=lambda r: self._group_key(r, group_by)):
                grp = list(grp)
                s_qty = s_un = s_tx = s_tot = 0.0
                for r in grp:
                    lines.append(r)
                    s_qty += r["quantity"]
                    s_un += r["untaxed"]
                    s_tx += r["tax"]
                    s_tot += r["total"]
                    _accumulate(r)
                subtotal = {
                    "type": "subtotal",
                    "quantity": s_qty,
                    "untaxed": s_un,
                    "tax": s_tx,
                    "total": s_tot,
                    label_field: "Subtotal: %s" % (key or "—"),
                }
                lines.append(subtotal)

        lines.append(
            {
                "type": "grand_total",
                "invoice_no": "Grand Total",
                "quantity": g_qty,
                "untaxed": g_un,
                "tax": g_tx,
                "total": g_tot,
            }
        )
        return lines
