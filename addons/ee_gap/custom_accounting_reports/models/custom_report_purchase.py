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
BILLED = "Billed"
UNBILLED = "Belum di-bill"


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
    # Receipts that no bill covers yet (Levi's sheet #67)
    # ------------------------------------------------------------------
    # A register built from bill lines can only ever show what has been
    # billed. In September 2026 that hid almost everything: 3,433 receipt
    # lines landed, and 3,430 of their purchase order lines still had no
    # posted bill. Accounting pulls this register per receiving period, so
    # those receipts belong in it — valued off the purchase order, which is
    # the only price they have until the invoice arrives.
    def _received_in_window(self, filters):
        """{purchase.order.line id: {"qty", "date"}} received inside the window.

        Quantity is net of returns to the vendor: a return keeps the
        ``purchase_line_id`` of the receipt it reverses, so counting every done
        move would report goods that went straight back out.
        """
        if not self._gr_available():
            return {}
        date_from = fields.Date.to_date(filters["date_from"])
        date_to = fields.Date.to_date(filters["date_to"])
        base = [
            ("state", "=", "done"),
            ("purchase_line_id", "!=", False),
            ("company_id", "in", list(filters["company_ids"])),
            ("date", ">=", datetime.combine(date_from, time.min)),
            ("date", "<=", datetime.combine(date_to, time.max)),
        ]
        Move = self.env["stock.move"].sudo()
        result = {}
        for usage, sign in (("internal", 1.0), ("supplier", -1.0)):
            groups = Move._read_group(
                domain=base + [("location_dest_id.usage", "=", usage)],
                groupby=["purchase_line_id"],
                aggregates=["quantity:sum", "date:min"],
            )
            for pol, qty, dt in groups:
                bucket = result.setdefault(pol.id, {"qty": 0.0, "date": None})
                bucket["qty"] += (qty or 0.0) * sign
                if sign > 0 and dt and (bucket["date"] is None or dt.date() < bucket["date"]):
                    bucket["date"] = dt.date()
        return result

    def _billed_quantities(self, po_line_ids, filters):
        """{purchase.order.line id: quantity already carried by bills}.

        Refund lines net the figure down, so a receipt billed and then credited
        counts as unbilled again. Draft bills are included only when the report
        itself is pulled with ``posted_only`` off, so the two populations always
        answer to the same state filter.
        """
        if not po_line_ids:
            return {}
        states = ("posted",) if filters.get("posted_only", True) else ("draft", "posted")
        AML = self.env["account.move.line"]
        result = {}
        for move_type, sign in (("in_invoice", 1.0), ("in_refund", -1.0)):
            groups = AML._read_group(
                domain=[
                    ("purchase_line_id", "in", list(po_line_ids)),
                    ("move_id.move_type", "=", move_type),
                    ("parent_state", "in", states),
                    ("display_type", "=", "product"),
                ],
                groupby=["purchase_line_id"],
                aggregates=["quantity:sum"],
            )
            for pol, qty in groups:
                result[pol.id] = result.get(pol.id, 0.0) + (qty or 0.0) * sign
        return result

    # ------------------------------------------------------------------
    # PO number, vendor reference, warehouse (Levi's sheet #25, gate K-1)
    # ------------------------------------------------------------------
    # The client fills Vendor Reference with the SES sales-order number; it is
    # the key they reconcile SES goods issues against EBR goods receipts, so it
    # travels with the PO number and the receiving warehouse.
    def _warehouse_label(self, pol):
        """Receiving warehouse of a purchase order line, or ''."""
        if not pol:
            return ""
        picking_type = pol.order_id.picking_type_id
        warehouse = picking_type.warehouse_id if picking_type else False
        return warehouse.display_name if warehouse else ""

    def _ou_label(self, ml):
        """Operating Unit of a bill line, used where there is no PO to read.

        Services and manual non-trade bills never touch a warehouse. Their
        Operating Unit is the nearest thing to one, and leaving the column
        blank for ~850 lines would read as missing data rather than as "this
        cost belongs to no warehouse".
        """
        if "l10n_ou_analytic_id" not in ml._fields:
            return ""
        ou = ml.l10n_ou_analytic_id
        return ou.display_name if ou else ""

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
        if show_gr:
            cols.append({"header": "Status Bill", "field": "bill_status", "kind": "text", "width": 14})
        cols.append({"header": "No. PO", "field": "po_no", "kind": "text", "width": 22})
        if self._purchase_type_available():
            cols.append({"header": "Type", "field": "ptype", "kind": "text", "width": 12})
        cols += [
            {"header": "Vendor", "field": "vendor", "kind": "text", "width": 28},
            {"header": "Vendor Ref", "field": "vendor_ref", "kind": "text", "width": 18},
            {"header": "Warehouse", "field": "warehouse", "kind": "text", "width": 22},
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
        ctx["show_bill_status"] = show_gr
        ctx["include_unbilled"] = bool(basis == "gr" and ctx["filters"].get("include_unbilled", True))
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
        if group_by == "gr_date":
            # The receipt date, not the basis date: on a bill-basis pull these
            # differ, and "By GR Date" has to mean the receipt either way.
            gr = row.get("gr_date")
            return gr.strftime("%Y-%m-%d") if gr else "—"
        if group_by == "warehouse":
            return row.get("warehouse") or "—"
        return None

    def _unbilled_rows(self, filters, has_ptype, want_ptype):
        """Register rows for goods received in the window that no bill covers.

        Valued off the purchase order line — ``price_subtotal / product_qty``
        rather than ``price_unit``, so the discount and the unit of measure are
        already in the figure — pro-rated to the quantity actually received.
        That is the accrual the receipt itself booked into GR/IR, which is why
        these rows tie to the GR/IR balance rather than to accounts payable.
        """
        received = self._received_in_window(filters)
        if not received:
            return []
        billed = self._billed_quantities(list(received), filters)
        pending = {}
        for pol_id, bucket in received.items():
            remainder = bucket["qty"] - billed.get(pol_id, 0.0)
            # Float noise on a netted quantity would otherwise emit rows worth
            # a fraction of a piece.
            if remainder <= 0.000001:
                continue
            pending[pol_id] = (remainder, bucket["date"])
        if not pending:
            return []

        gr_numbers = self._gr_numbers(list(pending), filters)
        partner_ids = set(filters.get("partner_ids") or ())
        po_type_available = has_ptype and "l10n_purchase_type" in self.env["purchase.order"]._fields
        rows = []
        for pol in self.env["purchase.order.line"].browse(list(pending)).exists():
            remainder, gr_date = pending[pol.id]
            order = pol.order_id
            if partner_ids and order.partner_id.id not in partner_ids:
                continue
            ptype = order.l10n_purchase_type if po_type_available else False
            if want_ptype == "unclassified":
                if ptype:
                    continue
            elif want_ptype != "all" and ptype != want_ptype:
                continue
            qty_ordered = pol.product_qty or 0.0
            unit_net = (pol.price_subtotal / qty_ordered) if qty_ordered else (pol.price_unit or 0.0)
            unit_gross = (pol.price_total / qty_ordered) if qty_ordered else unit_net
            untaxed = unit_net * remainder
            total = unit_gross * remainder
            rows.append(
                {
                    "date": gr_date,
                    "bill_date": None,
                    "gr_date": gr_date,
                    "gr_no": gr_numbers.get(pol.id, ""),
                    "invoice_no": "",
                    "bill_status": UNBILLED,
                    "po_no": order.name or "",
                    "vendor_ref": order.partner_ref or "",
                    "warehouse": self._warehouse_label(pol),
                    "ptype": PTYPE_LABELS.get(ptype, UNCLASSIFIED if has_ptype else ""),
                    "vendor": order.partner_id.display_name or "",
                    "item_code": pol.product_id.default_code or "",
                    "product": pol.product_id.name or "",
                    "label": pol.name or "",
                    "quantity": remainder,
                    "price_unit": pol.price_unit or 0.0,
                    "discount": pol.discount or 0.0,
                    "untaxed": untaxed,
                    "tax": total - untaxed,
                    "total": total,
                }
            )
        return rows

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
            pol = ml.purchase_line_id if show_gr else self.env["purchase.order.line"]
            pol_id = pol.id if pol else False
            gr_date = first_gr.get(pol_id) if pol_id else None
            rows.append(
                {
                    "date": (gr_date or ml.date) if basis == "gr" else ml.date,
                    "bill_date": ml.date,
                    "gr_date": gr_date,
                    "gr_no": gr_numbers.get(pol_id, "") if pol_id else "",
                    "invoice_no": ml.move_id.name or "",
                    "bill_status": BILLED,
                    "po_no": pol.order_id.name if pol else "",
                    "vendor_ref": (pol.order_id.partner_ref or "") if pol else "",
                    "warehouse": self._warehouse_label(pol) or self._ou_label(ml),
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

        if basis == "gr" and filters.get("include_unbilled", True):
            rows += self._unbilled_rows(filters, has_ptype, want_ptype)

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
            # "gr_date" deliberately labels into invoice_no: its own column is
            # rendered as a date, and a "Subtotal: 2026-09-01" string in a date
            # cell loses its formatting in the xlsx.
            label_field = {
                "vendor": "vendor",
                "product": "product",
                "purchase_type": "ptype",
                "warehouse": "warehouse",
            }.get(group_by, "invoice_no")
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
