# -*- coding: utf-8 -*-
"""Template upload Vendor Bill, lengkap dengan daftar nilai yang sah.

Sheet baris #75. SELECT-only -- tidak pernah menulis apa pun.

  docker exec -i -e OUT=/mnt/data_levis/Template_Upload_Vendor_Bill.xlsx \\
    odoo19-platform-odoo odoo shell -d prd_levis_begbal \\
    --no-http --max-cron-threads=0 --shell-interface=python \\
    < scripts/tenants/levis/122_build_vendor_bill_template.py

--------------------------------------------------------------------------
Apa yang sebenarnya terjadi pada #75
--------------------------------------------------------------------------
Klien menulis: *"Mohon beri nama di field OPERATING UNIT dan field pemilihan
BILL TYPE supaya terbaca ketika isi template upload vendor bill, saat ini tidak
terbaca oleh Odoo."*

Diperiksa 18-Sep-2026: **kedua field itu sudah bernama**.
``account.move.l10n_ou_analytic_id`` berlabel "Operating Unit" dan
``l10n_purchase_type`` berlabel "Purchase Type". Jadi masalahnya bukan label
yang hilang, melainkan salah satu dari dua hal yang sama-sama membuat kolom
"tidak terbaca" oleh ``base_import``:

1. **Judul kolomnya tidak cocok.** Klien menulis "BILL TYPE"; field-nya bernama
   "Purchase Type". base_import mencocokkan judul kolom dengan label atau nama
   teknis field -- "BILL TYPE" tidak cocok dengan keduanya, jadi kolomnya
   diabaikan diam-diam.
2. **Isinya tidak bisa di-resolve.** Field Selection hanya menerima label yang
   persis ("Trade" / "Non-Trade") atau nilai teknisnya ("trade" / "non_trade");
   Many2one hanya menerima nama yang persis ada di master.

Karena itu template ini memakai **nama teknis field sebagai judul kolom** --
satu-satunya bentuk yang tidak bisa salah cocok -- dan menyertakan sheet
"Referensi" berisi nilai yang benar-benar ada di database, supaya isian tidak
perlu ditebak.

--------------------------------------------------------------------------
Yang harus diketahui tentang base_import dan baris one2many
--------------------------------------------------------------------------
* Satu bill = satu baris header + baris-baris berikutnya **dengan sel header
  dikosongkan**. Baris yang sel headernya kosong dianggap lanjutan bill di
  atasnya.
* base_import **melewati field readonly**. Itu sebabnya template ini hanya
  memuat field yang benar-benar bisa ditulis.
* ``move_type`` wajib ``in_invoice`` -- tanpa itu Odoo membuat customer invoice.
"""

import os

OUT = os.environ.get("OUT", "/mnt/data_levis/Template_Upload_Vendor_Bill.xlsx")

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

company = env["res.company"].search([], order="id", limit=1)
Move = env["account.move"]
MoveLine = env["account.move.line"]

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
SUB_FILL = PatternFill("solid", fgColor="D9E2F3")
HEAD_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(bold=True, size=14)
NOTE_FONT = Font(italic=True, color="7F7F7F")

# (judul kolom = nama teknis, label manusia, wajib?, contoh)
COLUMNS = [
    ("move_type", "Tipe dokumen — selalu in_invoice", "WAJIB", "in_invoice"),
    ("partner_id", "Vendor (nama persis seperti di master)", "WAJIB", ""),
    ("invoice_date", "Tanggal Bill (YYYY-MM-DD)", "WAJIB", "2026-09-01"),
    ("invoice_date_due", "Tanggal Jatuh Tempo", "opsional", "2026-10-01"),
    ("ref", "Nomor Invoice Vendor", "disarankan", "INV/2026/0001"),
    ("journal_id", "Jurnal pembelian", "opsional", ""),
    ("l10n_purchase_type", "Purchase Type — inilah 'BILL TYPE'", "WAJIB", "non_trade"),
    ("l10n_ou_analytic_id", "Operating Unit (header)", "WAJIB", ""),
    ("invoice_line_ids/name", "Deskripsi baris", "WAJIB", "Biaya sewa September"),
    ("invoice_line_ids/account_id", "COA beban (kode + nama)", "WAJIB", ""),
    ("invoice_line_ids/quantity", "Qty", "WAJIB", "1"),
    ("invoice_line_ids/price_unit", "Harga satuan", "WAJIB", "1000000"),
    ("invoice_line_ids/tax_ids", "Pajak (pisahkan dengan koma bila lebih dari satu)", "opsional", ""),
    ("invoice_line_ids/x_custom_withholding_category_id", "Kode Objek PPh", "opsional", ""),
    ("invoice_line_ids/l10n_ou_analytic_id", "Operating Unit per baris", "opsional", ""),
]


def _first(model, domain, field="display_name", limit=1):
    rec = env[model].with_company(company).search(domain, limit=limit)
    return rec[field] if rec else ""


vendor = _first("res.partner", [("supplier_rank", ">", 0)])
ou = _first("account.analytic.account", [("plan_id.name", "=", "Operating Unit")])
expense = _first("account.account", [("account_type", "=", "expense")])
journal = _first("account.journal", [("type", "=", "purchase")])
kode_objek = _first("tax.withholding.category", [("active", "=", True)])
tax = _first("account.tax", [("type_tax_use", "=", "purchase"), ("amount", ">", 0)])

EXAMPLE = {
    "partner_id": vendor,
    "journal_id": journal,
    "l10n_ou_analytic_id": ou,
    "invoice_line_ids/account_id": expense,
    "invoice_line_ids/tax_ids": tax,
    "invoice_line_ids/x_custom_withholding_category_id": kode_objek,
    "invoice_line_ids/l10n_ou_analytic_id": ou,
}

wb = Workbook()

# --- sheet Import -----------------------------------------------------------
ws = wb.active
ws.title = "Import"
headers = [c[0] for c in COLUMNS]
ws.append(headers)
ws.append([c[1] for c in COLUMNS])
for idx, col in enumerate(COLUMNS, start=1):
    cell = ws.cell(row=1, column=idx)
    cell.fill = HEAD_FILL
    cell.font = HEAD_FONT
    cell.alignment = Alignment(vertical="center", wrap_text=True)
    sub = ws.cell(row=2, column=idx)
    sub.fill = SUB_FILL
    sub.font = Font(italic=True, size=9)
    sub.alignment = Alignment(vertical="top", wrap_text=True)
    ws.column_dimensions[get_column_letter(idx)].width = max(16, min(34, len(col[0]) + 8))
ws.freeze_panes = "A3"

row1 = [EXAMPLE.get(c[0], c[3]) for c in COLUMNS]
ws.append(row1)
# baris kedua dari bill yang SAMA: seluruh sel header dikosongkan
row2 = []
for col in COLUMNS:
    if col[0].startswith("invoice_line_ids/"):
        row2.append(EXAMPLE.get(col[0], ""))
    else:
        row2.append("")
row2[headers.index("invoice_line_ids/name")] = "Baris kedua bill yang sama"
row2[headers.index("invoice_line_ids/quantity")] = "1"
row2[headers.index("invoice_line_ids/price_unit")] = "250000"
ws.append(row2)
ws.append([])
note = ws.cell(
    row=ws.max_row + 1,
    column=1,
    value="BARIS 2 (abu-abu) hanya penjelasan — HAPUS sebelum diupload. "
    "Baris contoh di bawahnya memperlihatkan satu bill dengan dua baris: "
    "baris kedua mengosongkan seluruh kolom header.",
)
note.font = NOTE_FONT

# --- sheet Petunjuk ---------------------------------------------------------
wg = wb.create_sheet("Petunjuk")
wg.column_dimensions["A"].width = 34
wg.column_dimensions["B"].width = 22
wg.column_dimensions["C"].width = 64
wg["A1"] = "Template Upload Vendor Bill — sheet baris #75"
wg["A1"].font = TITLE_FONT
rows = [
    (
        "Kenapa kolom tidak terbaca",
        "",
        "Judul kolom harus cocok dengan nama teknis field atau labelnya. "
        "'BILL TYPE' tidak cocok dengan apa pun; nama fieldnya l10n_purchase_type, labelnya 'Purchase Type'. "
        "Template ini memakai nama teknis sebagai judul, jadi tidak bisa salah cocok.",
    ),
    (
        "Isi Selection",
        "",
        "l10n_purchase_type hanya menerima 'trade' atau 'non_trade' (atau label persis "
        "'Trade' / 'Non-Trade'). Selain itu diabaikan.",
    ),
    ("Isi Many2one", "", "Harus nama yang PERSIS ada di master. Lihat sheet Referensi."),
    (
        "Baris kedua dst",
        "",
        "Kosongkan SELURUH kolom header; hanya isi kolom invoice_line_ids/*. "
        "Baris itu akan menempel ke bill di atasnya.",
    ),
    (
        "Field readonly",
        "",
        "base_import melewati field readonly, jadi field seperti nomor bill tidak bisa "
        "diisi dari sini — Odoo yang menomori.",
    ),
    (
        "Cara upload",
        "",
        "Accounting ▸ Vendors ▸ Bills ▸ ⚙ Import records ▸ Upload file. "
        "Periksa pemetaan kolom di layar pratinjau sebelum Import.",
    ),
]
r = 3
for a, b, c in rows:
    wg.cell(row=r, column=1, value=a).font = Font(bold=True)
    wg.cell(row=r, column=2, value=b)
    wg.cell(row=r, column=3, value=c).alignment = Alignment(wrap_text=True)
    r += 1
r += 1
wg.cell(row=r, column=1, value="Kolom").font = Font(bold=True)
wg.cell(row=r, column=2, value="Wajib?").font = Font(bold=True)
wg.cell(row=r, column=3, value="Arti").font = Font(bold=True)
r += 1
for name, label, required, _example in COLUMNS:
    wg.cell(row=r, column=1, value=name)
    wg.cell(row=r, column=2, value=required)
    wg.cell(row=r, column=3, value=label).alignment = Alignment(wrap_text=True)
    r += 1

# --- sheet Referensi --------------------------------------------------------
wr = wb.create_sheet("Referensi")
wr.column_dimensions["A"].width = 26
wr.column_dimensions["B"].width = 52
wr.column_dimensions["C"].width = 30


def _block(title, pairs, start):
    wr.cell(row=start, column=1, value=title).font = Font(bold=True, size=12)
    start += 1
    wr.cell(row=start, column=1, value="Nilai yang sah").font = Font(bold=True)
    wr.cell(row=start, column=2, value="Keterangan").font = Font(bold=True)
    start += 1
    for value, note_text in pairs:
        wr.cell(row=start, column=1, value=value)
        wr.cell(row=start, column=2, value=note_text)
        start += 1
    return start + 1


row = 1
row = _block(
    "Purchase Type (l10n_purchase_type)",
    [("trade", "Trade — pembelian barang dagangan"), ("non_trade", "Non-Trade — biaya dan jasa")],
    row,
)

ous = env["account.analytic.account"].search([("plan_id.name", "=", "Operating Unit")], order="name")
row = _block("Operating Unit (%s pilihan)" % len(ous), [(o.display_name, "") for o in ous], row)

cats = env["tax.withholding.category"].search([("active", "=", True)], order="code")
row = _block(
    "Kode Objek PPh (%s pilihan)" % len(cats), [(c.display_name, c.bupot_object_code or "") for c in cats], row
)

taxes = env["account.tax"].with_company(company).search([("type_tax_use", "=", "purchase")], order="name")
row = _block("Pajak pembelian (%s pilihan)" % len(taxes), [(t.name, "%s%%" % t.amount) for t in taxes], row)

journals = env["account.journal"].with_company(company).search([("type", "=", "purchase")], order="code")
row = _block("Jurnal pembelian", [(j.display_name, j.code) for j in journals], row)

print("=" * 72)
print("Template Upload Vendor Bill")
print("=" * 72)
print("Operating Unit  : %s pilihan" % len(ous))
print("Kode Objek PPh  : %s pilihan" % len(cats))
print("Pajak pembelian : %s pilihan" % len(taxes))
print("Jurnal          : %s" % len(journals))
wb.save(OUT)
print("\nTemplate: %s" % OUT)
env.cr.rollback()
