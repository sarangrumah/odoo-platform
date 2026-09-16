# Template import Purchase Order dengan kolom Taxes -- prd_levis_begbal.
#
# Kenapa perlu: di Odoo 19 purchase.order.line.tax_ids BUKAN stored-compute.
# Satu-satunya yang mengisinya adalah onchange_product_id()
# (purchase/models/purchase_order_line.py:366), dan import SELALU melewati onchange.
# Tanpa kolom Taxes di file import, PPN tidak akan pernah terisi -- itulah sebab
# 243 PO Juli-Agustus 2026 menilai persediaan sebesar bruto, bukan DPP.
#
# Script ini hanya menulis file Excel ke /srv/sftp-share/files (File Browser /files).
# Tidak menyentuh database.
#
#   python3 scripts/tenants/levis/86_make_po_import_template.py

import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT = os.environ.get("OUT", "/srv/sftp-share/files/Template_Import_PO_dengan_PPN.xlsx")

# Kolom import Odoo. Nama teknis dipakai (bukan label) supaya pemetaan tidak
# bergantung pada bahasa antarmuka pengguna yang mengimpor.
COLUMNS = [
    ("name", "No PO -- KOSONGKAN agar Odoo memberi nomor sendiri (PO/T/EBR/...)", 24),
    ("partner_id", "Vendor. Harus sama persis dengan nama di master Contact.", 30),
    ("date_order", "Tanggal PO, format YYYY-MM-DD.", 14),
    ("picking_type_id", 'Gudang penerima, format "<Gudang>: Receipts".', 34),
    ("order_line/product_id", "Kode internal produk (Internal Reference), bukan barcode.", 26),
    ("order_line/product_qty", "Jumlah dipesan. Pastikan TIDAK tertukar dengan harga.", 14),
    ("order_line/price_unit", "Harga satuan SUDAH TERMASUK PPN.", 18),
    ("order_line/tax_ids", "WAJIB. Tanpa kolom ini PPN tidak akan terisi.", 26),
]

# Sengaja BUKAN "12% (Non-Luxury Good)": nama itu dipakai dua kali -- tax 21
# (pembelian) dan tax 28 (penjualan) -- sehingga ambigu saat import mencocokkan
# pajak berdasarkan nama. "PPN 12% (Included)" (tax 37) unik, khusus pembelian,
# price_include_override = tax_included, dan repartisinya ke akun yang sama
# (1117200001 VAT In). Perilaku hitungnya identik dengan tax 21.
TAX = "PPN 12% (Included)"
VENDOR = "PT SINAR EKA SELARAS TBK"
GUDANG = "OLS SES - PLAZA SENAYAN: Receipts"

# Dua PO contoh. Baris lanjutan sebuah PO hanya mengisi kolom order_line/* --
# kolom induk dikosongkan; begitulah Odoo mengenali baris milik PO yang sama.
CONTOH = [
    ("", VENDOR, "2026-08-07", GUDANG, "TS1000415", 3, 826086, TAX),
    ("", "", "", "", "005GO00000OS", 2, 508337, TAX),
    ("", "", "", "", "005CW00020OS", 5, 254137, TAX),
    ("", VENDOR, "2026-08-07", GUDANG, "TS1000415", 10, 826086, TAX),
    ("", "", "", "", "005GO00000OS", 4, 508337, TAX),
]

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
WAJIB_FILL = PatternFill("solid", fgColor="C00000")
CONTOH_FILL = PatternFill("solid", fgColor="FFF2CC")
TITLE_FONT = Font(bold=True, size=13, color="1F4E78")
SUB_FONT = Font(bold=True)
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

wb = Workbook()

# ==========================================================================
# Sheet 1 -- lembar yang diimpor. Harus bersih: hanya header + baris data.
# ==========================================================================
ws = wb.active
ws.title = "Import PO"
for i, (field, _keterangan, width) in enumerate(COLUMNS, start=1):
    cell = ws.cell(row=1, column=i, value=field)
    cell.fill = WAJIB_FILL if field == "order_line/tax_ids" else HDR_FILL
    cell.font, cell.border = HDR_FONT, BOX
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.column_dimensions[get_column_letter(i)].width = width
ws.row_dimensions[1].height = 32

for r, row in enumerate(CONTOH, start=2):
    for c, val in enumerate(row, start=1):
        cell = ws.cell(row=r, column=c, value=val)
        cell.border, cell.fill = BOX, CONTOH_FILL
        if c in (6, 7):
            cell.number_format = "#,##0" if c == 6 else "#,##0.00"

# Dropdown pajak supaya tidak salah ketik. Sengaja dipasang jauh ke bawah juga,
# agar baris tambahan buatan pengguna ikut tervalidasi.
dv = DataValidation(type="list", formula1=f'"{TAX}"', allow_blank=False, showDropDown=True)
dv.error = "Pilih pajak dari daftar. Lihat sheet 'Daftar Pajak'."
dv.errorTitle = "Pajak tidak dikenal"
ws.add_data_validation(dv)
dv.add("H2:H5000")
ws.freeze_panes = "A2"

# ==========================================================================
# Sheet 2 -- petunjuk
# ==========================================================================
ws2 = wb.create_sheet("Petunjuk")
ws2.column_dimensions["A"].width = 3
ws2.column_dimensions["B"].width = 30
ws2.column_dimensions["C"].width = 96

r = 2
ws2.cell(row=r, column=2, value="Template Import Purchase Order -- dengan kolom PPN").font = TITLE_FONT
r += 2

ws2.cell(row=r, column=2, value="Kenapa template ini ada").font = SUB_FONT
c = ws2.cell(
    row=r,
    column=3,
    value="Kolom Taxes di PO selama ini kosong karena file import tidak memuatnya. Di Odoo 19, "
    "pajak pada baris PO hanya terisi lewat onchange saat produk dipilih di layar -- dan import "
    "tidak pernah menjalankan onchange. Akibatnya PPN tidak terpisah, dan penerimaan barang "
    "menilai persediaan sebesar harga bruto, bukan DPP. Kolom order_line/tax_ids menutup celah itu.",
)
c.alignment = Alignment(wrap_text=True, vertical="top")
ws2.row_dimensions[r].height = 62
r += 2

ws2.cell(row=r, column=2, value="Aturan harga").font = SUB_FONT
c = ws2.cell(
    row=r,
    column=3,
    value="Harga di kolom price_unit adalah harga yang SUDAH TERMASUK PPN. Pajak "
    f'"{TAX}" bersifat included, sehingga Odoo memecahnya sendiri: DPP = harga / 1,11 dan '
    "PPN = harga - DPP (PPN 12% atas DPP nilai lain 11/12, PMK 11/2025 -- tarif efektif 11%). "
    "Total PO tidak berubah oleh adanya kolom ini; yang berubah hanya pemisahan DPP dan PPN.",
)
c.alignment = Alignment(wrap_text=True, vertical="top")
ws2.row_dimensions[r].height = 62
r += 2

ws2.cell(row=r, column=2, value="Cara mengisi").font = SUB_FONT
c = ws2.cell(
    row=r,
    column=3,
    value="Satu file untuk satu atau beberapa PO. Baris PERTAMA tiap PO mengisi seluruh kolom. "
    "Baris berikutnya milik PO yang sama hanya mengisi kolom order_line/* dan MENGOSONGKAN "
    "partner_id, date_order, picking_type_id -- begitulah Odoo tahu baris itu masih PO yang sama. "
    "Begitu kolom vendor terisi lagi, Odoo menganggapnya PO baru. Lihat 5 baris contoh di sheet "
    "'Import PO' (2 PO: 3 baris dan 2 baris).",
)
c.alignment = Alignment(wrap_text=True, vertical="top")
ws2.row_dimensions[r].height = 62
r += 2

ws2.cell(row=r, column=2, value="Cara mengimpor").font = SUB_FONT
c = ws2.cell(
    row=r,
    column=3,
    value="Purchases > Purchase Orders > tombol gear/Actions > Import records > Upload file. "
    "Hapus dulu baris contoh yang berwarna kuning. Pastikan Odoo memetakan kolom "
    "order_line/tax_ids ke field Taxes -- kalau tidak terpetakan, PPN tetap kosong. "
    "Gunakan tombol Test sebelum Import.",
)
c.alignment = Alignment(wrap_text=True, vertical="top")
ws2.row_dimensions[r].height = 50
r += 2

ws2.cell(row=r, column=2, value="Yang sering salah").font = SUB_FONT
c = ws2.cell(
    row=r,
    column=3,
    value="1. Kolom qty dan harga TERTUKAR. Ini pernah terjadi dan lolos sampai barang diterima: "
    "qty 124 juta pcs dengan harga Rp 1. Total rupiahnya tetap terlihat benar, jadi tidak "
    "ketahuan dari nilai PO -- periksa kolom qty sebelum impor.\n"
    "2. Kode produk memakai barcode, bukan Internal Reference.\n"
    "3. Nama vendor tidak persis sama dengan master Contact. Tulis nama induknya saja "
    '(mis. "PT SINAR EKA SELARAS TBK"), jangan alamat cabangnya.\n'
    "4. Gudang penerima salah, sehingga analytic Operating Unit ikut salah.",
)
c.alignment = Alignment(wrap_text=True, vertical="top")
ws2.row_dimensions[r].height = 80
r += 2

ws2.cell(row=r, column=2, value="Arti tiap kolom").font = SUB_FONT
r += 1
for field, keterangan, _w in COLUMNS:
    cc = ws2.cell(row=r, column=2, value=field)
    cc.font, cc.border = Font(name="Consolas", size=10), BOX
    if field == "order_line/tax_ids":
        cc.fill = PatternFill("solid", fgColor="FCE4D6")
    cc2 = ws2.cell(row=r, column=3, value=keterangan)
    cc2.border = BOX
    cc2.alignment = Alignment(wrap_text=True, vertical="top")
    r += 1

# ==========================================================================
# Sheet 3 -- daftar pajak yang sah
# ==========================================================================
ws3 = wb.create_sheet("Daftar Pajak")
ws3.column_dimensions["B"].width = 26
ws3.column_dimensions["C"].width = 12
ws3.column_dimensions["D"].width = 18
ws3.column_dimensions["E"].width = 60
r = 2
ws3.cell(row=r, column=2, value="Pajak Pembelian yang Sah").font = TITLE_FONT
r += 2
for i, h in enumerate(["Nama pajak (salin persis)", "Tarif", "Perlakuan", "Dipakai untuk"], start=2):
    cell = ws3.cell(row=r, column=i, value=h)
    cell.fill, cell.font, cell.border = HDR_FILL, HDR_FONT, BOX
r += 1
for nm, tarif, perlakuan, untuk in [
    (TAX, "11%", "Included", "STANDAR -- pakai ini. Harga PO sudah termasuk PPN. Nama unik, jadi aman saat import."),
    (
        "12% (Non-Luxury Good)",
        "11%",
        "Included",
        "JANGAN dipakai di file import: nama ini dimiliki dua pajak "
        "sekaligus (pembelian dan penjualan), sehingga import bisa memilih yang salah. Hitungannya sendiri sama.",
    ),
    ("PPN 12% (Excluded)", "11%", "Excluded", "Hanya bila harga PO adalah DPP dan PPN ditambahkan di atasnya."),
    ("PPN 1,1% (Excluded)", "1,1%", "Excluded", "Kasus khusus, jangan dipakai tanpa arahan Finance."),
]:
    for i, v in enumerate([nm, tarif, perlakuan, untuk], start=2):
        cell = ws3.cell(row=r, column=i, value=v)
        cell.border = BOX
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 2 and nm == TAX:
            cell.font = SUB_FONT
    r += 1

wb.save(OUT)
os.chmod(OUT, 0o644)
print(f"Tersimpan: {OUT}")
