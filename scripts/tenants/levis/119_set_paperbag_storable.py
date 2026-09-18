# -*- coding: utf-8 -*-
"""Nyalakan Track Inventory pada produk paper bag supaya COGS-nya terhitung.

Sheet baris #65. DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python < scripts/tenants/levis/119_set_paperbag_storable.py

--------------------------------------------------------------------------
Sebabnya, dikonfirmasi klien 18-Sep-2026
--------------------------------------------------------------------------
Klien menyatakan ini **salah input di master produk**: paper bag seharusnya
storable dan di-track inventory-nya. Karena ``is_storable = false``,
``levis.cogs.run._detail()`` melewatinya (``if not product.is_storable:
continue``) dan COGS paper bag tidak pernah terhitung sama sekali.

Perhatikan komentar di ``cogs_run.py`` menyebut paper bag sebagai contoh barang
non-persediaan. Komentar itu mengikuti konfigurasi yang keliru, bukan
sebaliknya -- setelah skrip ini dijalankan komentar itu tidak lagi benar.

--------------------------------------------------------------------------
Akibat yang harus disadari SEBELUM apply
--------------------------------------------------------------------------
1. Produk yang jadi storable akan **ikut terhitung di run COGS berikutnya**,
   termasuk untuk penjualan bulan-bulan yang sudah lewat, karena buku
   ``levis.cogs.charge`` tidak pernah memuat unit paper bag. Skrip ini
   melaporkan nilainya per bulan supaya Accounting tahu persis berapa yang akan
   muncul, dan di periode mana.
2. On-hand paper bag akan mulai dilacak dari NOL. Tidak ada saldo awal yang
   dibuat -- itu keputusan terpisah (stock opname / adjustment).
3. Hanya produk yang punya ``standard_price`` yang menghasilkan COGS. Produk
   Miscellaneous lain (GWP, patches) sengaja TIDAK disentuh: klien menyebut
   paper bag, dan barang giveaway punya perlakuan akuntansi sendiri.

Daftar produk diambil dari ``CODES`` (default: tiga SKU paper bag di
prd_levis_begbal). Tambahkan lewat env ``CODES=BGNM0003,BGNM0004``.
"""

import os
from collections import defaultdict
from datetime import date as date_cls

CONFIRM = os.environ.get("CONFIRM", "0") == "1"
CODES = [c.strip() for c in os.environ.get("CODES", "BGNM0003,BGNM0004,BGNM0005").split(",") if c.strip()]

company = env["res.company"].search([], order="id", limit=1)
Product = env["product.product"]

print("=" * 76)
print("Paper bag -> storable   --   %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 76)
print("Company: %s" % company.display_name)
print("SKU yang diminta: %s" % ", ".join(CODES))

products = Product.with_company(company).search([("default_code", "in", CODES)])
missing = set(CODES) - set(products.mapped("default_code"))
if missing:
    print("\n*** SKU tidak ditemukan: %s" % ", ".join(sorted(missing)))

if not products:
    print("\nTidak ada produk untuk diproses.")
else:
    print("\n%-14s %-38s %-8s %-10s %s" % ("SKU", "Nama", "Storable", "Cost", "Kategori"))
    for product in products:
        print(
            "%-14s %-38s %-8s %-10s %s"
            % (
                product.default_code,
                (product.name or "")[:38],
                "ya" if product.is_storable else "TIDAK",
                product.standard_price,
                product.categ_id.display_name,
            )
        )

    todo = products.filtered(lambda p: not p.is_storable)
    print("\nAkan diubah: %s dari %s produk." % (len(todo), len(products)))

    # --- berapa COGS yang akan muncul, per bulan per toko ---
    Charge = env["levis.cogs.charge"]
    warehouses = env["stock.warehouse"].search([("company_id", "=", company.id)])
    print("\nCOGS yang akan ikut terhitung (penjualan yang sudah terjadi):")
    per_month = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
    for warehouse in warehouses:
        # odoo shell does not expose ``fields``; build the window explicitly.
        for period in Charge._months_between(date_cls(2026, 1, 1), date_cls.today()):
            month_end = Charge._month_end(period)
            sold = Charge._sold_quantities(company, warehouse, period, month_end, products=products)
            for product, qty in sold.items():
                cost = product.with_company(company).standard_price
                if not cost or not qty:
                    continue
                per_month[period]["qty"] += qty
                per_month[period]["amount"] += qty * cost
    grand = 0.0
    for period in sorted(per_month):
        bucket = per_month[period]
        grand += bucket["amount"]
        print(
            "  %s  %8.0f unit  %s"
            % (period.strftime("%Y-%m"), bucket["qty"], company.currency_id.round(bucket["amount"]))
        )
    print("  %-10s %8s      %s" % ("TOTAL", "", company.currency_id.round(grand)))
    print(
        "\n  Angka itu akan muncul di run COGS berikutnya untuk bulan bersangkutan,\n"
        "  atau di periode berjalan bila bulannya sudah ditutup."
    )

    if CONFIRM:
        todo.product_tmpl_id.write({"is_storable": True})
        env.cr.commit()
        env.invalidate_all()
        print("\n  DIUBAH dan di-commit: %s produk kini storable." % len(todo))
        for product in Product.with_company(company).search([("default_code", "in", CODES)]):
            print("    %-14s storable=%s" % (product.default_code, product.is_storable))
    else:
        print("\n  DRY RUN -- tidak ada yang diubah. Jalankan dengan CONFIRM=1.")
        env.cr.rollback()
