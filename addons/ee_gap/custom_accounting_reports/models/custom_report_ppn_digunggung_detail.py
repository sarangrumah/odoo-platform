# -*- coding: utf-8 -*-
"""Rincian PPN Keluaran Digunggung sampai nomor transaksi.

``custom.report.ppn.digunggung`` reports the masa the way the SPT wants it:
aggregated, one line per period and one line per store per day. That is the
filing figure, but it is not an audit trail — a store day is still thousands of
struk deep, and when Finance or a tax auditor asks *"which transaction makes up
this rupiah"* there is nothing under the daily line to point at.

This report is that layer. One row per **transaction number**, with the same
PMK 131/2024 presentation (12% on a DPP Nilai Lain of 11/12), grouped by masa
so every block still adds up to the number carried into the SPT Masa PPN 1111.

Where the transaction number lives depends on how the sale was booked:

* **POS (PKP Pedagang Eceran).** Odoo posts *one* journal entry per session,
  so the GL stops at the session — the struk number only exists on
  ``pos.order``. Session entries are therefore expanded into their orders:
  ``No. Transaksi`` is the order name, ``No. Struk`` its ``pos_reference``.
  Per-order figures come from the order lines (``price_subtotal`` and
  ``price_subtotal_incl``), which tie to ``amount_tax`` to the rupiah.
* **Anything else** — a manual sales entry carrying output VAT — has its own
  journal entry, so it stays one row keyed on the move name.

The two sources never overlap: a session move is replaced by its orders, never
reported alongside them. Orders already invoiced (``state == 'invoiced'``) are
excluded, exactly as the recap excludes ``out_invoice``: those carry a buyer
identity and belong to ``custom.report.faktur.pajak`` plus the FK export.

Because the ledger rounds tax per struk while the report restates the masa, the
detail can differ from the GL by a few rupiah per period. That is disclosed
rather than hidden: a `Selisih pembulatan vs GL` note line appears under a masa
whose detail does not match its ledger figure to the rupiah.
"""

from __future__ import annotations

from collections import defaultdict

from odoo import models

from .custom_report_ppn_digunggung import MONTHS_ID, PMK_131_STATUTORY_RATE


class CustomReportPpnDigunggungDetail(models.AbstractModel):
    _name = "custom.report.ppn.digunggung.detail"
    _inherit = "custom.report.ppn.digunggung"
    _description = "Rincian PPN Keluaran Digunggung per Transaksi"

    _report_code = "ppn_digunggung_detail"
    _report_title = "Rincian PPN Keluaran Digunggung per Transaksi"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _xlsx_columns(self):
        return [
            {"header": "Masa Pajak", "field": "masa", "kind": "text", "width": 12},
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "No. Transaksi", "field": "doc_no", "kind": "text", "width": 34},
            {"header": "No. Struk / Ref", "field": "doc_ref", "kind": "text", "width": 20},
            {"header": "Sumber", "field": "source", "kind": "text", "width": 30},
            {"header": "Kode Toko", "field": "ou_code", "kind": "text", "width": 10},
            {"header": "Toko / Operating Unit", "field": "ou_name", "kind": "text", "width": 32},
            {"header": "Harga Jual (DPP Penuh)", "field": "dpp_penuh", "kind": "number", "width": 22},
            {"header": "DPP Nilai Lain", "field": "dpp_lain", "kind": "number", "width": 20},
            {"header": "Tarif", "field": "tarif", "kind": "number", "width": 8},
            {"header": "PPN Keluaran", "field": "ppn", "kind": "number", "width": 20},
        ]

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _build_lines(self, filters):
        taxes = self.env["account.tax"].browse(
            self.env["custom.report.faktur.pajak"]._ppn_tax_ids("sale", filters["company_ids"])
        )
        if not taxes:
            return [
                {"type": "note", "masa": "Tidak ada pajak PPN Keluaran pada perusahaan terpilih."},
                self._detail_grand_total(0.0, 0.0, 0.0),
            ]

        gl_by_move = self._gl_by_move(filters, taxes)
        if not gl_by_move:
            return [
                {"type": "note", "masa": "Tidak ada penyerahan digunggung pada periode ini."},
                self._detail_grand_total(0.0, 0.0, 0.0),
            ]

        sessions = self._sessions_for_moves(list(gl_by_move))
        rows = self._pos_rows(taxes, sessions)
        rows += self._move_rows(gl_by_move, sessions)
        return self._assemble(rows, gl_by_move)

    # -- GL side --------------------------------------------------------
    def _gl_by_move(self, filters, taxes):
        """``{move: [date, dpp_penuh, dpp_lain, ppn]}`` — the recap, per move.

        Same domain and same PMK restatement as the recap, only grouped one
        level finer. It is what every detail row is measured against.
        """
        AML = self.env["account.move.line"]
        base_domain = self._digunggung_domain(filters)
        per_move = {}

        for tax in taxes:
            factor, _tarif = self._digunggung_presentation(tax)
            for move, balance in AML._read_group(
                domain=base_domain + [("tax_ids", "in", [tax.id])],
                groupby=["move_id"],
                aggregates=["balance:sum"],
            ):
                # Sales sit on the credit side: flip the sign to read positive.
                dpp_penuh = -(balance or 0.0)
                bucket = per_move.setdefault(move, [move.date, 0.0, 0.0, 0.0])
                bucket[1] += dpp_penuh
                bucket[2] += dpp_penuh * factor
            for move, balance in AML._read_group(
                domain=base_domain + [("tax_line_id", "=", tax.id)],
                groupby=["move_id"],
                aggregates=["balance:sum"],
            ):
                bucket = per_move.setdefault(move, [move.date, 0.0, 0.0, 0.0])
                bucket[3] += -(balance or 0.0)
        return per_move

    def _sessions_for_moves(self, moves):
        """``{move_id: session}`` for the POS session entries in the range."""
        if "pos.session" not in self.env or not moves:
            return {}
        # ``sudo`` on the POS side only: every session here was reached through
        # a move the user could already read in the recap, so this widens the
        # rows by nothing — it just spares an accountant needing POS rights.
        sessions = self.env["pos.session"].sudo().search([("move_id", "in", [m.id for m in moves])])
        return {session.move_id.id: session for session in sessions}

    # -- POS side -------------------------------------------------------
    def _pos_rows(self, taxes, sessions):
        """One row per POS order behind the session entries in range."""
        if not sessions:
            return []
        Order = self.env["pos.order"].sudo()
        orders = Order.search(
            [
                ("session_id", "in", [session.id for session in sessions.values()]),
                ("state", "!=", "invoiced"),
            ]
        )
        if not orders:
            return []

        Line = self.env["pos.order.line"].sudo()
        has_ou = "operating_unit_id" in Order._fields
        # order id -> [dpp_penuh, dpp_lain, ppn, tarif]
        figures = defaultdict(lambda: [0.0, 0.0, 0.0, PMK_131_STATUTORY_RATE])
        for tax in taxes:
            factor, tarif = self._digunggung_presentation(tax)
            for order, subtotal, incl in Line._read_group(
                domain=[("order_id", "in", orders.ids), ("tax_ids", "in", [tax.id])],
                groupby=["order_id"],
                aggregates=["price_subtotal:sum", "price_subtotal_incl:sum"],
            ):
                figure = figures[order.id]
                figure[0] += subtotal or 0.0
                figure[1] += (subtotal or 0.0) * factor
                figure[2] += (incl or 0.0) - (subtotal or 0.0)
                figure[3] = tarif

        ou_names = self._ou_labels(
            {order.operating_unit_id.id for order in orders if has_ou and order.operating_unit_id}
        )
        rows = []
        for order in orders:
            dpp_penuh, dpp_lain, ppn, tarif = figures.get(order.id, (0.0, 0.0, 0.0, PMK_131_STATUTORY_RATE))
            if not (dpp_penuh or ppn):
                # An order with no PPN line (fully non-taxable) is not a
                # digunggung supply — leave it out rather than pad the report.
                continue
            session = order.session_id
            # The GL date is the session entry's, so the masa a struk belongs
            # to is the one its session posted into — not ``date_order``.
            date_value = session.move_id.date if session.move_id else order.date_order.date()
            ou = order.operating_unit_id if has_ou else False
            code, name = ou_names.get(ou.id if ou else False, ("", "(tanpa Operating Unit)"))
            rows.append(
                {
                    "sort_move": session.move_id.id if session.move_id else 0,
                    "masa": self._masa_label(date_value),
                    "date": date_value,
                    "doc_no": order.name or "",
                    "doc_ref": order.pos_reference or "",
                    "source": session.name or "",
                    "ou_code": code,
                    "ou_name": name,
                    "dpp_penuh": dpp_penuh,
                    "dpp_lain": dpp_lain,
                    "tarif": tarif,
                    "ppn": ppn,
                }
            )
        return rows

    # -- non-POS side ---------------------------------------------------
    def _move_rows(self, gl_by_move, sessions):
        """One row per journal entry that is not a POS session entry."""
        moves = [move for move in gl_by_move if move.id not in sessions]
        if not moves:
            return []
        has_ou = "operating_unit_id" in self.env["account.move"]._fields
        ou_names = self._ou_labels({move.operating_unit_id.id for move in moves if has_ou and move.operating_unit_id})
        rows = []
        for move in moves:
            date_value, dpp_penuh, dpp_lain, ppn = gl_by_move[move]
            ou = move.operating_unit_id if has_ou else False
            code, name = ou_names.get(ou.id if ou else False, ("", "(tanpa Operating Unit)"))
            rows.append(
                {
                    "sort_move": move.id,
                    "masa": self._masa_label(date_value),
                    "date": date_value,
                    "doc_no": move.name or "",
                    "doc_ref": move.ref or "",
                    "source": move.journal_id.name or "",
                    "ou_code": code,
                    "ou_name": name,
                    "dpp_penuh": dpp_penuh,
                    "dpp_lain": dpp_lain,
                    "tarif": PMK_131_STATUTORY_RATE,
                    "ppn": ppn,
                }
            )
        return rows

    # -- assembly -------------------------------------------------------
    def _assemble(self, rows, gl_by_move):
        """Group the transaction rows by masa, subtotal each, disclose drift."""
        gl_per_masa = defaultdict(float)
        for date_value, _penuh, _lain, ppn in gl_by_move.values():
            gl_per_masa[(date_value.year, date_value.month)] += ppn

        by_masa = defaultdict(list)
        for row in rows:
            by_masa[(row["date"].year, row["date"].month)].append(row)

        lines = []
        g_penuh = g_lain = g_ppn = 0.0
        for masa in sorted(by_masa):
            label = "%s %s" % (MONTHS_ID[masa[1] - 1], masa[0])
            lines.append({"type": "header", "label": "MASA %s" % label.upper()})
            penuh = lain = ppn = 0.0
            for row in sorted(
                by_masa[masa],
                key=lambda r: (r["date"], r["ou_name"], r["doc_no"]),
            ):
                penuh += row["dpp_penuh"]
                lain += row["dpp_lain"]
                ppn += row["ppn"]
                lines.append({key: value for key, value in row.items() if key != "sort_move"})
            lines.append(
                {
                    "type": "subtotal",
                    "masa": label,
                    "doc_no": "SUBTOTAL %s" % label,
                    "ou_name": "%s transaksi" % len(by_masa[masa]),
                    "dpp_penuh": penuh,
                    "dpp_lain": lain,
                    "ppn": ppn,
                }
            )
            drift = gl_per_masa.get(masa, 0.0) - ppn
            if round(drift, 2):
                # Per-struk rounding in the ledger against a masa restated in
                # one go: shown, never absorbed.
                lines.append(
                    {
                        "type": "note",
                        "masa": label,
                        "doc_no": self.env._(
                            "Selisih pembulatan vs GL: %(amount)s (PPN GL %(gl)s)",
                            amount="%.2f" % drift,
                            gl="%.2f" % gl_per_masa.get(masa, 0.0),
                        ),
                    }
                )
            g_penuh += penuh
            g_lain += lain
            g_ppn += ppn

        lines.append(self._detail_grand_total(g_penuh, g_lain, g_ppn))
        return lines

    @staticmethod
    def _detail_grand_total(dpp_penuh, dpp_lain, ppn):
        return {
            "type": "grand_total",
            "label": "TOTAL",
            "masa": "TOTAL",
            "dpp_penuh": dpp_penuh,
            "dpp_lain": dpp_lain,
            "ppn": ppn,
        }
