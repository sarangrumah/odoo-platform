# -*- coding: utf-8 -*-
"""Cocokkan jurnal koreksi PPN dengan penerimaan GR/IR pasangannya.

Kelompok A pada berkas serah-terima GR/IR. DRY RUN kecuali ``CONFIRM=1``.

  docker exec -i -e CONFIRM=1 -e OUT=/tmp/Match_PPN.xlsx \\
    odoo19-platform-odoo odoo shell -d prd_levis_begbal \\
    --no-http --max-cron-threads=0 --shell-interface=python \\
    < scripts/tenants/levis/115_grir_match_ppn_correction.py

Dijalankan lewat ``odoo shell`` (butuh ``env``). Perhatikan ``docker exec -e``,
bukan env var di shell host: skrip ini dialirkan lewat stdin ke proses di dalam
container, jadi yang dibaca ``os.environ`` adalah environment container itu.

--------------------------------------------------------------------------
Kenapa skrip 114 tidak bisa melakukannya
--------------------------------------------------------------------------
114 melakukan netting per ``purchase_line_id``. Yang tersisa sesudahnya adalah
202 jurnal **STJ bertipe ``entry``** berbunyi "Koreksi PPN Masukan atas GR
<nomor>" -- bukan vendor bill, dan barisnya **tidak punya ``purchase_line_id``
sama sekali**, sehingga tak pernah jadi kandidat di sana.

Pasangannya tetap ada, hanya kuncinya lain: nomor GR tertulis di
``account_move_line.name``. Diukur di prd_levis_begbal 17-Sep-2026, ke-202
nomor itu **seluruhnya** resolve ke picking, dan kedua sisi bertemu sampai
Rp 31,77 -- 201 dari 202 keranjang seimbang di bawah Rp 1, yang terburuk
meleset Rp 1,00.

Bentuknya 1:n -- satu baris koreksi melawan sampai 39 baris kredit GR milik
picking yang sama. Jadi pengelompokannya per (akun, picking), bukan per baris.

--------------------------------------------------------------------------
Jangan salah alarm: ratusan baris tetap bertanda terbuka
--------------------------------------------------------------------------
Odoo baru mencentang ``reconciled`` saat residual sebuah baris **tepat nol**.
Keranjang di sini bertemu sampai sen, bukan sampai nol mutlak, jadi kedua
sisinya tetap bertanda terbuka dengan residual sub-rupiah. Di gladi klon,
7.226 baris turun jadi 3.173 -- tetapi 481 di antaranya debu senilai total
Rp -46,90, dan sisanya yang 2.689 adalah penerimaan September yang memang
belum ditagih. Ukur keberhasilannya dari **netto residual per akun yang tidak
bergerak**, bukan dari jumlah baris yang tersisa.

--------------------------------------------------------------------------
Yang TIDAK disentuh
--------------------------------------------------------------------------
* **Penerimaan September yang belum ditagih** (kelompok B, Rp 4,28 M). Sudah
  diperiksa satu per satu: tak ada bill untuk baris PO-nya, posted maupun
  draft. Skrip ini hanya menjangkau picking yang namanya disebut sebuah jurnal
  koreksi, jadi tidak mungkin menyentuhnya.
* Baris yang punya ``purchase_line_id`` -- itu wilayah 114.
* Baris yang sudah terekonsiliasi.
"""

import os
import re

CONFIRM = os.environ.get("CONFIRM", "0") == "1"
CHUNK = int(os.environ.get("CHUNK", "50"))
OUT = os.environ.get("OUT", "/tmp/Match_PPN.xlsx")

# "Koreksi PPN Masukan atas GR 14701/IN/00015"
GR_IN_NAME = re.compile(r"atas GR ([A-Za-z0-9/._-]+)")

company = env["res.company"].search([], order="id", limit=1)
AML = env["account.move.line"]
Partial = env["account.partial.reconcile"]


def grir_accounts():
    """Akun GR/IR yang benar-benar membawa baris terbuka."""
    accounts = env["account.account"].browse()
    lines = AML.search(
        [
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("account_id.reconcile", "=", True),
            ("company_id", "=", company.id),
        ]
    )
    for account in lines.account_id:
        if (account.with_company(company).code or "").startswith("21031091"):
            accounts |= account
    return accounts


def snapshot(accounts):
    """(jumlah baris terbuka, netto residual) per akun -- bukti sebelum/sesudah."""
    out = {}
    for account in accounts:
        lines = AML.search(
            [("account_id", "=", account.id), ("parent_state", "=", "posted"), ("reconciled", "=", False)]
        )
        out[account.id] = (len(lines), sum(lines.mapped("amount_residual")))
    return out


accounts = grir_accounts()
before = snapshot(accounts)
print("=" * 78)
print("Cocokkan koreksi PPN <-> GR — %s" % ("APPLY" if CONFIRM else "DRY RUN"))
print("=" * 78)
for account in accounts:
    count, residual = before[account.id]
    print("  %-12s %7d baris terbuka   netto %18.2f" % (account.with_company(company).code, count, residual))

# --- sisi debit: jurnal koreksi yang menyebut sebuah nomor GR -------------
corrections = AML.search(
    [
        ("account_id", "in", accounts.ids),
        ("parent_state", "=", "posted"),
        ("reconciled", "=", False),
        ("purchase_line_id", "=", False),
        ("debit", ">", 0),
    ]
)
buckets = {}
unparsed = []
for line in corrections:
    found = GR_IN_NAME.search(line.name or "")
    if not found:
        unparsed.append(line)
        continue
    buckets.setdefault((line.account_id.id, found.group(1)), {"debit": AML, "credit": AML})["debit"] |= line

print(
    "\n  Baris koreksi: %d menyebut nomor GR, %d tidak (dilewati)."
    % (sum(len(b["debit"]) for b in buckets.values()), len(unparsed))
)

# --- sisi kredit: kaki GR/IR milik picking yang namanya disebut -----------
names = sorted({name for _, name in buckets})
pickings = env["stock.picking"].search([("name", "in", names)])
by_name = {picking.name: picking for picking in pickings}
moves = env["stock.move"].search([("picking_id", "in", pickings.ids)])
refs_by_picking = {}
for move in moves:
    refs_by_picking.setdefault(move.picking_id.id, []).append("GR-VAL:%d" % move.id)

all_refs = [ref for refs in refs_by_picking.values() for ref in refs]
credits = AML.search(
    [
        ("account_id", "in", accounts.ids),
        ("parent_state", "=", "posted"),
        ("reconciled", "=", False),
        ("credit", ">", 0),
        ("ref", "in", all_refs),
    ]
)
credit_by_ref = {}
for line in credits:
    credit_by_ref.setdefault((line.account_id.id, line.ref), AML)
    credit_by_ref[(line.account_id.id, line.ref)] |= line

missing = []
for key, bucket in buckets.items():
    account_id, name = key
    picking = by_name.get(name)
    if not picking:
        missing.append((name, "picking tidak ditemukan"))
        continue
    for ref in refs_by_picking.get(picking.id, []):
        bucket["credit"] |= credit_by_ref.get((account_id, ref), AML)
    if not bucket["credit"]:
        missing.append((name, "tidak ada kaki GR terbuka"))

ready = {key: b for key, b in buckets.items() if b["credit"]}
print(
    "  Keranjang: %d siap (%d baris debit, %d baris kredit), %d tanpa pasangan."
    % (
        len(ready),
        sum(len(b["debit"]) for b in ready.values()),
        sum(len(b["credit"]) for b in ready.values()),
        len(missing),
    )
)
for name, why in missing[:10]:
    print("    - %s: %s" % (name, why))

if not CONFIRM:
    total = sum(sum(b["debit"].mapped("amount_residual")) for b in ready.values())
    offset = sum(sum(b["credit"].mapped("amount_residual")) for b in ready.values())
    print("\n  Debit %.2f  vs  kredit %.2f  ->  selisih %.2f" % (total, offset, total + offset))
    print("\n  DRY RUN — tidak ada yang ditulis.")
    print("  Tambahkan -e CONFIRM=1 pada docker exec untuk menerapkan.")
else:
    # Rollback berarti menghapus partial-nya, bukan full-nya -- lihat skrip 114.
    partial_high_water = Partial.search([], order="id desc", limit=1).id or 0
    done = failed = 0
    per_bucket = []
    keys = sorted(ready)
    for index in range(0, len(keys), CHUNK):
        for key in keys[index : index + CHUNK]:
            bucket = ready[key]
            debit_before = sum(bucket["debit"].mapped("amount_residual"))
            credit_before = sum(bucket["credit"].mapped("amount_residual"))
            try:
                (bucket["debit"] | bucket["credit"]).reconcile()
            except Exception as exc:  # noqa: BLE001 — satu keranjang gagal tidak menghentikan sisanya
                failed += 1
                per_bucket.append(
                    (
                        key[1],
                        len(bucket["debit"]),
                        len(bucket["credit"]),
                        debit_before,
                        credit_before,
                        -1.0,
                        str(exc)[:70],
                    )
                )
                continue
            left = sum((bucket["debit"] | bucket["credit"]).mapped("amount_residual"))
            done += 1
            per_bucket.append(
                (key[1], len(bucket["debit"]), len(bucket["credit"]), debit_before, credit_before, left, "")
            )
        env.cr.commit()
        print("    ... %d/%d keranjang" % (min(index + CHUNK, len(keys)), len(keys)))

    new_partials = Partial.search([("id", ">", partial_high_water)]).ids
    after = snapshot(accounts)
    print("\n  Diproses %d keranjang (%d gagal); %d partial terbentuk." % (done, failed, len(new_partials)))
    print("\n  %-12s %22s %22s" % ("Akun", "baris sebelum->sesudah", "netto sebelum->sesudah"))
    for account in accounts:
        code = account.with_company(company).code
        count_before, residual_before = before[account.id]
        count_after, residual_after = after[account.id]
        flag = "" if abs(residual_after - residual_before) < 0.01 else "  <== NETTO BERUBAH, PERIKSA"
        print(
            "  %-12s %10d -> %-10d %.2f -> %.2f%s"
            % (code, count_before, count_after, residual_before, residual_after, flag)
        )

    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Per Keranjang"
        ws.append(["Nomor GR", "Baris debit", "Baris kredit", "Debit awal", "Kredit awal", "Sisa residual", "Catatan"])
        for row in per_bucket:
            ws.append(list(row))
        w2 = wb.create_sheet("Ringkasan")
        w2.append(["Akun", "Baris sebelum", "Baris sesudah", "Netto sebelum", "Netto sesudah"])
        for account in accounts:
            count_before, residual_before = before[account.id]
            count_after, residual_after = after[account.id]
            w2.append([account.with_company(company).code, count_before, count_after, residual_before, residual_after])
        w3 = wb.create_sheet("Rollback")
        w3.append(["Untuk membatalkan: hapus account.partial.reconcile di bawah ini."])
        w3.append(["Menghapus full_reconcile saja TIDAK cukup -- uangnya tetap ter-match."])
        w3.append([])
        w3.append(["account.partial.reconcile"])
        for partial_id in new_partials:
            w3.append([partial_id])
        wb.save(OUT)
        print("\n  Laporan: %s" % OUT)
    except Exception as exc:  # noqa: BLE001
        print("\n  (laporan xlsx gagal: %s)" % str(exc)[:70])
