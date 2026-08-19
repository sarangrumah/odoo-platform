# -*- coding: utf-8 -*-
"""Build the DJP Coretax "e-Faktur Keluaran" FK/OF rows for any invoice set.

The layout is a two-record sheet: one ``FK`` row per invoice (35 columns)
followed by its ``OF`` item rows (16 columns). Every literal in the ``*_COLUMNS``
tuples is transcribed from the official DJP template and must not be
"corrected" — Coretax matches on the header text.

This lives in its own AbstractModel rather than on the masa-pajak wizard because
four entry points need it: the invoice form button, the invoice list action, the
date-range reporting wizard, and the original masa-pajak wizard. The wizards
reach it through ``_inherit`` (so every helper stays on ``self``, exactly as
before); ``account.move`` reaches it through ``self.env[...]``.

Two invariants the DJP importer checks, and that the row builder therefore
guarantees on the values *as literally written*:

* ``HARGA_TOTAL - DISKON == DPP`` on every OF row;
* the FK totals equal the sum of the OF column beneath them.

Both are about the written cells, not the underlying floats, which is why the
money columns are rounded to whole rupiah and the residual is absorbed by the
last OF row. See ``FK_AMOUNT_ROUNDING`` and ``_round_and_plug``.
"""

from __future__ import annotations

import base64
import io
import logging

from odoo import _, models
from odoo.addons.custom_tax_id.models.uom_inherit import CORETAX_UOM_FALLBACK
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_round

_logger = logging.getLogger(__name__)

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# The grid the FK/OF money columns are written on: whole rupiah. This belongs to
# the DJP file format, not to the ledger — Odoo ships IDR with a rounding of
# 0.01 and both production tenants keep it that way, so taking the grid from
# ``currency.rounding`` would emit decimals Coretax does not accept. Every money
# cell in the client's reference workbook is a whole rupiah.
FK_AMOUNT_ROUNDING = 1.0

# PMK 131/2024. The statutory PPN rate is 12%; the 11%-effective rate everyone
# actually charges is filed as *12% on a "nilai lain" base of 11/12 of the
# price*, not as a bare 11% tariff — Coretax has no 11% tariff to accept. The
# arithmetic is exact (12% x 11/12 == 11%), so a line the ledger booked at 11%
# exports with the identical PPN rupiah; only its presentation changes.
PMK_131_EFFECTIVE_RATE = 11.0
PMK_131_STATUTORY_RATE = 12.0
PMK_131_DPP_FACTOR = 11.0 / 12.0

FK_COLUMNS = (
    "FK",
    "NPWP_WP",
    "ID_TKU_WP",
    "KD_JENIS_TRANSAKSI",
    "FG_PENGGANTI",
    "NOMOR_FAKTUR",
    "MASA_PAJAK",
    "TAHUN_PAJAK",
    "TANGGAL_FAKTUR",
    "NPWP",
    "JENIS_IDENTITAS",
    "NIK_NOMOR_PASSPORT",
    "KODE_NEGARA",
    "NAMA",
    "EMAIL_PEMBELI",
    "ALAMAT_PEMBELI",
    "TKU_PEMBELI",
    "JUMLAH_DPP",
    "JUMLAH_DPP_LAIN",
    "JUMLAH_PPN",
    "JUMLAH_PPNBM",
    "ID_KETERANGAN_TAMBAHAN",
    "FG_UANG_MUKA",
    "NOMOR_FAKTUR_UM_SEBELUMNYA",
    "UANG_MUKA_DPP",
    "UANG_MUKA_DPP_LAIN",
    "UANG_MUKA_PPN",
    "UANG_MUKA_PPNBM",
    "REFERENSI",
    "KODE_DOKUMEN_PENDUKUNG",
    "BRANCH/FIELD_TAMBAHAN_1",
    "FIELD_TAMBAHAN_2",
    "FIELD_TAMBAHAN_3",
    "FIELD_TAMBAHAN_4",
    "FIELD_TAMBAHAN_5",
)

OF_COLUMNS = (
    "OF",
    "BARANG_JASA",
    "KODE_OBJEK",
    "NAMA",
    "SATUAN",
    "HARGA_SATUAN",
    "JUMLAH_BARANG",
    "HARGA_TOTAL",
    "DISKON",
    "CHECK_DPP_LAIN",
    "DPP",
    "DPP_LAIN",
    "TARIF_PPN",
    "PPN",
    "TARIF_PPNBM",
    "PPNBM",
)


class CoretaxFkBuilder(models.AbstractModel):
    _name = "custom.coretax.fk.builder"
    _description = "Coretax e-Faktur Keluaran (FK/OF) row builder"

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _fmt_date(value):
        """DJP asks for dd/mm/yyyy and matches it as text.

        Writing a real date cell would let Excel's locale decide the rendering,
        which is exactly how import files get silently rejected.
        """
        return value.strftime("%d/%m/%Y") if value else ""

    @staticmethod
    def _digits(value):
        return (value or "").replace(".", "").replace("-", "").replace(" ", "")

    @staticmethod
    def _partner_address(partner):
        parts = [
            partner.street,
            partner.street2,
            partner.city,
            partner.state_id.name,
            partner.zip,
        ]
        return ", ".join([p for p in parts if p])

    def _fk_pemotong(self, company):
        """(npwp, nitku_suffix) for the FK header.

        FK/OF carries no "NPWP Penandatangan" column, so — unlike the bupot
        layouts — it must not be blocked on a signer.
        """
        npwp = company._check_coretax_pemotong(require_signer=False)
        return npwp, company.x_custom_nitku_suffix or ""

    @staticmethod
    def _line_vat(line):
        """(dpp, dpp_lain, ppn, tarif_ppn, uses_dpp_lain) for one invoice line.

        ``dpp`` is the contractual base; ``dpp_lain`` is the PMK 131/2024 "nilai
        lain" base the PPN is actually charged on.

        Three cases, in order:

        * a tax configured as *DPP Nilai Lain* carries its own factor and rate —
          emitted as configured;
        * a plain 11% tax is the same PMK 131/2024 arrangement expressed the
          short way in the ledger, so it is *presented* in the filing form:
          TARIF_PPN 12 on a DPP_LAIN of 11/12, CHECK_DPP_LAIN 'Y'. The PPN
          rupiah is unchanged (12% x 11/12 == 11%), so the file still ties to
          the GL. Emitting a bare 11% tariff instead gets the import rejected —
          Coretax only knows the statutory 12%;
        * anything else (12% penuh, 15%, PPnBM rates) is a regular DPP: the two
          bases coincide and CHECK_DPP_LAIN is 'N'.
        """
        dpp = line.price_subtotal
        vat = line.tax_ids.filtered(lambda t: t.amount_type == "percent" and t.amount > 0)[:1]
        if not vat:
            return dpp, 0.0, 0.0, 0.0, False
        if vat.x_custom_dpp_method == "nilai_lain" and vat.x_custom_dpp_factor:
            dpp_lain = vat._dpp_adjust(dpp)
            return dpp, dpp_lain, dpp_lain * vat.amount / 100.0, vat.amount, True
        if float_is_zero(vat.amount - PMK_131_EFFECTIVE_RATE, precision_digits=4):
            dpp_lain = dpp * PMK_131_DPP_FACTOR
            return (
                dpp,
                dpp_lain,
                dpp_lain * PMK_131_STATUTORY_RATE / 100.0,
                PMK_131_STATUTORY_RATE,
                True,
            )
        return dpp, dpp, dpp * vat.amount / 100.0, vat.amount, False

    @staticmethod
    def _item_jenis(line):
        """ "Jenis Barang Jasa" for one OF item row: "Jasa" or "Barang".

        A down-payment line carries no product of its own — core builds it from
        a "fake" SO line — so reading ``line.product_id.type`` reports every
        down payment as "Barang", even one paid against a pure services order.
        Fall back to the products of the originating order, which is what the
        down payment is actually for.

        "Jasa" only when *every* product billed is a service: a mixed order has
        no single truthful answer, and "Barang" is the safer of the two.
        """
        products = line.product_id
        if not products and "sale_line_ids" in line._fields:
            products = line.sale_line_ids.order_id.order_line.filtered(
                lambda sol: sol.product_id and not sol.display_type and not sol.is_downpayment
            ).product_id
        if products and all(product.type == "service" for product in products):
            return "Jasa"
        return "Barang"

    @staticmethod
    def _is_uang_muka(move):
        """True when this faktur *is* a down payment, for FG_UANG_MUKA.

        Core bills a down payment through a "fake" order line that carries no
        product of its own, so the only trustworthy marker is the originating
        sale order line's ``is_downpayment``. Every billed line has to be one:
        the settlement invoice carries the deducted down payment *alongside* the
        goods it settles, and that is a regular faktur, not a down-payment one.

        The companion columns (NOMOR_FAKTUR_UM_SEBELUMNYA, UANG_MUKA_*) are the
        settlement side of the arrangement — how much already-invoiced down
        payment a final faktur subtracts — and they stay empty until the client
        confirms how they file it: the number wanted there is the *nomor faktur
        pajak* Coretax assigned to the earlier faktur, which this database does
        not hold.
        """
        lines = move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
        if not lines or "sale_line_ids" not in lines._fields:
            return False
        return all(line.sale_line_ids and all(sol.is_downpayment for sol in line.sale_line_ids) for line in lines)

    @staticmethod
    def _round_and_plug(raw_values, rounding):
        """Whole-currency-unit OF amounts whose written sum ties to the total.

        Rounding each line independently and then rounding their sum gives two
        numbers that disagree by a rupiah or two, and Coretax rejects an FK
        total that does not equal the OF column beneath it. So: round every line
        but the last one DOWN, and let the last line absorb the entire residual.

        DOWN rather than half-even because that is what the client's reference
        workbook does — three equal thirds of 3.740.000 come out as
        1.246.666 / 1.246.666 / 1.246.668, not 1.246.667 twice.

        Callers pass ``FK_AMOUNT_ROUNDING`` — a whole-rupiah grid — so
        ``sum(written) == total`` holds bit-exactly. (On a fractional grid it
        would hold only to within that grid, since 0.01 has no exact binary
        representation and summing it drifts in the last bits.)

        Returns ``(written_values, total)``.
        """
        if not raw_values:
            return [], 0.0
        total = float_round(sum(raw_values), precision_rounding=rounding)
        written = [float_round(value, precision_rounding=rounding, rounding_method="DOWN") for value in raw_values[:-1]]
        # Every term is already a multiple of ``rounding``, so this only strips
        # float noise — it cannot move the value off the grid.
        written.append(float_round(total - sum(written), precision_rounding=rounding))
        return written, total

    # ------------------------------------------------------------ validation

    def _coretax_fk_check_moves(self, moves):
        """Validate a selection for FK export.

        Returns ``(moves_ordered, company)``. Raises ``UserError`` — never
        silently drops a record, because a tax file that quietly omits an
        invoice is worse than one that refuses to render.
        """
        if not moves:
            raise UserError(_("Tidak ada faktur yang dipilih untuk diekspor."))

        wrong_type = moves.filtered(lambda m: m.move_type != "out_invoice")
        if wrong_type:
            raise UserError(
                _(
                    "Hanya Faktur Penjualan (customer invoice) yang bisa diekspor ke "
                    "e-Faktur Keluaran.\n\nBukan faktur penjualan:\n%s",
                    "\n".join("  - %s" % (m.display_name or m.name) for m in wrong_type),
                )
            )

        not_posted = moves.filtered(lambda m: m.state != "posted")
        if not_posted:
            labels = dict(moves._fields["state"]._description_selection(self.env))
            raise UserError(
                _(
                    "Faktur berikut belum di-posting, sehingga tidak bisa diekspor ke "
                    "Coretax:\n%s\n\nPosting faktur tersebut terlebih dahulu, lalu ulangi "
                    "ekspor.",
                    "\n".join(
                        "  - %s (%s)" % (m.display_name or m.name, labels.get(m.state, m.state)) for m in not_posted
                    ),
                )
            )

        undated = moves.filtered(lambda m: not m.invoice_date)
        if undated:
            raise UserError(
                _(
                    "Faktur berikut tidak punya Tanggal Faktur, sehingga masa dan tahun "
                    "pajaknya tidak bisa ditentukan:\n%s",
                    "\n".join("  - %s" % (m.display_name or m.name) for m in undated),
                )
            )

        companies = moves.company_id
        if len(companies) > 1:
            raise UserError(
                _(
                    "Pilih faktur dari satu perusahaan saja — satu berkas FK hanya memuat "
                    "satu NPWP Wajib Pajak.\n\nPerusahaan terpilih: %s",
                    ", ".join(companies.mapped("name")),
                )
            )

        return moves.sorted(lambda m: (m.invoice_date, m.name or "")), companies

    # ------------------------------------------------------- empty-selection

    def _coretax_fk_empty_hints(self, date_from, date_to, company, partner_ids=None, journal_ids=None):
        """Explain an empty FK selection by loosening one filter at a time.

        "Tidak ada data" is almost never an empty month — it is the active
        company, a draft invoice, or a nota kredit that the user counted on.
        Each probe keeps the period and drops exactly one condition, so the
        line that comes back names the filter that actually emptied the set.
        Record rules already bound every search to the user's allowed
        companies, so the cross-company probe cannot leak another tenant.
        """
        Move = self.env["account.move"]
        period = [("invoice_date", ">=", date_from), ("invoice_date", "<=", date_to)]
        posted_sale = period + [("move_type", "=", "out_invoice"), ("state", "=", "posted")]
        hints = []

        elsewhere = Move._read_group(
            posted_sale + [("company_id", "!=", company.id)],
            groupby=["company_id"],
            aggregates=["__count"],
        )
        if elsewhere:
            per_company = [
                _("%(name)s (%(count)s faktur)", name=other.display_name, count=count) for other, count in elsewhere
            ]
            hints.append(
                _(
                    "Ada faktur ter-posting di periode ini, tetapi milik perusahaan lain: "
                    "%(companies)s. Satu berkas FK hanya memuat satu NPWP — ganti "
                    "'Perusahaan' di wizard (atau pindah perusahaan aktif), lalu ekspor "
                    "per perusahaan.",
                    companies=", ".join(per_company),
                )
            )

        in_company = [("company_id", "=", company.id)]
        unposted = Move.search_count(
            period + in_company + [("move_type", "=", "out_invoice"), ("state", "!=", "posted")]
        )
        if unposted:
            hints.append(
                _(
                    "%(count)s faktur penjualan di periode ini belum ter-posting (draft/batal). "
                    "Coretax hanya menerima faktur ter-posting — posting dulu, lalu ulangi ekspor.",
                    count=unposted,
                )
            )

        refunds = Move.search_count(period + in_company + [("move_type", "=", "out_refund"), ("state", "=", "posted")])
        if refunds:
            hints.append(
                _(
                    "%(count)s nota kredit (retur penjualan) ada di periode ini. Nota kredit "
                    "tidak masuk berkas FK — gunakan template Retur.",
                    count=refunds,
                )
            )

        if partner_ids:
            loosened = Move.search_count(posted_sale + in_company + self._coretax_journal_domain(journal_ids))
            if loosened:
                hints.append(
                    _(
                        "Tanpa filter pelanggan ada %(count)s faktur — filter pelanggannya yang terlalu sempit.",
                        count=loosened,
                    )
                )
        if journal_ids:
            loosened = Move.search_count(posted_sale + in_company + self._coretax_partner_domain(partner_ids))
            if loosened:
                hints.append(
                    _(
                        "Tanpa filter jurnal ada %(count)s faktur — filter jurnalnya yang terlalu sempit.",
                        count=loosened,
                    )
                )

        if not hints:
            # Nothing anywhere in the period: point at the nearest invoice so the
            # user can see at a glance whether they are off by a month.
            nearest = Move.search(
                [("move_type", "=", "out_invoice"), ("state", "=", "posted")] + in_company,
                order="invoice_date desc",
                limit=1,
            )
            if nearest:
                hints.append(
                    _(
                        "Faktur penjualan ter-posting terakhir di %(company)s bertanggal "
                        "%(date)s — periksa kembali periode yang dipilih.",
                        company=company.name,
                        date=self._fmt_date(nearest.invoice_date),
                    )
                )
            else:
                hints.append(
                    _(
                        "Belum ada satu pun faktur penjualan ter-posting di %(company)s.",
                        company=company.name,
                    )
                )
        return hints

    @staticmethod
    def _coretax_partner_domain(partner_ids):
        return [("partner_id", "child_of", partner_ids.ids)] if partner_ids else []

    @staticmethod
    def _coretax_journal_domain(journal_ids):
        return [("journal_id", "in", journal_ids.ids)] if journal_ids else []

    # --------------------------------------------------------- row building

    def _coretax_fk_rows(self, moves, company=None):
        """([FK_COLUMNS, OF_COLUMNS], data_rows) for an arbitrary invoice set.

        MASA_PAJAK / TAHUN_PAJAK are derived per invoice from ``invoice_date``,
        not from a wizard field, so a selection spanning two tax periods emits
        the right period on each FK row.
        """
        company = company or moves.company_id[:1] or self.env.company
        npwp_wp, nitku = self._fk_pemotong(company)
        rows = []
        for move in moves:
            partner = move.partner_id.commercial_partner_id
            items = move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
            if not items:
                continue
            of_rows, totals = self._coretax_fk_of_rows(move, items)
            rows.append(
                [
                    "FK",
                    npwp_wp,
                    nitku,
                    # KD_JENIS_TRANSAKSI 04 = "Other Tax Base" (DPP Nilai Lain),
                    # 01 = to another party. Chosen per invoice from whether any
                    # line actually rides a nilai-lain tax.
                    "04" if any(r[9] == "Y" for r in of_rows) else "01",
                    "0",  # FG_PENGGANTI — replacements go through the Faktur
                    # Pengganti wizard, which owns the 01/02 status code.
                    "",  # NOMOR_FAKTUR — assigned by Coretax on import
                    "%02d" % move.invoice_date.month,
                    str(move.invoice_date.year),
                    self._fmt_date(move.invoice_date),
                    partner._custom_coretax_npwp(),
                    "",  # JENIS_IDENTITAS
                    "",  # NIK_NOMOR_PASSPORT
                    partner.country_id.x_custom_code_alpha3 or "",
                    partner.name or "",
                    partner.email or "",
                    self._partner_address(partner),
                    partner._custom_coretax_nitku()[-6:] if partner._custom_coretax_npwp() else "",
                    totals[0],
                    totals[1],
                    totals[2],
                    0,  # JUMLAH_PPNBM
                    "",  # ID_KETERANGAN_TAMBAHAN
                    "1" if self._is_uang_muka(move) else "0",  # FG_UANG_MUKA
                    "",
                    0,
                    0,
                    0,
                    0,
                    move.ref or move.name or "",
                    "",  # KODE_DOKUMEN_PENDUKUNG
                    "HO",  # BRANCH
                    "",
                    "",
                    "",
                    "",
                ]
            )
            rows.extend(of_rows)
        return [FK_COLUMNS, OF_COLUMNS], rows

    def _coretax_fk_of_rows(self, move, items):
        """(of_rows, [jumlah_dpp, jumlah_dpp_lain, jumlah_ppn]) for one invoice."""
        rounding = FK_AMOUNT_ROUNDING
        raw = [self._line_vat(line) for line in items]

        dpps, jumlah_dpp = self._round_and_plug([r[0] for r in raw], rounding)
        lains, jumlah_lain = self._round_and_plug([r[1] for r in raw], rounding)
        ppns, jumlah_ppn = self._round_and_plug([r[2] for r in raw], rounding)

        of_rows = []
        for index, line in enumerate(items):
            tarif, uses = raw[index][3], raw[index][4]
            dpp = dpps[index]
            harga_total, diskon = self._coretax_fk_gross_and_discount(line, dpp)
            of_rows.append(
                [
                    "OF",
                    self._item_jenis(line),
                    # Kode objek barang/jasa: '000000' is the generic
                    # catch-all in CODE_OF_GOODS / CODE_OF_SERVICES, and
                    # what the client's own samples use throughout.
                    "000000",
                    line.product_id.name or line.name or "",
                    line.product_uom_id.x_custom_coretax_code or CORETAX_UOM_FALLBACK,
                    line.price_unit,
                    line.quantity,
                    harga_total,
                    diskon,
                    "Y" if uses else "N",
                    dpp,
                    lains[index],
                    tarif,
                    ppns[index],
                    0,
                    0,
                ]
            )
        return of_rows, [jumlah_dpp, jumlah_lain, jumlah_ppn]

    @staticmethod
    def _coretax_fk_gross_and_discount(line, dpp):
        """(HARGA_TOTAL, DISKON) such that HARGA_TOTAL - DISKON == DPP exactly.

        DJP wants the gross before discount in HARGA_TOTAL and the discount
        itself in DISKON; the client's reference workbook shows the three tying
        (340.000 x 5 = 1.700.000 - 340.000 = 1.360.000). Writing DISKON as a
        flat 0 — which is what this used to do — breaks that tie on every
        discounted line.

        The gross is reconstructed from the discount percentage rather than from
        ``price_unit * quantity`` so it stays correct when the line carries a
        price-included tax, where ``price_unit`` is gross of PPN but ``dpp``
        (``price_subtotal``) is not. With no discount the two are identical.
        DISKON is then derived from the *written* DPP, so the invariant survives
        the residual plug on the last line.
        """
        discount = line.discount or 0.0
        if discount and discount < 100.0:
            gross = dpp / (1.0 - discount / 100.0)
        else:
            gross = line.price_unit * line.quantity
        harga_total = float_round(gross, precision_rounding=FK_AMOUNT_ROUNDING)
        diskon = harga_total - dpp
        if diskon < 0:
            # A negative discount is a surcharge, which the FK layout has no
            # column for. Emitting one gets the file bounced, so collapse it and
            # say so rather than shipping a value DJP rejects.
            _logger.warning(
                "e-Faktur FK: negative DISKON on %s line %s (gross %s < DPP %s); emitting HARGA_TOTAL = DPP instead",
                line.move_id.name,
                line.name,
                harga_total,
                dpp,
            )
            return dpp, 0.0
        return harga_total, diskon

    # ------------------------------------------------------------------ render

    def _render(self, header_rows, data_rows, sheet_name):
        """Header rows first (row 1..n), then data. No banner, no formatting.

        ``custom.report.engine`` prefixes a title/company/period banner and
        formats numbers for humans; a DJP import file must start its header on
        row 1 and carry raw values, hence xlsxwriter directly.
        """
        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(sheet_name[:31])
        # Everything is written as text or number exactly as built; a bold
        # header is cosmetic and Coretax ignores it.
        bold = workbook.add_format({"bold": True})

        row = 0
        for header in header_rows:
            for col, value in enumerate(header):
                sheet.write(row, col, value, bold)
            row += 1
        for data in data_rows:
            for col, value in enumerate(data):
                sheet.write(row, col, value)
            row += 1

        workbook.close()
        return output.getvalue()

    # ------------------------------------------------------------------ export

    @staticmethod
    def _coretax_fk_slug(value):
        """Filename-safe fragment: '/' and spaces are the only real offenders."""
        return "".join(c if c.isalnum() else "_" for c in (value or "")).strip("_")

    def _coretax_fk_filename(self, moves, stem="faktur_keluaran"):
        """One naming rule for every entry point.

        A single invoice is named after itself so the accountant can find it; a
        multi-invoice export is named after the tax period it covers, falling
        back to a count when the selection straddles two periods.
        """
        if len(moves) == 1:
            return "%s_%s.xlsx" % (stem, self._coretax_fk_slug(moves.name))
        periods = {(m.invoice_date.month, m.invoice_date.year) for m in moves}
        if len(periods) == 1:
            month, year = periods.pop()
            return "%s_%02d_%04d.xlsx" % (stem, month, year)
        latest = max(moves.mapped("invoice_date"))
        return "%s_%d_faktur_%s.xlsx" % (stem, len(moves), latest.strftime("%Y%m%d"))

    def _coretax_fk_export(self, moves, filename=None):
        """Validate, build, render and hand back a browser download."""
        moves, company = self._coretax_fk_check_moves(moves)
        header_rows, data_rows = self._coretax_fk_rows(moves, company=company)
        if not data_rows:
            raise UserError(
                _("Faktur terpilih tidak memiliki baris barang/jasa, sehingga tidak ada yang bisa diekspor.")
            )
        content = self._render(header_rows, data_rows, "Import FK")
        values = {
            "name": filename or self._coretax_fk_filename(moves),
            "type": "binary",
            "datas": base64.b64encode(content),
            "mimetype": XLSX_MIMETYPE,
        }
        if len(moves) == 1:
            # Single invoice: also file it under the invoice's own attachments,
            # so re-exporting later is not the only way to find it again.
            values.update({"res_model": moves._name, "res_id": moves.id})
        attachment = self.env["ir.attachment"].create(values)
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
