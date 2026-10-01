# -*- coding: utf-8 -*-
"""Buang baris ``levis.cogs.charge`` yang jurnalnya sudah tidak ada.

DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i odoo19-platform-odoo \\
    odoo shell -d prd_levis_begbal --no-http --max-cron-threads=0 \\
    --shell-interface=python < scripts/tenants/levis/128_purge_orphan_cogs_charges.py

--------------------------------------------------------------------------
Kenapa skrip ini ada
--------------------------------------------------------------------------
``levis.cogs.charge`` adalah satu-satunya yang menjaga satu unit tidak
dibebankan dua kali: ``levis.cogs.run._detail()`` menguranginya sebelum
mengusulkan apa pun. Tapi ``move_id``-nya ``ondelete="set null"`` — menghapus
jurnalnya membuang penunjuknya, BUKAN barisnya. Baris yatim itu tetap berkata
"unit ini sudah dibebankan" padahal di GL tidak ada apa-apa, dan unitnya hilang
dari COGS selamanya.

30-Sep-2026 di ``prd_levis_begbal`` itu bukan teori: run September di-generate
pukul 06:25 (6.962 baris, 15.579 unit, Rp 5.432.744.040,88), lalu run dan
jurnalnya dihapus. Ledger-nya selamat, jurnalnya tidak — dan compute ulang
September sejak itu menghasilkan Rp 0.

Skrip ini membuang baris yang jurnalnya HILANG atau BATAL. Baris yang jurnalnya
masih ada tapi masih draft TIDAK disentuh: itu bukan yatim, itu antrian posting.

Sesudah 19.0.1.64.0 skrip ini cuma pembersih riwayat — ``_detail()`` sendiri
sudah berhenti menghitung baris yang jurnalnya tidak hidup, dan
``account.move.unlink()`` membersihkan ledger-nya ikut jurnal.
"""

import os
from collections import defaultdict

CONFIRM = os.environ.get("CONFIRM", "0") == "1"

Charge = env["levis.cogs.charge"]
Run = env["levis.cogs.run"]
Catchup = env["levis.cogs.catchup"]
rp = lambda amount: "{:>18,.2f}".format(amount)  # noqa: E731

print("=" * 78)
print("128 — baris ledger COGS tanpa jurnal hidup   %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 78)

# ---------------------------------------------------------------- inventarisasi
buckets = {"hilang": Charge, "batal": Charge, "draft": Charge, "posted": Charge}
for charge in Charge.search([]):
    move = charge.move_id
    if not move:
        buckets["hilang"] |= charge
    elif move.state == "cancel":
        buckets["batal"] |= charge
    elif move.state == "draft":
        buckets["draft"] |= charge
    else:
        buckets["posted"] |= charge


def ringkas(label, records):
    if not records:
        print("  %-8s -" % label)
        return
    per_period = defaultdict(lambda: [0, 0.0, 0.0])
    for charge in records:
        row = per_period[(charge.period_date, charge.source)]
        row[0] += 1
        row[1] += charge.quantity
        row[2] += charge.amount
    for (period, source), (rows, qty, amount) in sorted(per_period.items()):
        print("  %-8s %s %-8s %6d baris %9.1f unit %s" % (label, period, source, rows, qty, rp(amount)))


print("\nLedger per status jurnalnya:")
for label in ("posted", "draft", "batal", "hilang"):
    ringkas(label, buckets[label])

orphan = buckets["hilang"] | buckets["batal"]
if not orphan:
    print("\nTidak ada baris yatim. Tidak ada yang perlu dikerjakan.")
else:
    print(
        "\nYatim: %d baris, %.1f unit, %s"
        % (len(orphan), sum(orphan.mapped("quantity")), rp(sum(orphan.mapped("amount"))))
    )

# ------------------------------------------------- run/catchup yang ikut yatim
stale_runs = Run.search([("state", "=", "generated"), ("move_id", "=", False)])
if stale_runs:
    print("\nRun 'generated' yang jurnalnya hilang (akan dikembalikan ke 'computed'):")
    for run in stale_runs:
        print("  %s  %s..%s  %s" % (run.name, run.date_from, run.date_to, rp(run.total_cogs)))

stale_catchups = Catchup.search([("move_id", "=", False)])
if stale_catchups:
    print("\nCatch-up yang jurnalnya hilang (akan dihapus, barisnya ikut):")
    for catchup in stale_catchups:
        print("  %s  %s  %s" % (catchup.name, catchup.book_date, rp(catchup.total_cogs)))

# -------------------------------------------------------- dampak ke usulan run
print("\nDampak ke usulan COGS periodik (setelah pembersihan):")
company = env["res.company"].search([], order="id", limit=1)
per_period = defaultdict(lambda: [0.0, 0.0])
for charge in orphan:
    row = per_period[charge.period_date]
    row[0] += charge.quantity
    row[1] += charge.amount
for period, (qty, amount) in sorted(per_period.items()):
    print("  %s kembali bisa diusulkan: %9.1f unit, %s (basis harga saat itu)" % (period, qty, rp(amount)))
if not per_period:
    print("  (tidak ada)")

# ------------------------------------------------------------ jurnal yang draft
print("\nJurnal COGS yang masih draft — ini ANTRIAN POSTING, bukan yatim:")
draft_moves = buckets["draft"].mapped("move_id")
for move in draft_moves.sorted("date"):
    rows = buckets["draft"].filtered(lambda c, m=move: c.move_id == m)
    print(
        "  %-20s %s %s  (%d baris ledger, %.1f unit)"
        % (move.name or "/", move.date, rp(sum(move.line_ids.mapped("debit"))), len(rows), sum(rows.mapped("quantity")))
    )
if not draft_moves:
    print("  (tidak ada)")

# --------------------------------------------------------------------- eksekusi
if not CONFIRM:
    print("\nDRY RUN — tidak ada yang diubah. Jalankan ulang dengan CONFIRM=1 untuk menerapkan.")
else:
    n_orphan = len(orphan)
    orphan.unlink()
    n_runs = len(stale_runs)
    stale_runs.write({"state": "computed"})
    n_catchups = len(stale_catchups)
    stale_catchups.unlink()
    env.cr.commit()
    print(
        "\nDITERAPKAN: %d baris ledger dihapus, %d run dikembalikan ke 'computed', %d catch-up dihapus."
        % (n_orphan, n_runs, n_catchups)
    )
    print("Langkah berikutnya: compute ulang run bulan yang terdampak, periksa angkanya, baru generate.")
