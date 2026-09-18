# -*- coding: utf-8 -*-
"""Audit pemetaan Kode Objek PPh -> COA, dua sisi.

Pending Tax #7 / T17. SELECT-only -- tidak pernah menulis apa pun.

  docker exec -i -e OUT=/mnt/data_levis/Audit_Mapping_COA_PPh.xlsx \\
    odoo19-platform-odoo odoo shell -d prd_levis_begbal \\
    --no-http --max-cron-threads=0 --shell-interface=python \\
    < scripts/tenants/levis/118_audit_pph_coa_mapping.py

--------------------------------------------------------------------------
Dua sisi yang harus dibandingkan, dan kenapa
--------------------------------------------------------------------------
``tax.withholding.rule.account_id`` adalah pemetaan yang dipelihara Tim Tax per
Kode Objek. Tetapi yang menulis GL adalah mesin pajak bawaan Odoo, yang
mengambil akun dari **repartition line** milik ``account.tax`` dan sama sekali
tidak mengenal Kode Objek. Jadi ada dua sumber kebenaran yang bisa menyimpang
diam-diam.

Per 18-Sep-2026 di ``prd_levis_begbal`` keduanya **cocok untuk seluruh kode yang
dipakai**: Z1-1F -> 2104100001, tujuh kode Z5-* -> 2104100005, Z3-3I ->
2104100003. Itu kebetulan konfigurasi yang benar, bukan sesuatu yang dijamin.

Sejak `custom_tax_id` 0.9.0 ada gerbang di ``_post`` yang menolak bill bila
keduanya berbeda (`custom_tax_id.withholding_account_guard`, default 1).
Laporan ini adalah sisi manusianya: apa yang dipetakan, apa yang benar-benar
dikredit, dan berapa banyak dokumen yang terlibat.

**Cara memperbaiki bila ada yang BEDA:** arahkan repartition line milik tax itu
ke akun yang disebut rule -- BUKAN mengaktifkan jalur engine withholding, yang
akan membukukan uang yang sama dua kali (lihat T17 di plan).
"""

import os
from collections import defaultdict

OUT = os.environ.get("OUT", "/mnt/data_levis/Audit_Mapping_COA_PPh.xlsx")
DATE_FROM = os.environ.get("DATE_FROM", "2026-01-01")

company = env["res.company"].search([], order="id", limit=1)
Rule = env["tax.withholding.rule"]


def _code(account):
    return account.with_company(company).code if account else ""


print("=" * 78)
print("Audit pemetaan Kode Objek PPh -> COA   (company: %s)" % company.display_name)
print("=" * 78)

# --- sisi 1: apa yang dipetakan rule, dan seberapa sering kode itu dipakai ---
lines = env["account.move.line"].search(
    [
        ("company_id", "=", company.id),
        ("parent_state", "=", "posted"),
        ("move_id.move_type", "in", ("in_invoice", "in_refund")),
        ("date", ">=", DATE_FROM),
        ("x_custom_withholding_category_id", "!=", False),
    ]
)
usage = defaultdict(lambda: {"lines": 0, "moves": set(), "dpp": 0.0})
for line in lines:
    bucket = usage[line.x_custom_withholding_category_id]
    bucket["lines"] += 1
    bucket["moves"].add(line.move_id.id)
    bucket["dpp"] += line.price_subtotal

rows = []
for category, bucket in sorted(usage.items(), key=lambda kv: -kv[1]["lines"]):
    rule = Rule._rule_for_category(category, company)
    rows.append(
        {
            "code": category.code or "",
            "bupot": category.bupot_object_code or "",
            "name": category.name or "",
            "pph_kind": category.pph_kind or "",
            "rule": rule.name if rule else "(tidak ada rule aktif)",
            "rule_account": _code(rule.account_id) if rule else "",
            "lines": bucket["lines"],
            "moves": len(bucket["moves"]),
            "dpp": bucket["dpp"],
        }
    )

print("\nKode Objek yang dipakai sejak %s: %s" % (DATE_FROM, len(rows)))
print("%-8s %-12s %-10s %6s %7s  %s" % ("Kode", "Bupot", "Jenis", "Baris", "Bill", "COA rule"))
for row in rows:
    print(
        "%-8s %-12s %-10s %6s %7s  %s"
        % (row["code"], row["bupot"], row["pph_kind"], row["lines"], row["moves"], row["rule_account"])
    )

# --- sisi 2: akun yang benar-benar dikredit oleh tax native ---
tax_lines = env["account.move.line"].search(
    [
        ("company_id", "=", company.id),
        ("parent_state", "=", "posted"),
        ("move_id.move_type", "in", ("in_invoice", "in_refund")),
        ("date", ">=", DATE_FROM),
        ("tax_line_id", "!=", False),
    ]
)
actual = defaultdict(lambda: {"lines": 0, "balance": 0.0})
for line in tax_lines:
    if line.tax_line_id.amount >= 0:
        continue
    actual[(line.tax_line_id, line.account_id)]["lines"] += 1
    actual[(line.tax_line_id, line.account_id)]["balance"] += line.balance

print("\nAkun yang benar-benar dikredit mesin pajak:")
print("%-28s %-12s %6s  %s" % ("Tax", "COA", "Baris", "Saldo"))
for (tax, account), bucket in sorted(actual.items(), key=lambda kv: -kv[1]["lines"]):
    print(
        "%-28s %-12s %6s  %s"
        % (tax.name[:28], _code(account), bucket["lines"], company.currency_id.round(bucket["balance"]))
    )

# --- verdict: apakah keduanya sepakat, per bill terposting ---
print("\nMemeriksa setiap bill terposting terhadap gerbang _post ...")
moves = env["account.move"].search(
    [
        ("company_id", "=", company.id),
        ("state", "=", "posted"),
        ("move_type", "in", ("in_invoice", "in_refund")),
        ("date", ">=", DATE_FROM),
    ]
)
mismatch_rows = []
for move in moves:
    for tax_line, used, target in move._custom_withholding_account_mismatches():
        mismatch_rows.append(
            {
                "move": move.name,
                "date": move.date,
                "tax": tax_line.tax_line_id.name,
                "used": _code(used),
                "target": _code(target),
                "balance": tax_line.balance,
            }
        )
print("  Bill diperiksa: %s" % len(moves))
print("  Bill dengan akun PPh yang TIDAK sesuai mapping: %s" % len(mismatch_rows))
if not mismatch_rows:
    print("  -> Seluruh kode objek yang dipakai sudah konsisten dengan COA di rule.")
else:
    for row in mismatch_rows[:15]:
        print("     %s  %s  posting ke %s  seharusnya %s" % (row["move"], row["tax"], row["used"], row["target"]))

try:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Mapping"
    ws.append(
        ["Kode Objek", "Kode Bupot", "Nama", "Jenis PPh", "Rule", "COA di Rule", "Baris Bill", "Jumlah Bill", "DPP"]
    )
    for row in rows:
        ws.append(
            [
                row["code"],
                row["bupot"],
                row["name"],
                row["pph_kind"],
                row["rule"],
                row["rule_account"],
                row["lines"],
                row["moves"],
                row["dpp"],
            ]
        )
    w2 = wb.create_sheet("Akun Dikredit")
    w2.append(["Tax", "COA", "Baris", "Saldo"])
    for (tax, account), bucket in sorted(actual.items(), key=lambda kv: -kv[1]["lines"]):
        w2.append([tax.name, _code(account), bucket["lines"], bucket["balance"]])
    w3 = wb.create_sheet("Selisih")
    w3.append(["Bill", "Tanggal", "Tax", "Posting ke", "Seharusnya", "Saldo"])
    for row in mismatch_rows:
        w3.append([row["move"], row["date"], row["tax"], row["used"], row["target"], row["balance"]])
    if not mismatch_rows:
        w3.append(["(tidak ada selisih)", "", "", "", "", ""])
    wb.save(OUT)
    print("\nLaporan: %s" % OUT)
except Exception as exc:  # noqa: BLE001
    print("\n(laporan xlsx gagal: %s)" % str(exc)[:70])

env.cr.rollback()
