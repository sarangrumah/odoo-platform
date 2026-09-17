# -*- coding: utf-8 -*-
"""Backfill rekonsiliasi GR/IR untuk bill yang mendahului T02a.

Sheet baris #61. DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 -e OUT=/tmp/Backfill_GRIR.xlsx \\
    odoo19-platform-odoo odoo shell -d prd_levis_begbal \\
    --no-http --max-cron-threads=0 --shell-interface=python \\
    < scripts/tenants/levis/114_grir_backfill_reconcile.py

Dijalankan lewat ``odoo shell`` (butuh ``env``), bukan python biasa. Hilangkan
``-e CONFIRM=1`` untuk dry run. Perhatikan ``docker exec -e``, bukan env var di
shell host: skrip ini dialirkan lewat stdin ke proses di dalam container, jadi
yang dibaca ``os.environ`` adalah environment container itu.

--------------------------------------------------------------------------
Kenapa ini menjalankan ulang T02a, bukan FIFO sendiri
--------------------------------------------------------------------------
Sejak 17-Sep-2026 setiap vendor bill yang diposting me-netting akrual GR/IR-nya
sendiri (``account.move._levis_reconcile_grir``). Yang tertinggal hanyalah bill
yang diposting **sebelum** itu. Jadi backfill-nya adalah menjalankan hal yang
sama pada dokumen-dokumen itu -- bukan mengarang pencocokan kedua.

Itu bukan sekadar kenyamanan. Satu-satunya tautan antara kedua sisi adalah
``purchase_line_id`` pada baris bill dan ref ``GR-VAL:<stock_move_id>`` pada
jurnal penerimaan: diperiksa di prd_levis_begbal, **36.669 baris kredit GR/IR
yang belum terekonsiliasi seluruhnya ber-ref GR-VAL dan NOL di antaranya punya
``purchase_line_id``**. Menulis pencocokan kedua berarti dua definisi "kaki GR
mana milik baris bill mana", dan keduanya akan menyimpang diam-diam.

Pengelompokannya pun sudah benar dengan sendirinya: T02a merekonsiliasi per
(akun, himpunan baris PO milik satu bill), sehingga grup terbesar sebesar bill
terbesar -- bukan satu ``account.full.reconcile`` raksasa berisi 63 ribu baris,
yang akan kuadratik saat pembuatan partial dan mimpi buruk bila kelak ada
reset-to-draft.

--------------------------------------------------------------------------
Yang TIDAK disentuh
--------------------------------------------------------------------------
* **Penerimaan yang memang belum ditagih.** Per 17-Sep-2026 akun 2103109121
  memuat 2.482 baris kredit September tanpa satu pun debit, netto
  Rp 4.062.598.680. Itu posisi terbuka yang sah. Skrip ini hanya memproses
  **bill**, jadi penerimaan tanpa bill tidak pernah tersentuh -- dan memang
  tidak boleh.
* Akun AR/AP. Hanya akun yang dikenali ``_levis_grir_account()`` yang ikut.
* Baris yang sudah terekonsiliasi.
"""

import os

CONFIRM = os.environ.get("CONFIRM", "0") == "1"
CHUNK = int(os.environ.get("CHUNK", "25"))
OUT = os.environ.get("OUT", "/mnt/data_levis/Backfill_GRIR.xlsx")

company = env["res.company"].search([], order="id", limit=1)
AML = env["account.move.line"]
Move = env["account.move"]


def grir_accounts():
    """Akun GR/IR yang benar-benar membawa baris terbuka."""
    lines = AML.search(
        [
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("account_id.reconcile", "=", True),
            ("company_id", "=", company.id),
        ]
    )
    accounts = env["account.account"].browse()
    for line in lines:
        code = line.account_id.with_company(company).code or ""
        if code.startswith("21031091"):
            accounts |= line.account_id
    return accounts


def snapshot(accounts):
    """(jumlah baris terbuka, netto residual) per akun -- bukti sebelum/sesudah."""
    out = {}
    for acc in accounts:
        lines = AML.search(
            [
                ("account_id", "=", acc.id),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
            ]
        )
        out[acc.id] = (len(lines), sum(lines.mapped("amount_residual")))
    return out


accounts = grir_accounts()
before = snapshot(accounts)
print("=" * 78)
print("Backfill GR/IR — %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 78)
for acc in accounts:
    n, res = before[acc.id]
    print("  %-12s %7d baris terbuka   netto %18.2f" % (acc.with_company(company).code, n, res))

# Bill terposting yang masih memegang kaki GR/IR belum terekonsiliasi.
candidates = AML.search(
    [
        ("account_id", "in", accounts.ids),
        ("parent_state", "=", "posted"),
        ("reconciled", "=", False),
        ("purchase_line_id", "!=", False),
        ("move_id.move_type", "in", ("in_invoice", "in_refund")),
    ]
)
bills = candidates.move_id.sorted(lambda m: (m.invoice_date or m.date, m.id))
print("\n  Kandidat: %d bill memegang %d baris debit belum terekonsiliasi." % (len(bills), len(candidates)))

if not CONFIRM:
    print("\n  DRY RUN — tidak ada yang ditulis.")
    print("  Tambahkan -e CONFIRM=1 pada docker exec untuk menerapkan.")
else:
    done = failed = 0
    new_fulls = set()
    per_bill = []
    # Undoing this means deleting the partials, not the fulls: a full is just a
    # marker Odoo sets when a group's residual reaches zero, and unlinking it
    # leaves the money still matched. Every partial created from here on is
    # ours, so one high-water mark is a complete rollback list -- and it stays
    # correct even for the bills that only matched partially and so never
    # produced a full at all (on the clone, 408 bills produced just 27).
    Partial = env["account.partial.reconcile"]
    partial_high_water = Partial.search([], order="id desc", limit=1).id or 0
    for index in range(0, len(bills), CHUNK):
        chunk = bills[index : index + CHUNK]
        for move in chunk:
            legs_before = AML.search_count(
                [("move_id", "=", move.id), ("account_id", "in", accounts.ids), ("reconciled", "=", False)]
            )
            try:
                move._levis_reconcile_grir()
            except Exception as exc:  # noqa: BLE001 — satu bill gagal tidak boleh menghentikan sisanya
                failed += 1
                per_bill.append((move.name, legs_before, -1, str(exc)[:80]))
                continue
            legs_after = AML.search_count(
                [("move_id", "=", move.id), ("account_id", "in", accounts.ids), ("reconciled", "=", False)]
            )
            fulls = AML.search(
                [("move_id", "=", move.id), ("account_id", "in", accounts.ids), ("full_reconcile_id", "!=", False)]
            ).mapped("full_reconcile_id.id")
            new_fulls.update(fulls)
            done += 1
            per_bill.append((move.name, legs_before, legs_after, ""))
        env.cr.commit()
        print("    ... %d/%d bill" % (min(index + CHUNK, len(bills)), len(bills)))

    new_partials = Partial.search([("id", ">", partial_high_water)]).ids
    after = snapshot(accounts)
    print(
        "\n  Diproses %d bill (%d gagal); %d partial + %d full terbentuk."
        % (done, failed, len(new_partials), len(new_fulls))
    )
    print("\n  %-12s %18s %18s" % ("Akun", "baris sebelum", "baris sesudah"))
    for acc in accounts:
        code = acc.with_company(company).code
        nb, rb = before[acc.id]
        na, ra = after[acc.id]
        flag = "" if abs(ra - rb) < 0.01 else "  <== NETTO BERUBAH, PERIKSA"
        print("  %-12s %10d -> %-10d netto %.2f -> %.2f%s" % (code, nb, na, rb, ra, flag))

    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Per Bill"
        ws.append(["Bill", "Baris terbuka sebelum", "sesudah", "Catatan"])
        for row in per_bill:
            ws.append(list(row))
        w2 = wb.create_sheet("Ringkasan")
        w2.append(["Akun", "Baris sebelum", "Baris sesudah", "Netto sebelum", "Netto sesudah"])
        for acc in accounts:
            nb, rb = before[acc.id]
            na, ra = after[acc.id]
            w2.append([acc.with_company(company).code, nb, na, rb, ra])
        w3 = wb.create_sheet("Rollback")
        w3.append(["Untuk membatalkan: hapus account.partial.reconcile di bawah ini."])
        w3.append(["Menghapus full_reconcile saja TIDAK cukup -- uangnya tetap ter-match."])
        w3.append([])
        w3.append(["account.partial.reconcile", "account.full.reconcile (turunan)"])
        fulls = sorted(new_fulls)
        for index, pid in enumerate(new_partials):
            w3.append([pid, fulls[index] if index < len(fulls) else ""])
        wb.save(OUT)
        print("\n  Laporan: %s" % OUT)
    except Exception as exc:  # noqa: BLE001
        print("\n  (laporan xlsx gagal: %s)" % str(exc)[:70])
