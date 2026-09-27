# -*- coding: utf-8 -*-
"""Seed the cash-deposit store rules derived from deposits already mapped by hand.

Run through ``odoo shell``. Idempotent: a rule whose key already resolves to the
same store is left alone, and one that resolves to a *different* store is
reported and skipped rather than rewritten -- Finance's own mapping outranks
anything derived from it.

    docker exec -i odoo19-platform-odoo odoo shell -d <db> --no-http \
        --max-cron-threads=0 < scripts/tenants/levis/80_load_cash_deposit_rules.py

Set ``CASH_RULES_APPLY=1`` to write; without it the script only reports.
``CASH_RULES_CSV`` points at the rules file (default: ``cash_deposit_ou_rules.csv``
in the working directory).

The rows come from ``cash_deposit_ou_rules.csv``, which was produced by reading
785 deposits Finance had already attributed and keeping only the signals that
resolved to exactly one store. Nothing in it is invented: ``bukti_baris`` is how
many historical deposits support the row.
"""

import csv
import os
import pathlib

APPLY = os.environ.get("CASH_RULES_APPLY") == "1"

# ``odoo shell`` execs this file rather than importing it, so there is no
# ``__file__`` to locate the CSV from. The path is an input, not a guess.
CSV = pathlib.Path(os.environ.get("CASH_RULES_CSV") or "cash_deposit_ou_rules.csv")
if not CSV.exists():
    raise SystemExit(
        f"{CSV} not found. Copy cash_deposit_ou_rules.csv next to where you run "
        "odoo shell, or set CASH_RULES_CSV to its full path."
    )

Map = env["levis.bank.mid.map"].sudo()
Analytic = env["account.analytic.account"].sudo()
company = env.company

created = skipped = conflict = 0
rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
print(f"{len(rows)} usulan dibaca dari {CSV}")

for row in rows:
    key = (row["key"] or "").strip()
    store = (row["operating_unit"] or "").strip()
    kind = "terminal" if row["match_type"] == "terminal" else "keyword"
    if not key or not store:
        continue
    ou = Analytic.search([("name", "=", store), ("company_id", "in", (company.id, False))], limit=1)
    if not ou:
        print(f"  LEWAT  {kind:9} {key:12} -> Operating Unit '{store}' tidak ada di database ini")
        skipped += 1
        continue
    existing = Map.search([("company_id", "=", company.id), ("match_type", "=", kind)])
    same = existing.filtered(
        lambda r, k=key, t=kind: (
            Map._normalise_terminal(r.key) == Map._normalise_terminal(k)
            if t == "terminal"
            else Map._compact(r.key) == Map._compact(k)
        )
    )
    if same:
        if same[0].analytic_account_id != ou:
            print(
                f"  BENTROK {kind:9} {key:12} sudah dipetakan ke "
                f"'{same[0].analytic_account_id.display_name}', usulan bilang '{store}' — DILEWATI"
            )
            conflict += 1
        else:
            skipped += 1
        continue
    if APPLY:
        Map.create(
            {
                "name": f"Setoran tunai — {store}",
                "match_type": kind,
                "key": key,
                "analytic_account_id": ou.id,
                "company_id": company.id,
                "channel": "cash",
                "sequence": 20,
                "note": f"Diturunkan dari {row['bukti_baris']} setoran yang sudah dipetakan manual. {row.get('catatan') or ''}".strip(),
            }
        )
    created += 1
    print(f"  {'BUAT' if APPLY else 'AKAN BUAT'}  {kind:9} {key:12} -> {store}")

print(f"\nbaru {created} | sudah ada {skipped} | bentrok {conflict}")
if APPLY:
    env.cr.commit()
    print("disimpan.")
else:
    print("DRY RUN — set CASH_RULES_APPLY=1 untuk menyimpan.")
