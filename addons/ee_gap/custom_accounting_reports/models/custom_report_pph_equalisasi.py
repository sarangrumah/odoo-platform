# -*- coding: utf-8 -*-
"""Ekualisasi Biaya vs Objek Pemotongan PPh.

Scans vendor-bill lines whose product carries a PPh withholding category and
flags those that were NOT withheld — the classic audit-defense check ("biaya
objek PPh yang belum dipotong"). Depends on
``product.template.x_custom_withholding_category_id`` and
``account.move.withholding.line`` (``custom_tax_id``); degrades to a note when
absent.
"""

from __future__ import annotations

from datetime import date as date_cls

from odoo import models


class CustomReportPphEqualisasi(models.AbstractModel):
    _name = "custom.report.pph.equalisasi"
    _inherit = "custom.report.engine"
    _description = "Ekualisasi Biaya vs Objek Pemotongan PPh"

    _report_code = "pph_equalisasi"
    _report_title = "Ekualisasi Biaya vs Objek Pemotongan PPh"

    @staticmethod
    def _opt(record, field_name, default=""):
        if record and field_name in record._fields:
            return record[field_name] or default
        return default

    def _xlsx_columns(self):
        return [
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "No. Dokumen", "field": "doc_no", "kind": "text", "width": 18},
            {"header": "Lawan Transaksi", "field": "partner", "kind": "text", "width": 26},
            {"header": "Produk", "field": "product", "kind": "text", "width": 24},
            {"header": "Kategori PPh", "field": "kategori", "kind": "text", "width": 22},
            {"header": "DPP", "field": "dpp", "kind": "number", "width": 18},
            {"header": "Status", "field": "status", "kind": "text", "width": 16},
            {"header": "PPh Dipotong", "field": "pph", "kind": "number", "width": 18},
        ]

    def _build_lines(self, filters):
        Template = self.env["product.template"]
        if "x_custom_withholding_category_id" not in Template._fields:
            return [
                {"type": "note", "doc_no": "Modul PPh (custom_tax_id) belum terpasang — tidak ada data."},
                {"type": "grand_total", "doc_no": "TOTAL", "dpp": 0.0, "pph": 0.0},
            ]

        AML = self.env["account.move.line"]
        domain = [
            ("company_id", "in", list(filters["company_ids"])),
            ("date", ">=", filters["date_from"]),
            ("date", "<=", filters["date_to"]),
            ("move_id.move_type", "in", ("in_invoice", "in_refund")),
            ("display_type", "=", "product"),
            ("product_id.product_tmpl_id.x_custom_withholding_category_id", "!=", False),
        ]
        if filters.get("posted_only", True):
            domain.append(("parent_state", "=", "posted"))
        else:
            domain.append(("parent_state", "in", ("draft", "posted")))
        lines = AML.search(domain)

        # Which of these lines were actually withheld?
        withheld = {}
        if "account.move.withholding.line" in self.env and lines:
            wls = self.env["account.move.withholding.line"].sudo().search(
                [("move_line_id", "in", lines.ids)]
            )
            for wl in wls:
                withheld[wl.move_line_id.id] = withheld.get(wl.move_line_id.id, 0.0) + (wl.tax_amount or 0.0)

        rows = []
        g_dpp = g_pph = 0.0
        belum = 0
        for ml in lines.sorted(lambda l: (l.date or date_cls.min, l.move_id.name or "")):
            move = ml.move_id
            partner = move.commercial_partner_id or move.partner_id
            template = ml.product_id.product_tmpl_id
            category = self._opt(template, "x_custom_withholding_category_id", False)
            dpp = ml.price_subtotal or 0.0
            pph = withheld.get(ml.id, 0.0)
            is_withheld = ml.id in withheld
            if not is_withheld:
                belum += 1
            rows.append(
                {
                    "date": ml.date,
                    "doc_no": move.name or "",
                    "partner": partner.display_name or "",
                    "product": template.display_name or "",
                    "kategori": category.name if category else "",
                    "dpp": dpp,
                    "status": "Dipotong" if is_withheld else "BELUM dipotong",
                    "pph": pph,
                }
            )
            g_dpp += dpp
            g_pph += pph

        rows.append(
            {
                "type": "grand_total",
                "doc_no": "TOTAL",
                "partner": "%d baris objek PPh, %d BELUM dipotong" % (len(rows), belum),
                "dpp": g_dpp,
                "pph": g_pph,
            }
        )
        return rows
