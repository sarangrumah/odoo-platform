# -*- coding: utf-8 -*-
"""Build the delivery-status workbook for the client sheet
"List Kendala System ODOO" (worksheets EO + FASHION).

One row per request, mirroring docs/kendala-sheet-jul2026-status.md so the two
never drift. Statuses are a closed set so the summary can be counted from the
rows rather than typed in by hand.
"""
import xlsxwriter

OUT = "status-delivery-kendala-jul2026.xlsx"

DONE = "Selesai"
HOLD = "Ditahan"
CLIENT = "Menunggu Klien"
NOREPRO = "Tidak Reproduce"

# (no, item, status, keterangan, bukti/verifikasi, commit)
EO = [
    ("1", "Migrasi saldo TB tidak disertai detail AR/AP per partner", CLIENT,
     "Butuh listing outstanding per pelanggan/vendor dari klien",
     "Seluruh DB hanya 9 baris AR (2 partner) / 19 AP (7 partner)", ""),
    ("2", "Transaksi valuta asing belum bisa — kurs belum di-set", CLIENT,
     "Butuh daftar kurs yang dipakai (kurs tengah BI / kurs pajak) dan per tanggal apa",
     "res_currency_rate = 0 baris untuk IDR/USD/CNY", ""),
    ("3", "Kartu utang & piutang belum terintegrasi dengan data input", DONE,
     "Bug nyata pada flattener layar — BUKAN terhambat item #1 seperti dilaporkan awal. "
     "Export XLSX selalu benar; hanya tampilan layar yang kosong",
     "ARKA: 9 baris kosong -> 34 baris terisi. Levi's: 378 / 4.989 baris", "cea129b"),
    ("4", "Bank masuk/keluar masih lewat COA perantara", NOREPRO,
     "TIDAK diubah. Perlu klien menunjukkan transaksi mana yang dimaksud",
     "payment_account_id NULL di semua payment method line; payment posted langsung "
     "Dr BCA Main Bank / Cr Trade Receivables. Bank statement = 0", ""),
    ("5", "Purchase report keluar Trial Balance", DONE,
     "Report code tidak terdaftar di dispatcher sehingga jatuh ke fallback Trial Balance",
     "prd_levis_begbal 69 baris; prd_arkaaim 9 baris", "5a405ab"),
    ("6", "Jurnal DP masuk ke COA penjualan", DONE,
     "downpayment_account_id diarahkan ke 2108100001 Advances from customers",
     "Diterapkan pada 2 company; re-run script melaporkan OK / 0 changes", "8db557e"),
    ("7", "Akses closing period belum tersedia", CLIENT,
     "Butuh konfirmasi periode mana yang ditutup — lock date memblokir posting",
     "fiscalyear_lock_date & tax_lock_date NULL di kedua company", ""),
    ("8", "Nilai perolehan asset selisih vs report accounting", HOLD,
     "DITAHAN menunggu konfirmasi. Ternyata DUA komponen, bukan satu",
     "Perolehan: register 27.145.108.236 vs GL 27.110.131.391 = selisih 34.976.845. "
     "Accum-dep: 6.786.277.002,84 vs GL 7.341.288.299 = selisih +/- 555.011.296", ""),
    ("9", "No document depresiasi per bulan belum muncul", HOLD,
     "Kode SELESAI & teruji. POSTING PRODUKSI DITAHAN menunggu keputusan klien. "
     "Akarnya bukan penomoran: jurnal belum pernah dibuat sama sekali",
     "Uji di trn_arkaaim_begbal: 3.320 baris -> 1 jurnal 565.523.083,57; GL accum-dep "
     "bergerak persis sebesar itu; reverse 1 baris tidak mengubah jurnal bulanan", "d1c8952"),
    ("10", "Sales report kosong padahal ada di detail beginning balance", DONE,
     "Wizard dapat pilihan Sumber Data: Invoice+POS atau Akun Pendapatan (GL). "
     "Dibuat sebagai pilihan basis, bukan sumber ketiga, agar tidak double-count",
     "Basis GL 735.585.585 = revenue GL independen (selisih 0,00); basis dokumen "
     "hanya 150.000.000", "cea129b"),
    ("11", "PPh withholding belum otomatis per kode objek", DONE,
     "Engine sudah ada tapi registry kosong; 107 kode objek dimuat + modul di-upgrade",
     "107 kategori + 214 rule (107 x 2 company), 0 rule tanpa akun, 0 SKIP", ""),
    ("12", "Setting due date belum sesuai ketentuan Erajaya", CLIENT,
     "Butuh aturan due date yang eksak dari klien",
     "12 payment term sudah tersedia", ""),
    ("13", "Alamat AIM belum lengkap di Bill / Jurnal Voucher", CLIENT,
     "Butuh alamat persis sesuai NPWP AIM",
     "Company 1 street hanya 'Erajaya Plaza' (street2 & zip kosong); company 2 lengkap", ""),
    ("14", "Tambah nomor seri faktur pajak saat tarik GL", DONE,
     "2 kolom opsional (No. FP Masukan / Keluaran), default OFF karena modul dipakai "
     "semua tenant", "408 baris ber-NSFP di prd_levis_begbal; 17 di prd_arkaaim", "849fadc"),
    ("15", "Generate format impor PSIAP faktur keluaran", CLIENT,
     "Butuh template impor PSIAP dari klien",
     "0 hasil pencarian 'PSIAP' di seluruh source tree", ""),
]

FASHION = [
    ("1.1", "Rekap PPh + Kode Objek, COA Expense, No/Tgl Invoice, No Dok Jurnal", DONE,
     "SUDAH LIVE SEJAK AWAL — kelima kolom sudah ada. Nol development",
     "Terverifikasi pada kode terpasang di /opt", ""),
    ("1.2", "Report Import PPN Masukan (8 kolom)", DONE,
     "Report sudah punya persis 8 kolom yang diminta; terblokir bug dispatcher",
     "prd_levis_begbal 27 baris", "5a405ab"),
    ("1.3", "Report Ekualisasi Biaya vs Objek Pemotongan PPh", DONE,
     "4 kolom ditambah + sumber data dilebarkan. Menambah kolom saja akan menyerahkan "
     "report yang tetap kosong: bill di-input tanpa produk",
     "0 -> 112 baris. PPN tepat 11% dari DPP per baris", "849fadc"),
    ("1.4", "Report Upload Retur Pajak", CLIENT,
     "Butuh template import Coretax dari klien", "", ""),
    ("1.5", "Report Upload Faktur Pajak Keluaran", CLIENT,
     "Butuh template XLS Mitra Pajakku. Modul yang ada adalah API adapter, "
     "bukan penulis template", "", ""),
    ("1.6", "Mapping COA jurnal PPh, tetap bisa diubah Accounting", DONE,
     "SUDAH TERPENUHI — mapping configurable per rule",
     "107 rule active, account_id NULL = 0", ""),
    ("2", "Jurnal PPh input manual tidak muncul di Rekap PPh", DONE,
     "Kini menangkap PPh dari native tax & jurnal manual, dengan kolom Sumber. "
     "50 baris withholding tanpa jurnal GL sengaja dikecualikan + ditampilkan sbg note",
     "50 -> 105 baris; total 532.229.118,00 tie PERSIS ke GL credit", "45b5f78"),
    ("3", "Report Import PPN Masukan keluar Trial Balance", DONE,
     "Bug dispatcher yang sama dengan EO #5", "prd_levis_begbal 27 baris", "5a405ab"),
    ("4", "Belum ada GL Open Items / Outstanding balance", DONE,
     "Report baru, residual dihitung AS-OF per tanggal (bukan residual saat ini)",
     "3.827 baris, 18.397.721.518,82 = saldo GL akun rekonsiliasi (selisih 0,00)", "5465932"),
    ("5", "Report mapping vendor bill vs payment number", DONE,
     "Satu report untuk item #5 dan #13. Bill tanpa alokasi tetap tampil "
     "'Belum dibayar' sehingga sekaligus jadi daftar bill terhutang",
     "151 baris (100 belum dibayar / 48 lunas / 3 batal); sisa -5.330.536.589,74 "
     "= jumlah residual bill (selisih 0,00)", "5465932"),
    ("6", "On Hand Inventory report belum ada", DONE,
     "Modul terinstall. CATATAN: akan tampil kosong sampai penerimaan barang "
     "dicatat di Odoo", "prd_levis_begbal: 0 stock_quant, 0 purchase order", ""),
    ("7", "Purchase Return report belum ada", DONE,
     "Modul terinstall. CATATAN: akan tampil kosong sampai retur dicatat di Odoo",
     "0 pergerakan retur ke supplier", ""),
    ("8", "Purchase report keluar Trial Balance", DONE,
     "Bug dispatcher yang sama", "prd_levis_begbal 69 baris", "5a405ab"),
    ("9", "Sales report belum menampilkan data apapun", DONE,
     "POS jadi sumber kedua. Revenue retail tidak lewat customer invoice: "
     "16.064 order walk-in, revenue masuk GL lewat 860 jurnal penutup sesi",
     "0 -> 11.496 baris (Juni 2026); Sales Net 5.633.504.522,00 = revenue GL", "ef10d55"),
    ("10", "Sales report detail layout X24DN (COGS & margin)", DONE,
     "17 kolom. Store/Register/Txn di-parse dari pos_reference. Diskon dari "
     "ri_src_discount (field discount bernilai 0 di semua baris). COGS sebasis "
     "levis.cogs.run agar konsisten dengan GL. CATATAN: MARGIN BELUM BERMAKNA "
     "sampai cost produk tersedia",
     "Gross-Diskon-Total = 0,00; Net+Pajak-Total = 0,00; Net-COGS-Margin = 0,00. "
     "Diskon 1.234.678.813 = jumlah ri_src_discount", "ef10d55"),
    ("11", "Keterangan jurnal PPh & PPN hilang saat reset to draft", DONE,
     "Label dipertahankan; jurnal PPh direverse di periodenya sendiri; withholding "
     "line dibersihkan agar re-post menghitung ulang",
     "Uji: menggandakan nilai bill di draft memindahkan PPh 1.351.351,35 -> "
     "2.702.702,70 dengan jurnal baru (sebelumnya tetap basi)", "45b5f78"),
    ("12", "Modul Petty Cash all store", DONE,
     "SUDAH TER-DEPLOY sejak awal. Perlu config per-store + training",
     "custom_petty_cash 19.0.0.4.0 terinstall; 0 record", ""),
    ("13", "Report payment bill", DONE,
     "Dikerjakan bersama item #5 (permintaan identik)", "Lihat item #5", "5465932"),
]

WAITING = [
    ("EO #1", "Listing outstanding AR/AP per pelanggan dan vendor"),
    ("EO #2", "Daftar kurs yang dipakai (kurs tengah BI / kurs pajak) dan per tanggal apa"),
    ("EO #4", "Transaksi mana yang menunjukkan COA perantara — tidak reproduce di sistem"),
    ("EO #7", "Periode mana yang mau ditutup (lock date memblokir posting)"),
    ("EO #8", "Konfirmasi untuk melanjutkan rekonsiliasi selisih asset (DITAHAN)"),
    ("EO #9", "Persetujuan posting backlog depresiasi Juni 2026 Rp565.523.083,57 + aktifkan cron (DITAHAN)"),
    ("EO #12", "Aturan due date Erajaya yang eksak"),
    ("EO #13", "Alamat AIM persis sesuai NPWP"),
    ("EO #15", "Template impor PSIAP"),
    ("FASHION 1.4", "Template import Coretax untuk Retur Pajak"),
    ("FASHION 1.5", "Template XLS Mitra Pajakku"),
    ("FASHION 1.6", "Konfirmasi COA jurnal PPh sesuai sheet tim Tax"),
    ("FASHION 2", "Keputusan atas 50 withholding line Rp161.676.135,96 tanpa jurnal GL — dibersihkan atau dibukukan?"),
    ("FASHION 4", "Periksa partial reconcile Rp75.405.550 yang menggantung ke move draft 8282/2026/07/042"),
    ("FASHION 6 & 7", "Penerimaan barang & retur dicatat di Odoo agar kedua report terisi"),
    ("FASHION 10", "Cost produk / penerimaan barang agar kolom Margin bermakna"),
]

DEPLOY = [
    ("custom_accounting_reports", "19.0.0.14.0", "16 DB",
     "5 produksi, 2 tenant lain, 2 training, rnd_levis, demo, 2 tst_mdm, 3 snapshot"),
    ("custom_tax_id", "19.0.0.5.0", "14 DB", "Semua DB yang memasang modul"),
    ("custom_wms_reports + 2 dependensi", "19.0.0.2.0", "2 DB", "prd_levis_begbal, rnd_levis"),
    ("custom_accounting_asset", "19.0.0.5.0", "1 DB",
     "trn_arkaaim_begbal saja — produksi sengaja belum (lihat EO #9)"),
]

wb = xlsxwriter.Workbook(OUT)

C_INK, C_RULE, C_BAND = "#111820", "#D9E1E8", "#F6F8FA"
title = wb.add_format({"bold": True, "font_size": 16, "font_color": C_INK, "font_name": "Calibri"})
sub = wb.add_format({"font_size": 10, "font_color": "#48555F", "italic": True})
hdr = wb.add_format({"bold": True, "font_size": 10, "bg_color": "#EFF3F7", "font_color": "#48555F",
                     "border": 1, "border_color": C_RULE, "align": "left", "valign": "vcenter",
                     "text_wrap": True})
cell = wb.add_format({"font_size": 10, "border": 1, "border_color": C_RULE,
                      "valign": "top", "text_wrap": True})
cell_c = wb.add_format({"font_size": 10, "border": 1, "border_color": C_RULE,
                        "valign": "top", "align": "center"})
mono = wb.add_format({"font_size": 9, "font_name": "Consolas", "border": 1,
                      "border_color": C_RULE, "valign": "top", "text_wrap": True})
STATUS_FMT = {
    DONE: wb.add_format({"font_size": 10, "bold": True, "bg_color": "#E2F0EA", "font_color": "#176E52",
                         "border": 1, "border_color": C_RULE, "align": "center", "valign": "vcenter"}),
    HOLD: wb.add_format({"font_size": 10, "bold": True, "bg_color": "#FBEBDA", "font_color": "#B4610C",
                         "border": 1, "border_color": C_RULE, "align": "center", "valign": "vcenter"}),
    CLIENT: wb.add_format({"font_size": 10, "bold": True, "bg_color": "#E6ECF5", "font_color": "#2B4A7D",
                           "border": 1, "border_color": C_RULE, "align": "center", "valign": "vcenter"}),
    NOREPRO: wb.add_format({"font_size": 10, "bold": True, "bg_color": "#F6E6E9", "font_color": "#8A4A57",
                            "border": 1, "border_color": C_RULE, "align": "center", "valign": "vcenter"}),
}
big = wb.add_format({"bold": True, "font_size": 22, "align": "center", "valign": "vcenter",
                     "border": 1, "border_color": C_RULE})
big_lbl = wb.add_format({"font_size": 10, "align": "center", "valign": "vcenter",
                         "border": 1, "border_color": C_RULE, "text_wrap": True})


def item_sheet(name, rows, caption):
    ws = wb.add_worksheet(name)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    ws.write(0, 0, name, title)
    ws.write(1, 0, caption, sub)
    heads = ["No", "Permintaan Klien", "Status", "Keterangan", "Bukti / Verifikasi", "Commit"]
    widths = [6, 46, 17, 58, 62, 12]
    for i, (h, w) in enumerate(zip(heads, widths)):
        ws.write(3, i, h, hdr)
        ws.set_column(i, i, w)
    ws.set_row(3, 28)
    for r, row in enumerate(rows, start=4):
        no, item, status, ket, bukti, commit = row
        ws.write(r, 0, no, cell_c)
        ws.write(r, 1, item, cell)
        ws.write(r, 2, status, STATUS_FMT[status])
        ws.write(r, 3, ket, cell)
        ws.write(r, 4, bukti, cell)
        ws.write(r, 5, commit, mono)
    ws.freeze_panes(4, 2)
    ws.autofilter(3, 0, 3 + len(rows), 5)
    return ws


item_sheet("EO (ARKA-AIM)", EO, "15 permintaan · database produksi: prd_arkaaim")
item_sheet("FASHION (Levi's-EBR)", FASHION,
           "13 baris sheet dihitung 18 entri (item #1 berisi 6 sub-request) · database produksi: prd_levis_begbal")

# ---------- Ringkasan ----------
ws = wb.add_worksheet("Ringkasan")
wb.worksheets_objs.insert(0, wb.worksheets_objs.pop())  # put it first
ws.write(0, 0, "Status Delivery — List Kendala System ODOO", title)
ws.write(1, 0, "Worksheet EO (ARKA-AIM) + FASHION (Levi's/EBR) · posisi 30 Juli 2026", sub)
ws.set_column(0, 0, 26)
ws.set_column(1, 1, 14)
ws.set_column(2, 2, 74)

allrows = EO + FASHION
counts = {}
for _n, _i, st, _k, _b, _c in allrows:
    counts[st] = counts.get(st, 0) + 1

ws.write(3, 0, "Total permintaan", hdr)
ws.write(3, 1, len(allrows), big)
ws.write(3, 2, "33 entri dari 28 baris sheet — item FASHION #1 dihitung 6 sub-request terpisah", cell)
ws.set_row(3, 34)

r = 5
ws.write(r, 0, "Status", hdr); ws.write(r, 1, "Jumlah", hdr); ws.write(r, 2, "Arti", hdr)
meaning = {
    DONE: "Sudah selesai dan aktif di database produksi",
    HOLD: "Ditahan menunggu keputusan / konfirmasi (EO #8 dan EO #9)",
    CLIENT: "Menunggu nilai, dokumen, atau template dari klien",
    NOREPRO: "Tidak dapat direproduksi di sistem — perlu klarifikasi klien",
}
r += 1
for st in (DONE, HOLD, CLIENT, NOREPRO):
    ws.write(r, 0, st, STATUS_FMT[st])
    ws.write(r, 1, counts.get(st, 0), big)
    ws.write(r, 2, meaning[st], cell)
    ws.set_row(r, 30)
    r += 1

r += 1
ws.write(r, 0, "Catatan penting", hdr); ws.write(r, 1, "", hdr); ws.write(r, 2, "", hdr)
r += 1
notes = [
    ("Sisa development", "NOL",
     "Seluruh item yang belum tuntas kini menunggu keputusan atau data dari pihak lain, "
     "bukan menunggu pengerjaan."),
    ("Perlu disampaikan", "3 report",
     "FASHION #6 (On Hand) dan #7 (Purchase Return) akan tampil KOSONG sampai penerimaan "
     "barang & retur dicatat di Odoo. Kolom MARGIN pada FASHION #10 belum bermakna sampai "
     "cost produk tersedia (0 dari 3.865 produk terjual punya cost). Ketiganya sudah "
     "menandai keterbatasan ini di dalam report-nya sendiri."),
    ("Posting ditahan", "Rp565.523.083,57",
     "Backlog depresiasi Juni 2026 belum diposting ke prd_arkaaim dan cron masih non-aktif, "
     "menunggu persetujuan klien."),
]
for a, b, c in notes:
    ws.write(r, 0, a, cell)
    ws.write(r, 1, b, cell_c)
    ws.write(r, 2, c, cell)
    r += 1

# ---------- Menunggu Klien ----------
ws2 = wb.add_worksheet("Menunggu Klien")
ws2.write(0, 0, "Menunggu Klien", title)
ws2.write(1, 0, "Nilai, dokumen, keputusan, atau data yang harus datang dari pihak klien", sub)
ws2.write(3, 0, "Item", hdr); ws2.write(3, 1, "Yang dibutuhkan", hdr)
ws2.set_column(0, 0, 18); ws2.set_column(1, 1, 104)
for i, (a, b) in enumerate(WAITING, start=4):
    ws2.write(i, 0, a, cell); ws2.write(i, 1, b, cell)
ws2.freeze_panes(4, 0)
ws2.autofilter(3, 0, 3 + len(WAITING), 1)

# ---------- Deployment ----------
ws3 = wb.add_worksheet("Deployment")
ws3.write(0, 0, "Jejak Deployment", title)
ws3.write(1, 0, "Versi modul seragam di seluruh database yang memasangnya — nol drift", sub)
for i, h in enumerate(["Modul", "Versi", "Jumlah DB", "Keterangan"]):
    ws3.write(3, i, h, hdr)
for i, w in enumerate([38, 14, 12, 70]):
    ws3.set_column(i, i, w)
for i, row in enumerate(DEPLOY, start=4):
    ws3.write(i, 0, row[0], mono)
    ws3.write(i, 1, row[1], cell_c)
    ws3.write(i, 2, row[2], cell_c)
    ws3.write(i, 3, row[3], cell)
r = 4 + len(DEPLOY) + 1
ws3.write(r, 0, "Backup", hdr); ws3.write(r, 3, "", hdr)
ws3.write(r + 1, 0, "pg_dump", cell)
ws3.write(r + 1, 3, "Diambil sebelum setiap rollout; ukuran dan integritas gzip diverifikasi. "
                    "Tersimpan di /opt/odoo-platform/backups/", cell)

wb.close()
print("written:", OUT)
