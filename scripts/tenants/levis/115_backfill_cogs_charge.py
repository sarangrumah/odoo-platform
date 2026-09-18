# -*- coding: utf-8 -*-
"""Backfill ``levis.cogs.charge`` untuk run COGS yang mendahului buku itu.

Sheet baris #74. DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python < scripts/tenants/levis/115_backfill_cogs_charge.py

Dijalankan lewat ``odoo shell`` (butuh ``env``), bukan python biasa. Perhatikan
``docker exec -e``: skrip ini dialirkan lewat stdin ke proses di dalam
container, jadi yang dibaca ``os.environ`` adalah environment container itu.

--------------------------------------------------------------------------
Masalahnya
--------------------------------------------------------------------------
``levis.cogs.charge`` adalah SATU-SATUNYA penjaga terhadap pembebanan ganda:
``levis.cogs.run._detail()`` mengurangkannya sebelum mengusulkan apa pun, dan
catch-up penerimaan melakukan hal yang sama. Run yang dibangkitkan oleh versi
kode yang mendahului buku itu karena itu **tak terlihat** oleh run berikutnya --
ia membukukan biayanya, tetapi tidak ada yang mencatat bahwa ia membukukannya.

Di ``prd_levis_begbal`` itu persis keadaan Juni 2026:

  COGS/2026/0001  Juni   posted  GLJV/2026/06/0032   0 baris charge
  COGS/2026/0002  Juli   posted  GLJV/2026/07/0126   14.715 baris
  COGS/2026/0003  Agustus posted GLJV/2026/08/0018    9.685 baris

Akibatnya run ulang Juni (``COGS/2026/0004``) mengusulkan seluruh bulan itu
lagi: 657 baris, 7.441 unit, Rp 4.227.985.550 -- tepat seperti yang dilaporkan
klien.

--------------------------------------------------------------------------
Kenapa rekonstruksinya sah, bukan tebakan
--------------------------------------------------------------------------
Karena bukunya KOSONG, ``_detail()`` tidak mengurangkan apa pun, sehingga ia
mereproduksi persis detail yang dulu dibukukan run itu. Itu bukan harapan:
``COGS/2026/0004`` sudah membuktikannya di produksi -- 657 baris, 7.441 unit,
selisih nilai Rp 0,11 (pembulatan), dan ``zero_cost_qty = 0`` pada **seluruh**
657 baris di kedua run. Tidak ada satu pun unit Juni yang waktu itu tanpa harga,
jadi tidak ada bagian yang ambigu.

Bila kelak ada run lain yang ``zero_cost_qty > 0``, rekonstruksi hanya akan
mengurangkan unit-unit yang HARI INI berharga -- arah yang aman menurut
docstring modulnya sendiri: biaya tertunda, tidak pernah dobel.

--------------------------------------------------------------------------
Yang TIDAK disentuh
--------------------------------------------------------------------------
* Jurnal yang sudah diposting. Skrip ini hanya menulis baris buku, nol jurnal.
* Run yang bukunya sudah terisi (``action_backfill_charges`` menolaknya).
* Run berstatus draft/computed.
"""

import os

CONFIRM = os.environ.get("CONFIRM", "0") == "1"

Run = env["levis.cogs.run"]
Charge = env["levis.cogs.charge"]

runs = Run.search([("state", "=", "generated")], order="date_from")
stale = runs.filtered(lambda r: r.total_cogs and not r.charge_ids)

print("=" * 72)
print("Backfill levis.cogs.charge  --  %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 72)
print("\nRun COGS yang sudah generated: %s" % len(runs))
for run in runs:
    print(
        "  %-16s %s .. %s  %-18s  charge=%s  total=%s"
        % (
            run.name,
            run.date_from,
            run.date_to,
            run.move_id.name or "-",
            len(run.charge_ids),
            run.currency_id.round(run.total_cogs),
        )
    )

if not stale:
    print("\nTidak ada run tanpa buku charge. Tidak ada yang perlu dikerjakan.")
else:
    print("\nRun tanpa buku charge: %s" % ", ".join(stale.mapped("name")))
    total_rows = 0
    total_amount = 0.0
    total_qty = 0.0
    for run in stale:
        rows = [row for row in run._detail() if row["cost"] and not run.company_id.currency_id.is_zero(row["amount"])]
        qty = sum(row["quantity"] for row in rows)
        amount = sum(row["amount"] for row in rows)
        total_rows += len(rows)
        total_qty += qty
        total_amount += amount
        print(
            "\n  %s: akan ditulis %s baris buku, %s unit, %s"
            % (run.name, len(rows), qty, run.currency_id.round(amount))
        )
        print("    jurnal yang dulu dibukukan: %s  (%s)" % (run.move_id.name, run.currency_id.round(run.total_cogs)))
        drift = run.currency_id.round(amount - run.total_cogs)
        print("    selisih rekonstruksi vs jurnal: %s" % drift)
        if abs(drift) > 1.0:
            print(
                "    *** PERIKSA DULU: selisih di atas Rp 1. Populasi penjualan atau "
                "harga pokok sudah bergeser sejak run itu; jangan apply tanpa "
                "konfirmasi Accounting."
            )

    print("\n  TOTAL: %s baris, %s unit, %s" % (total_rows, total_qty, total_amount))

    if CONFIRM:
        for run in stale:
            run.action_backfill_charges()
        env.cr.commit()
        env.invalidate_all()
        print("\n  DITULIS dan di-commit.")
    else:
        print("\n  DRY RUN -- tidak ada yang ditulis. Jalankan dengan CONFIRM=1.")

# --------------------------------------------------------------------------
# Bukti penutupan: sesudah buku terisi, hitung ulang periode yang sama harus
# menghasilkan NOL baris -- itulah yang diminta klien di baris #74.
# --------------------------------------------------------------------------
print("\n" + "-" * 72)
print("Verifikasi: hitung ulang periode yang sudah ter-charge")
print("-" * 72)
for run in runs:
    detail = Run.new(
        {
            "company_id": run.company_id.id,
            "date_from": run.date_from,
            "date_to": run.date_to,
            "journal_id": run.journal_id.id,
        }
    )._detail()
    pending = sum(row["quantity"] for row in detail)
    print(
        "  periode %s .. %s -> %s baris detail, %s unit belum ter-charge"
        % (run.date_from, run.date_to, len(detail), pending)
    )

if not CONFIRM:
    env.cr.rollback()
    print("\n(dry run: transaksi di-rollback)")
