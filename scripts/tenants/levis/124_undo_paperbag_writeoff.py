# -*- coding: utf-8 -*-
"""Kembalikan stok paper bag yang ter-write-off saat Track Inventory dinyalakan.

Lanjutan sheet baris #65. DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python < scripts/tenants/levis/124_undo_paperbag_writeoff.py

--------------------------------------------------------------------------
Apa yang terjadi
--------------------------------------------------------------------------
Menyalakan ``is_storable`` pada BGNM0003/0004/0005 (skrip 119) membuat Odoo
langsung merekonsiliasi on-hand-nya: ia membuat tiga ``stock.move``
ber-``is_inventory`` dari ``EBR/Stock`` ke lokasi virtual ``Inventory
adjustment``, **memindahkan seluruh 48.500 unit keluar dari stok**.

Itu salah, dan ini sebabnya penting:

* Barangnya **diterima 07-Sep-2026** (3 receipt move, 48.500 unit,
  Rp 141.758.647) dan **sudah di-bill 09-Sep** lewat
  ``BILL/T/EBR/2026/09/00001``, yang mendebit GR/IR 2103109124 sebesar nilai
  yang sama. Jadi persediaannya **memang terkapitalisasi di GL**.
* Write-off itu **tidak membuat jurnal apa pun** -- lokasi "Inventory
  adjustment" belum punya ``valuation_account_id`` (itu sheet #71, skrip 123).

Akibatnya buku stok berkata NOL sementara GL berkata Rp 141.758.647. Skrip ini
mengembalikan kuantitasnya sehingga keduanya sepakat lagi.

--------------------------------------------------------------------------
Kenapa aman
--------------------------------------------------------------------------
Pembalikannya juga **netral terhadap GL**, dengan alasan yang sama: selama
lokasi adjustment belum punya akun valuasi, tidak ada jurnal yang terbentuk ke
arah mana pun. Jalankan skrip ini SEBELUM skrip 123.

Kuantitas yang dikembalikan diambil dari penerimaannya sendiri, bukan diketik.
Berapa yang sebenarnya masih ada secara fisik adalah pertanyaan stock opname --
skrip ini hanya memulihkan keadaan sebelum perubahan, tidak mengarang saldo.
"""

import os

CONFIRM = os.environ.get("CONFIRM", "0") == "1"
CODES = [c.strip() for c in os.environ.get("CODES", "BGNM0003,BGNM0004,BGNM0005").split(",") if c.strip()]

company = env["res.company"].search([], order="id", limit=1)
Quant = env["stock.quant"]
products = env["product.product"].with_company(company).search([("default_code", "in", CODES)])

print("=" * 76)
print("Pulihkan stok paper bag   --   %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 76)

adjustment = env["stock.location"].search([("usage", "=", "inventory")], limit=1)
if adjustment.valuation_account_id:
    print(
        "\n*** BERHENTI: lokasi '%s' sudah punya akun valuasi (%s).\n"
        "    Pembalikan tidak lagi netral terhadap GL. Tinjau manual."
        % (adjustment.complete_name, adjustment.valuation_account_id.display_name)
    )
else:
    moves = env["stock.move"].search(
        [
            ("is_inventory", "=", True),
            ("product_id", "in", products.ids),
            ("state", "=", "done"),
        ]
    )
    print("\nInventory move yang ditemukan: %s" % len(moves))
    plan = {}
    for move in moves:
        # Hanya yang MENGELUARKAN stok (internal -> inventory) yang dipulihkan.
        if move.location_id.usage != "internal" or move.location_dest_id.usage != "inventory":
            continue
        key = (move.product_id, move.location_id)
        plan[key] = plan.get(key, 0.0) + move.quantity

    print("\n%-14s %-24s %12s %12s %12s" % ("SKU", "Lokasi", "On-hand kini", "Dipulihkan", "Menjadi"))
    for (product, location), qty in sorted(plan.items(), key=lambda kv: kv[0][0].default_code or ""):
        current = sum(
            Quant.search([("product_id", "=", product.id), ("location_id", "=", location.id)]).mapped("quantity")
        )
        print(
            "%-14s %-24s %12s %12s %12s"
            % (product.default_code, location.complete_name[:24], current, qty, current + qty)
        )

    print("\nJurnal yang akan terbentuk: TIDAK ADA (lokasi adjustment tanpa akun valuasi).")

    if not plan:
        print("\nTidak ada yang perlu dipulihkan.")
    elif CONFIRM:
        for (product, location), qty in plan.items():
            quant = Quant.with_context(inventory_mode=True).search(
                [("product_id", "=", product.id), ("location_id", "=", location.id)], limit=1
            )
            if not quant:
                quant = Quant.with_context(inventory_mode=True).create(
                    {"product_id": product.id, "location_id": location.id}
                )
            quant = quant.with_context(inventory_mode=True)
            quant.inventory_quantity = quant.quantity + qty
            quant.action_apply_inventory()
        env.cr.commit()
        env.invalidate_all()
        print("\n  DIPULIHKAN dan di-commit.")
        for product in products:
            on_hand = sum(
                Quant.search([("product_id", "=", product.id), ("location_id.usage", "=", "internal")]).mapped(
                    "quantity"
                )
            )
            print("    %-14s on-hand internal = %s" % (product.default_code, on_hand))
    else:
        print("\n  DRY RUN -- tidak ada yang diubah. Jalankan dengan CONFIRM=1.")
        env.cr.rollback()
