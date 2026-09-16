# Usulan koreksi PPN Masukan yang terlanjur masuk harga pokok -- prd_levis_begbal.
#
# Latar: harga di PO sudah TERMASUK PPN (DPP nilai lain 11/12, PMK 11/2025 -> tarif
# efektif 11%). Tetapi 225 PO dibuat lewat import Excel, dan import melewati
# onchange_product_id() -- satu-satunya tempat Odoo 19 mengisi purchase.order.line.tax_ids
# (purchase/models/purchase_order_line.py:366 -> _product_id_change -> _compute_tax_id).
# Akibatnya kolom Taxes kosong di 20.829 baris, dan _get_gross_price_unit() (baris 484)
# memakai harga bruto apa adanya sebagai harga pokok, bukan hasil compute_all()['total_void'].
#
# Dampaknya sudah masuk buku besar: jurnal GR (custom_levis_localization, ref
# GR-VAL:<stock_move_id>, jurnal "Inventory Valuation") mendebit Persediaan sebesar
# nilai BRUTO dan mengkredit GR/IR Clearing sebesar nilai bruto juga. PPN Masukan yang
# semestinya menunggu faktur pajak ikut terkapitalisasi ke persediaan.
#
# Script ini SELECT-ONLY. Tidak ada UPDATE/INSERT ke Odoo; satu-satunya tulisan adalah
# file Excel di /srv/sftp-share/files (unduh lewat File Browser /files).
#
#   python3 scripts/tenants/levis/84_report_ppn_included_correction.py
#
# Env:  DB   -> database (default prd_levis_begbal)
#       OUT  -> path file xlsx

import csv
import io
import os
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

PG = "odoo19-platform-postgres"
DB = os.environ.get("DB", "prd_levis_begbal")
OUT = os.environ.get("OUT", "/srv/sftp-share/files/Usulan_Koreksi_PPN_Masukan_PO_Agustus2026.xlsx")

# PPN 12% atas DPP nilai lain 11/12 => tarif efektif 11% dari DPP.
# Harga PO adalah bruto (sudah termasuk PPN), jadi DPP = bruto / 1,11.
GROSS = Decimal("1.11")
CENT = Decimal("0.01")

MONEY = "#,##0.00"
QTY = "#,##0"
HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
SUB_FONT = Font(bold=True)
TITLE_FONT = Font(bold=True, size=13, color="1F4E78")
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")
OK_FILL = PatternFill("solid", fgColor="E2EFDA")
NEU_FILL = PatternFill("solid", fgColor="DDEBF7")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def q(sql):
    """Run a read-only query and return a list of dicts."""
    out = subprocess.run(
        [
            "docker",
            "exec",
            PG,
            "sh",
            "-c",
            f'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d {DB} --csv -v ON_ERROR_STOP=1 -c "{sql}"',
        ],
        capture_output=True,
        text=True,
    )
    if out.returncode:
        sys.exit(f"query failed:\n{out.stderr}")
    return list(csv.DictReader(io.StringIO(out.stdout)))


def dpp_of(gross):
    """DPP = bruto / 1,11 dibulatkan ke sen; PPN = sisanya (tidak ada rupiah hilang)."""
    return (Decimal(gross) / GROSS).quantize(CENT, rounding=ROUND_HALF_UP)


def f(v):
    return float(v)


def head(ws, row, cols, widths=None):
    for i, c in enumerate(cols, start=1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.fill, cell.font, cell.border = HDR_FILL, HDR_FONT, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w


def money_cell(ws, row, col, val, bold=False, fill=None):
    cell = ws.cell(row=row, column=col, value=f(val))
    cell.number_format = MONEY
    cell.border = BOX
    if bold:
        cell.font = SUB_FONT
    if fill:
        cell.fill = fill
    return cell


# --------------------------------------------------------------------------
# 1. Rekap GL jurnal GR yang sudah terbukukan, per akun
# --------------------------------------------------------------------------
gl = q(
    "select a.id acc_id, a.code_store->>'1' kode, a.name->>'en_US' akun, "
    "a.account_type, sum(l.debit) debit, sum(l.credit) kredit, count(*) baris "
    "from account_move_line l "
    "join account_move m on m.id = l.move_id "
    "join account_journal j on j.id = m.journal_id "
    "join account_account a on a.id = l.account_id "
    "where j.name->>'en_US' = 'Inventory Valuation' and m.ref like 'GR-VAL:%' "
    "and m.state = 'posted' "
    "group by 1,2,3,4 order by 2"
)

# --------------------------------------------------------------------------
# 2. Rekap per PO, lewat GR-VAL:<stock_move_id> -> purchase_line -> purchase_order
# --------------------------------------------------------------------------
per_po = q(
    "select o.id po_id, o.name po, p.name vendor, o.date_order::date tgl, o.state, "
    "count(*) baris, sum(sm.product_qty) qty, sum(sm.value) bruto "
    "from account_move am "
    "join account_journal j on j.id = am.journal_id "
    "join stock_move sm on sm.id = split_part(am.ref, ':', 2)::int "
    "join purchase_order_line pl on pl.id = sm.purchase_line_id "
    "join purchase_order o on o.id = pl.order_id "
    "join res_partner p on p.id = o.partner_id "
    "where j.name->>'en_US' = 'Inventory Valuation' and am.ref like 'GR-VAL:%' "
    "and am.state = 'posted' "
    "group by 1,2,3,4,5 order by o.name"
)

# --------------------------------------------------------------------------
# 2b. Rekap per dokumen GR -- satuan jurnal koreksi yang disetujui FICO:
#     satu jurnal per stock.picking, ref PPN-INC-KOREKSI:<nama GR>.
# --------------------------------------------------------------------------
per_gr = q(
    "select sp.name gr, o.name po, p.name vendor, am.date::date tgl, "
    "count(*) baris, sum(sm.product_qty) qty, sum(sm.value) bruto "
    "from account_move am "
    "join account_journal j on j.id = am.journal_id "
    "join stock_move sm on sm.id = split_part(am.ref, ':', 2)::int "
    "join stock_picking sp on sp.id = sm.picking_id "
    "join purchase_order_line pl on pl.id = sm.purchase_line_id "
    "join purchase_order o on o.id = pl.order_id "
    "join res_partner p on p.id = o.partner_id "
    "where j.name->>'en_US' = 'Inventory Valuation' and am.ref like 'GR-VAL:%' "
    "and am.state = 'posted' "
    "group by 1,2,3,4 order by sp.name"
)

# --------------------------------------------------------------------------
# 3. Detail satu PO sebagai contoh perhitungan
# --------------------------------------------------------------------------
sample_po = per_po[0]["po"] if per_po else None
detail = (
    q(
        "select pl.id line_id, pt.default_code sku, pt.name->>'en_US' produk, "
        "sm.product_qty qty, sm.price_unit harga, sm.value bruto "
        "from account_move am "
        "join account_journal j on j.id = am.journal_id "
        "join stock_move sm on sm.id = split_part(am.ref, ':', 2)::int "
        "join purchase_order_line pl on pl.id = sm.purchase_line_id "
        "join purchase_order o on o.id = pl.order_id "
        "join product_product pp on pp.id = sm.product_id "
        "join product_template pt on pt.id = pp.product_tmpl_id "
        f"where j.name->>'en_US' = 'Inventory Valuation' and am.ref like 'GR-VAL:%' "
        f"and am.state = 'posted' and o.name = '{sample_po}' "
        "order by pt.default_code limit 25"
    )
    if sample_po
    else []
)

# --------------------------------------------------------------------------
# Hitungan
# --------------------------------------------------------------------------
t_bruto = sum(Decimal(r["bruto"]) for r in per_po)
t_dpp = sum(dpp_of(r["bruto"]) for r in per_po)
t_ppn = t_bruto - t_dpp
t_qty = sum(Decimal(r["qty"]) for r in per_po)
t_baris = sum(int(r["baris"]) for r in per_po)

wb = Workbook()

# ==========================================================================
# Sheet 1 -- Ringkasan
# ==========================================================================
ws = wb.active
ws.title = "Ringkasan"
ws.column_dimensions["A"].width = 3
ws.column_dimensions["B"].width = 46
ws.column_dimensions["C"].width = 26
ws.column_dimensions["D"].width = 72

r = 2
ws.cell(row=r, column=2, value="Usulan Koreksi PPN Masukan yang Terkapitalisasi ke Persediaan").font = TITLE_FONT
r += 1
ws.cell(row=r, column=2, value=f"Database {DB} - PO Agustus 2026 - untuk persetujuan FICO").font = Font(
    italic=True, color="808080"
)
r += 2

for label, val, note in [
    (
        "Masalah",
        "Kolom Taxes kosong di seluruh PO",
        "225 PO / 20.829 baris dibuat lewat import Excel. Import melewati onchange_product_id(), "
        "satu-satunya tempat Odoo 19 mengisi tax_ids pada baris PO. Akibatnya amount_tax = 0 di semua PO.",
    ),
    (
        "Akibat ke harga pokok",
        "Persediaan dicatat sebesar BRUTO",
        "Karena tax_ids kosong, _get_gross_price_unit() memakai harga PO apa adanya. Seharusnya "
        "memakai compute_all()['total_void'], yaitu porsi non-deductible saja -- yakni DPP, "
        "karena PPN Masukan dapat dikreditkan dan bukan unsur harga pokok.",
    ),
    (
        "Dasar tarif",
        "PPN 12% x DPP nilai lain 11/12",
        "PMK 11/2025 -- tarif efektif 11% dari DPP. Harga PO sudah termasuk PPN, sehingga "
        "DPP = harga / 1,11 dan PPN = harga - DPP.",
    ),
    (
        "Sudah masuk buku besar?",
        "YA - 20.829 jurnal, posted",
        "Jurnal GR (jurnal Inventory Valuation, ref GR-VAL:<stock_move_id>) sudah posted: "
        "Debit Persediaan / Kredit GR-IR Clearing, keduanya sebesar nilai bruto.",
    ),
    (
        "Barang sudah keluar / terjual?",
        "BELUM - 0 move keluar",
        "Tidak ada pengeluaran barang dari lot ini, sehingga koreksi belum menyentuh HPP. "
        "Ini alasan koreksi masih dapat dilakukan bersih.",
    ),
    (
        "Tagihan vendor terbit?",
        "Tidak ada yang aktif",
        "Hanya 1 bill pernah dibuat (BILL/T/EBR/2026/08/00001) dan statusnya CANCEL. "
        "Tidak ada utang usaha yang perlu ikut dikoreksi.",
    ),
    (
        "Periode",
        "Juli-Agustus 2026, TERBUKA",
        "fiscalyear_lock_date = 30-Jun-2026. GR bertanggal 31-Jul s/d 06-Aug-2026, "
        "jadi koreksi dapat dibukukan di periode berjalan tanpa membuka periode terkunci.",
    ),
]:
    c = ws.cell(row=r, column=2, value=label)
    c.font, c.fill, c.border = SUB_FONT, NEU_FILL, BOX
    c = ws.cell(row=r, column=3, value=val)
    c.font, c.border = SUB_FONT, BOX
    c.alignment = Alignment(wrap_text=True, vertical="top")
    c = ws.cell(row=r, column=4, value=note)
    c.border = BOX
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 42
    r += 1

r += 1
ws.cell(row=r, column=2, value="Angka Koreksi").font = TITLE_FONT
r += 1
head(ws, r, ["", "Keterangan", "Jumlah", "Catatan"])
r += 1
for label, val, note in [
    ("Nilai GR tercatat (bruto)", t_bruto, "Sama dengan total debit Persediaan di jurnal GR."),
    ("Seharusnya - DPP", t_dpp, "Bruto / 1,11. Ini nilai persediaan yang benar."),
    ("PPN Masukan (koreksi)", t_ppn, "Turunkan Persediaan dan GR/IR Clearing sebesar ini."),
]:
    ws.cell(row=r, column=2, value=label).border = BOX
    money_cell(ws, r, 3, val, bold=True, fill=WARN_FILL if "PPN" in label else None)
    c = ws.cell(row=r, column=4, value=note)
    c.border = BOX
    c.alignment = Alignment(wrap_text=True)
    r += 1

ws.cell(row=r, column=2, value="Jumlah PO / baris / qty").border = BOX
c = ws.cell(row=r, column=3, value=f"{len(per_po)} PO / {t_baris:,} baris / {t_qty:,.0f} pcs")
c.border, c.font = BOX, SUB_FONT
r += 2

ws.cell(row=r, column=2, value="Usulan Tindakan").font = TITLE_FONT
r += 1
for i, step in enumerate(
    [
        "Bukukan jurnal koreksi untuk menurunkan Persediaan dan GR/IR Clearing sebesar "
        "PPN Masukan -- SATU JURNAL PER DOKUMEN GR (ref PPN-INC-KOREKSI:<nama GR>), "
        "bertanggal akhir bulan periode GR-nya, agar saldo tetap terpisah per GR. "
        "Rinciannya di sheet 'Rekap per GR'. Tidak ada dampak ke laba rugi.",
        "Isi kolom Taxes pada 20.829 baris PO dengan pajak pembelian 12% included, "
        "sehingga nilai DPP dan PPN tampil benar di PO dan mengalir ke tagihan vendor.",
        "Selaraskan harga pokok pada 20.829 stock move ke DPP, agar lapisan FIFO "
        "tidak membawa harga bruto ke HPP saat barang mulai terjual.",
        "Tambahkan kolom Taxes pada template import PO -- import selamanya melewati "
        "onchange yang mengisi pajak, jadi tanpa kolom ini masalahnya akan berulang.",
    ],
    start=1,
):
    ws.cell(row=r, column=2, value=f"{i}.").font = SUB_FONT
    c = ws.cell(row=r, column=3, value=step)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
    ws.row_dimensions[r].height = 40
    r += 1

# ==========================================================================
# Sheet 2 -- Dampak Jurnal
# ==========================================================================
ws2 = wb.create_sheet("Dampak Jurnal")
r = 2
ws2.cell(row=r, column=2, value="A. Jurnal GR yang sudah terbukukan (posted)").font = TITLE_FONT
r += 2
head(
    ws2,
    r,
    ["", "Kode Akun", "Nama Akun", "Tipe", "Baris", "Debit", "Kredit"],
    [3, 16, 44, 20, 10, 20, 20],
)
r += 1
gl_start = r
for g in gl:
    ws2.cell(row=r, column=2, value=g["kode"]).border = BOX
    ws2.cell(row=r, column=3, value=g["akun"]).border = BOX
    ws2.cell(row=r, column=4, value=g["account_type"]).border = BOX
    c = ws2.cell(row=r, column=5, value=int(g["baris"]))
    c.number_format, c.border = QTY, BOX
    money_cell(ws2, r, 6, Decimal(g["debit"]))
    money_cell(ws2, r, 7, Decimal(g["kredit"]))
    r += 1
ws2.cell(row=r, column=3, value="TOTAL").font = SUB_FONT
money_cell(ws2, r, 6, sum(Decimal(g["debit"]) for g in gl), bold=True)
money_cell(ws2, r, 7, sum(Decimal(g["kredit"]) for g in gl), bold=True)
r += 3

ws2.cell(row=r, column=2, value="B. Seharusnya - nilai DPP").font = TITLE_FONT
r += 1
c = ws2.cell(
    row=r,
    column=2,
    value="PPN Masukan tidak dikapitalisasi ke persediaan; pengakuannya menunggu faktur pajak "
    "dan dibukukan saat tagihan vendor diterima.",
)
c.font = Font(italic=True, color="808080")
ws2.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
r += 2
head(
    ws2, r, ["", "Kode Akun", "Nama Akun", "Bruto tercatat", "DPP seharusnya", "PPN (selisih)"], [3, 16, 44, 20, 20, 20]
)
r += 1
koreksi = []
for g in gl:
    bruto = Decimal(g["debit"]) + Decimal(g["kredit"])
    dpp = dpp_of(bruto)
    ppn = bruto - dpp
    koreksi.append((g, bruto, dpp, ppn))
    ws2.cell(row=r, column=2, value=g["kode"]).border = BOX
    ws2.cell(row=r, column=3, value=g["akun"]).border = BOX
    money_cell(ws2, r, 4, bruto)
    money_cell(ws2, r, 5, dpp, fill=OK_FILL)
    money_cell(ws2, r, 6, ppn, fill=WARN_FILL)
    r += 1
ws2.cell(row=r, column=3, value="TOTAL").font = SUB_FONT
money_cell(ws2, r, 4, sum(k[1] for k in koreksi), bold=True)
money_cell(ws2, r, 5, sum(k[2] for k in koreksi), bold=True)
money_cell(ws2, r, 6, sum(k[3] for k in koreksi), bold=True)
r += 3

ws2.cell(row=r, column=2, value="C. Usulan jurnal koreksi").font = TITLE_FONT
r += 1
c = ws2.cell(
    row=r,
    column=2,
    value="Dibukukan SATU JURNAL PER DOKUMEN GR (ref PPN-INC-KOREKSI:<nama GR>), bertanggal "
    "akhir bulan periode GR-nya, sehingga saldo koreksi tetap terpisah per GR. Angka di bawah "
    "adalah totalnya. Menurunkan kedua sisi neraca sebesar PPN Masukan; tidak menyentuh laba rugi.",
)
c.font = Font(italic=True, color="808080")
ws2.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
r += 2
head(ws2, r, ["", "Kode Akun", "Nama Akun", "Keterangan", "Debit", "Kredit"], [3, 16, 44, 40, 20, 20])
r += 1
tot_d = tot_k = Decimal("0")
for g, bruto, dpp, ppn in koreksi:
    if g["account_type"] == "liability_current":
        ws2.cell(row=r, column=2, value=g["kode"]).border = BOX
        ws2.cell(row=r, column=3, value=g["akun"]).border = BOX
        ws2.cell(row=r, column=4, value="Koreksi PPN Masukan atas GR PO Agustus 2026").border = BOX
        money_cell(ws2, r, 5, ppn)
        money_cell(ws2, r, 6, Decimal("0"))
        tot_d += ppn
        r += 1
for g, bruto, dpp, ppn in koreksi:
    if g["account_type"] == "asset_current":
        ws2.cell(row=r, column=2, value=g["kode"]).border = BOX
        ws2.cell(row=r, column=3, value=g["akun"]).border = BOX
        ws2.cell(row=r, column=4, value="Keluarkan PPN Masukan dari harga pokok persediaan").border = BOX
        money_cell(ws2, r, 5, Decimal("0"))
        money_cell(ws2, r, 6, ppn)
        tot_k += ppn
        r += 1
ws2.cell(row=r, column=4, value="TOTAL").font = SUB_FONT
money_cell(ws2, r, 5, tot_d, bold=True, fill=NEU_FILL)
money_cell(ws2, r, 6, tot_k, bold=True, fill=NEU_FILL)
r += 2
c = ws2.cell(
    row=r,
    column=2,
    value="Catatan: PPN Masukan belum diakui sebagai aset pajak pada jurnal ini. Pengakuannya "
    "terjadi saat tagihan vendor dibukukan -- Debit GR/IR Clearing (DPP) + Debit PPN Masukan, "
    "Kredit Utang Usaha (bruto) -- sehingga GR/IR Clearing tertutup tepat.",
)
c.alignment = Alignment(wrap_text=True, vertical="top")
ws2.merge_cells(start_row=r, start_column=2, end_row=r + 2, end_column=7)

# ==========================================================================
# Sheet 3 -- Rekap per PO
# ==========================================================================
ws3 = wb.create_sheet("Rekap per PO")
r = 2
ws3.cell(row=r, column=2, value="Rincian per Purchase Order").font = TITLE_FONT
r += 2
head(
    ws3,
    r,
    ["", "No PO", "Vendor", "Tanggal", "Status", "Baris", "Qty", "Bruto tercatat", "DPP seharusnya", "PPN (koreksi)"],
    [3, 24, 34, 13, 12, 9, 11, 20, 20, 20],
)
r += 1
for row in per_po:
    bruto = Decimal(row["bruto"])
    dpp = dpp_of(bruto)
    ws3.cell(row=r, column=2, value=row["po"]).border = BOX
    ws3.cell(row=r, column=3, value=row["vendor"]).border = BOX
    ws3.cell(row=r, column=4, value=row["tgl"]).border = BOX
    ws3.cell(row=r, column=5, value=row["state"]).border = BOX
    c = ws3.cell(row=r, column=6, value=int(row["baris"]))
    c.number_format, c.border = QTY, BOX
    c = ws3.cell(row=r, column=7, value=f(Decimal(row["qty"])))
    c.number_format, c.border = QTY, BOX
    money_cell(ws3, r, 8, bruto)
    money_cell(ws3, r, 9, dpp)
    money_cell(ws3, r, 10, bruto - dpp)
    r += 1
ws3.cell(row=r, column=3, value=f"TOTAL ({len(per_po)} PO)").font = SUB_FONT
c = ws3.cell(row=r, column=6, value=t_baris)
c.number_format, c.font = QTY, SUB_FONT
c = ws3.cell(row=r, column=7, value=f(t_qty))
c.number_format, c.font = QTY, SUB_FONT
money_cell(ws3, r, 8, t_bruto, bold=True)
money_cell(ws3, r, 9, t_dpp, bold=True, fill=OK_FILL)
money_cell(ws3, r, 10, t_ppn, bold=True, fill=WARN_FILL)
ws3.freeze_panes = "B6"

# ==========================================================================
# Sheet 3b -- Rekap per dokumen GR (satuan jurnal koreksi)
# ==========================================================================
ws5 = wb.create_sheet("Rekap per GR")
r = 2
ws5.cell(row=r, column=2, value="Rincian per Dokumen Goods Receipt").font = TITLE_FONT
r += 1
c = ws5.cell(
    row=r,
    column=2,
    value="Satu baris di sini = satu jurnal koreksi, ref PPN-INC-KOREKSI:<nama GR>, "
    "bertanggal akhir bulan periode GR-nya. Saldo koreksi terpisah per GR.",
)
c.font = Font(italic=True, color="808080")
r += 2
head(
    ws5,
    r,
    [
        "",
        "Dokumen GR",
        "No PO",
        "Vendor",
        "Tgl GR",
        "Baris",
        "Qty",
        "Bruto tercatat",
        "DPP seharusnya",
        "PPN (koreksi)",
    ],
    [3, 22, 24, 32, 13, 9, 11, 20, 20, 20],
)
r += 1
g_bruto = g_dpp = Decimal("0")
for row in per_gr:
    bruto = Decimal(row["bruto"])
    dpp = dpp_of(bruto)
    g_bruto += bruto
    g_dpp += dpp
    ws5.cell(row=r, column=2, value=row["gr"]).border = BOX
    ws5.cell(row=r, column=3, value=row["po"]).border = BOX
    ws5.cell(row=r, column=4, value=row["vendor"]).border = BOX
    ws5.cell(row=r, column=5, value=row["tgl"]).border = BOX
    c = ws5.cell(row=r, column=6, value=int(row["baris"]))
    c.number_format, c.border = QTY, BOX
    c = ws5.cell(row=r, column=7, value=f(Decimal(row["qty"])))
    c.number_format, c.border = QTY, BOX
    money_cell(ws5, r, 8, bruto)
    money_cell(ws5, r, 9, dpp)
    money_cell(ws5, r, 10, bruto - dpp)
    r += 1
ws5.cell(row=r, column=4, value=f"TOTAL ({len(per_gr)} dokumen GR)").font = SUB_FONT
money_cell(ws5, r, 8, g_bruto, bold=True)
money_cell(ws5, r, 9, g_dpp, bold=True, fill=OK_FILL)
money_cell(ws5, r, 10, g_bruto - g_dpp, bold=True, fill=WARN_FILL)
ws5.freeze_panes = "B6"

# ==========================================================================
# Sheet 4 -- Contoh perhitungan
# ==========================================================================
ws4 = wb.create_sheet("Contoh Perhitungan")
r = 2
ws4.cell(row=r, column=2, value=f"Contoh per item - {sample_po}").font = TITLE_FONT
r += 1
c = ws4.cell(row=r, column=2, value="Maksimal 25 baris pertama, untuk memverifikasi cara hitung DPP = bruto / 1,11.")
c.font = Font(italic=True, color="808080")
r += 2
head(
    ws4,
    r,
    ["", "SKU", "Produk", "Qty", "Harga (bruto)", "Harga DPP", "Nilai bruto", "Nilai DPP", "PPN"],
    [3, 20, 46, 9, 16, 16, 18, 18, 16],
)
r += 1
for d in detail:
    bruto = Decimal(d["bruto"])
    dpp = dpp_of(bruto)
    ws4.cell(row=r, column=2, value=d["sku"]).border = BOX
    ws4.cell(row=r, column=3, value=d["produk"]).border = BOX
    c = ws4.cell(row=r, column=4, value=f(Decimal(d["qty"])))
    c.number_format, c.border = QTY, BOX
    money_cell(ws4, r, 5, Decimal(d["harga"]))
    money_cell(ws4, r, 6, dpp_of(d["harga"]))
    money_cell(ws4, r, 7, bruto)
    money_cell(ws4, r, 8, dpp, fill=OK_FILL)
    money_cell(ws4, r, 9, bruto - dpp, fill=WARN_FILL)
    r += 1

wb.save(OUT)

print(f"Database      : {DB}")
print(f"PO / baris    : {len(per_po)} PO, {t_baris:,} baris, {t_qty:,.0f} pcs")
print(f"Bruto GR      : {t_bruto:>20,.2f}")
print(f"DPP seharusnya: {t_dpp:>20,.2f}")
print(f"PPN (koreksi) : {t_ppn:>20,.2f}")
print("Rekap GL jurnal GR yang terbukukan:")
for g in gl:
    print(f"  {g['kode']:<12} {g['akun'][:42]:<44} D {Decimal(g['debit']):>18,.2f}  K {Decimal(g['kredit']):>18,.2f}")
print(f"Tersimpan     : {OUT}")
