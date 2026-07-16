"""Load the card BIN / MDR table (levis.mdr.bin) from a CSV.

Item #3 of docs/levis/CONFIG_FOLLOWUPS.md. `levis.mdr.bin` ships empty, so MDR
netting on Register Payment cannot run until Finance supplies the real table.
This is the loader for when they do -- scripts/tenants/levis/mdr_bin.csv is a
template with the expected columns.

    MDR_APPLY=1 docker exec -i odoo19-platform-odoo odoo shell -d prd_levis \
        --no-http < scripts/tenants/levis/73_load_mdr_bin.py

Idempotent -- matches on (card_scheme, bin_from, bin_to, date_start) and updates
in place, so re-running with a corrected CSV fixes rows rather than duplicating.

Validates before writing, because the model cannot:
  * BIN ranges must not overlap within the same card_scheme + validity period.
    levis.mdr.bin declares that rule via the deprecated `_sql_constraints` list,
    which Odoo 19 silently ignores -- no constraint exists in the database. If a
    payment's BIN matched two rows, which MDR applies is undefined.
  * mdr_account_id must be an expense account.
  * acquirer bank must exist, matched on Kode BI (res.bank.l10n_id_bi_code).
"""

import csv
import os
import sys

env = env  # noqa: F821  (injected by `odoo shell`)

APPLY = os.environ.get("MDR_APPLY") == "1"
CSV_PATH = os.environ.get("MDR_CSV", "/tmp/mdr_bin.csv")

tag = "APPLY" if APPLY else "DRY"
log = lambda m: print(f"[{tag}] {m}")  # noqa: E731

company = env["res.company"].search([], limit=1)
Acc = env["account.account"].with_company(company)
Bank = env["res.bank"]
Bin = env["levis.mdr.bin"]

if not os.path.exists(CSV_PATH):
    sys.exit(f"FATAL: {CSV_PATH} not found (copy mdr_bin.csv into the container)")

rows = []
with open(CSV_PATH, encoding="utf-8-sig") as fh:
    for raw in csv.DictReader(l for l in fh if not l.lstrip().startswith("#")):
        if not (raw.get("name") or "").strip():
            continue
        rows.append({k: (v or "").strip() for k, v in raw.items()})

if not rows:
    sys.exit(f"FATAL: no data rows in {CSV_PATH} -- did you replace the template?")

log(f"read {len(rows)} row(s) from {CSV_PATH}")

# ------------------------------------------------------------------ validate
errors = []
for i, r in enumerate(rows, 1):
    if r["bin_from"] > r["bin_to"]:
        errors.append(f"row {i} ({r['name']}): bin_from > bin_to")
    if len(r["bin_from"]) != len(r["bin_to"]):
        errors.append(f"row {i} ({r['name']}): bin_from/bin_to differ in length")
    if not (r.get("mdr_percent") or r.get("mdr_fixed")):
        errors.append(f"row {i} ({r['name']}): both mdr_percent and mdr_fixed are empty")

    acc = Acc.search([("code", "=", r["mdr_account_code"])], limit=1)
    if not acc:
        errors.append(f"row {i} ({r['name']}): account {r['mdr_account_code']} not found")
    elif acc.account_type != "expense":
        errors.append(f"row {i} ({r['name']}): account {r['mdr_account_code']} is {acc.account_type}, expected expense")

    if not Bank.search([("l10n_id_bi_code", "=", r["acquirer_bank_code"])], limit=1):
        errors.append(f"row {i} ({r['name']}): no bank with Kode BI {r['acquirer_bank_code']!r}")

# overlapping BIN ranges within the same scheme -- the check the DB does not do
for i, a in enumerate(rows):
    for b in rows[i + 1 :]:
        if a["card_scheme"] != b["card_scheme"]:
            continue
        if a["bin_from"] <= b["bin_to"] and b["bin_from"] <= a["bin_to"]:
            errors.append(
                f"BIN overlap in scheme {a['card_scheme']}: "
                f"{a['name']} [{a['bin_from']}-{a['bin_to']}] vs "
                f"{b['name']} [{b['bin_from']}-{b['bin_to']}]"
            )

if errors:
    print()
    for e in errors:
        print(f"  ERROR  {e}")
    sys.exit(f"\nFATAL: {len(errors)} validation error(s) -- nothing written")

log("validation passed")

# --------------------------------------------------------------------- load
created = updated = 0
for r in rows:
    vals = {
        "name": r["name"],
        "card_scheme": r["card_scheme"],
        "bin_from": r["bin_from"],
        "bin_to": r["bin_to"],
        "acquirer_bank_id": Bank.search([("l10n_id_bi_code", "=", r["acquirer_bank_code"])], limit=1).id,
        "mdr_percent": float(r["mdr_percent"] or 0),
        "mdr_fixed": float(r["mdr_fixed"] or 0),
        "mdr_account_id": Acc.search([("code", "=", r["mdr_account_code"])], limit=1).id,
        "date_start": r["date_start"] or False,
        "date_end": r["date_end"] or False,
        "company_id": company.id,
    }
    existing = Bin.search(
        [
            ("card_scheme", "=", r["card_scheme"]),
            ("bin_from", "=", r["bin_from"]),
            ("bin_to", "=", r["bin_to"]),
            ("date_start", "=", r["date_start"] or False),
        ],
        limit=1,
    )
    if existing:
        log(f"update  {r['name']}  [{r['bin_from']}-{r['bin_to']}]")
        if APPLY:
            existing.write(vals)
        updated += 1
    else:
        log(f"create  {r['name']}  [{r['bin_from']}-{r['bin_to']}]  {r['mdr_percent']}%")
        if APPLY:
            Bin.create(vals)
        created += 1

if APPLY:
    env.cr.commit()
    log(f"committed: {created} created, {updated} updated")
else:
    log(f"{created} to create, {updated} to update. Re-run with MDR_APPLY=1 to write.")
