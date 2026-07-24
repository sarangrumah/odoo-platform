# -*- coding: utf-8 -*-
"""Rekap PPh Pemotongan per Jenis Penghasilan (PPh 23 / 4(2) / 26 / 22).

Reads ``account.move.withholding.line`` (populated on vendor-bill post by the
``custom_tax_id`` withholding engine), grouped by jenis PPh then jenis
penghasilan (``tax.withholding.category``). This is the granular working paper
behind the e-Bupot: it shows *which kind of income* was withheld, per lawan
transaksi, with DPP / tarif / PPh.

The source model is optional; when ``custom_tax_id`` is absent the report
degrades to an informational note.
"""

from __future__ import annotations

from datetime import date as date_cls

from odoo import models


_PPH_ORDER = ["pph_22", "pph_23", "pph_4_2", "pph_26", "pph_21"]
_PPH_LABEL = {
    "pph_21": "PPh 21",
    "pph_22": "PPh 22",
    "pph_23": "PPh 23",
    "pph_4_2": "PPh 4 ayat (2)",
    "pph_26": "PPh 26",
}


class CustomReportPphWithholding(models.AbstractModel):
    _name = "custom.report.pph.withholding"
    _inherit = "custom.report.engine"
    _description = "Rekap PPh Pemotongan per Jenis Penghasilan"

    _report_code = "pph_withholding"
    _report_title = "Rekap PPh Pemotongan (per Jenis Penghasilan)"

    def _xlsx_columns(self):
        return [
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "No. Dokumen", "field": "doc_no", "kind": "text", "width": 18},
            {"header": "No. Dokumen Jurnal", "field": "journal_no", "kind": "text", "width": 18},
            {"header": "No. Invoice", "field": "invoice_no", "kind": "text", "width": 18},
            {"header": "Tgl Invoice", "field": "invoice_date", "kind": "date", "width": 12},
            {"header": "NPWP/NIK", "field": "npwp", "kind": "text", "width": 20},
            {"header": "Lawan Transaksi", "field": "partner", "kind": "text", "width": 28},
            {"header": "Kode Objek Pajak", "field": "kode_objek", "kind": "text", "width": 14},
            {"header": "Jenis PPh", "field": "jenis_pph", "kind": "text", "width": 14},
            {"header": "Jenis Penghasilan", "field": "jenis_penghasilan", "kind": "text", "width": 26},
            {"header": "COA Expense", "field": "coa_expense", "kind": "text", "width": 30},
            {"header": "DPP", "field": "dpp", "kind": "number", "width": 18},
            {"header": "Tarif (%)", "field": "tarif", "kind": "number", "width": 10},
            {"header": "PPh Dipotong", "field": "pph", "kind": "number", "width": 18},
        ]

    def _build_lines(self, filters):
        pph_kind = filters.get("pph_kind") or "all"

        if "account.move.withholding.line" not in self.env:
            return [
                {"type": "note", "doc_no": "Modul PPh (custom_tax_id) belum terpasang — tidak ada data."},
                {"type": "grand_total", "doc_no": "TOTAL", "dpp": 0.0, "pph": 0.0},
            ]

        WL = self.env["account.move.withholding.line"].sudo()
        domain = [
            ("company_id", "in", list(filters["company_ids"])),
            ("move_id.date", ">=", filters["date_from"]),
            ("move_id.date", "<=", filters["date_to"]),
        ]
        if filters.get("posted_only", True):
            domain.append(("move_id.state", "=", "posted"))
        if pph_kind != "all":
            domain.append(("pph_kind", "=", pph_kind))
        records = WL.search(domain)

        buckets = {}
        for wl in records:
            move = wl.move_id
            partner = move.commercial_partner_id or move.partner_id
            # Separate PPh journal entry ("Pemotongan PPh …"), when custom_tax_id
            # books it as its own move; blank if the field/module is absent.
            wmove = self._opt(move, "x_custom_withholding_move_id")
            journal_no = wmove.name if wmove else ""
            # Expense account of the withheld source line.
            exp_acc = wl.move_line_id.account_id if wl.move_line_id else False
            coa_expense = ""
            if exp_acc:
                coa_expense = ("%s %s" % (self._account_code(exp_acc), exp_acc.name or "")).strip()
            buckets.setdefault(wl.pph_kind, []).append(
                {
                    "date": move.date or move.invoice_date,
                    "doc_no": move.name or "",
                    "journal_no": journal_no,
                    "invoice_no": move.ref or "",
                    "invoice_date": move.invoice_date,
                    "npwp": self._opt(partner, "x_custom_npwp") or self._opt(partner, "x_custom_nik"),
                    "partner": partner.display_name or "",
                    "kode_objek": wl.category_id.bupot_object_code or (wl.category_id.code or ""),
                    "jenis_pph": _PPH_LABEL.get(wl.pph_kind, wl.pph_kind or ""),
                    "jenis_penghasilan": wl.category_id.name or (wl.category_id.code or ""),
                    "coa_expense": coa_expense,
                    "dpp": wl.base_amount or 0.0,
                    "tarif": wl.tarif or 0.0,
                    "pph": wl.tax_amount or 0.0,
                }
            )

        lines = []
        g_dpp = g_pph = 0.0
        ordered = [k for k in _PPH_ORDER if k in buckets] + [k for k in buckets if k not in _PPH_ORDER]
        for kind in ordered:
            group = sorted(
                buckets[kind],
                key=lambda r: (r["jenis_penghasilan"], r["date"] or date_cls.min, r["doc_no"]),
            )
            s_dpp = s_pph = 0.0
            for row in group:
                lines.append(row)
                s_dpp += row["dpp"]
                s_pph += row["pph"]
            lines.append(
                {
                    "type": "subtotal",
                    "doc_no": "Subtotal %s" % _PPH_LABEL.get(kind, kind),
                    "dpp": s_dpp,
                    "pph": s_pph,
                }
            )
            g_dpp += s_dpp
            g_pph += s_pph

        lines.append({"type": "grand_total", "doc_no": "TOTAL", "dpp": g_dpp, "pph": g_pph})
        return lines
