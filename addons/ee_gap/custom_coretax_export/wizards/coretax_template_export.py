# -*- coding: utf-8 -*-
"""Render the DJP Coretax import workbooks.

Each ``_rows_*`` builder returns plain Python rows; ``_render`` turns them into
a workbook. Keeping the two apart means the column layouts can be unit-tested
without xlsxwriter in the loop.

Every literal in the ``*_COLUMNS`` tuples below is transcribed from the official
DJP template and must not be "corrected" — ``Nomor Setifikat Insentif`` is
misspelled in the template itself, and Coretax matches on the header text.
"""

from __future__ import annotations

import base64
import logging

from odoo import _, fields, models
from odoo.addons.custom_tax_id.models.uom_inherit import CORETAX_UOM_FALLBACK
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

# The FK/OF layout and the helpers it shares with the other templates now live
# in the builder mixin, so all four e-Faktur entry points run one copy. Re-export
# the column tuples here: they were part of this module's namespace long before
# the split, and importers outside the addon may still reach for them.
from ..models.coretax_fk_builder import FK_COLUMNS, OF_COLUMNS  # noqa: F401

_logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Column layouts (verbatim from the DJP template workbooks)
# --------------------------------------------------------------------------

BPPU_COLUMNS = (
    "NPWP Pemotong",
    "NITKU Pemotong (6 Digit Terakhir)",
    "Masa Pajak",
    "Tahun Pajak",
    "NPWP Penerima Penghasilan",
    "NITKU Penerima Penghasilan (22 Digit)",
    "Nama Penerima Penghasilan",
    "Email",
    "Jenis PPh",
    "Kode Objek Pajak",
    "Fasilitas Insentif",
    "Nomor Setifikat Insentif",
    "Tarif Fasilitas",
    "Penghasilan Bruto",
    "Jenis Dokumen Referensi",
    "Nomor Dokumen Referensi",
    "Tanggal Dokumen Referensi",
    "Metode Pembayaran bagi Pemotong Instansi Pemerintah",
    "Nomor SP2D",
    "NPWP Penandatangan",
    "Tanggal Pemotongan",
    "User Id",
    "Referensi",
)

BP21_COLUMNS = (
    "NPWP Pemotong",
    "NITKU Pemotong (6 Digit Terakhir)",
    "Masa Pajak",
    "Tahun Pajak",
    "NPWP Penerima Penghasilan",
    "NITKU Penerima Penghasilan (22 Digit)",
    "Nama Penerima Penghasilan",
    "Email",
    "Kode Objek Pajak",
    "Fasilitas Insentif",
    "Nomor Setifikat Insentif",
    "Tarif Fasilitas",
    "Gross Up (Y/N)",
    "Penghasilan Bruto Sebelumnya",
    "Penghasilan Bruto",
    "Norma Penghasilan Neto",
    "PTKP",
    "Jenis Dokumen Referensi",
    "Nomor Dokumen Referensi",
    "Tanggal Dokumen Referensi",
    "NPWP Penandatangan",
    "Tanggal Pemotongan",
    "User Id",
    "Referensi",
    "Referensi 3",
    "Referensi 4",
    "Referensi 5",
)

BPNR_COLUMNS = (
    "NPWP Pemotong",
    "NITKU Pemotong (6 Digit Terakhir)",
    "Masa Pajak",
    "Tahun Pajak",
    "TIN Penerima Penghasilan",
    "Nama Penerima Penghasilan",
    "Alamat Penerima Penghasilan",
    "Email",
    "Kode Negara",
    "Nomor Passport",
    "Nomor KITAP/KITAS",
    "Tempat Lahir",
    "Tanggal lahir",
    "Jenis PPh",
    "Kode Objek Pajak",
    "Fasilitas Insentif",
    "Nomor Setifikat Insentif",
    "Tarif Fasilitas",
    "Penghasilan Bruto",
    "Norma Penghasilan Neto",
    "Jenis Dokumen Referensi",
    "Nomor Dokumen Referensi",
    "Tanggal Dokumen Referensi",
    "Metode Pembayaran bagi Pemotong Instansi Pemerintah",
    "Nomor SP2D",
    "NPWP Penandatangan",
    "Tanggal Pemotongan",
    "User Id",
    "Referensi",
    "Referensi 3",
    "Referensi 4",
    "Referensi 5",
)

RETUR_COLUMNS = (
    "Baris",
    "Nomor Faktur",
    "NPWP Penjual",
    "Tanggal Retur",
    "DPP Retur",
    "DPP Lain Retur",
    "PPN Retur",
    "PPnBM Retur",
    "Total DPP Retur",
    "Total DPP Lain Retur",
    "Total PPN Retur",
    "Total PPnBM Retur",
)

RETUR_DETAIL_COLUMNS = (
    "Baris",
    "Jenis Barang Jasa",
    "Nama Barang Jasa",
    "Kode Barang Jasa",
    "Jumlah Barang Jasa",
    "Satuan Ukur Barang Jasa",
    "Harga Satuan",
    "Jumlah Barang Retur",
    "Diskon Retur",
    "DPP Retur",
    "Flag DPP Lain Retur",
    "DPP Lain Retur",
    "PPN Retur",
    "Tarif PPnBM",
    "PPNBM Retur",
)

# Tax List — not a DJP import file, so no template to transcribe. This is a
# reference dump of the company's configured taxes grouped by tax group ("tax
# categories"), with the Coretax-relevant DPP nilai-lain settings alongside the
# rate so the client can reconcile Odoo's tax master against Coretax.
# --- DJP Coretax: Faktur Pajak Keluaran (sheet "Faktur" + "DetailFaktur") ---
# Verbatim from the client's own template, docs/projects/levis/tax-templates/
# "Sample Template Faktur Pajak Keluaran CORETAX.xlsx". Do not reorder: the
# importer reads by position, and the sheet's own "Keterangan" tab is the
# authority on which of these are mandatory.
FAKTUR_CORETAX_COLUMNS = (
    "Baris",
    "Tanggal Faktur",
    "Jenis Faktur",
    "Kode Transaksi",
    "Keterangan Tambahan",
    "Dokumen Pendukung",
    "Period Dok Pendukung",
    "Referensi",
    "Cap Fasilitas",
    "ID TKU Penjual",
    "NPWP/NIK Pembeli",
    "Jenis ID Pembeli",
    "Negara Pembeli",
    "Nomor Dokumen Pembeli",
    "Nama Pembeli",
    "Alamat Pembeli",
    "Email Pembeli",
    "ID TKU Pembeli",
)

DETAIL_FAKTUR_CORETAX_COLUMNS = (
    "Baris",
    "Barang/Jasa",
    "Kode Barang Jasa",
    "Nama Barang/Jasa",
    "Nama Satuan Ukur",
    "Harga Satuan",
    "Jumlah Barang Jasa",
    "Total Diskon",
    "DPP",
    "DPP Nilai Lain",
    "Tarif PPN",
    "PPN",
    "Tarif PPnBM",
    "PPnBM",
)

# --- Mitra Pajakku: Retur Pajak Masukan (one sheet, RM rows + OF rows) ---
# The OF header repeats four names (RETUR_DISKON, RETUR_DPP, RETUR_DPP_LAIN,
# RETUR_PPN): columns 9-16 carry the *faktur* figures and 17-23 the *retur*
# ones. Kept verbatim, duplicates and all, because the importer reads by
# position and "tidying" the names would break it.
RM_COLUMNS = (
    "RM",
    "NPWP_WP",
    "ID_TKU_WP",
    "NPWP",
    "NAMA",
    "KD_JENIS_TRANSAKSI",
    "FG_PENGGANTI",
    "NOMOR_FAKTUR",
    "TANGGAL_FAKTUR",
    "IS_CREDITABLE",
    "NOMOR_DOKUMEN_RETUR",
    "TANGGAL_RETUR",
    "MASA_PAJAK_RETUR",
    "TAHUN_PAJAK_RETUR",
    "NILAI_RETUR_DPP",
    "NILAI_RETUR_DPP_LAIN",
    "NILAI_RETUR_PPN",
    "NILAI_RETUR_PPNBM",
    "KETERANGAN",
    "BRANCH/FIELD_TAMBAHAN_1",
    "FIELD_TAMBAHAN_2",
    "FIELD_TAMBAHAN_3",
    "FIELD_TAMBAHAN_4",
    "FIELD_TAMBAHAN_5",
)

RM_OF_COLUMNS = (
    "OF",
    "BARANG_JASA",
    "KODE_OBJEK",
    "NAMA",
    "SATUAN",
    "HARGA_SATUAN",
    "JUMLAH_BARANG",
    "HARGA_TOTAL",
    "RETUR_DISKON",
    "CHECK_DPP_LAIN",
    "RETUR_DPP",
    "RETUR_DPP_LAIN",
    "TARIF_PPN",
    "RETUR_PPN",
    "TARIF_PPNBM_FAKTUR",
    "PPNBM_FAKTUR",
    "RETUR_BARANG_JASA",
    "RETUR_DISKON",
    "RETUR_DPP",
    "RETUR_DPP_LAIN",
    "RETUR_PPN",
    "TARIF_PPNBM",
    "RETUR_PPNBM",
)

# --- Digunggung (PKP Pedagang Eceran) --------------------------------------
# A retail seller issues a struk, not a faktur per buyer, so there is no buyer
# identity to export. DJP's own template says what to write instead:
# "NPWP/NIK Pembeli ... isikan dengan 0000000000000000 jika Jenis ID Pembeli
# selain TIN" and "ID TKU Pembeli ... jika selain TIN isikan dengan 000000".
DIGUNGGUNG_KODE_TRANSAKSI = "04"  # DPP Nilai Lain — matches the PMK 131 presentation
DIGUNGGUNG_NPWP_PEMBELI = "0000000000000000"
DIGUNGGUNG_JENIS_ID = "Other ID"
DIGUNGGUNG_NEGARA = "IDN"
DIGUNGGUNG_NO_DOKUMEN = "-"
DIGUNGGUNG_NAMA_PEMBELI = "Pembeli Eceran"
DIGUNGGUNG_ID_TKU_PEMBELI = "000000"
DIGUNGGUNG_SATUAN = "UM.0018"  # Unit
DIGUNGGUNG_BARANG = "A"  # Barang

TAXLIST_COLUMNS = (
    "Grup Pajak",
    "Nama Pajak",
    "Penggunaan",
    "Tipe",
    "Tarif (%)",
    "Metode DPP",
    "Faktor DPP",
    "Kategori DPP",
    "Deskripsi",
    "Aktif",
)

# Human-readable labels for the account.tax selection values.
TYPE_TAX_USE_LABEL = {
    "sale": "Penjualan",
    "purchase": "Pembelian",
    "none": "Tidak Digunakan",
}
AMOUNT_TYPE_LABEL = {
    "percent": "Persen",
    "fixed": "Nominal",
    "group": "Grup",
    "division": "Bagi",
}
DPP_METHOD_LABEL = {
    "regular": "Regular",
    "nilai_lain": "Nilai Lain",
}

# `pph_kind` on tax.withholding.category -> the Jenis PPh literal each template
# expects. The Unifikasi list sheet spells 4(2) as "PPH4-2"; the Non-Resident
# one uses mixed case and "PPh4a2". Do not unify these.
JENIS_PPH_UNIFIKASI = {
    "pph_15": "PPH15",
    "pph_22": "PPH22",
    "pph_23": "PPH23",
    "pph_4_2": "PPH4-2",
}
JENIS_PPH_NON_RESIDENT = {
    "pph_26": "PPh26",
    "pph_4_2": "PPh4a2",
}
UNIFIKASI_KINDS = tuple(JENIS_PPH_UNIFIKASI)
NON_RESIDENT_KINDS = tuple(JENIS_PPH_NON_RESIDENT)

# "OTHER : Lainnya" — the catch-all in the Jenis Dokumen Referensi master, and
# what the client's own samples use for invoice-backed bupot.
DOC_REF_OTHER = "07"


class CoretaxTemplateExportWizard(models.TransientModel):
    _name = "custom.coretax.template.export.wizard"
    # The FK/OF layout plus the render and formatting helpers are shared with the
    # invoice-driven entry points; inheriting the builder keeps every one of them
    # reachable on ``self``, exactly where the other _rows_* builders expect.
    _inherit = "custom.coretax.fk.builder"
    _description = "Coretax Import File Export (DJP Templates)"

    template = fields.Selection(
        [
            ("bppu", "Bupot Unifikasi (PPh 23 / 4(2) / 22 / 15)"),
            ("bp21", "Bupot PPh 21"),
            ("bpnr", "Bupot Non-Resident (PPh 26)"),
            ("fk", "e-Faktur Keluaran — Mitra Pajakku (Import FK)"),
            ("fk_coretax", "e-Faktur Keluaran — Coretax (Faktur + DetailFaktur)"),
            ("retur", "Retur Masukan — Coretax (Retur + DetailRetur)"),
            ("retur_pajakku", "Retur Masukan — Mitra Pajakku (RM + OF)"),
            ("taxlist", "Tax List (Daftar Pajak)"),
        ],
        required=True,
        default="bppu",
        string="Template",
    )
    masa_pajak = fields.Selection(
        [(str(m).zfill(2), str(m).zfill(2)) for m in range(1, 13)],
        required=True,
        string="Masa Pajak",
        default=lambda self: str(fields.Date.context_today(self).month).zfill(2),
    )
    tahun_pajak = fields.Integer(
        required=True,
        string="Tahun Pajak",
        default=lambda self: fields.Date.context_today(self).year,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        string="Pemotong",
    )
    tanggal_pemotongan = fields.Date(
        string="Tanggal Pemotongan",
        help="Emitted in the 'Tanggal Pemotongan' column. Defaults to the last "
        "day of the masa pajak, which is how the client's samples are cut.",
    )

    file_data = fields.Binary(string="File", readonly=True, attachment=False)
    fk_source = fields.Selection(
        [
            ("invoice", "Faktur penjualan (out_invoice)"),
            ("digunggung", "Rekap digunggung (PKP Pedagang Eceran)"),
            ("both", "Keduanya"),
        ],
        string="Sumber Faktur Keluaran",
        default="invoice",
        required=True,
        help="Faktur penjualan: satu FK per out_invoice, pembeli teridentifikasi. "
        "Rekap digunggung: satu FK per hari per toko dari penyerahan eceran, "
        "yang tidak pernah menjadi out_invoice. Keduanya tidak tumpang tindih — "
        "setiap rupiah PPN Keluaran masuk tepat satu di antaranya — jadi "
        "'Keduanya' aman dan itulah yang lengkap untuk peritel.",
    )

    file_name = fields.Char(readonly=True)
    line_count = fields.Integer(readonly=True, string="Baris Terekspor")

    # ---------------------------------------------------------------- helpers

    def _period_bounds(self):
        """First and last date of the selected masa pajak."""
        self.ensure_one()
        start = fields.Date.to_date("%04d-%02d-01" % (self.tahun_pajak, int(self.masa_pajak)))
        if int(self.masa_pajak) == 12:
            end = fields.Date.to_date("%04d-12-31" % self.tahun_pajak)
        else:
            nxt = fields.Date.to_date("%04d-%02d-01" % (self.tahun_pajak, int(self.masa_pajak) + 1))
            end = fields.Date.subtract(nxt, days=1)
        return start, end

    def _cut_date(self):
        self.ensure_one()
        return self.tanggal_pemotongan or self._period_bounds()[1]

    # ``_fmt_date`` and ``_digits`` come from ``custom.coretax.fk.builder``.

    # Layouts that carry an "NPWP Penandatangan" column, and therefore cannot be
    # emitted without one. FK/OF and Retur Masukan have no such column, so they
    # must not be blocked on it.
    _SIGNER_TEMPLATES = ("bppu", "bp21", "bpnr")

    def _pemotong(self):
        """(npwp, nitku_suffix, penandatangan, user_id), validated."""
        self.ensure_one()
        company = self.company_id
        npwp = company._check_coretax_pemotong(require_signer=self.template in self._SIGNER_TEMPLATES)
        return (
            npwp,
            company.x_custom_nitku_suffix or "",
            self._digits(company.x_custom_npwp_penandatangan),
            company.x_custom_coretax_user_id or "",
        )

    def _withholding_lines(self, kinds):
        """Posted withholding lines of the given pph kinds inside the masa pajak."""
        self.ensure_one()
        start, end = self._period_bounds()
        return self.env["account.move.withholding.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("pph_kind", "in", list(kinds)),
                ("move_id.state", "=", "posted"),
                ("move_id.invoice_date", ">=", start),
                ("move_id.invoice_date", "<=", end),
            ],
            order="move_id, id",
        )

    # ------------------------------------------------------------- row builders

    def _rows_bppu(self):
        npwp_pemotong, nitku, signer, user_id = self._pemotong()
        cut = self._fmt_date(self._cut_date())
        rows = []
        for line in self._withholding_lines(UNIFIKASI_KINDS):
            move = line.move_id
            partner = move.partner_id.commercial_partner_id
            rows.append(
                [
                    npwp_pemotong,
                    nitku,
                    self.masa_pajak,
                    str(self.tahun_pajak),
                    partner._custom_coretax_npwp(),
                    partner._custom_coretax_nitku(),
                    partner.name or "",
                    partner.email or "",
                    JENIS_PPH_UNIFIKASI.get(line.pph_kind, ""),
                    line.category_id.bupot_object_code or "",
                    line.fasilitas_insentif or "9",
                    line.nomor_sertifikat_insentif or "",
                    line.tarif_fasilitas or 0,
                    line.base_amount,
                    DOC_REF_OTHER,
                    move.ref or move.name or "",
                    self._fmt_date(move.invoice_date),
                    "",  # Metode Pembayaran — non-government cutter, left blank
                    "",  # Nomor SP2D — idem
                    signer,
                    cut,
                    user_id,
                    "",  # Referensi — not mandatory
                ]
            )
        return [BPPU_COLUMNS], rows

    def _rows_bp21(self):
        npwp_pemotong, nitku, signer, user_id = self._pemotong()
        cut = self._fmt_date(self._cut_date())
        rows = []
        for line in self._withholding_lines(("pph_21",)):
            move = line.move_id
            partner = move.partner_id.commercial_partner_id
            rows.append(
                [
                    npwp_pemotong,
                    nitku,
                    self.masa_pajak,
                    str(self.tahun_pajak),
                    partner._custom_coretax_npwp() or self._digits(partner.x_custom_nik),
                    partner._custom_coretax_nitku(),
                    partner.name or "",
                    partner.email or "",
                    line.category_id.bupot_object_code or "",
                    line.fasilitas_insentif or "9",
                    line.nomor_sertifikat_insentif or "",
                    line.tarif_fasilitas or 0,
                    "N",  # Gross Up — the engine books gross, never grossed-up
                    0,  # Penghasilan Bruto Sebelumnya
                    line.base_amount,
                    line.norma_penghasilan_neto or 0,
                    partner.x_custom_ptkp or "",
                    DOC_REF_OTHER,
                    move.ref or move.name or "",
                    self._fmt_date(move.invoice_date),
                    signer,
                    cut,
                    user_id,
                    "",
                    "",
                    "",
                    "",
                ]
            )
        return [BP21_COLUMNS], rows

    def _rows_bpnr(self):
        npwp_pemotong, nitku, signer, user_id = self._pemotong()
        cut = self._fmt_date(self._cut_date())
        rows = []
        for line in self._withholding_lines(NON_RESIDENT_KINDS):
            move = line.move_id
            partner = move.partner_id.commercial_partner_id
            rows.append(
                [
                    npwp_pemotong,
                    nitku,
                    self.masa_pajak,
                    str(self.tahun_pajak),
                    partner.x_custom_tin or "",
                    partner.name or "",
                    self._partner_address(partner),
                    partner.email or "",
                    partner.country_id.x_custom_code_alpha3 or "",
                    partner.x_custom_passport or "",
                    partner.x_custom_kitas or "",
                    partner.x_custom_birth_place or "",
                    self._fmt_date(partner.x_custom_birth_date),
                    JENIS_PPH_NON_RESIDENT.get(line.pph_kind, ""),
                    line.category_id.bupot_object_code or "",
                    line.fasilitas_insentif or "9",
                    line.nomor_sertifikat_insentif or "",
                    line.tarif_fasilitas or 0,
                    line.base_amount,
                    line.norma_penghasilan_neto or 0,
                    DOC_REF_OTHER,
                    move.ref or move.name or "",
                    self._fmt_date(move.invoice_date),
                    "",
                    "",
                    signer,
                    cut,
                    user_id,
                    "",
                    "",
                    "",
                    "",
                ]
            )
        return [BPNR_COLUMNS], rows

    # ------------------------------------------------- e-Faktur / Retur helpers

    def _vat_moves(self, move_types):
        self.ensure_one()
        start, end = self._period_bounds()
        return self.env["account.move"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("move_type", "in", move_types),
                ("state", "=", "posted"),
                ("invoice_date", ">=", start),
                ("invoice_date", "<=", end),
            ],
            order="invoice_date, name",
        )

    # ``_line_vat`` and ``_item_jenis`` come from ``custom.coretax.fk.builder``.

    # ------------------------------------------------------------------
    # Digunggung — the retail seller's side of PPN Keluaran
    # ------------------------------------------------------------------
    def _digunggung_details(self):
        """One row per (trading day, store) from ``custom.report.ppn.digunggung``.

        Reused rather than re-derived: that report already resolves which taxes
        count as PPN Keluaran, restates them PMK 131-style (12 % statutory on a
        DPP Nilai Lain of 11/12) and excludes anything that is an invoice. Two
        implementations of "what is a digunggung supply" would drift, and the
        report is the one Finance already reconciles against the SPT.
        """
        start, end = self._period_bounds()
        report = self.env["custom.report.ppn.digunggung"]
        filters = {
            "date_from": start,
            "date_to": end,
            "company_ids": self.company_id.ids,
            "partner_ids": [],
            "posted_only": True,
        }
        # Only the per-day/per-store detail rows: headers, subtotals and the
        # grand total would double-count.
        return [row for row in report._build_lines(filters) if not row.get("type")]

    def _digunggung_seller_tku(self):
        """22-digit NITKU: the 16-digit NPWP plus a 6-digit branch, HO = 000000."""
        npwp = (self.company_id._check_coretax_pemotong(require_signer=False) or "").strip()
        return "%s%s" % (npwp, "000000")

    def _digunggung_label(self, row):
        return "Penyerahan eceran %s - %s" % (
            row.get("ou_name") or "(tanpa Operating Unit)",
            row["date"].strftime("%d/%m/%Y"),
        )

    def _rows_fk(self):
        """One FK row per invoice, each followed by its OF item rows.

        ``_vat_moves`` already bounds the search to the selected masa pajak and
        to posted invoices, so the per-invoice MASA_PAJAK / TAHUN_PAJAK the
        builder derives from ``invoice_date`` are provably the wizard's own
        values — this path keeps emitting exactly what it did before.
        """
        headers, rows = self._coretax_fk_rows(
            self._vat_moves(("out_invoice",))
            if self.fk_source in ("invoice", "both")
            else self.env["account.move"].browse(),
            company=self.company_id,
        )
        if self.fk_source in ("digunggung", "both"):
            rows = rows + self._digunggung_fk_pajakku_rows()
        return headers, rows

    def _digunggung_fk_pajakku_rows(self):
        """Digunggung supplies as Mitra Pajakku FK/OF pairs.

        One FK per (day, store): that is the grain a PKP Pedagang Eceran
        actually reports, and the grain the digunggung report already ties to
        the SPT. The OF line underneath it is the day's takings as a single
        unit — there is no per-item detail to export, because a struk is not an
        invoice line in this ledger.
        """
        npwp = (self.company_id._check_coretax_pemotong(require_signer=False) or "").strip()
        rows = []
        for row in self._digunggung_details():
            tanggal = row["date"]
            label = self._digunggung_label(row)
            dpp = round(row["dpp_penuh"], 2)
            dpp_lain = round(row["dpp_lain"], 2)
            ppn = round(row["ppn"], 2)
            tarif = row.get("tarif") or 0.0
            rows.append(
                [
                    "FK",
                    npwp,
                    "000000",
                    DIGUNGGUNG_KODE_TRANSAKSI,
                    "0",
                    "",
                    tanggal.strftime("%m"),
                    str(tanggal.year),
                    tanggal.strftime("%Y-%m-%d"),
                    DIGUNGGUNG_NPWP_PEMBELI,
                    DIGUNGGUNG_JENIS_ID,
                    "",
                    DIGUNGGUNG_NEGARA,
                    DIGUNGGUNG_NAMA_PEMBELI,
                    "",
                    row.get("ou_name") or "",
                    DIGUNGGUNG_ID_TKU_PEMBELI,
                    dpp,
                    dpp_lain,
                    ppn,
                    0,
                    "",
                    "0",
                    "",
                    0,
                    0,
                    0,
                    0,
                    label,
                    "",
                    row.get("ou_code") or "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            rows.append(
                [
                    "OF",
                    "Barang",
                    "000000",
                    label,
                    DIGUNGGUNG_SATUAN,
                    dpp,
                    1,
                    dpp,
                    0,
                    "Y",
                    dpp,
                    dpp_lain,
                    tarif,
                    ppn,
                    0,
                    0,
                ]
            )
        return rows

    def _rows_fk_coretax(self):
        """DJP Coretax layout: sheet ``Faktur`` beside sheet ``DetailFaktur``.

        Same figures as the Mitra Pajakku export, different shape — and a
        genuinely different workbook, two sheets rather than one, which is why
        this returns sheet tuples instead of a single header/row pair.
        """
        faktur, detail = [], []
        tku_penjual = self._digunggung_seller_tku()
        baris = 0

        if self.fk_source in ("invoice", "both"):
            for move in self._vat_moves(("out_invoice",)):
                baris += 1
                partner = move.partner_id
                faktur.append(
                    [
                        baris,
                        move.invoice_date.strftime("%d/%m/%Y") if move.invoice_date else "",
                        "Normal",
                        move.l10n_id_kode_transaksi or "01",
                        "",
                        "",
                        "",
                        move.name or "",
                        "",
                        tku_penjual,
                        (partner.vat or DIGUNGGUNG_NPWP_PEMBELI).replace(".", "").replace("-", ""),
                        "TIN" if partner.vat else DIGUNGGUNG_JENIS_ID,
                        DIGUNGGUNG_NEGARA,
                        "-" if partner.vat else DIGUNGGUNG_NO_DOKUMEN,
                        partner.name or "",
                        self._partner_address(partner),
                        partner.email or "",
                        "000000",
                    ]
                )
                for line in move.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
                    dpp, dpp_lain, ppn, tarif, _uses = self._line_vat(line)
                    detail.append(
                        [
                            baris,
                            DIGUNGGUNG_BARANG,
                            "",
                            line.product_id.name or line.name or "",
                            line.product_uom_id.x_custom_coretax_code or CORETAX_UOM_FALLBACK,
                            line.price_unit,
                            line.quantity,
                            0,
                            round(dpp, 2),
                            round(dpp_lain, 2),
                            tarif,
                            round(ppn, 2),
                            0,
                            0,
                        ]
                    )

        if self.fk_source in ("digunggung", "both"):
            for row in self._digunggung_details():
                baris += 1
                tanggal = row["date"]
                label = self._digunggung_label(row)
                dpp = round(row["dpp_penuh"], 2)
                dpp_lain = round(row["dpp_lain"], 2)
                ppn = round(row["ppn"], 2)
                faktur.append(
                    [
                        baris,
                        tanggal.strftime("%d/%m/%Y"),
                        "Normal",
                        DIGUNGGUNG_KODE_TRANSAKSI,
                        "",
                        "",
                        "",
                        label,
                        "",
                        tku_penjual,
                        DIGUNGGUNG_NPWP_PEMBELI,
                        DIGUNGGUNG_JENIS_ID,
                        DIGUNGGUNG_NEGARA,
                        DIGUNGGUNG_NO_DOKUMEN,
                        DIGUNGGUNG_NAMA_PEMBELI,
                        row.get("ou_name") or "",
                        "",
                        DIGUNGGUNG_ID_TKU_PEMBELI,
                    ]
                )
                detail.append(
                    [
                        baris,
                        DIGUNGGUNG_BARANG,
                        "",
                        label,
                        DIGUNGGUNG_SATUAN,
                        dpp,
                        1,
                        0,
                        dpp,
                        dpp_lain,
                        row.get("tarif") or 0.0,
                        ppn,
                        0,
                        0,
                    ]
                )

        if not faktur:
            return [], []
        return [
            ("Faktur", [list(FAKTUR_CORETAX_COLUMNS)], faktur),
            ("DetailFaktur", [list(DETAIL_FAKTUR_CORETAX_COLUMNS)], detail),
        ], faktur

    def _rows_retur(self):
        """Retur Masukan: banner, Retur table, END sentinel, DetailRetur table.

        Unlike the bupot templates this is not a flat sheet, so it returns a
        pre-laid-out block that ``_render`` writes verbatim.
        """
        # Retur carries the NPWP Pembeli banner only — no signer column.
        npwp_pembeli = self.company_id._check_coretax_pemotong(require_signer=False)
        block = [["Retur"], ["NPWP Pembeli", "", npwp_pembeli], [], list(RETUR_COLUMNS)]
        details = [[], ["DetailRetur"], list(RETUR_DETAIL_COLUMNS)]

        baris = 0
        for move in self._vat_moves(("in_refund",)):
            origin = move.reversed_entry_id
            faktur = origin.x_custom_nsfp if origin else ""
            if not faktur:
                # A retur must point at the faktur it reverses; without the
                # NSFP the row is unimportable, so skip rather than emit junk.
                _logger.info("Retur Masukan: skipping %s, no NSFP on origin", move.name)
                continue
            baris += 1
            items = move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
            t_dpp = t_lain = t_ppn = 0.0
            for line in items:
                dpp, dpp_lain, ppn, _tarif, uses = self._line_vat(line)
                t_dpp += dpp
                t_lain += dpp_lain
                t_ppn += ppn
                details.append(
                    [
                        baris,
                        "A",  # Jenis Barang Jasa — 'A' = barang in the sample
                        line.product_id.name or line.name or "",
                        "000000",
                        line.quantity,
                        line.product_uom_id.x_custom_coretax_code or CORETAX_UOM_FALLBACK,
                        line.price_unit,
                        line.quantity,
                        0,
                        dpp,
                        "Yes" if uses else "No",
                        dpp_lain,
                        ppn,
                        0,
                        0,
                    ]
                )
            block.append(
                [
                    baris,
                    faktur,
                    move.partner_id.commercial_partner_id._custom_coretax_npwp(),
                    self._fmt_date(move.invoice_date),
                    t_dpp,
                    t_lain,
                    t_ppn,
                    0,
                    t_dpp,
                    t_lain,
                    t_ppn,
                    0,
                ]
            )
        if not baris:
            return [], []
        # The client's own template is two SHEETS -- ``Retur`` beside
        # ``DetailRetur`` -- not one sheet with an END sentinel between the two
        # tables. Corrected 17-Sep-2026 against
        # "Sample Template Retur Pajak Masukan CORETAX.xlsx"; the previous
        # layout had been written from an assumption and never had data to
        # expose it.
        retur_sheet = [["Retur"], ["NPWP Pembeli", "", npwp_pembeli], [], list(RETUR_COLUMNS)]
        return [
            ("Retur", retur_sheet, block[4:]),
            ("DetailRetur", [list(RETUR_DETAIL_COLUMNS)], details[3:]),
        ], block[4:]

    # ------------------------------------------- Retur Masukan — Mitra Pajakku

    def _rows_retur_pajakku(self):
        """Retur Masukan in the Mitra Pajakku shape: one ``RM`` row per credit
        note, each followed by its ``OF`` item rows.

        Same source and the same guard as the Coretax variant: a retur that
        cannot name the faktur it reverses is unimportable, so it is skipped
        with a log line rather than emitted as junk.
        """
        npwp_wp = self.company_id._check_coretax_pemotong(require_signer=False)
        rows = []
        for move in self._vat_moves(("in_refund",)):
            origin = move.reversed_entry_id
            faktur = origin.x_custom_nsfp if origin else ""
            if not faktur:
                _logger.info("Retur Masukan (Pajakku): skipping %s, no NSFP on origin", move.name)
                continue
            items = move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
            t_dpp = t_lain = t_ppn = 0.0
            of_rows = []
            for line in items:
                dpp, dpp_lain, ppn, tarif, uses = self._line_vat(line)
                t_dpp += dpp
                t_lain += dpp_lain
                t_ppn += ppn
                satuan = line.product_uom_id.x_custom_coretax_code or CORETAX_UOM_FALLBACK
                harga_total = (line.price_unit or 0.0) * (line.quantity or 0.0)
                of_rows.append(
                    [
                        "OF",
                        "Barang",
                        "000000",
                        line.product_id.name or line.name or "",
                        satuan,
                        line.price_unit,
                        line.quantity,
                        harga_total,
                        0,
                        "Y" if uses else "N",
                        round(dpp, 2),
                        round(dpp_lain, 2),
                        tarif,
                        round(ppn, 2),
                        0,
                        0,
                        line.quantity,
                        0,
                        round(dpp, 2),
                        round(dpp_lain, 2),
                        round(ppn, 2),
                        0,
                        0,
                    ]
                )
            retur_date = move.invoice_date or move.date
            rows.append(
                [
                    "RM",
                    npwp_wp,
                    "000000",
                    move.partner_id.commercial_partner_id._custom_coretax_npwp(),
                    move.partner_id.commercial_partner_id.name or "",
                    origin.l10n_id_kode_transaksi or "01",
                    "0",
                    faktur,
                    self._fmt_date(origin.invoice_date),
                    "1",
                    move.name or "",
                    self._fmt_date(retur_date),
                    retur_date.strftime("%m") if retur_date else "",
                    str(retur_date.year) if retur_date else "",
                    round(t_dpp, 2),
                    round(t_lain, 2),
                    round(t_ppn, 2),
                    0,
                    "",
                    "HO",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            rows.extend(of_rows)
        if not rows:
            return [], []
        return [list(RM_COLUMNS), list(RM_OF_COLUMNS)], rows

    # -------------------------------------------------------------- Tax List

    def _rows_taxlist(self):
        """Every tax configured for the pemotong, grouped by tax group.

        Not period-bound: this is a master reference, so masa/tahun pajak are
        ignored. Ordering follows the tax group name, then sale before purchase,
        then descending rate, so PPN keluaran/masukan land next to each other.
        """
        self.ensure_one()
        taxes = (
            self.env["account.tax"].with_context(active_test=False).search([("company_id", "=", self.company_id.id)])
        )
        taxes = taxes.sorted(
            key=lambda t: (
                (t.tax_group_id.name or "").lower(),
                0 if t.type_tax_use == "sale" else 1,
                -t.amount,
                t.id,
            )
        )
        rows = []
        for tax in taxes:
            rows.append(
                [
                    tax.tax_group_id.name or "",
                    tax.name or "",
                    TYPE_TAX_USE_LABEL.get(tax.type_tax_use, tax.type_tax_use or ""),
                    AMOUNT_TYPE_LABEL.get(tax.amount_type, tax.amount_type or ""),
                    tax.amount,
                    DPP_METHOD_LABEL.get(tax.x_custom_dpp_method, tax.x_custom_dpp_method or ""),
                    tax.x_custom_dpp_factor or 0,
                    tax.x_custom_dpp_category or "",
                    html2plaintext(tax.description).strip() if tax.description else "",
                    "Y" if tax.active else "N",
                ]
            )
        return [TAXLIST_COLUMNS], rows

    # ``_partner_address`` and ``_render`` come from ``custom.coretax.fk.builder``.

    # ------------------------------------------------------------------ action

    _BUILDERS = {
        "bppu": ("_rows_bppu", "Template", "sample_pph_uni_bppu"),
        "bp21": ("_rows_bp21", "Template", "sample_pph_21_bp_21"),
        "bpnr": ("_rows_bpnr", "Template", "sample_pph_uni_bp_nr"),
        "fk": ("_rows_fk", "Import FK", "faktur_keluaran_pajakku"),
        "fk_coretax": ("_rows_fk_coretax", None, "faktur_keluaran_coretax"),
        "retur": ("_rows_retur", None, "retur_masukan_coretax"),
        "retur_pajakku": ("_rows_retur_pajakku", "Import RM", "retur_masukan_pajakku"),
        "taxlist": ("_rows_taxlist", "Tax List", "tax_list"),
    }

    def action_export(self):
        self.ensure_one()
        builder = self._BUILDERS.get(self.template)
        if not builder:
            raise UserError(_("Template %s belum diimplementasikan.") % self.template)
        method, sheet_name, stem = builder
        header_rows, data_rows = getattr(self, method)()
        if not data_rows:
            start, end = self._period_bounds()
            # The FK sheet is the one template whose emptiness has a cheap
            # explanation — reuse the date-range wizard's probes instead of the
            # generic "periksa bukti potong" line, which sends the user looking
            # in the wrong place entirely.
            if self.template in ("fk", "fk_coretax"):
                if self.fk_source == "digunggung":
                    detail = _(
                        "Sumber dipilih 'Rekap digunggung', tetapi tidak ada penyerahan "
                        "eceran ber-PPN Keluaran di periode ini. Periksa Rekap PPN "
                        "Digunggung untuk masa yang sama."
                    )
                else:
                    detail = "\n\n".join(self._coretax_fk_empty_hints(start, end, self.company_id))
                    if self.fk_source == "invoice":
                        detail += _(
                            "\n\nPeritel tidak menerbitkan faktur per pembeli: setel "
                            "'Sumber Faktur Keluaran' ke Rekap digunggung."
                        )
            elif self.template in ("retur", "retur_pajakku"):
                detail = _(
                    "Retur Masukan diambil dari nota kredit pemasok (vendor credit note) "
                    "ter-posting di periode ini — bukan dari retur penjualan."
                )
            elif self.template == "taxlist":
                detail = _("Perusahaan ini belum punya pajak yang terkonfigurasi.")
            else:
                detail = _("Periksa: apakah ada bukti potong ter-posting di periode tersebut?")
            raise UserError(
                _(
                    "Tidak ada data untuk masa pajak %(masa)s/%(tahun)s pada template ini.\n"
                    "  - perusahaan: %(company)s\n"
                    "  - periode %(start)s s/d %(end)s\n\n%(detail)s",
                    masa=self.masa_pajak,
                    tahun=self.tahun_pajak,
                    company=self.company_id.display_name,
                    start=start,
                    end=end,
                    detail=detail,
                )
            )
        # ``sheet_name is None`` marks a multi-sheet template: the builder then
        # returns sheet tuples in place of header rows, because the Coretax
        # layouts are two sheets and no single-sheet file will import.
        if sheet_name is None:
            content = self._render_sheets(header_rows)
        else:
            content = self._render(header_rows, data_rows, sheet_name)
        self.write(
            {
                "file_data": base64.b64encode(content),
                "file_name": "%s_%s_%s.xlsx" % (stem, self.masa_pajak, self.tahun_pajak),
                "line_count": len(data_rows),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
