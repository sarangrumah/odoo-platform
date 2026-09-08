# Laporan PO yang memuat SKU yang sama pada lebih dari satu baris -- prd_levis_begbal.
#
# Kenapa perlu: setiap ukuran garmen adalah varian tersendiri dengan PROD SKU sendiri.
# File upload PO yang kolom produknya tersalin turun memesan satu ukuran berkali-kali,
# dan penerimaan membukukan persis itu -- receipt mewarisi produknya dari PO
# (custom_levis_localization/models/stock_move.py::_check_levis_receipt_line_from_po),
# jadi saat barang dibuka isinya 25/26/27/28 sementara sistem mencatat 4x size 25.
#
# Guard baru (localization 19.0.1.49.0) menutup pintu itu ke depan; script ini mencari
# yang sudah terlanjur, lengkap dengan apa yang sudah terjadi pada tiap PO:
# receipt-nya sudah divalidasi atau belum, jurnal GR sudah terbit atau belum, dan
# tagihan vendornya sudah diposting atau belum -- karena tiga hal itulah yang
# menentukan jalur koreksinya.
#
# Kolom "Varian lain yang tidak dipesan" memuat ukuran lain pada template yang sama.
# Itu bukan bukti kesalahan, itu bahan pemeriksaan: kalau ukuran yang dimaksud ada di
# sana, hampir pasti barisnya yang salah.
#
# SELECT-ONLY. Tidak menulis apa pun ke database; satu-satunya keluaran adalah CSV.
#
#   python3 scripts/tenants/levis/103_report_po_duplicate_sku.py
#
# Env:  DB     -> database (default prd_levis_begbal)
#       OUT    -> path CSV (default /srv/sftp-share/files/PO_SKU_Ganda.csv)
#       SINCE  -> hanya PO dengan date_order >= tanggal ini (default 2026-01-01)
#       STATES -> daftar state PO yang diperiksa (default draft,sent,purchase,done)

import csv
import io
import os
import subprocess
import sys

PG = "odoo19-platform-postgres"
DB = os.environ.get("DB", "prd_levis_begbal")
OUT = os.environ.get("OUT", "/srv/sftp-share/files/PO_SKU_Ganda.csv")
SINCE = os.environ.get("SINCE", "2026-01-01")
STATES = [s.strip() for s in os.environ.get("STATES", "draft,sent,purchase,done").split(",") if s.strip()]

# Satu baris per (PO, SKU yang berulang). Semua agregat dihitung di SQL supaya
# laporan tetap ringan di DB produksi.
SQL = """
WITH dup AS (
    SELECT pol.order_id,
           pol.product_id,
           COUNT(*)          AS line_count,
           SUM(pol.product_qty) AS qty_total,
           MIN(pol.price_unit)  AS price_min,
           MAX(pol.price_unit)  AS price_max
      FROM purchase_order_line pol
      JOIN purchase_order po ON po.id = pol.order_id
     WHERE pol.product_id IS NOT NULL
       AND COALESCE(pol.display_type, '') = ''
       AND po.state = ANY(%(states)s)
       AND po.date_order >= %(since)s::timestamp
     GROUP BY pol.order_id, pol.product_id
    HAVING COUNT(*) > 1
),
ordered AS (   -- semua varian yang memang dipesan di PO itu
    SELECT DISTINCT pol.order_id, pol.product_id
      FROM purchase_order_line pol
     WHERE pol.product_id IS NOT NULL
)
SELECT po.name                                    AS po_name,
       po.state                                   AS po_state,
       to_char(po.date_order, 'YYYY-MM-DD')       AS po_date,
       rp.name                                    AS vendor,
       pp.default_code                            AS sku,
       COALESCE(pt.name->>'en_US', pt.name->>'id_ID') AS product_name,
       (SELECT string_agg(pav.name->>'en_US', ' / ' ORDER BY pav.id)
          FROM product_template_attribute_value ptav
          JOIN product_attribute_value pav ON pav.id = ptav.product_attribute_value_id
         WHERE ptav.id = ANY(
                   SELECT v.product_template_attribute_value_id
                     FROM product_variant_combination v
                    WHERE v.product_product_id = pp.id))  AS varian,
       dup.line_count,
       dup.qty_total,
       dup.price_min,
       dup.price_max,
       (SELECT string_agg(sib.default_code, ', ' ORDER BY sib.default_code)
          FROM product_product sib
         WHERE sib.product_tmpl_id = pp.product_tmpl_id
           AND sib.active
           AND sib.id NOT IN (SELECT o.product_id FROM ordered o WHERE o.order_id = po.id)
       )                                          AS varian_tak_dipesan,
       (SELECT string_agg(DISTINCT sp.name || ' [' || sp.state || ']', ', ')
          FROM stock_picking sp
          JOIN stock_move sm ON sm.picking_id = sp.id
         WHERE sm.purchase_line_id IN (
                   SELECT id FROM purchase_order_line
                    WHERE order_id = po.id AND product_id = pp.id))  AS receipts,
       -- Jurnal valuasi GR dikenali lewat ref 'GR-VAL:<stock_move_id>', bukan lewat
       -- product_id: baris jurnalnya tidak selalu membawa produk.
       (SELECT string_agg(DISTINCT am.name || ' [' || am.state || ']', ', ')
          FROM account_move am
         WHERE am.ref IN (
                   SELECT 'GR-VAL:' || sm.id
                     FROM stock_move sm
                    WHERE sm.purchase_line_id IN (
                              SELECT id FROM purchase_order_line
                               WHERE order_id = po.id AND product_id = pp.id)))  AS jurnal_gr,
       (SELECT string_agg(DISTINCT am.name || ' [' || am.state || ']', ', ')
          FROM account_move_line aml
          JOIN account_move am ON am.id = aml.move_id
         WHERE aml.purchase_line_id IN (
                   SELECT id FROM purchase_order_line
                    WHERE order_id = po.id AND product_id = pp.id))  AS bills
  FROM dup
  JOIN purchase_order po ON po.id = dup.order_id
  JOIN product_product pp ON pp.id = dup.product_id
  JOIN product_template pt ON pt.id = pp.product_tmpl_id
  LEFT JOIN res_partner rp ON rp.id = po.partner_id
 ORDER BY po.date_order DESC, po.name, pp.default_code
"""

HEADER = [
    "PO",
    "State",
    "Tanggal",
    "Vendor",
    "SKU",
    "Produk",
    "Varian",
    "Jumlah Baris",
    "Total Qty",
    "Harga Min",
    "Harga Max",
    "Varian lain yang tidak dipesan",
    "Receipt",
    "Jurnal GR",
    "Tagihan",
]


def query():
    """Jalankan SQL di container postgres dan kembalikan baris CSV."""
    sql = SQL.replace("%(states)s", "'{" + ",".join(STATES) + "}'").replace("%(since)s", "'%s'" % SINCE)
    # SQL lewat stdin, bukan -c: pernyataannya panjang dan penuh tanda kutip. Kredensial
    # dibaca dari env container, dan ON_ERROR_STOP wajib -- tanpa itu psql pulang dengan
    # exit 0 meski query-nya gagal.
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            PG,
            "sh",
            "-c",
            'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d %s --csv -v ON_ERROR_STOP=1 -f -' % DB,
        ],
        input=sql,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.exit("psql gagal:\n" + (proc.stderr or proc.stdout))
    return list(csv.reader(io.StringIO(proc.stdout)))


def main():
    rows = query()
    if not rows:
        sys.exit("query tidak mengembalikan apa-apa -- periksa DB '%s'" % DB)
    body = rows[1:]  # buang header psql, pakai header sendiri (bahasa Indonesia)
    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(body)
    print("%s: %d baris (PO x SKU) ditulis ke %s" % (DB, len(body), OUT))
    if body:
        print("\nContoh 10 teratas:")
        for row in body[:10]:
            print("  %-24s %-14s x%-3s qty %-8s | varian lain: %s" % (row[0], row[4], row[7], row[8], row[11] or "-"))


if __name__ == "__main__":
    main()
