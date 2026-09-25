# -*- coding: utf-8 -*-
"""Akui jurnal COGS yang dibuat TANGAN di dalam ledger ``levis.cogs.charge``.

Prasyarat sebelum COGS catch-up boleh berjalan otomatis (autopost / cron).
DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python < scripts/tenants/levis/126_seed_cogs_charge_manual.py

--------------------------------------------------------------------------
Kenapa skrip ini ada
--------------------------------------------------------------------------
``levis.cogs.charge`` adalah SATU-SATUNYA yang menjaga satu unit tidak
dibebankan dua kali. Jurnal yang dibuat tangan tidak meninggalkan baris di sana,
jadi catch-up menganggap unitnya belum pernah dibebankan.

Per 25-Sep-2026 di ``prd_levis_begbal`` itu bukan teori:

* FA membukukan ``GLJV/2026/08/0021`` (31-Agu, **Rp 531.048.759**, ref "Cost of
  Goods Sold Agustus 2026 (Issue Item Terjual Tanpa PO)") atas 904 unit yang saat
  run Agustus masih ber-COGS 0.
* Catch-up kemudian membebankan **Rp 528.443.941 (897 unit)** untuk BULAN
  PENJUALAN Agustus ke empat jurnal draft September.
* Selisihnya, Rp 2.604.639, tepat = 7 unit RIBCAGE yang tak pernah punya PO.

Selama draft itu belum diposting, kerugiannya nol. Begitu posting dijalankan
otomatis, Agustus dobel dan periodenya sudah terkunci.

--------------------------------------------------------------------------
Yang dilakukan
--------------------------------------------------------------------------
Bagian A -- untuk setiap bulan penjualan yang sudah dibukukan tangan:
  baris charge ``catchup`` bulan itu dipindahkan ke jurnal manualnya
  (``source='manual'``), dan porsi bulan itu dikeluarkan dari jurnal draft
  catch-up. Ledger tetap menyatakan unitnya SUDAH dibebankan -- jadi catch-up,
  run bulanan maupun session COGS tidak akan menyentuhnya lagi.

Bagian B -- item yang tak pernah punya PO (``NOPO_CODES``): ``standard_price``
  diisi dari harga PO ukuran lain style yang sama, dan bulan yang sudah
  dibukukan tangan (``NOPO_MONTHS``) di-seed sebagai charge ``manual``.
  Bulan yang belum dibukukan sengaja DIBIARKAN -- itu bagian catch-up.

Skrip menolak jalan kalau jurnal manualnya tidak posted, atau kalau porsi bulan
itu sudah ikut terposting di jurnal catch-up (artinya dobelnya sudah terjadi dan
butuh keputusan akuntansi, bukan skrip).
"""

import os
from datetime import date

CONFIRM = os.environ.get("CONFIRM", "0") == "1"
# Bulan penjualan yang sudah dibukukan tangan -> ref jurnalnya (substring).
MANUAL = os.environ.get("MANUAL", "2026-08:Issue Item Terjual Tanpa PO")
NOPO_CODES = [
    c.strip() for c in os.environ.get("NOPO_CODES", "005DS0005026,005DS0005027,005DS0005028").split(",") if c.strip()
]
NOPO_PRICE = float(os.environ.get("NOPO_PRICE", "372081.9825"))
NOPO_MONTHS = [m.strip() for m in os.environ.get("NOPO_MONTHS", "2026-07,2026-08").split(",") if m.strip()]
TOLERANCE = float(os.environ.get("TOLERANCE", "0.02"))  # 2 % antara manual dan catch-up

Charge = env["levis.cogs.charge"]
Move = env["account.move"]
company = env["res.company"].search([], order="id", limit=1)
rp = lambda amount: "{:>18,.2f}".format(amount)  # noqa: E731


def month_start(text):
    year, month = (int(part) for part in text.split("-")[:2])
    return date(year, month, 1)


print("=" * 78)
print("Seed levis.cogs.charge untuk jurnal COGS manual   --   %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 78)
print("Company: %s" % company.display_name)

stop = []

# ---------------------------------------------------------------- bagian A
for spec in [s for s in MANUAL.split(",") if s.strip()]:
    period_text, _, ref_part = spec.partition(":")
    period = month_start(period_text)
    manual = Move.search(
        [
            ("company_id", "=", company.id),
            ("ref", "ilike", ref_part.strip()),
            ("date", ">=", period),
            ("date", "<=", Charge._month_end(period)),
        ]
    )
    charges = Charge.search([("company_id", "=", company.id), ("period_date", "=", period), ("source", "=", "catchup")])
    print("\n" + "-" * 78)
    print("A. Bulan penjualan %s" % period.strftime("%m/%Y"))
    print("-" * 78)
    if not manual:
        print("  Tidak ada jurnal manual dengan ref ~ %r di bulan itu -- dilewati." % ref_part.strip())
        continue
    if len(manual) > 1:
        stop.append("Lebih dari satu jurnal manual cocok untuk %s: %s" % (period_text, manual.mapped("name")))
        continue
    if manual.state != "posted":
        stop.append("Jurnal manual %s belum posted." % manual.name)
        continue
    manual_total = sum(manual.line_ids.mapped("debit"))
    print("  Jurnal manual  : %s  %s  %s" % (manual.name, manual.date, rp(manual_total)))
    if not charges:
        print("  Catch-up belum pernah membebankan bulan ini -- tidak ada yang dipindahkan.")
        continue

    posted_moves = charges.mapped("move_id").filtered(lambda m: m.state == "posted")
    if posted_moves:
        stop.append(
            "Porsi %s sudah TERPOSTING di %s -- dobelnya sudah terjadi, butuh keputusan akuntansi."
            % (period_text, ", ".join(posted_moves.mapped("name") or [str(posted_moves.ids)]))
        )
        continue

    catchup_total = sum(charges.mapped("amount"))
    print(
        "  Catch-up bulan : %s baris, %s unit, %s" % (len(charges), sum(charges.mapped("quantity")), rp(catchup_total))
    )
    print("  Selisih        : %s" % rp(manual_total - catchup_total))
    if manual_total and abs(manual_total - catchup_total) / manual_total > TOLERANCE:
        stop.append(
            "Selisih manual vs catch-up %s melebihi %.0f%% -- populasinya mungkin BEDA, periksa dulu."
            % (period_text, TOLERANCE * 100)
        )
        continue

    print("\n  Per Operating Unit (manual vs catch-up):")
    per_ou = {}
    for line in manual.line_ids.filtered(lambda line: line.debit):
        for key in line.analytic_distribution or {}:
            for part in str(key).split(","):
                per_ou.setdefault(int(part), [0.0, 0.0])[0] += line.debit
    for charge in charges:
        ou = charge.warehouse_id.l10n_ou_analytic_id
        per_ou.setdefault(ou.id, [0.0, 0.0])[1] += charge.amount
    for ou_id, (manual_amount, catchup_amount) in sorted(per_ou.items(), key=lambda item: -item[1][0]):
        ou = env["account.analytic.account"].browse(ou_id)
        gap = abs(manual_amount - catchup_amount)
        # Puluhan rupiah = pembulatan ratusan baris, bukan populasi yang beda.
        flag = "" if gap < 1.0 else ("   (pembulatan)" if gap < 1000.0 else "   <-- BEDA, periksa")
        print("    %-38s %s %s%s" % (ou.name or ou_id, rp(manual_amount), rp(catchup_amount), flag))

    label = "COGS catch-up %s" % period.strftime("%m/%Y")
    drafts = charges.mapped("catchup_id")
    print("\n  Draft yang dipangkas:")
    for catchup in drafts:
        drop_lines = catchup.line_ids.filtered(lambda line: line.period_date == period)
        drop_move = catchup.move_id.line_ids.filtered(lambda line: (line.name or "").startswith(label))
        keep = sum((catchup.move_id.line_ids - drop_move).filtered(lambda line: line.debit).mapped("debit"))
        print(
            "    %-18s %s  buang %s baris jurnal (%s), sisa %s"
            % (
                catchup.name,
                catchup.book_date,
                len(drop_move),
                rp(sum(drop_move.filtered(lambda line: line.debit).mapped("debit"))),
                rp(keep),
            )
        )
        if CONFIRM:
            drop_move.unlink()
            drop_lines.unlink()

    if CONFIRM:
        charges.write({"source": "manual", "move_id": manual.id, "catchup_id": False})
        for catchup in drafts:
            if not catchup.move_id.line_ids:
                catchup.move_id.unlink()

# ---------------------------------------------------------------- bagian B
print("\n" + "-" * 78)
print("B. Item tanpa PO: %s" % ", ".join(NOPO_CODES))
print("-" * 78)
products = env["product.product"].with_company(company).search([("default_code", "in", NOPO_CODES)])
missing = set(NOPO_CODES) - set(products.mapped("default_code"))
if missing:
    print("  Tidak ditemukan: %s" % ", ".join(sorted(missing)))
for product in products:
    print("  %-16s standard_price %s -> %s" % (product.default_code, rp(product.standard_price), rp(NOPO_PRICE)))

warehouses = env["stock.warehouse"].search([("company_id", "=", company.id)])
seeded = 0
for period_text in NOPO_MONTHS:
    period = month_start(period_text)
    for warehouse in warehouses:
        sold = Charge._sold_quantities(company, warehouse, period, Charge._month_end(period), products=products)
        charged = Charge._charged_quantities(company, warehouse, period, products=products)
        for product, qty in sold.items():
            rest = qty - charged.get(product, 0.0)
            if rest <= 0:
                continue
            amount = company.currency_id.round(rest * NOPO_PRICE)
            manual = Move.search(
                [
                    ("company_id", "=", company.id),
                    ("ref", "ilike", "Tanpa PO"),
                    ("date", ">=", period),
                    ("date", "<=", Charge._month_end(period)),
                ],
                limit=1,
            )
            print(
                "  %s  %-30s %-16s %5s unit  %s  -> %s"
                % (
                    period.strftime("%m/%Y"),
                    warehouse.name,
                    product.default_code,
                    rest,
                    rp(amount),
                    manual.name or "(tanpa jurnal manual)",
                )
            )
            seeded += 1
            if CONFIRM:
                Charge.create(
                    {
                        "company_id": company.id,
                        "product_id": product.id,
                        "warehouse_id": warehouse.id,
                        "period_date": period,
                        "quantity": rest,
                        "amount": amount,
                        "source": "manual",
                        "move_id": manual.id or False,
                    }
                )
if not seeded:
    print("  Tidak ada yang perlu di-seed (semuanya sudah ada di ledger).")

# ---------------------------------------------------------------- penutup
print("\n" + "=" * 78)
if stop:
    print("BERHENTI -- tidak ada yang diubah:")
    for reason in stop:
        print("  * %s" % reason)
    env.cr.rollback()
elif CONFIRM:
    if products:
        products.write({"standard_price": NOPO_PRICE})
    env.cr.commit()
    env.invalidate_all()
    print("DITERAPKAN dan di-commit.")
    for source in ("catchup", "run", "session", "manual"):
        rows = Charge.search([("company_id", "=", company.id), ("source", "=", source)])
        if rows:
            print(
                "  %-8s %5s baris  %8s unit  %s"
                % (source, len(rows), sum(rows.mapped("quantity")), rp(sum(rows.mapped("amount"))))
            )
else:
    print("DRY RUN -- tidak ada yang diubah. Jalankan dengan CONFIRM=1.")
    env.cr.rollback()
