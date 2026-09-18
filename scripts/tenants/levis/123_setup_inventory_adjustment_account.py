# -*- coding: utf-8 -*-
"""Akun beban untuk selisih stock opname (inventory adjustment).

Sheet baris #71. DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python \\
    < scripts/tenants/levis/123_setup_inventory_adjustment_account.py

--------------------------------------------------------------------------
Yang diminta
--------------------------------------------------------------------------
"COA Biaya (Debit) 7218000001 Inventory write-off pada Inventory (Credit)"
untuk selisih stock opname, baik dari pihak internal maupun eksternal.

--------------------------------------------------------------------------
Di mana akun itu sebenarnya diatur
--------------------------------------------------------------------------
Bukan di product category, melainkan di **lokasi virtual "Inventory
adjustment"** (``stock.location.valuation_account_id``). Untuk kategori
ber-valuasi otomatis, Odoo membukukan selisih opname sebagai:

    selisih kurang : Dr <valuation_account lokasi>  / Cr Stock Valuation
    selisih lebih  : Dr Stock Valuation             / Cr <valuation_account>

Diperiksa 18-Sep-2026 di ``prd_levis_begbal``: lokasi "Inventory adjustment"
(id 11) **kosong** akun valuasinya, sementara seluruh kategori produk memakai
``property_valuation = real_time`` + ``cost_method = fifo``. Jadi akunnya memang
akan dipakai begitu diisi -- dan selama kosong, opname pertama akan gagal atau
mendarat di akun bawaan.

Akun ``7218000001 Inventory write-off`` (expense) sudah ada di chart.

**Catatan penting:** ini hanya mengatur ke mana selisihnya dibukukan. Tidak ada
selisih opname yang dibuat oleh skrip ini, dan tidak ada opname yang pernah
dijalankan di DB ini (nol ``stock.move`` ber-``is_inventory`` sepanjang 2026).
"""

import os

CONFIRM = os.environ.get("CONFIRM", "0") == "1"
ACCOUNT_CODE = os.environ.get("ACCOUNT_CODE", "7218000001")

company = env["res.company"].search([], order="id", limit=1)
account = env["account.account"].with_company(company).search([("code", "=", ACCOUNT_CODE)], limit=1)
locations = env["stock.location"].search([("usage", "=", "inventory")])

print("=" * 74)
print("Akun selisih stock opname   --   %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 74)
print("Company : %s" % company.display_name)
print("Akun    : %s" % (account.display_name if account else "TIDAK DITEMUKAN — batal"))

if not account:
    print("\nAkun %s tidak ada di chart company ini." % ACCOUNT_CODE)
else:
    print("\nLokasi ber-usage 'inventory': %s" % len(locations))
    todo = env["stock.location"].browse()
    for location in locations:
        current = location.valuation_account_id
        mark = (
            "sudah sesuai" if current == account else ("kosong" if not current else "BEDA: %s" % current.display_name)
        )
        print("  [%s] %-26s %s" % (location.id, location.complete_name, mark))
        if current != account:
            todo |= location

    print("\nAkan diisi/diubah: %s lokasi." % len(todo))

    # Apakah akunnya memang akan terpakai? Valuasi otomatis atau tidak.
    categories = env["product.category"].with_company(company).search([])
    real_time = categories.filtered(lambda c: c.property_valuation == "real_time")
    print("Kategori produk ber-valuasi real_time: %s dari %s" % (len(real_time), len(categories)))
    if not real_time:
        print("  *** Tidak ada kategori ber-valuasi otomatis: akun ini tidak akan pernah dipakai.")

    inventory_moves = env["stock.move"].search_count([("is_inventory", "=", True)])
    print("Stock move ber-is_inventory yang sudah ada: %s" % inventory_moves)

    if not todo:
        print("\nTidak ada yang perlu diubah.")
    elif CONFIRM:
        todo.valuation_account_id = account.id
        env.cr.commit()
        env.invalidate_all()
        print("\n  DIISI dan di-commit.")
        for location in env["stock.location"].browse(todo.ids):
            print(
                "    [%s] %s -> %s" % (location.id, location.complete_name, location.valuation_account_id.display_name)
            )
    else:
        print("\n  DRY RUN -- tidak ada yang diubah. Jalankan dengan CONFIRM=1.")
        env.cr.rollback()
