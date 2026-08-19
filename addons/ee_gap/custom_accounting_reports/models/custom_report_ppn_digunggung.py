# -*- coding: utf-8 -*-
"""Rekap PPN Keluaran Digunggung (PKP Pedagang Eceran).

Retail sales are not invoiced one by one: a PKP Pedagang Eceran issues a
struk per transaction and reports the masa in aggregate — the *faktur pajak
digunggung* — instead of uploading an e-Faktur per buyer. In Odoo those sales
land as POS journal entries (``move_type == 'entry'``), never as
``out_invoice``, which is precisely why ``custom.report.faktur.pajak`` and the
FK/OF export show nothing for a retail tenant: both are keyed on invoices.

This report covers that gap from the other side. It sums the output VAT that
rides on **non-invoice** moves, so every rupiah of PPN Keluaran is accounted
for by exactly one of the two reports:

* per-faktur, buyer identified → ``custom.report.faktur.pajak`` + FK export;
* digunggung, buyer not identified → here.

Two blocks, both from the same figures:

* **Rekap per masa** — one line per tax period, the number to carry into the
  SPT Masa PPN 1111;
* **Rincian harian per toko** — one line per trading day per Operating Unit,
  the audit trail that ties the masa total back to the POS sessions.

Presentation follows PMK 131/2024, the same convention
``custom_coretax_export`` uses on FK rows: a tax booked at an effective 11% is
presented as the statutory **12% on a DPP Nilai Lain of 11/12** of the selling
price. The PPN rupiah is unchanged (12% x 11/12 == 11%), so the report still
ties to the GL; only the base and the tariff are restated into the shape DJP
expects. A tax already configured as ``nilai_lain`` keeps its own factor.

Operating Unit is read defensively: without ``custom_operating_unit_docs`` the
per-store breakdown collapses into a single "(tanpa Operating Unit)" bucket
rather than failing.
"""

from __future__ import annotations

from collections import defaultdict

from odoo import models

# PMK 131/2024, mirrored from ``custom_coretax_export`` so both surfaces
# restate an 11% tax identically.
PMK_131_EFFECTIVE_RATE = 11.0
PMK_131_STATUTORY_RATE = 12.0
PMK_131_DPP_FACTOR = 11.0 / 12.0

MONTHS_ID = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "Mei",
    "Jun",
    "Jul",
    "Agu",
    "Sep",
    "Okt",
    "Nov",
    "Des",
)


class CustomReportPpnDigunggung(models.AbstractModel):
    _name = "custom.report.ppn.digunggung"
    _inherit = "custom.report.engine"
    _description = "Rekap PPN Keluaran Digunggung (Pedagang Eceran)"

    _report_code = "ppn_digunggung"
    _report_title = "Rekap PPN Keluaran Digunggung (Pedagang Eceran)"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _xlsx_columns(self):
        return [
            {"header": "Masa Pajak", "field": "masa", "kind": "text", "width": 14},
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "Kode Toko", "field": "ou_code", "kind": "text", "width": 12},
            {"header": "Toko / Operating Unit", "field": "ou_name", "kind": "text", "width": 34},
            {"header": "Jml Dokumen", "field": "doc_count", "kind": "number", "width": 12},
            {"header": "Harga Jual (DPP Penuh)", "field": "dpp_penuh", "kind": "number", "width": 22},
            {"header": "DPP Nilai Lain", "field": "dpp_lain", "kind": "number", "width": 20},
            {"header": "Tarif", "field": "tarif", "kind": "number", "width": 8},
            {"header": "PPN Keluaran", "field": "ppn", "kind": "number", "width": 20},
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _digunggung_presentation(self, tax):
        """``(factor, tarif)`` restating ``tax`` the way DJP expects it.

        A tax configured as *DPP Nilai Lain* carries its own factor and rate. A
        plain 11% tax is the PMK 131/2024 arrangement written the short way in
        the ledger and is presented as 12% on 11/12. Anything else is a regular
        base: factor 1, its own tariff.
        """
        if getattr(tax, "x_custom_dpp_method", False) == "nilai_lain" and getattr(tax, "x_custom_dpp_factor", 0.0):
            return tax.x_custom_dpp_factor, tax.amount
        if abs(tax.amount - PMK_131_EFFECTIVE_RATE) < 1e-4:
            return PMK_131_DPP_FACTOR, PMK_131_STATUTORY_RATE
        return 1.0, tax.amount

    @staticmethod
    def _masa_label(date_value):
        return "%s %s" % (MONTHS_ID[date_value.month - 1], date_value.year)

    def _digunggung_domain(self, filters):
        """Base-line domain: posted retail sales, never a customer invoice.

        ``out_invoice`` / ``out_refund`` are excluded on purpose — those carry a
        buyer identity and belong to the per-faktur report and the FK export.
        Including them here would double-count them across the two reports.
        """
        domain = self._base_move_line_domain(filters)
        domain += [("move_id.move_type", "not in", ("out_invoice", "out_refund"))]
        if filters.get("operating_unit_ids") and "operating_unit_id" in self.env["account.move.line"]._fields:
            domain += [("operating_unit_id", "in", list(filters["operating_unit_ids"]))]
        return domain

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _build_lines(self, filters):
        AML = self.env["account.move.line"]
        has_ou = "operating_unit_id" in AML._fields
        ppn_ids = self.env["custom.report.faktur.pajak"]._ppn_tax_ids("sale", filters["company_ids"])
        taxes = self.env["account.tax"].browse(ppn_ids)
        if not taxes:
            return [
                {"type": "note", "masa": "Tidak ada pajak PPN Keluaran pada perusahaan terpilih."},
                self._grand_total_row(0.0, 0.0, 0.0, 0),
            ]

        base_domain = self._digunggung_domain(filters)
        groupby = ["date:day"] + (["operating_unit_id"] if has_ou else [])

        # key -> [dpp_penuh, dpp_lain, ppn]; doc ids per key for the count.
        buckets = defaultdict(lambda: [0.0, 0.0, 0.0])
        tarif_seen = {}
        doc_ids = defaultdict(set)

        for tax in taxes:
            factor, tarif = self._digunggung_presentation(tax)

            base_rows = AML._read_group(
                domain=base_domain + [("tax_ids", "in", [tax.id])],
                groupby=groupby,
                aggregates=["balance:sum", "move_id:array_agg"],
            )
            for row in base_rows:
                day, ou = (row[0], row[1]) if has_ou else (row[0], self.env["account.move.line"].browse())
                balance, move_ids = row[-2], row[-1]
                # Sales sit on the credit side: flip the sign so the report
                # reads in positive rupiah.
                dpp_penuh = -(balance or 0.0)
                key = (day.date() if hasattr(day, "date") else day, ou.id if has_ou else False)
                buckets[key][0] += dpp_penuh
                buckets[key][1] += dpp_penuh * factor
                tarif_seen[key] = tarif
                doc_ids[key].update(move_ids or [])

            tax_rows = AML._read_group(
                domain=base_domain + [("tax_line_id", "=", tax.id)],
                groupby=groupby,
                aggregates=["balance:sum"],
            )
            for row in tax_rows:
                day, ou = (row[0], row[1]) if has_ou else (row[0], self.env["account.move.line"].browse())
                key = (day.date() if hasattr(day, "date") else day, ou.id if has_ou else False)
                buckets[key][2] += -(row[-1] or 0.0)

        if not buckets:
            return [
                {"type": "note", "masa": "Tidak ada penyerahan digunggung pada periode ini."},
                self._grand_total_row(0.0, 0.0, 0.0, 0),
            ]

        ou_names = self._ou_labels({ou_id for _day, ou_id in buckets if ou_id})

        # --- rekap per masa -------------------------------------------------
        per_masa = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
        masa_tarif = {}
        for (day, ou_id), (penuh, lain, ppn) in buckets.items():
            masa = (day.year, day.month)
            per_masa[masa][0] += penuh
            per_masa[masa][1] += lain
            per_masa[masa][2] += ppn
            per_masa[masa][3] += len(doc_ids[(day, ou_id)])
            masa_tarif.setdefault(masa, tarif_seen.get((day, ou_id), PMK_131_STATUTORY_RATE))

        rows = [{"type": "header", "label": "REKAP PER MASA PAJAK (untuk SPT Masa PPN 1111)"}]
        g_penuh = g_lain = g_ppn = 0.0
        g_docs = 0
        for masa in sorted(per_masa):
            penuh, lain, ppn, docs = per_masa[masa]
            rows.append(
                {
                    "type": "subtotal",
                    "masa": "%s %s" % (MONTHS_ID[masa[1] - 1], masa[0]),
                    "ou_name": "Seluruh toko (digunggung)",
                    "doc_count": docs,
                    "dpp_penuh": penuh,
                    "dpp_lain": lain,
                    "tarif": masa_tarif.get(masa, PMK_131_STATUTORY_RATE),
                    "ppn": ppn,
                }
            )
            g_penuh += penuh
            g_lain += lain
            g_ppn += ppn
            g_docs += docs

        # --- rincian harian per toko ---------------------------------------
        rows.append({"type": "header", "label": "RINCIAN HARIAN PER TOKO"})
        for day, ou_id in sorted(buckets, key=lambda k: (k[0], ou_names.get(k[1], ("", ""))[1])):
            penuh, lain, ppn = buckets[(day, ou_id)]
            code, name = ou_names.get(ou_id, ("", "(tanpa Operating Unit)"))
            rows.append(
                {
                    "masa": self._masa_label(day),
                    "date": day,
                    "ou_code": code,
                    "ou_name": name,
                    "doc_count": len(doc_ids[(day, ou_id)]),
                    "dpp_penuh": penuh,
                    "dpp_lain": lain,
                    "tarif": tarif_seen.get((day, ou_id), PMK_131_STATUTORY_RATE),
                    "ppn": ppn,
                }
            )

        rows.append(self._grand_total_row(g_penuh, g_lain, g_ppn, g_docs))
        return rows

    @staticmethod
    def _grand_total_row(dpp_penuh, dpp_lain, ppn, doc_count):
        return {
            "type": "grand_total",
            "label": "TOTAL",
            "masa": "TOTAL",
            "doc_count": doc_count,
            "dpp_penuh": dpp_penuh,
            "dpp_lain": dpp_lain,
            "ppn": ppn,
        }

    def _ou_labels(self, ou_ids):
        """``{id: (code, name)}`` for the Operating Units in play."""
        if not ou_ids or "operating.unit" not in self.env:
            return {}
        units = self.env["operating.unit"].browse(sorted(ou_ids)).exists()
        return {ou.id: (ou.code or "", ou.name or "") for ou in units}
