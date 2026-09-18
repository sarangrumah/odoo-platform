# -*- coding: utf-8 -*-
"""Penomoran dokumen gudang: GR, Internal Transfer, Scrap.

Sheet baris #68, #69, #70. DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python < scripts/tenants/levis/120_set_document_numbering.py

--------------------------------------------------------------------------
Yang diminta klien, dan bentuk yang benar-benar dipakai
--------------------------------------------------------------------------
| Sheet | Diminta klien          | Dipakai skrip ini                  |
|-------|------------------------|------------------------------------|
| #68   | GR/EBR/2026/09/00001   | GR/<kode wh>/YYYY/MM/NNNNN         |
| #69   | INTF/2026/09/00001     | INTF/<kode wh>/YYYY/MM/NNNNN       |
| #70   | STSCP/2026/09/00001    | STSCP/YYYY/MM/NNNNN                |
| #70   | STADJ/2026/09/00001    | STADJ/YYYY/MM/NNNNN (lihat bawah)  |

**Kenapa INTF ikut memakai kode warehouse padahal contoh klien tidak.**
Setiap picking type punya ``ir.sequence`` sendiri -- ada 34 tipe "Internal
Transfers", satu per warehouse. Memberi ketiga puluh empat sequence itu prefix
``INTF/YYYY/MM/`` yang sama berarti 34 pencacah berjalan paralel dan
**menghasilkan nomor dokumen yang sama persis**. Kode warehouse adalah unsur
"kode toko" yang memang diminta #68, jadi dipakai konsisten di keduanya.
Contoh klien untuk GR (``GR/EBR/...``) memang sudah berbentuk begitu.

**STADJ tidak diatur di sini.** Inventory adjustment di Odoo 19 bukan dokumen:
ia hanya ``stock.move`` ber-``is_inventory``, tanpa picking dan tanpa nomor.
Penomorannya ditangani `custom_levis_localization` 1.55.0 lewat
``stock.quant._apply_inventory`` yang menarik satu nomor per *apply* dan
menitipkannya di ``stock.move.inventory_name`` -- kait bawaan Odoo. Sequence-nya
dibuat modul itu (``levis.stock.adjustment``), bukan skrip ini.

--------------------------------------------------------------------------
Yang TIDAK berubah
--------------------------------------------------------------------------
* **Dokumen yang sudah ada tetap memakai nomor lamanya.** Prefix hanya mengatur
  nomor BERIKUTNYA. Tidak ada dokumen yang di-rename.
* Picking type selain Receipts, Internal Transfers dan Scrap tidak disentuh --
  PACK/PICK/QC/STOR/XD/POS/OUT tetap seperti sekarang.
* Pencacah ikut rentang tanggal (``use_date_range``), jadi nomor urut kembali ke
  1 setiap bulan, seperti bentuk yang diminta.
"""

import os

CONFIRM = os.environ.get("CONFIRM", "0") == "1"

Sequence = env["ir.sequence"]
PickingType = env["stock.picking.type"]

DATE_PART = "%(range_year)s/%(range_month)s/"

print("=" * 78)
print("Penomoran dokumen gudang   --   %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 78)

plan = []

# --- #68 Goods Receipt, per warehouse -------------------------------------
for ptype in PickingType.search([("code", "=", "incoming")], order="id"):
    warehouse = ptype.warehouse_id
    if not warehouse or not warehouse.code:
        print("  ! lewati picking type %s: tanpa warehouse/kode" % ptype.display_name)
        continue
    plan.append((ptype.sequence_id, "GR/%s/%s" % (warehouse.code, DATE_PART), "#68 GR %s" % warehouse.name))

# --- #69 Internal Transfers, per warehouse --------------------------------
for ptype in PickingType.search([("code", "=", "internal")], order="id"):
    if "internal transfer" not in (ptype.name or "").lower():
        continue  # PACK / PICK / QC / STOR / XD keep their own numbering
    warehouse = ptype.warehouse_id
    if not warehouse or not warehouse.code:
        continue
    plan.append(
        (ptype.sequence_id, "INTF/%s/%s" % (warehouse.code, DATE_PART), "#69 Internal Transfer %s" % warehouse.name)
    )

# --- #70 Scrap, one company-wide counter ----------------------------------
scrap_seq = Sequence.search([("code", "=", "stock.scrap")], limit=1)
if scrap_seq:
    plan.append((scrap_seq, "STSCP/%s" % DATE_PART, "#70 Scrap"))
else:
    print("  ! sequence stock.scrap tidak ditemukan")

changes = [(seq, prefix, label) for seq, prefix, label in plan if seq and seq.prefix != prefix]
already = len(plan) - len(changes)

print("\nSequence dalam lingkup: %s  (sudah sesuai: %s, akan diubah: %s)" % (len(plan), already, len(changes)))
print("\n%-34s %-26s -> %s" % ("Untuk", "Prefix sekarang", "Prefix baru"))
for seq, prefix, label in changes:
    print("%-34s %-26s -> %s" % (label[:34], seq.prefix or "(kosong)", prefix))

# --- STADJ: lapor keadaannya, jangan diam-diam ----------------------------
adj_seq = Sequence.search([("code", "=", "levis.stock.adjustment")], limit=1)
print("\n#70 Inventory Adjustment (STADJ):")
if adj_seq:
    print("  sequence '%s' sudah ada, prefix %s" % (adj_seq.code, adj_seq.prefix))
    print("  dipakai otomatis oleh stock.quant._apply_inventory (custom_levis_localization >= 1.55.0)")
else:
    print("  BELUM ADA. Pasang/-u custom_levis_localization 1.55.0 dulu; sequence-nya")
    print("  dibuat oleh modul itu, bukan oleh skrip ini.")

if not changes:
    print("\nTidak ada yang perlu diubah.")
elif CONFIRM:
    for seq, prefix, _label in changes:
        seq.write({"prefix": prefix, "padding": 5, "use_date_range": True})
    env.cr.commit()
    env.invalidate_all()
    print("\n  DIUBAH dan di-commit: %s sequence." % len(changes))
    for seq, prefix, label in changes:
        print("    %-34s %s" % (label[:34], seq.prefix))
    print("\n  Dokumen yang sudah ada TIDAK di-rename; nomor baru berlaku untuk dokumen berikutnya.")
else:
    print("\n  DRY RUN -- tidak ada yang diubah. Jalankan dengan CONFIRM=1.")
    env.cr.rollback()
