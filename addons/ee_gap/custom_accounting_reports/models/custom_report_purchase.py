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

from datetime import date as date_cls
from itertools import groupby

from odoo import models

PTYPE_LABELS = {"trade": "Trade", "non_trade": "Non-Trade"}
UNCLASSIFIED = "Unclassified"


class CustomReportPurchase(models.AbstractModel):
    _name = "custom.report.purchase"
    _inherit = "custom.report.engine"
    _description = "Custom Purchase Register"

    _report_code = "purchase"
    _report_title = "Purchase Report"

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
        if self._purchase_type_available():
            return [
                {"header": "Date", "field": "date", "kind": "date", "width": 12},
                {"header": "Bill No", "field": "invoice_no", "kind": "text", "width": 18},
                {"header": "Type", "field": "ptype", "kind": "text", "width": 12},
                {"header": "Vendor", "field": "vendor", "kind": "text", "width": 28},
                {"header": "Product", "field": "product", "kind": "text", "width": 26},
                {"header": "Description", "field": "label", "kind": "text", "width": 30},
                {"header": "Qty", "field": "quantity", "kind": "number", "width": 10},
                {"header": "Unit Price", "field": "price_unit", "kind": "number", "width": 14},
                {"header": "Disc %", "field": "discount", "kind": "number", "width": 9},
                {"header": "Untaxed", "field": "untaxed", "kind": "number", "width": 16},
                {"header": "Tax", "field": "tax", "kind": "number", "width": 14},
                {"header": "Total", "field": "total", "kind": "number", "width": 16},
            ]
        return [
            {"header": "Date", "field": "date", "kind": "date", "width": 12},
            {"header": "Bill No", "field": "invoice_no", "kind": "text", "width": 18},
            {"header": "Vendor", "field": "vendor", "kind": "text", "width": 28},
            {"header": "Product", "field": "product", "kind": "text", "width": 26},
            {"header": "Description", "field": "label", "kind": "text", "width": 30},
            {"header": "Qty", "field": "quantity", "kind": "number", "width": 10},
            {"header": "Unit Price", "field": "price_unit", "kind": "number", "width": 14},
            {"header": "Disc %", "field": "discount", "kind": "number", "width": 9},
            {"header": "Untaxed", "field": "untaxed", "kind": "number", "width": 16},
            {"header": "Tax", "field": "tax", "kind": "number", "width": 14},
            {"header": "Total", "field": "total", "kind": "number", "width": 16},
        ]

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
        domain = [
            ("company_id", "in", filters["company_ids"]),
            ("date", ">=", filters["date_from"]),
            ("date", "<=", filters["date_to"]),
            ("move_id.move_type", "in", ("in_invoice", "in_refund")),
            ("display_type", "=", "product"),
        ]
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

        rows = []
        for ml in self.env["account.move.line"].search(domain):
            ptype = self._resolve_purchase_type(ml) if has_ptype else False
            if want_ptype == "unclassified":
                if ptype:
                    continue
            elif want_ptype != "all" and ptype != want_ptype:
                continue
            sign = -1.0 if ml.move_id.move_type == "in_refund" else 1.0
            untaxed = ml.price_subtotal * sign
            total = ml.price_total * sign
            rows.append(
                {
                    "date": ml.date,
                    "invoice_no": ml.move_id.name or "",
                    "ptype": PTYPE_LABELS.get(ptype, UNCLASSIFIED if has_ptype else ""),
                    "vendor": ml.move_id.partner_id.display_name or "",
                    "product": ml.product_id.display_name or "",
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
