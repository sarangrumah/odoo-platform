# -*- coding: utf-8 -*-
"""Bangun enam template laporan gudang yang berkasnya tidak pernah dikirim klien.

Sheet baris #26, #27, #28, #64, #69, #70. SELECT-only -- tidak pernah menulis
apa pun ke database.

  docker exec -i -e OUT=/mnt/data_levis odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python < scripts/tenants/levis/117_build_report_templates.py

Dijalankan lewat ``odoo shell`` (butuh ``env``), bukan python biasa.

--------------------------------------------------------------------------
Kenapa skrip ini ada
--------------------------------------------------------------------------
Lima kali klien menulis "referensi template terlampir" dan lima kali berkasnya
tidak ada -- tidak di lampiran workbook konfirmasi, tidak di ``/srv/sftp-share``,
tidak di repo. Menunggu sudah dicoba sejak Juli dan tidak menghasilkan apa-apa.

Jadi kita balik arahnya: kita yang mengirim template, berisi kolom yang kita
asumsikan plus **baris contoh dari data mereka sendiri**, dan klien tinggal
mencoret atau menambah. Sheet "Petunjuk" di tiap berkas menyebutkan sumber data
tiap kolom, sehingga yang didiskusikan adalah hal yang benar: bukan "kolomnya
apa saja" melainkan "apakah angka ini yang Anda maksud".

--------------------------------------------------------------------------
TEMUAN YANG MENGUBAH BENTUK TIGA TEMPLATE -- baca sebelum menyunting
--------------------------------------------------------------------------
Diperiksa langsung di ``prd_levis_begbal`` 18-Sep-2026:

1. **Penjualan POS tidak pernah membuat ``stock.move``.** 82.482 baris
   ``pos.order.line`` (91.008 unit) dan **NOL** move berlokasi tujuan
   ``customer``. Laporan movement yang dibangun dari ``stock.move`` saja akan
   menampilkan penerimaan dan retur tetapi **tidak satu pun penjualan** --
   sementara kolom "balance stock setelah transaksi" yang diminta #64 justru
   menuntut penjualan ikut. Karena itu sumbernya WAJIB gabungan
   ``stock.move`` + ``pos.order.line``.

2. **Sepanjang 2026 hanya ada dua jenis pergerakan stok:** penerimaan
   (supplier -> internal, 46.500 move, 31-Jul s/d 17-Sep) dan satu batch retur
   (internal -> supplier, 200 move, 06-Agu). **Internal transfer, inventory
   adjustment dan scrap belum pernah terjadi di Odoo.** Laporan #69 dan #70
   karena itu akan kosong sampai alur itu benar-benar dipakai -- templatenya
   tetap dikirim supaya formatnya disepakati lebih dulu, tetapi jangan
   menjanjikan angka.

3. **On-hand ditulis oleh snapshot X20, bukan oleh buku pergerakan.**
   ``stock_quant`` internal = 119.763 unit hari ini. Karena penjualan tidak
   punya move dan adjustment tidak pernah dibukukan, rantai
   "saldo awal +/- pergerakan" **tidak akan sama** dengan on-hand. Selisihnya
   bukan bug laporan; itu memang belum terekam di mana pun. Template #64
   menyediakan baris "Selisih tidak terjelaskan" supaya hal ini terlihat,
   bukan tersembunyi.

Semua asumsi ditandai **[ASUMSI]** di sheet Petunjuk.
"""

import os

OUT_DIR = os.environ.get("OUT", "/mnt/data_levis")
LIMIT = int(os.environ.get("LIMIT", "15"))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(color="FFFFFF", bold=True)
NOTE_FONT = Font(italic=True, color="7F7F7F")
TITLE_FONT = Font(bold=True, size=14)

company = env["res.company"].search([], order="id", limit=1)


def _sheet_header(ws, headers, widths=None):
    ws.append(headers)
    for idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=idx)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(idx)].width = (widths or {}).get(idx, 18)
    ws.freeze_panes = "A2"


def _guide(wb, title, intro, columns, notes, params=None):
    """Sheet Petunjuk: tujuan, parameter tarikan, sumber tiap kolom, catatan."""
    ws = wb.create_sheet("Petunjuk", 0)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 78
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    row = 3
    for line in intro:
        ws.cell(row=row, column=1, value=line[0]).font = Font(bold=True)
        ws.cell(row=row, column=2, value=line[1]).alignment = Alignment(wrap_text=True)
        row += 1
    if params:
        row += 1
        ws.cell(row=row, column=1, value="Parameter tarikan").font = Font(bold=True, size=12)
        row += 1
        for name, desc in params:
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=desc).alignment = Alignment(wrap_text=True)
            row += 1
    row += 1
    ws.cell(row=row, column=1, value="Kolom dan sumbernya").font = Font(bold=True, size=12)
    row += 1
    ws.cell(row=row, column=1, value="Kolom").font = Font(bold=True)
    ws.cell(row=row, column=2, value="Diambil dari").font = Font(bold=True)
    row += 1
    for name, source in columns:
        ws.cell(row=row, column=1, value=name)
        ws.cell(row=row, column=2, value=source).alignment = Alignment(wrap_text=True)
        row += 1
    row += 1
    ws.cell(row=row, column=1, value="Catatan").font = Font(bold=True, size=12)
    row += 1
    for note in notes:
        ws.cell(row=row, column=1, value=note).alignment = Alignment(wrap_text=True)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        row += 1
    return ws


def _save(wb, name):
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    path = os.path.join(OUT_DIR, name)
    wb.save(path)
    print("  %s" % path)
    return path


# ---------------------------------------------------------------------------
# Data contoh, diambil dari tenant sendiri
# ---------------------------------------------------------------------------
def _movement_ledger():
    """One item at one warehouse, every movement in date order.

    Picked automatically: the (product, warehouse) pair with the most
    movements on BOTH sides, so the sample shows a receipt and its sales
    together instead of two unrelated lists. That is also the shape #64 asks
    for -- "per item code per warehouse".
    """
    env.cr.execute(
        """
        WITH recv AS (
            SELECT m.product_id, w.id AS wh_id, count(*) n
            FROM stock_move m
            JOIN stock_picking_type spt ON spt.id = m.picking_type_id
            JOIN stock_warehouse w ON w.id = spt.warehouse_id
            WHERE m.state = 'done'
              AND m.location_dest_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
            GROUP BY 1, 2
        ), sold AS (
            SELECT l.product_id, cfg.warehouse_id AS wh_id, count(*) n
            FROM pos_order_line l
            JOIN pos_order o ON o.id = l.order_id AND o.state IN ('paid', 'done', 'invoiced')
            JOIN pos_session s ON s.id = o.session_id
            JOIN pos_config cfg ON cfg.id = s.config_id
            GROUP BY 1, 2
        )
        SELECT r.product_id, r.wh_id
        FROM recv r JOIN sold s ON s.product_id = r.product_id AND s.wh_id = r.wh_id
        ORDER BY (r.n + s.n) DESC LIMIT 1
        """
    )
    picked = env.cr.fetchone()
    if not picked:
        return None, []
    product_id, wh_id = picked
    env.cr.execute(
        """
        SELECT pp.default_code, pt.name->>'en_US', pc.complete_name, w.name
        FROM product_product pp
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        LEFT JOIN product_category pc ON pc.id = pt.categ_id
        CROSS JOIN stock_warehouse w
        WHERE pp.id = %s AND w.id = %s
        """,
        (product_id, wh_id),
    )
    head = env.cr.fetchone()

    env.cr.execute(
        """
        SELECT m.date::date AS d, 'Goods Receive' AS kind, p.name AS doc,
               COALESCE(po.name, p.origin, '') AS ref, m.quantity AS qty_in, 0 AS qty_out
        FROM stock_move m
        JOIN stock_picking p ON p.id = m.picking_id
        JOIN stock_picking_type spt ON spt.id = m.picking_type_id
        LEFT JOIN purchase_order_line pol ON pol.id = m.purchase_line_id
        LEFT JOIN purchase_order po ON po.id = pol.order_id
        WHERE m.state = 'done' AND m.product_id = %s AND spt.warehouse_id = %s
          AND m.location_dest_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
        UNION ALL
        SELECT o.date_order::date, 'Point of Sales', o.name, cfg.name, 0, l.qty
        FROM pos_order_line l
        JOIN pos_order o ON o.id = l.order_id AND o.state IN ('paid', 'done', 'invoiced')
        JOIN pos_session s ON s.id = o.session_id
        JOIN pos_config cfg ON cfg.id = s.config_id
        WHERE l.product_id = %s AND cfg.warehouse_id = %s
        ORDER BY 1, 3
        """,
        (product_id, wh_id, product_id, wh_id),
    )
    return head, env.cr.fetchall()


def _return_samples(limit):
    env.cr.execute(
        """
        SELECT m.date::date, p.name, po.name, rp.name, po.partner_ref,
               w.name, pp.default_code, pt.name->>'en_US', pc.complete_name,
               m.quantity, p.origin
        FROM stock_move m
        JOIN stock_picking p ON p.id = m.picking_id
        LEFT JOIN purchase_order_line pol ON pol.id = m.purchase_line_id
        LEFT JOIN purchase_order po ON po.id = pol.order_id
        LEFT JOIN res_partner rp ON rp.id = po.partner_id
        JOIN stock_picking_type spt ON spt.id = m.picking_type_id
        LEFT JOIN stock_warehouse w ON w.id = spt.warehouse_id
        JOIN product_product pp ON pp.id = m.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        LEFT JOIN product_category pc ON pc.id = pt.categ_id
        WHERE m.state = 'done' AND m.location_dest_id IN
              (SELECT id FROM stock_location WHERE usage = 'supplier')
        ORDER BY m.date DESC LIMIT %s
        """,
        (limit,),
    )
    return env.cr.fetchall()


def _pos_samples(limit):
    env.cr.execute(
        """
        SELECT o.date_order::date, cfg.name, o.name, pp.default_code,
               pc.complete_name, l.qty
        FROM pos_order_line l
        JOIN pos_order o ON o.id = l.order_id
        JOIN pos_session s ON s.id = o.session_id
        JOIN pos_config cfg ON cfg.id = s.config_id
        JOIN product_product pp ON pp.id = l.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        LEFT JOIN product_category pc ON pc.id = pt.categ_id
        WHERE o.state IN ('paid', 'done', 'invoiced')
        ORDER BY o.date_order DESC LIMIT %s
        """,
        (limit,),
    )
    return env.cr.fetchall()


def _quant_samples(limit):
    # Warehouse is reached through the location tree: a quant sits on some
    # descendant of the warehouse's view location, so parent_path prefix is the
    # only honest join. (The same correlated subquery is what makes the live
    # Stock Summary report slow -- see sheet #59.)
    env.cr.execute(
        """
        SELECT w.name, pp.default_code, pt.name->>'en_US', pc.complete_name,
               q.quantity,
               COALESCE((pp.standard_price->>%s)::float, 0)
        FROM stock_quant q
        JOIN stock_location l ON l.id = q.location_id
        LEFT JOIN stock_location wl ON l.parent_path LIKE wl.parent_path || '%%'
        LEFT JOIN stock_warehouse w ON w.view_location_id = wl.id
        JOIN product_product pp ON pp.id = q.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        LEFT JOIN product_category pc ON pc.id = pt.categ_id
        WHERE l.usage = 'internal' AND q.quantity <> 0
        ORDER BY q.quantity DESC LIMIT %s
        """,
        (str(company.id), limit),
    )
    return env.cr.fetchall()


print("=" * 72)
print("Membangun template laporan gudang  ->  %s" % OUT_DIR)
print("=" * 72)

BLOCKED = (
    "[ASUMSI] Kolom dan urutannya adalah usulan kami, bukan kutipan dari "
    "berkas Anda -- berkas referensi yang disebut di sheet belum pernah kami "
    "terima. Mohon coret, tambah, atau ubah urutannya langsung di sheet ini."
)

# ---------------------------------------------------------------------------
# #64 Movement Inventory Detail
# ---------------------------------------------------------------------------
wb = Workbook()
ws = wb.create_sheet("Template")
_sheet_header(
    ws,
    [
        "Tanggal",
        "Warehouse",
        "Tipe Transaksi",
        "Nomor Transaksi",
        "Deskripsi",
        "Item Code",
        "Product Category",
        "Quantity In",
        "Quantity Out",
        "Balance Stock",
    ],
    {1: 12, 2: 26, 3: 18, 4: 22, 5: 34, 6: 16, 7: 30, 8: 13, 9: 13, 10: 15},
)
head, ledger = _movement_ledger()
code, name, categ, wh = head or ("", "", "", "")
ws.append(["", wh, "Beginning Balance", "", "Saldo awal periode", code, categ, "", "", 0])
balance = 0.0
for d, kind, doc, ref, qty_in, qty_out in ledger:
    balance += (qty_in or 0.0) - (qty_out or 0.0)
    ws.append(
        [
            d,
            wh,
            kind,
            doc,
            ("Penerimaan %s" % ref) if kind == "Goods Receive" else ("Penjualan POS %s" % ref),
            code,
            categ,
            qty_in or "",
            -(qty_out or 0.0) if qty_out else "",
            balance,
        ]
    )
ws.append(["", wh, "Ending Balance", "", "Saldo akhir periode", code, categ, "", "", balance])
ws.append(["", "", "", "", "", "", "", "", "", ""])
ws.cell(
    row=ws.max_row + 1,
    column=1,
    value="Contoh nyata: item %s di %s. Diterima dan terjual seluruhnya lewat data "
    "prd_levis_begbal Anda sendiri." % (code, wh),
).font = NOTE_FONT
ws.cell(
    row=ws.max_row + 1,
    column=1,
    value="Perhatikan saldo akhirnya: yang diterima di Odoo lebih sedikit daripada yang "
    "terjual, karena saldo awal toko tidak pernah dibukukan sebagai pergerakan. "
    "Itulah yang dimaksud catatan nomor 2 di sheet Petunjuk.",
).font = NOTE_FONT
_guide(
    wb,
    "Template Movement Inventory Detail  --  sheet baris #64",
    [
        (
            "Tujuan",
            "Rincian pergerakan stok per item per warehouse, satu baris per transaksi, "
            "dengan saldo berjalan sesudah tiap baris.",
        ),
        ("Status", BLOCKED),
    ],
    [
        ("Tanggal", "stock.move.date untuk penerimaan/retur; pos.order.date_order untuk penjualan"),
        ("Warehouse", "stock.move.picking_type_id.warehouse_id; untuk POS dari pos.config (toko)"),
        ("Tipe Transaksi", "Goods Receive / Purchase Return / Point of Sales / Internal Transfer / Adjustment / Scrap"),
        ("Nomor Transaksi", "Nomor picking, atau nomor pos.order untuk penjualan"),
        ("Deskripsi", "Keterangan bebas: vendor, origin, atau alasan adjustment"),
        ("Item Code", "product.default_code (SKU)"),
        ("Product Category", "product.categ_id nama lengkap"),
        ("Quantity In", "Positif, hanya untuk pergerakan masuk"),
        ("Quantity Out", "Negatif, hanya untuk pergerakan keluar"),
        ("Balance Stock", "Saldo awal +/- akumulasi pergerakan sampai baris ini"),
    ],
    [
        "PENTING -- penjualan POS tidak membuat stock.move di Odoo tenant ini. Diperiksa "
        "18-Sep-2026: 82.482 baris pos.order.line (91.008 unit) dan NOL stock.move ke lokasi "
        "customer. Jadi laporan ini menggabungkan dua sumber: stock.move untuk penerimaan/retur "
        "dan pos.order.line untuk penjualan.",
        "PENTING -- on-hand di Odoo ditulis oleh snapshot X20, bukan oleh rantai pergerakan. "
        "Karena itu 'saldo awal +/- pergerakan' TIDAK akan persis sama dengan on-hand. "
        "Selisihnya akan kami tampilkan sebagai baris tersendiri, bukan disembunyikan. "
        "Mohon konfirmasi apakah ini bisa diterima, atau apakah adjustment harus mulai "
        "dibukukan di Odoo lebih dulu.",
        "Sepanjang 2026 di Odoo baru ada dua jenis pergerakan: penerimaan (46.500 move) dan "
        "satu batch retur (200 move, 06-Agu). Internal Transfer, Adjustment dan Scrap akan "
        "muncul di laporan ini begitu alurnya dipakai.",
        "Baris contoh di sheet Template diambil dari data prd_levis_begbal Anda sendiri.",
    ],
    params=[
        ("From Date / Until Date", "Rentang tanggal pergerakan"),
        ("Item Code", "Opsional; kosong = semua item"),
        ("Warehouse", "Opsional; kosong = semua warehouse"),
        ("Product Category", "Opsional"),
    ],
)
_save(wb, "Template_Movement_Inventory_Detail.xlsx")

# ---------------------------------------------------------------------------
# #69 Internal Transfer Stock Detail
# ---------------------------------------------------------------------------
wb = Workbook()
ws = wb.create_sheet("Template")
_sheet_header(
    ws,
    [
        "Tanggal",
        "Nomor Transaksi",
        "Warehouse Asal",
        "Lokasi Asal",
        "Warehouse Tujuan",
        "Lokasi Tujuan",
        "Item Code",
        "Item Name",
        "Product Category",
        "Quantity",
        "Unit Cost",
        "Value",
        "Status",
        "Keterangan",
    ],
    {1: 12, 2: 22, 3: 24, 4: 24, 5: 24, 6: 24, 7: 16, 8: 32, 9: 28, 10: 11, 11: 14, 12: 16, 13: 11, 14: 28},
)
ws.append(
    [
        "2026-09-01",
        "INTF/2026/09/00001",
        "EBR - HEAD OFFICE",
        "HO/Stock",
        "OLS SES - PACIFIC PLACE MALL",
        "PP/Stock",
        "A1234567",
        "CONTOH ITEM",
        "Textile / WOMENS BOTTOMS",
        10,
        250000,
        2500000,
        "Done",
        "Mutasi antar toko",
    ]
)
ws.append(["", "", "", "", "", "", "", "", "", "", "", "", "", ""])
ws.cell(
    row=3, column=1, value="(Belum ada data internal transfer di Odoo -- baris di atas contoh format)"
).font = NOTE_FONT
_guide(
    wb,
    "Template Internal Transfer Stock Detail  --  sheet baris #69",
    [
        ("Tujuan", "Rincian mutasi stok antar lokasi/warehouse internal."),
        ("Status", BLOCKED),
    ],
    [
        ("Tanggal", "stock.move.date"),
        ("Nomor Transaksi", "stock.picking.name -- diminta berformat INTF/2026/09/00001"),
        ("Warehouse / Lokasi Asal", "stock.move.location_id dan warehouse induknya"),
        ("Warehouse / Lokasi Tujuan", "stock.move.location_dest_id dan warehouse induknya"),
        ("Item Code / Name", "product.default_code, product.name"),
        ("Product Category", "product.categ_id nama lengkap"),
        ("Quantity", "stock.move.quantity (kuantitas done)"),
        ("Unit Cost", "[ASUMSI] product.standard_price per company saat penarikan"),
        ("Value", "Quantity x Unit Cost"),
        ("Status", "stock.picking.state"),
        ("Keterangan", "stock.picking.origin / note"),
    ],
    [
        "BELUM ADA DATANYA. Sepanjang 2026 tidak ada satu pun pergerakan internal -> internal "
        "di prd_levis_begbal. Laporan ini akan kosong sampai mutasi antar toko benar-benar "
        "dijalankan lewat Odoo. Format disepakati sekarang supaya tidak menunggu dua kali.",
        "Penomoran INTF/YYYY/MM/NNNNN adalah perubahan ir.sequence pada picking type internal. "
        "Itu mengubah penomoran dokumen berjalan, jadi kami tahan sampai Accounting menyetujui.",
        "[ASUMSI] Unit Cost memakai standard_price saat penarikan, bukan biaya historis saat "
        "mutasi -- Odoo 19 tidak menyimpan nilai per move untuk mutasi internal. Mohon "
        "konfirmasi apakah ini cukup.",
    ],
    params=[
        ("From Date / Until Date", "Rentang tanggal"),
        ("Warehouse", "Opsional, asal atau tujuan"),
        ("Item Code", "Opsional"),
    ],
)
_save(wb, "Template_Internal_Transfer_Stock_Detail.xlsx")

# ---------------------------------------------------------------------------
# #70 Adjustment + Scrap
# ---------------------------------------------------------------------------
wb = Workbook()
for kind, prefix, reason_col in (
    ("Adjustment", "STADJ/2026/09/00001", "Alasan Adjustment"),
    ("Scrap", "STSCP/2026/09/00001", "Alasan Scrap"),
):
    ws = wb.create_sheet(kind)
    _sheet_header(
        ws,
        [
            "Tanggal",
            "Nomor Transaksi",
            "Warehouse",
            "Lokasi",
            "Item Code",
            "Item Name",
            "Product Category",
            "Qty Sistem",
            "Qty Fisik",
            "Qty Selisih",
            "Unit Cost",
            "Value",
            reason_col,
            "COA Beban",
            "User",
        ],
        {1: 12, 2: 22, 3: 24, 4: 22, 5: 16, 6: 32, 7: 28, 8: 12, 9: 12, 10: 12, 11: 14, 12: 16, 13: 26, 14: 24, 15: 18},
    )
    ws.append(
        [
            "2026-09-01",
            prefix,
            "EBR - HEAD OFFICE",
            "HO/Stock",
            "A1234567",
            "CONTOH ITEM",
            "Textile / WOMENS BOTTOMS",
            100,
            98,
            -2,
            250000,
            -500000,
            "Stock opname internal" if kind == "Adjustment" else "Rusak / tidak layak jual",
            "7218000001 Inventory write-off",
            "devina",
        ]
    )
    ws.cell(
        row=3, column=1, value="(Belum ada data %s di Odoo -- baris di atas contoh format)" % kind.lower()
    ).font = NOTE_FONT
_guide(
    wb,
    "Template Adjustment & Scrap Stock Report  --  sheet baris #70 dan #71",
    [
        ("Tujuan", "Rincian penyesuaian stok (stock opname) dan pemusnahan/scrap, beserta nilai dan COA bebannya."),
        ("Status", BLOCKED),
    ],
    [
        ("Tanggal", "stock.move.date / stock.scrap.date_done"),
        ("Nomor Transaksi", "Diminta berformat STADJ/2026/09/00001 dan STSCP/2026/09/00001"),
        ("Warehouse / Lokasi", "Lokasi internal yang disesuaikan"),
        ("Item Code / Name", "product.default_code, product.name"),
        ("Qty Sistem", "Kuantitas on-hand sebelum penyesuaian"),
        ("Qty Fisik", "Hasil hitung fisik"),
        ("Qty Selisih", "Fisik - Sistem; negatif = kurang"),
        ("Unit Cost", "[ASUMSI] product.standard_price per company"),
        ("Value", "Qty Selisih x Unit Cost"),
        ("Alasan", "[ASUMSI] field bebas pada dokumen; untuk scrap dari stock.scrap"),
        ("COA Beban", "7218000001 Inventory write-off (Dr) lawan Inventory (Cr), sesuai #71"),
        ("User", "Pembuat dokumen"),
    ],
    [
        "BELUM ADA DATANYA. Tidak ada satu pun inventory adjustment maupun scrap di prd_levis_begbal sepanjang 2026.",
        "#71 meminta setting jurnal adjustment Dr 7218000001 Inventory write-off / Cr Inventory. "
        "Itu setting product category (property_stock_account_*) plus lokasi inventory adjustment, "
        "dan kami kerjakan bersama laporan ini supaya angkanya konsisten sejak transaksi pertama.",
        "[ASUMSI] Scrap dan Adjustment dipisah per sheet karena COA dan alasannya berbeda, "
        "walau klien menulis 'bisa disamakan'. Kalau lebih suka satu sheet dengan kolom Tipe, "
        "mohon dicoret.",
    ],
    params=[
        ("From Date / Until Date", "Rentang tanggal"),
        ("Warehouse", "Opsional"),
        ("Tipe", "Adjustment / Scrap / keduanya"),
    ],
)
_save(wb, "Template_Adjustment_Scrap_Stock_Report.xlsx")

# ---------------------------------------------------------------------------
# #26 Purchase Return Report
# ---------------------------------------------------------------------------
wb = Workbook()
ws = wb.create_sheet("Template")
_sheet_header(
    ws,
    [
        "Tanggal Retur",
        "Nomor Retur",
        "No. PO",
        "Vendor",
        "Vendor Ref",
        "Warehouse",
        "Item Code",
        "Item Name",
        "Product Category",
        "Qty Retur",
        "Unit Cost",
        "Value",
        "No. GR Asal",
        "No. Credit Note",
        "Alasan",
    ],
    {1: 13, 2: 22, 3: 22, 4: 30, 5: 16, 6: 26, 7: 16, 8: 32, 9: 28, 10: 11, 11: 14, 12: 16, 13: 20, 14: 20, 15: 26},
)
for row in _return_samples(LIMIT):
    date, picking, po, vendor, vref, wh, code, name, categ, qty, origin = row
    ws.append(
        [
            date,
            picking,
            po or "",
            vendor or "",
            vref or "",
            wh or "",
            code or "",
            name or "",
            categ or "",
            qty,
            "",
            "",
            origin or "",
            "(belum ada)",
            "",
        ]
    )
_guide(
    wb,
    "Template Purchase Return Report  --  sheet baris #26",
    [
        (
            "Tujuan",
            "Rincian retur pembelian ke vendor, ditarik dari menu Invoicing > Reporting seperti Purchase Report.",
        ),
        ("Status", BLOCKED),
    ],
    [
        ("Tanggal Retur", "stock.move.date pada pergerakan internal -> supplier"),
        ("Nomor Retur", "stock.picking.name"),
        ("No. PO / Vendor / Vendor Ref", "purchase.order lewat stock.move.purchase_line_id"),
        ("Warehouse", "picking_type_id.warehouse_id"),
        ("Item Code / Name / Category", "product"),
        ("Qty Retur", "stock.move.quantity"),
        ("Unit Cost / Value", "[ASUMSI] stock.move.value bila ada, jatuh ke harga PO bila tidak"),
        ("No. GR Asal", "Dari origin picking ('Return of ...')"),
        ("No. Credit Note", "KOSONG SECARA STRUKTUR -- lihat catatan"),
        ("Alasan", "[ASUMSI] field bebas pada picking"),
    ],
    [
        "Sumbernya sisi STOK, bukan nota kredit. Di prd_levis_begbal ada 3 in_refund terposting "
        "(semua 27-Jul, pembatalan invoice non-trade) yang keenam baris produknya TIDAK punya "
        "purchase_line_id, dan 200 stock move retur (06-Agu) dari PO trade Agustus. Keduanya "
        "tidak terhubung sama sekali. Menggabungkannya lewat join apa pun akan mengarang relasi.",
        "Karena itu kolom No. Credit Note dibiarkan kosong: di tenant ini retur belum menghasilkan "
        "nota kredit. Mohon konfirmasi apakah alurnya akan diubah.",
        "PERINGATAN KUALITAS DATA: 200 move retur 06-Agu membawa kuantitas yang sebenarnya HARGA "
        "(413011, 698987, 540112 ...), sisa insiden PO tertukar qty/harga. Angka contoh di sheet "
        "Template memperlihatkannya apa adanya -- jangan dipakai sebagai acuan nilai.",
        "Tim MnP akan mencoba satu transaksi retur di Odoo pada pertemuan 18-Sep. Begitu ada satu "
        "transaksi yang benar, template ini diisi ulang dengan datanya.",
    ],
    params=[("From Date / Until Date", "Rentang tanggal retur"), ("Vendor", "Opsional"), ("Warehouse", "Opsional")],
)
_save(wb, "Template_Purchase_Return_Report.xlsx")

# ---------------------------------------------------------------------------
# #27 Summary Inventory (per periode, dengan movement in/out)
# ---------------------------------------------------------------------------
wb = Workbook()
ws = wb.create_sheet("Template")
_sheet_header(
    ws,
    [
        "Warehouse",
        "Item Code",
        "Item Name",
        "Product Category",
        "UoM",
        "Beginning Qty",
        "Beginning Value",
        "In Qty",
        "In Value",
        "Out Qty",
        "Out Value",
        "Adjustment Qty",
        "Adjustment Value",
        "Ending Qty",
        "Ending Value",
    ],
    {1: 26, 2: 16, 3: 34, 4: 28, 5: 8, 6: 14, 7: 16, 8: 11, 9: 15, 10: 11, 11: 15, 12: 14, 13: 16, 14: 13, 15: 16},
)
for wh, code, name, categ, qty, cost in _quant_samples(LIMIT):
    ws.append(
        [
            wh or "",
            code or "",
            name or "",
            categ or "",
            "Units",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            qty,
            round((qty or 0) * (cost or 0), 2),
        ]
    )
_guide(
    wb,
    "Template Summary Inventory  --  sheet baris #27 dan #59",
    [
        (
            "Tujuan",
            "Ringkasan persediaan seluruh warehouse dalam satu tarikan, "
            "dengan total movement masuk dan keluar selama periode.",
        ),
        ("Status", BLOCKED),
    ],
    [
        ("Warehouse", "stock.warehouse dari lokasi quant"),
        ("Item Code / Name / Category", "product"),
        ("UoM", "product.uom_id -- seluruh 47.995 baris PO tenant ini memakai Units"),
        ("Beginning Qty / Value", "[ASUMSI] posisi pada From Date"),
        ("In Qty / Value", "Penerimaan + transfer masuk selama periode"),
        ("Out Qty / Value", "Penjualan POS + retur + transfer keluar selama periode"),
        ("Adjustment Qty / Value", "Selisih yang tidak terjelaskan oleh pergerakan"),
        ("Ending Qty / Value", "stock_quant pada Until Date x standard_price"),
    ],
    [
        "PENTING -- Odoo tenant ini TIDAK menyimpan posisi historis. stock_quant adalah "
        "posisi SEKARANG, dan stock_valuation_layer tidak ada di database ini. Beginning Qty "
        "pada tanggal lampau karena itu harus dihitung mundur dari pergerakan -- dan karena "
        "penjualan POS tidak punya stock.move, perhitungan mundur itu tidak lengkap.",
        "[ASUMSI] Kolom Adjustment menampung selisih tersebut secara jujur, sehingga "
        "Beginning + In - Out + Adjustment = Ending selalu benar secara aritmetika. "
        "Mohon konfirmasi apakah pendekatan ini diterima.",
        "Angka Ending di sheet Template adalah on-hand nyata hari ini dari prd_levis_begbal "
        "(quant internal: 44.629 baris, 119.763 unit).",
        "Keluhan performa #59 sudah dikonfirmasi: SQL mentahnya saja 2,5 detik. Optimasi peta "
        "lokasi->warehouse ikut dalam pengerjaannya.",
    ],
    params=[
        ("From Period", "DD/MM/YYYY"),
        ("Until Period", "DD/MM/YYYY"),
        ("Warehouse", "Opsional; kosong = SEMUA warehouse sekaligus (inti permintaan #28)"),
        ("Product Category", "Opsional"),
    ],
)
_save(wb, "Template_Summary_Inventory.xlsx")

# ---------------------------------------------------------------------------
# #28 Inventory per Warehouse (as of)
# ---------------------------------------------------------------------------
wb = Workbook()
ws = wb.create_sheet("Template")
_sheet_header(
    ws,
    [
        "As Of",
        "Warehouse",
        "Operating Unit",
        "Item Code",
        "Item Name",
        "Product Category",
        "UoM",
        "Qty On Hand",
        "Unit Cost",
        "Total Value",
    ],
    {1: 12, 2: 26, 3: 26, 4: 16, 5: 34, 6: 28, 7: 8, 8: 13, 9: 14, 10: 18},
)
for wh, code, name, categ, qty, cost in _quant_samples(LIMIT):
    ws.append(
        [
            "(as of)",
            wh or "",
            "",
            code or "",
            name or "",
            categ or "",
            "Units",
            qty,
            cost,
            round((qty or 0) * (cost or 0), 2),
        ]
    )
_guide(
    wb,
    "Template Inventory per Warehouse  --  sheet baris #28",
    [
        ("Tujuan", "Posisi persediaan per warehouse pada satu tanggal, seluruh warehouse dalam satu tarikan."),
        ("Status", BLOCKED),
    ],
    [
        ("As Of", "Tanggal posisi yang diinput user"),
        ("Warehouse", "stock.warehouse dari lokasi quant"),
        (
            "Operating Unit",
            "[ASUMSI] stock.warehouse.l10n_ou_analytic_id, supaya bisa direkonsiliasi dengan GL per toko",
        ),
        ("Item Code / Name / Category", "product"),
        ("Qty On Hand", "stock_quant pada lokasi internal"),
        ("Unit Cost", "product.standard_price dibaca per company"),
        ("Total Value", "Qty x Unit Cost"),
    ],
    [
        "PENTING -- stock_quant adalah posisi SEKARANG. Tarikan 'As Of' tanggal lampau hanya "
        "bisa dihitung mundur dari pergerakan, dan penjualan POS tidak punya stock.move. "
        "Sampai hal itu diselesaikan, As Of hanya jujur untuk tanggal hari ini.",
        "Keluhan 16-Sep 'penarikan inventory per warehouse harus satu-satu per warehouse' "
        "dijawab dengan membuat Warehouse OPSIONAL: kosong berarti semua warehouse sekaligus, "
        "dikelompokkan per warehouse.",
        "Angka contoh adalah on-hand nyata hari ini: 22 warehouse punya quant, total 119.763 unit.",
    ],
    params=[("As Of", "DD/MM/YYYY"), ("Warehouse", "Opsional; kosong = semua"), ("Product Category", "Opsional")],
)
_save(wb, "Template_Inventory_per_Warehouse.xlsx")

print("\nSelesai. Enam template dibuat.")
env.cr.rollback()
