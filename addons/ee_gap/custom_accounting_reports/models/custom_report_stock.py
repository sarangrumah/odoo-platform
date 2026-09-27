# -*- coding: utf-8 -*-
"""Stock-side registers pulled from Invoicing ▸ Reporting (sheet #26, #27, #28,
#59, #64, #69, #70).

Six reports over one shared mixin, because they are six windows on the same two
populations and duplicating the plumbing six times is how they drift apart.

Why they live here and not in ``custom_wms_reports``
----------------------------------------------------
The client asked, repeatedly, to pull them from **Invoicing ▸ Reporting**, next
to the Purchase Report. Putting a menuitem for a WMS action under this module's
root would force ``custom_accounting_reports`` to depend on ``custom_wms_reports``
— dragging WMS, cycle counts, barcode and stock_account onto eight accounting
databases that have no warehouse. Building the reports here instead costs one
extra SQL read per report and no dependency at all: every stock access is
guarded at runtime exactly as ``custom.report.purchase._gr_available`` already
does for the goods-receipt basis.

The two populations, and the trap between them
-----------------------------------------------
🔴 **POS sales never create a ``stock.move`` on this tenant.** Measured on
``prd_levis_begbal`` 18-Sep-2026: 82,482 ``pos.order.line`` rows (91,008 units)
against **zero** moves to a customer location. A movement report built on
``stock.move`` alone shows receipts and returns and **not one sale**, while the
running-balance column #64 asks for is meaningless without them. So the movement
report reads ``stock.move`` UNION ``pos.order.line``, and anything that claims to
show "out" must do the same.

🔴 **On-hand is written by the X20 snapshot, not by a movement ledger.** So
"opening ± movement" does not reconcile to ``stock_quant``, and the summary
report carries the difference as its own Adjustment column rather than hiding
it. Saying so in a column is the honest form; silently balancing is not.

⚠️ ``stock_valuation_layer`` does not exist in this database and ``stock_quant``
is the position **now**, so a genuinely historical as-of has to be walked back
from movements. Where a report cannot do that honestly it says which date it is
really answering.
"""

from collections import defaultdict
from datetime import date as date_cls, datetime, time
from itertools import groupby

from odoo import fields, models

_POS_SOLD_STATES = ("paid", "done", "invoiced")

# Movement kinds, in the order Accounting reads them.
KIND_OPENING = "Beginning Balance"
KIND_RECEIPT = "Goods Receive"
KIND_RETURN = "Purchase Return"
KIND_SALE = "Point of Sales"
KIND_TRANSFER_IN = "Internal Transfer In"
KIND_TRANSFER_OUT = "Internal Transfer Out"
KIND_ADJUSTMENT = "Adjustment"
KIND_SCRAP = "Scrap"
KIND_CLOSING = "Ending Balance"


class CustomReportStockMixin(models.AbstractModel):
    """Shared plumbing for the stock registers."""

    _name = "custom.report.stock.mixin"
    _inherit = "custom.report.engine"
    _description = "Custom Stock Report Mixin"

    # ------------------------------------------------------------------
    # Availability guards — this addon must not depend on stock or POS
    # ------------------------------------------------------------------
    def _stock_available(self):
        return "stock.move" in self.env and "stock.quant" in self.env

    def _pos_available(self):
        return "pos.order.line" in self.env

    # ------------------------------------------------------------------
    # Location → warehouse, materialised once
    # ------------------------------------------------------------------
    def _warehouse_by_location(self, company_ids):
        """{location id: warehouse record} for every internal location.

        Built from the ``parent_path`` prefix of each warehouse's view location,
        **once**, into a dict. The live Stock Summary does this as a correlated
        subquery per row and takes 2.5 seconds on raw SQL before the ORM even
        starts — that is sheet #59's "berat untuk ditarik", and this is the fix.
        """
        if not self._stock_available():
            return {}
        Warehouse = self.env["stock.warehouse"].sudo()
        warehouses = Warehouse.search([("company_id", "in", list(company_ids))])
        prefixes = []
        for warehouse in warehouses:
            view = warehouse.view_location_id
            if view and view.parent_path:
                prefixes.append((view.parent_path, warehouse))
        # Longest prefix first: a nested warehouse view must win over its parent.
        prefixes.sort(key=lambda item: len(item[0]), reverse=True)

        locations = self.env["stock.location"].sudo().search([("usage", "=", "internal")])
        mapping = {}
        for location in locations:
            path = location.parent_path or ""
            for prefix, warehouse in prefixes:
                if path.startswith(prefix):
                    mapping[location.id] = warehouse
                    break
        return mapping

    def _unit_costs(self, products, company):
        """{product id: standard_price} read in the company's context."""
        if not products:
            return {}
        return {p.id: p.standard_price for p in products.with_company(company)}

    def _quant_rows(self, filters):
        """On-hand per (warehouse, product) with cost, in one query.

        ``standard_price`` is company-dependent jsonb in Odoo 19, so it is read
        with the company key rather than through 45,000 browse records — that
        alone was seventeen seconds of the position report.
        """
        if not self._stock_available():
            return []
        company_ids = tuple(filters["company_ids"])
        company_key = str(list(company_ids)[0])
        where = ["l.usage = 'internal'", "q.company_id IN %(companies)s", "q.quantity <> 0"]
        params = {"companies": company_ids, "company_key": company_key}
        if filters.get("product_ids"):
            where.append("q.product_id IN %(products)s")
            params["products"] = tuple(filters["product_ids"])
        if filters.get("categ_ids"):
            where.append("pt.categ_id IN %(categs)s")
            params["categs"] = tuple(self._categ_descendants(filters["categ_ids"]))
        self.env.cr.execute(
            """
            SELECT q.location_id, q.product_id, pp.default_code,
                   pt.name->>'en_US', pc.complete_name,
                   SUM(q.quantity),
                   COALESCE((pp.standard_price->>%(company_key)s)::float, 0)
            FROM stock_quant q
            JOIN stock_location l ON l.id = q.location_id
            JOIN product_product pp ON pp.id = q.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN product_category pc ON pc.id = pt.categ_id
            WHERE """
            + " AND ".join(where)
            + """
            GROUP BY 1, 2, 3, 4, 5, 7
            """,
            params,
        )
        return self.env.cr.fetchall()

    def _compute(self, filters=None):
        """Hand the column spec to the PDF, so one template serves all six.

        Every other report in this addon writes its ``<th>`` literally, which is
        why adding a column there forces a ``-u`` on thirteen databases. These
        six render from ``_xlsx_columns()`` instead: the xlsx and the PDF can no
        longer disagree, and a new column is Python only.
        """
        ctx = super()._compute(filters)
        ctx["columns"] = self._xlsx_columns()
        ctx["stock_available"] = self._stock_available()
        ctx["report_note"] = self._report_note()
        return ctx

    def _report_note(self):
        """A caveat printed under the header, or empty."""
        return ""

    def _ou_label(self, warehouse):
        """Operating Unit of a warehouse, where the tenant field exists."""
        if not warehouse or "l10n_ou_analytic_id" not in warehouse._fields:
            return ""
        ou = warehouse.l10n_ou_analytic_id
        return ou.display_name if ou else ""

    # ------------------------------------------------------------------
    # The two populations
    # ------------------------------------------------------------------
    def _move_domain(self, filters, extra=None):
        date_from = fields.Date.to_date(filters["date_from"])
        date_to = fields.Date.to_date(filters["date_to"])
        domain = [
            ("state", "=", "done"),
            ("company_id", "in", list(filters["company_ids"])),
            ("date", ">=", datetime.combine(date_from, time.min)),
            ("date", "<=", datetime.combine(date_to, time.max)),
        ]
        return domain + (extra or [])

    def _pos_lines(self, filters, product_ids=None, warehouse_ids=None, categ_ids=None):
        """Sold quantity per (date, warehouse, product, order), in one query.

        The sale side of every stock register — there is no stock move to read,
        see the module docstring. Raw SQL rather than ``search`` + browse: this
        tenant has 82,482 POS lines and the ORM round-trip alone put the
        movement report over twenty seconds, which is the very complaint (#59)
        these reports exist to answer.
        """
        if not self._pos_available():
            return []
        date_from = fields.Date.to_date(filters["date_from"])
        date_to = fields.Date.to_date(filters["date_to"])
        where = [
            "o.state IN %(states)s",
            "o.date_order >= %(date_from)s",
            "o.date_order <= %(date_to)s",
            "l.company_id IN %(companies)s",
        ]
        params = {
            "states": _POS_SOLD_STATES,
            "date_from": datetime.combine(date_from, time.min),
            "date_to": datetime.combine(date_to, time.max),
            "companies": tuple(filters["company_ids"]),
        }
        if product_ids:
            where.append("l.product_id IN %(products)s")
            params["products"] = tuple(product_ids)
        if categ_ids:
            where.append("pt.categ_id IN %(categs)s")
            params["categs"] = tuple(self._categ_descendants(categ_ids))
        if warehouse_ids:
            where.append("cfg.warehouse_id IN %(warehouses)s")
            params["warehouses"] = tuple(warehouse_ids)
        self.env.cr.execute(
            """
            SELECT o.date_order::date, cfg.warehouse_id, w.name, l.product_id,
                   pp.default_code, pt.name->>'en_US', pc.complete_name,
                   o.name, SUM(l.qty)
            FROM pos_order_line l
            JOIN pos_order o ON o.id = l.order_id
            JOIN pos_session s ON s.id = o.session_id
            JOIN pos_config cfg ON cfg.id = s.config_id
            LEFT JOIN stock_warehouse w ON w.id = cfg.warehouse_id
            JOIN product_product pp ON pp.id = l.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN product_category pc ON pc.id = pt.categ_id
            WHERE """
            + " AND ".join(where)
            + """
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
            """,
            params,
        )
        return [
            {
                "date": row[0],
                "warehouse_id": row[1] or 0,
                "warehouse": row[2] or "",
                "product_id": row[3],
                "item_code": row[4] or "",
                "product": row[5] or "",
                "categ": row[6] or "",
                "doc": row[7] or "",
                "qty": row[8] or 0.0,
            }
            for row in self.env.cr.fetchall()
        ]

    def _categ_descendants(self, categ_ids):
        return set(self.env["product.category"].sudo().search([("id", "child_of", list(categ_ids))]).ids)


class CustomReportStockMovement(models.AbstractModel):
    """#64 — every movement of an item at a warehouse, with a running balance."""

    _name = "custom.report.stock.movement"
    _inherit = "custom.report.stock.mixin"
    _description = "Movement Inventory Detail"

    _report_code = "stock_movement"
    _report_title = "Movement Inventory Detail"

    def _report_note(self):
        return (
            "Penjualan POS tidak membuat stock move di Odoo, jadi baris Point of Sales "
            "dibaca dari pos.order.line. On-hand sendiri ditulis snapshot X20, sehingga "
            "'saldo awal ± pergerakan' tidak selalu sama dengan on-hand."
        )

    def _xlsx_columns(self):
        return [
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "Warehouse", "field": "warehouse", "kind": "text", "width": 26},
            {"header": "Tipe Transaksi", "field": "kind", "kind": "text", "width": 20},
            {"header": "Nomor Transaksi", "field": "doc", "kind": "text", "width": 24},
            {"header": "Deskripsi", "field": "label", "kind": "text", "width": 32},
            {"header": "Item Code", "field": "item_code", "kind": "text", "width": 16},
            {"header": "Product Category", "field": "categ", "kind": "text", "width": 28},
            {"header": "Quantity In", "field": "qty_in", "kind": "number", "width": 13},
            {"header": "Quantity Out", "field": "qty_out", "kind": "number", "width": 13},
            {"header": "Balance Stock", "field": "balance", "kind": "number", "width": 15},
        ]

    def _movement_rows(self, filters):
        """Every movement in the window, one SQL read plus the POS side.

        Browsing ``stock.move`` record by record took 22 seconds over 46,500
        receipts on prd_levis_begbal. The classification below is the same one
        the ORM version made, moved into the join.
        """
        if not self._stock_available():
            return []
        product_ids = filters.get("product_ids") or []
        warehouse_ids = set(filters.get("warehouse_ids") or [])
        categ_ids = filters.get("categ_ids") or []
        date_from = fields.Date.to_date(filters["date_from"])
        date_to = fields.Date.to_date(filters["date_to"])

        where = [
            "m.state = 'done'",
            "m.company_id IN %(companies)s",
            "m.date >= %(date_from)s",
            "m.date <= %(date_to)s",
            "(ls.usage IN ('internal', 'supplier', 'inventory') OR ld.usage IN ('internal', 'supplier', 'inventory'))",
        ]
        params = {
            "companies": tuple(filters["company_ids"]),
            "date_from": datetime.combine(date_from, time.min),
            "date_to": datetime.combine(date_to, time.max),
        }
        if product_ids:
            where.append("m.product_id IN %(products)s")
            params["products"] = tuple(product_ids)
        if categ_ids:
            where.append("pt.categ_id IN %(categs)s")
            params["categs"] = tuple(self._categ_descendants(categ_ids))

        self.env.cr.execute(
            """
            SELECT m.date::date, m.product_id, pp.default_code, pc.complete_name,
                   COALESCE(sp.name, m.inventory_name, m.reference, ''),
                   COALESCE(sp.origin, m.reference, ''),
                   m.quantity, ls.id, ld.id, ls.usage, ld.usage,
                   m.is_inventory, m.scrap_id
            FROM stock_move m
            JOIN stock_location ls ON ls.id = m.location_id
            JOIN stock_location ld ON ld.id = m.location_dest_id
            JOIN product_product pp ON pp.id = m.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN product_category pc ON pc.id = pt.categ_id
            LEFT JOIN stock_picking sp ON sp.id = m.picking_id
            WHERE """
            + " AND ".join(where)
            + """
            ORDER BY m.date, m.id
            """,
            params,
        )
        raw = self.env.cr.fetchall()

        wh_by_loc = self._warehouse_by_location(filters["company_ids"])
        rows = []
        for (
            when,
            product_id,
            code,
            categ,
            doc,
            label,
            qty,
            src_id,
            dst_id,
            src_usage,
            dst_usage,
            is_inventory,
            scrap_id,
        ) in raw:
            qty = float(qty or 0.0)
            if not qty:
                continue
            src_wh = wh_by_loc.get(src_id)
            dst_wh = wh_by_loc.get(dst_id)

            def _row(kind, warehouse, signed):
                return {
                    "date": when,
                    "warehouse": warehouse.display_name if warehouse else "",
                    "warehouse_id": warehouse.id if warehouse else 0,
                    "kind": kind,
                    "doc": doc or "",
                    "label": label or "",
                    "item_code": code or "",
                    "product_id": product_id,
                    "categ": categ or "",
                    "signed": signed,
                }

            if scrap_id:
                kind, warehouse, sign = KIND_SCRAP, src_wh, -1
            elif is_inventory:
                kind = KIND_ADJUSTMENT
                warehouse = src_wh or dst_wh
                sign = 1 if dst_usage == "internal" else -1
            elif src_usage == "supplier" and dst_usage == "internal":
                kind, warehouse, sign = KIND_RECEIPT, dst_wh, 1
            elif src_usage == "internal" and dst_usage == "supplier":
                kind, warehouse, sign = KIND_RETURN, src_wh, -1
            elif src_usage == "internal" and dst_usage == "internal":
                # One transfer, two rows: it leaves one warehouse and enters
                # another, and a per-warehouse balance that sees only one half
                # is wrong on both sides.
                if src_wh and dst_wh and src_wh != dst_wh:
                    if not warehouse_ids or src_wh.id in warehouse_ids:
                        rows.append(_row(KIND_TRANSFER_OUT, src_wh, -qty))
                    if not warehouse_ids or dst_wh.id in warehouse_ids:
                        rows.append(_row(KIND_TRANSFER_IN, dst_wh, qty))
                continue
            else:
                continue

            if warehouse_ids and (not warehouse or warehouse.id not in warehouse_ids):
                continue
            rows.append(_row(kind, warehouse, qty * sign))

        for pos in self._pos_lines(filters, product_ids, warehouse_ids or None, categ_ids or None):
            rows.append(
                {
                    "date": pos["date"],
                    "warehouse": pos["warehouse"],
                    "warehouse_id": pos["warehouse_id"],
                    "kind": KIND_SALE,
                    "doc": pos["doc"],
                    "label": "Penjualan POS",
                    "item_code": pos["item_code"],
                    "product_id": pos["product_id"],
                    "categ": pos["categ"],
                    "signed": -(pos["qty"] or 0.0),
                }
            )
        return rows

    def _build_lines(self, filters):
        rows = self._movement_rows(filters)
        if not rows:
            return [{"type": "grand_total", "kind": "Grand Total", "qty_in": 0.0, "qty_out": 0.0, "balance": 0.0}]

        # One running balance per (warehouse, product): a balance summed across
        # items is not a stock position, it is a number that happens to add up.
        rows.sort(key=lambda r: (r["warehouse"], r["item_code"], r["date"] or date_cls.min, r["doc"]))
        lines = []
        total_in = total_out = 0.0
        for (warehouse, item_code), group in groupby(rows, key=lambda r: (r["warehouse"], r["item_code"])):
            group = list(group)
            balance = 0.0
            lines.append(
                {
                    "type": "subtotal",
                    "warehouse": warehouse,
                    "item_code": item_code,
                    "kind": KIND_OPENING,
                    "categ": group[0]["categ"],
                    "balance": 0.0,
                }
            )
            for row in group:
                signed = row["signed"]
                balance += signed
                total_in += signed if signed > 0 else 0.0
                total_out += signed if signed < 0 else 0.0
                lines.append(
                    {
                        "date": row["date"],
                        "warehouse": row["warehouse"],
                        "kind": row["kind"],
                        "doc": row["doc"],
                        "label": row["label"],
                        "item_code": row["item_code"],
                        "categ": row["categ"],
                        "qty_in": signed if signed > 0 else "",
                        "qty_out": signed if signed < 0 else "",
                        "balance": balance,
                    }
                )
            lines.append(
                {
                    "type": "subtotal",
                    "warehouse": warehouse,
                    "item_code": item_code,
                    "kind": KIND_CLOSING,
                    "categ": group[0]["categ"],
                    "balance": balance,
                }
            )
        lines.append(
            {
                "type": "grand_total",
                "kind": "Grand Total",
                "qty_in": total_in,
                "qty_out": total_out,
                "balance": total_in + total_out,
            }
        )
        return lines


class CustomReportInventorySummary(models.AbstractModel):
    """#27 / #59 — every warehouse in one pull, with the period's movement."""

    _name = "custom.report.inventory.summary"
    _inherit = "custom.report.stock.mixin"
    _description = "Summary Inventory"

    _report_code = "inventory_summary"
    _report_title = "Summary Inventory"

    def _xlsx_columns(self):
        return [
            {"header": "Warehouse", "field": "warehouse", "kind": "text", "width": 26},
            {"header": "Operating Unit", "field": "ou", "kind": "text", "width": 24},
            {"header": "Item Code", "field": "item_code", "kind": "text", "width": 16},
            {"header": "Item Name", "field": "product", "kind": "text", "width": 32},
            {"header": "Product Category", "field": "categ", "kind": "text", "width": 26},
            {"header": "Beginning Qty", "field": "begin_qty", "kind": "number", "width": 13},
            {"header": "In Qty", "field": "in_qty", "kind": "number", "width": 11},
            {"header": "Out Qty", "field": "out_qty", "kind": "number", "width": 11},
            {"header": "Adjustment Qty", "field": "adj_qty", "kind": "number", "width": 14},
            {"header": "Ending Qty", "field": "end_qty", "kind": "number", "width": 12},
            {"header": "Unit Cost", "field": "cost", "kind": "number", "width": 14},
            {"header": "Ending Value", "field": "end_value", "kind": "number", "width": 18},
        ]

    def _group_key(self, row, group_by):
        if group_by == "warehouse":
            return row.get("warehouse") or "—"
        if group_by == "category":
            return row.get("categ") or "—"
        return None

    def _build_lines(self, filters):
        if not self._stock_available():
            return [{"type": "grand_total", "warehouse": "Grand Total"}]

        movement = self.env["custom.report.stock.movement"]
        rows = movement._movement_rows(filters)

        # Movement, split the way the client's template asks: In, Out, and the
        # Adjustment bucket that makes the arithmetic close honestly.
        buckets = defaultdict(lambda: {"in": 0.0, "out": 0.0, "adj": 0.0})
        for row in rows:
            key = (row["warehouse_id"], row["product_id"])
            signed = row["signed"]
            if row["kind"] in (KIND_ADJUSTMENT, KIND_SCRAP):
                buckets[key]["adj"] += signed
            elif signed > 0:
                buckets[key]["in"] += signed
            else:
                buckets[key]["out"] += signed

        wh_by_loc = self._warehouse_by_location(filters["company_ids"])
        warehouse_ids = set(filters.get("warehouse_ids") or [])
        ending = defaultdict(float)
        meta = {}
        for location_id, product_id, code, name, categ, qty, cost in self._quant_rows(filters):
            warehouse = wh_by_loc.get(location_id)
            if warehouse_ids and (not warehouse or warehouse.id not in warehouse_ids):
                continue
            key = (warehouse.id if warehouse else 0, product_id)
            ending[key] += float(qty or 0.0)
            meta[key] = (warehouse, code or "", name or "", categ or "", cost or 0.0)

        # A (warehouse, item) that moved but holds nothing today still belongs
        # in the report — that is exactly the line Accounting looks for.
        missing = [key for key in buckets if key not in meta]
        if missing:
            self.env.cr.execute(
                """
                SELECT pp.id, pp.default_code, pt.name->>'en_US', pc.complete_name,
                       COALESCE((pp.standard_price->>%s)::float, 0)
                FROM product_product pp
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN product_category pc ON pc.id = pt.categ_id
                WHERE pp.id IN %s
                """,
                (str(list(filters["company_ids"])[0]), tuple({key[1] for key in missing})),
            )
            extra = {row[0]: row[1:] for row in self.env.cr.fetchall()}
            warehouses = {
                wh.id: wh
                for wh in self.env["stock.warehouse"].browse(list({key[0] for key in missing if key[0]})).exists()
            }
            for key in missing:
                info = extra.get(key[1])
                if not info:
                    continue
                ending.setdefault(key, 0.0)
                meta[key] = (warehouses.get(key[0]), info[0] or "", info[1] or "", info[2] or "", info[3] or 0.0)

        lines = []
        totals = defaultdict(float)
        for key, end_qty in ending.items():
            info = meta.get(key)
            if not info:
                continue
            warehouse, code, name, categ, cost = info
            bucket = buckets.get(key, {"in": 0.0, "out": 0.0, "adj": 0.0})
            # Derived, not read: there is no historical position in this
            # database, so beginning is what the movement implies.
            row = {
                "warehouse": warehouse.display_name if warehouse else "(tanpa warehouse)",
                "ou": self._ou_label(warehouse),
                "item_code": code,
                "product": name,
                "categ": categ,
                "begin_qty": end_qty - bucket["in"] - bucket["out"] - bucket["adj"],
                "in_qty": bucket["in"],
                "out_qty": bucket["out"],
                "adj_qty": bucket["adj"],
                "end_qty": end_qty,
                "cost": cost,
                "end_value": end_qty * cost,
            }
            lines.append(row)
            for field in ("begin_qty", "in_qty", "out_qty", "adj_qty", "end_qty", "end_value"):
                totals[field] += row[field]

        group_by = filters.get("group_by") or "none"
        if group_by == "none":
            lines.sort(key=lambda r: (r["warehouse"], r["item_code"]))
        else:
            grouped = []
            lines.sort(key=lambda r: (self._group_key(r, group_by) or "", r["item_code"]))
            for key, group in groupby(lines, key=lambda r: self._group_key(r, group_by)):
                group = list(group)
                grouped.extend(group)
                subtotal = {"type": "subtotal", "warehouse": "Subtotal: %s" % (key or "—")}
                for field in ("begin_qty", "in_qty", "out_qty", "adj_qty", "end_qty", "end_value"):
                    subtotal[field] = sum(r[field] for r in group)
                grouped.append(subtotal)
            lines = grouped

        grand = {"type": "grand_total", "warehouse": "Grand Total"}
        grand.update(totals)
        lines.append(grand)
        return lines


class CustomReportInventoryWarehouse(models.AbstractModel):
    """#28 — the position per warehouse, every warehouse in one pull."""

    _name = "custom.report.inventory.warehouse"
    _inherit = "custom.report.stock.mixin"
    _description = "Inventory per Warehouse"

    _report_code = "inventory_warehouse"
    _report_title = "Inventory per Warehouse"

    def _xlsx_columns(self):
        return [
            {"header": "Warehouse", "field": "warehouse", "kind": "text", "width": 26},
            {"header": "Operating Unit", "field": "ou", "kind": "text", "width": 24},
            {"header": "Item Code", "field": "item_code", "kind": "text", "width": 16},
            {"header": "Item Name", "field": "product", "kind": "text", "width": 34},
            {"header": "Product Category", "field": "categ", "kind": "text", "width": 26},
            {"header": "Qty On Hand", "field": "qty", "kind": "number", "width": 13},
            {"header": "Unit Cost", "field": "cost", "kind": "number", "width": 14},
            {"header": "Total Value", "field": "value", "kind": "number", "width": 18},
        ]

    def _group_key(self, row, group_by):
        if group_by == "category":
            return row.get("categ") or "—"
        return row.get("warehouse") or "—"

    def _build_lines(self, filters):
        if not self._stock_available():
            return [{"type": "grand_total", "warehouse": "Grand Total", "qty": 0.0, "value": 0.0}]

        wh_by_loc = self._warehouse_by_location(filters["company_ids"])
        warehouse_ids = set(filters.get("warehouse_ids") or [])

        per_key = defaultdict(float)
        meta = {}
        for location_id, product_id, code, name, categ, qty, cost in self._quant_rows(filters):
            warehouse = wh_by_loc.get(location_id)
            if warehouse_ids and (not warehouse or warehouse.id not in warehouse_ids):
                continue
            key = (warehouse.id if warehouse else 0, product_id)
            per_key[key] += float(qty or 0.0)
            meta[key] = (warehouse, code or "", name or "", categ or "", cost or 0.0)

        rows = []
        for key, qty in per_key.items():
            warehouse, code, name, categ, cost = meta[key]
            rows.append(
                {
                    "warehouse": warehouse.display_name if warehouse else "(tanpa warehouse)",
                    "ou": self._ou_label(warehouse),
                    "item_code": code,
                    "product": name,
                    "categ": categ,
                    "qty": qty,
                    "cost": cost,
                    "value": qty * cost,
                }
            )

        group_by = filters.get("group_by") or "warehouse"
        rows.sort(key=lambda r: (self._group_key(r, group_by) or "", r["item_code"]))
        lines = []
        g_qty = g_value = 0.0
        for key, group in groupby(rows, key=lambda r: self._group_key(r, group_by)):
            group = list(group)
            s_qty = sum(r["qty"] for r in group)
            s_value = sum(r["value"] for r in group)
            lines.extend(group)
            lines.append(
                {"type": "subtotal", "warehouse": "Subtotal: %s" % (key or "—"), "qty": s_qty, "value": s_value}
            )
            g_qty += s_qty
            g_value += s_value
        lines.append({"type": "grand_total", "warehouse": "Grand Total", "qty": g_qty, "value": g_value})
        return lines


class CustomReportPurchaseReturn(models.AbstractModel):
    """#26 — returns to the vendor, read from the stock side.

    🔴 The source is stock, **not** credit notes, and the two cannot be joined.
    On ``prd_levis_begbal`` there are 3 posted ``in_refund`` documents (all
    27-Jul, invoice cancellations of non-trade bills) whose six product lines
    carry **no** ``purchase_line_id`` at all, and 200 return stock moves (06-Aug)
    from a trade PO. Nothing connects them; any join would be invented. So the
    credit-note column is structurally empty here and says so.
    """

    _name = "custom.report.purchase.return"
    _inherit = "custom.report.stock.mixin"
    _description = "Purchase Return Report"

    _report_code = "purchase_return"
    _report_title = "Purchase Return Report"

    def _report_note(self):
        return (
            "Peringatan kualitas data: sebagian baris retur 06-Agu-2026 membawa "
            "kuantitas yang sebenarnya HARGA (sisa insiden PO tertukar qty/harga). "
            "Angkanya ditampilkan apa adanya — jangan dipakai sebagai acuan nilai "
            "sebelum PO-nya dikoreksi."
        )

    def _xlsx_columns(self):
        return [
            {"header": "Tanggal Retur", "field": "date", "kind": "date", "width": 13},
            {"header": "Nomor Retur", "field": "doc", "kind": "text", "width": 22},
            {"header": "No. PO", "field": "po_no", "kind": "text", "width": 22},
            {"header": "Vendor", "field": "vendor", "kind": "text", "width": 30},
            {"header": "Vendor Ref", "field": "vendor_ref", "kind": "text", "width": 16},
            {"header": "Warehouse", "field": "warehouse", "kind": "text", "width": 26},
            {"header": "Item Code", "field": "item_code", "kind": "text", "width": 16},
            {"header": "Item Name", "field": "product", "kind": "text", "width": 30},
            {"header": "Product Category", "field": "categ", "kind": "text", "width": 26},
            {"header": "Qty Retur", "field": "qty", "kind": "number", "width": 11},
            {"header": "Unit Cost", "field": "cost", "kind": "number", "width": 14},
            {"header": "Value", "field": "value", "kind": "number", "width": 16},
            {"header": "No. GR Asal", "field": "origin", "kind": "text", "width": 22},
            {"header": "No. Credit Note", "field": "credit_note", "kind": "text", "width": 18},
        ]

    def _group_key(self, row, group_by):
        if group_by == "vendor":
            return row.get("vendor") or "—"
        if group_by == "warehouse":
            return row.get("warehouse") or "—"
        if group_by == "month":
            return row["date"].strftime("%Y-%m") if row.get("date") else "—"
        return None

    def _build_lines(self, filters):
        if not self._stock_available():
            return [{"type": "grand_total", "doc": "Grand Total", "qty": 0.0, "value": 0.0}]

        extra = [("location_dest_id.usage", "=", "supplier"), ("location_id.usage", "=", "internal")]
        if filters.get("partner_ids"):
            extra.append(("purchase_line_id.order_id.partner_id", "in", list(filters["partner_ids"])))
        moves = self.env["stock.move"].sudo().search(self._move_domain(filters, extra), order="date, id")

        wh_by_loc = self._warehouse_by_location(filters["company_ids"])
        company = self.env["res.company"].browse(list(filters["company_ids"])[0])
        costs = self._unit_costs(moves.mapped("product_id"), company)
        warehouse_ids = set(filters.get("warehouse_ids") or [])

        rows = []
        for move in moves:
            warehouse = wh_by_loc.get(move.location_id.id)
            if warehouse_ids and (not warehouse or warehouse.id not in warehouse_ids):
                continue
            order = move.purchase_line_id.order_id
            qty = move.quantity or 0.0
            # move.value is the receipt's own valuation where stock_account
            # wrote one; standard_price is the honest fallback.
            value = (
                abs(move.value) if "value" in move._fields and move.value else qty * costs.get(move.product_id.id, 0.0)
            )
            rows.append(
                {
                    "date": move.date.date() if move.date else None,
                    "doc": move.picking_id.name or move.reference or "",
                    "po_no": order.name or "",
                    "vendor": order.partner_id.display_name or "",
                    "vendor_ref": order.partner_ref or "",
                    "warehouse": warehouse.display_name if warehouse else "",
                    "item_code": move.product_id.default_code or "",
                    "product": move.product_id.name or "",
                    "categ": move.product_id.categ_id.complete_name or "",
                    "qty": qty,
                    "cost": (value / qty) if qty else 0.0,
                    "value": value,
                    "origin": move.picking_id.origin or "",
                    "credit_note": "",
                }
            )
        return self._flat_with_totals(rows, filters, ("qty", "value"), label_field="doc")

    def _flat_with_totals(self, rows, filters, numeric_fields, label_field):
        """Shared tail: optional grouping, subtotals, grand total."""
        group_by = filters.get("group_by") or "none"
        lines = []
        totals = defaultdict(float)
        if group_by == "none":
            for row in sorted(rows, key=lambda r: (r.get("date") or date_cls.min, r.get(label_field) or "")):
                lines.append(row)
                for field in numeric_fields:
                    totals[field] += row.get(field) or 0.0
        else:
            rows.sort(key=lambda r: (self._group_key(r, group_by) or "", r.get("date") or date_cls.min))
            for key, group in groupby(rows, key=lambda r: self._group_key(r, group_by)):
                group = list(group)
                lines.extend(group)
                subtotal = {"type": "subtotal", label_field: "Subtotal: %s" % (key or "—")}
                for field in numeric_fields:
                    subtotal[field] = sum(r.get(field) or 0.0 for r in group)
                    totals[field] += subtotal[field]
                lines.append(subtotal)
        grand = {"type": "grand_total", label_field: "Grand Total"}
        grand.update(totals)
        lines.append(grand)
        return lines


class CustomReportStockTransfer(models.AbstractModel):
    """#69 — internal transfers between locations and warehouses."""

    _name = "custom.report.stock.transfer"
    _inherit = "custom.report.stock.mixin"
    _description = "Internal Transfer Stock Detail"

    _report_code = "stock_transfer"
    _report_title = "Internal Transfer Stock Detail"

    def _xlsx_columns(self):
        return [
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "Nomor Transaksi", "field": "doc", "kind": "text", "width": 22},
            {"header": "Warehouse Asal", "field": "wh_from", "kind": "text", "width": 24},
            {"header": "Lokasi Asal", "field": "loc_from", "kind": "text", "width": 24},
            {"header": "Warehouse Tujuan", "field": "wh_to", "kind": "text", "width": 24},
            {"header": "Lokasi Tujuan", "field": "loc_to", "kind": "text", "width": 24},
            {"header": "Item Code", "field": "item_code", "kind": "text", "width": 16},
            {"header": "Item Name", "field": "product", "kind": "text", "width": 30},
            {"header": "Product Category", "field": "categ", "kind": "text", "width": 26},
            {"header": "Quantity", "field": "qty", "kind": "number", "width": 11},
            {"header": "Unit Cost", "field": "cost", "kind": "number", "width": 14},
            {"header": "Value", "field": "value", "kind": "number", "width": 16},
            {"header": "Keterangan", "field": "label", "kind": "text", "width": 28},
        ]

    def _group_key(self, row, group_by):
        if group_by == "warehouse":
            return row.get("wh_from") or "—"
        if group_by == "month":
            return row["date"].strftime("%Y-%m") if row.get("date") else "—"
        return None

    def _build_lines(self, filters):
        if not self._stock_available():
            return [{"type": "grand_total", "doc": "Grand Total", "qty": 0.0, "value": 0.0}]

        extra = [
            ("location_id.usage", "=", "internal"),
            ("location_dest_id.usage", "=", "internal"),
            ("is_inventory", "=", False),
        ]
        moves = self.env["stock.move"].sudo().search(self._move_domain(filters, extra), order="date, id")
        wh_by_loc = self._warehouse_by_location(filters["company_ids"])
        company = self.env["res.company"].browse(list(filters["company_ids"])[0])
        costs = self._unit_costs(moves.mapped("product_id"), company)
        warehouse_ids = set(filters.get("warehouse_ids") or [])

        rows = []
        for move in moves:
            src_wh = wh_by_loc.get(move.location_id.id)
            dst_wh = wh_by_loc.get(move.location_dest_id.id)
            if warehouse_ids and not (
                (src_wh and src_wh.id in warehouse_ids) or (dst_wh and dst_wh.id in warehouse_ids)
            ):
                continue
            qty = move.quantity or 0.0
            cost = costs.get(move.product_id.id, 0.0)
            rows.append(
                {
                    "date": move.date.date() if move.date else None,
                    "doc": move.picking_id.name or move.reference or "",
                    "wh_from": src_wh.display_name if src_wh else "",
                    "loc_from": move.location_id.complete_name or "",
                    "wh_to": dst_wh.display_name if dst_wh else "",
                    "loc_to": move.location_dest_id.complete_name or "",
                    "item_code": move.product_id.default_code or "",
                    "product": move.product_id.name or "",
                    "categ": move.product_id.categ_id.complete_name or "",
                    "qty": qty,
                    "cost": cost,
                    "value": qty * cost,
                    "label": move.picking_id.origin or "",
                }
            )
        return self.env["custom.report.purchase.return"]._flat_with_totals(
            rows, filters, ("qty", "value"), label_field="doc"
        )


class CustomReportStockAdjustment(models.AbstractModel):
    """#70 — inventory adjustments and scrap, with their expense account."""

    _name = "custom.report.stock.adjustment"
    _inherit = "custom.report.stock.mixin"
    _description = "Adjustment & Scrap Stock Report"

    _report_code = "stock_adjustment"
    _report_title = "Adjustment & Scrap Stock Report"

    def _xlsx_columns(self):
        return [
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "Tipe", "field": "kind", "kind": "text", "width": 13},
            {"header": "Nomor Transaksi", "field": "doc", "kind": "text", "width": 24},
            {"header": "Warehouse", "field": "warehouse", "kind": "text", "width": 24},
            {"header": "Lokasi", "field": "location", "kind": "text", "width": 24},
            {"header": "Item Code", "field": "item_code", "kind": "text", "width": 16},
            {"header": "Item Name", "field": "product", "kind": "text", "width": 30},
            {"header": "Product Category", "field": "categ", "kind": "text", "width": 26},
            {"header": "Qty Selisih", "field": "qty", "kind": "number", "width": 12},
            {"header": "Unit Cost", "field": "cost", "kind": "number", "width": 14},
            {"header": "Value", "field": "value", "kind": "number", "width": 16},
            {"header": "Alasan", "field": "reason", "kind": "text", "width": 26},
            {"header": "COA Beban", "field": "account", "kind": "text", "width": 26},
        ]

    def _group_key(self, row, group_by):
        if group_by == "warehouse":
            return row.get("warehouse") or "—"
        if group_by == "kind":
            return row.get("kind") or "—"
        if group_by == "month":
            return row["date"].strftime("%Y-%m") if row.get("date") else "—"
        return None

    def _build_lines(self, filters):
        if not self._stock_available():
            return [{"type": "grand_total", "doc": "Grand Total", "qty": 0.0, "value": 0.0}]

        want = filters.get("adjustment_kind") or "all"
        wh_by_loc = self._warehouse_by_location(filters["company_ids"])
        company = self.env["res.company"].browse(list(filters["company_ids"])[0])
        warehouse_ids = set(filters.get("warehouse_ids") or [])

        moves = (
            self.env["stock.move"]
            .sudo()
            .search(self._move_domain(filters, [("is_inventory", "=", True)]), order="date, id")
        )
        scraps = (
            self.env["stock.move"]
            .sudo()
            .search(self._move_domain(filters, [("scrap_id", "!=", False)]), order="date, id")
        )
        costs = self._unit_costs((moves | scraps).mapped("product_id"), company)

        # The account an adjustment books against lives on the virtual location
        # (sheet #71), not on the product category.
        adjustment_account = ""
        virtual = self.env["stock.location"].sudo().search([("usage", "=", "inventory")], limit=1)
        if virtual and virtual.valuation_account_id:
            account = virtual.valuation_account_id.with_company(company)
            adjustment_account = "%s %s" % (account.code or "", account.name or "")

        rows = []
        for move in moves:
            if want == "scrap":
                continue
            internal = move.location_id if move.location_id.usage == "internal" else move.location_dest_id
            warehouse = wh_by_loc.get(internal.id)
            if warehouse_ids and (not warehouse or warehouse.id not in warehouse_ids):
                continue
            qty = (move.quantity or 0.0) * (1 if move.location_dest_id.usage == "internal" else -1)
            cost = costs.get(move.product_id.id, 0.0)
            rows.append(
                {
                    "date": move.date.date() if move.date else None,
                    "kind": "Adjustment",
                    "doc": move.inventory_name or move.reference or "",
                    "warehouse": warehouse.display_name if warehouse else "",
                    "location": internal.complete_name or "",
                    "item_code": move.product_id.default_code or "",
                    "product": move.product_id.name or "",
                    "categ": move.product_id.categ_id.complete_name or "",
                    "qty": qty,
                    "cost": cost,
                    "value": qty * cost,
                    "reason": move.inventory_name or "",
                    "account": adjustment_account,
                }
            )
        for move in scraps:
            if want == "adjustment":
                continue
            scrap = move.scrap_id
            warehouse = wh_by_loc.get(move.location_id.id)
            if warehouse_ids and (not warehouse or warehouse.id not in warehouse_ids):
                continue
            qty = -(move.quantity or 0.0)
            cost = costs.get(move.product_id.id, 0.0)
            rows.append(
                {
                    "date": move.date.date() if move.date else None,
                    "kind": "Scrap",
                    "doc": scrap.name or move.reference or "",
                    "warehouse": warehouse.display_name if warehouse else "",
                    "location": move.location_id.complete_name or "",
                    "item_code": move.product_id.default_code or "",
                    "product": move.product_id.name or "",
                    "categ": move.product_id.categ_id.complete_name or "",
                    "qty": qty,
                    "cost": cost,
                    "value": qty * cost,
                    "reason": self._opt(scrap, "scrap_reason_tag_ids")
                    and ", ".join(scrap.scrap_reason_tag_ids.mapped("name"))
                    or "",
                    "account": adjustment_account,
                }
            )
        return self.env["custom.report.purchase.return"]._flat_with_totals(
            rows, filters, ("qty", "value"), label_field="doc"
        )
