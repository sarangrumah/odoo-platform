"""Seed the PPh withholding registry (kode objek pajak) from the EBR mapping.

Source: "Kode Pajak Odoo - EBR (update).xlsx" -> scripts/tenants/levis/withholding_codes.csv
(107 kode objek pajak: PPh 23 x70, PPh 4(2) x10, PPh 26 x26, PPh 21 x1).

The `custom_tax_id` module ships only placeholder seed files, so on every levis DB
`tax.withholding.category` / `tax.withholding.rule` are empty. This loads them:

  * one `tax.withholding.category`  per row  (code / pph_kind / bupot_object_code / name)
  * one `tax.withholding.rule`       per row  (tarif + account Hutang Pajak by COA code)

Idempotent — matches on category.code, updates in place, safe to re-run.

    docker exec -i odoo19-platform-odoo odoo shell -d prd_levis \
        --no-http < scripts/tenants/levis/70_load_withholding.py

Notes / decisions confirmed by Finance:
  * Tax Treaty rows (13x DGT PPh 26) + PPh 21 row have a FLEXIBLE rate -> rule.tarif=0,
    flagged in notes ("Tarif fleksibel — isi manual per transaksi (P3B/DGT)").
  * EBR code of sheet row 91 corrected Z6-5T -> Z6-5U (row 90 keeps Z6-5T);
    the sheet's `unique(code)` collision is thus resolved before import.
  * bupot_object_code 28-423-01 intentionally appears twice (Z5-CV & Z1-1R) —
    PENDING Finance confirmation; both kept, logged below. Delete one later if needed.
"""

import csv
import os
import sys

env = env  # noqa: F821  (injected by `odoo shell`)
log = lambda m: sys.stderr.write("[wht] " + m + "\n") or sys.stderr.flush()

CSV = os.path.join(os.path.dirname(__file__) if "__file__" in dir() else
                   "scripts/tenants/levis", "withholding_codes.csv")
# `odoo shell` reads the script from stdin, so __file__ is unset -> use the path
# the file was piped from. Fall back to /tmp if mounted there.
for cand in (CSV, "/tmp/withholding_codes.csv",
             "scripts/tenants/levis/withholding_codes.csv"):
    if os.path.exists(cand):
        CSV = cand
        break
else:  # pragma: no cover
    raise SystemExit("withholding_codes.csv not found (copy it into the container)")

Category = env["tax.withholding.category"]
Rule = env["tax.withholding.rule"]

# Resolve the payable accounts once, per company that runs its own books.
companies = env["res.company"].search([])

rows = list(csv.DictReader(open(CSV)))
log("loaded %d rows from %s" % (len(rows), CSV))

# --- sanity: unique codes, known object-code duplicates -------------------
codes = [r["code"] for r in rows]
dup_codes = sorted({c for c in codes if codes.count(c) > 1})
if dup_codes:
    raise SystemExit("duplicate category codes in CSV: %s" % dup_codes)
objs = [r["bupot_object_code"] for r in rows]
dup_objs = sorted({o for o in objs if objs.count(o) > 1})
for o in dup_objs:
    who = [r["code"] for r in rows if r["bupot_object_code"] == o]
    log("NOTE object-code %s used by %s (pending Finance confirmation)" % (o, who))

cat_created = cat_updated = rule_created = rule_updated = 0

for r in rows:
    code = r["code"].strip()
    kind = r["pph_kind"].strip()
    obj = r["bupot_object_code"].strip()
    name = r["name"].strip()
    legal = r["legal_basis"].strip()
    tarif_raw = r["tarif"].strip()
    flexible = tarif_raw == ""
    tarif = 0.0 if flexible else float(tarif_raw)

    cat = Category.search([("code", "=", code)], limit=1)
    cvals = {"code": code, "pph_kind": kind, "bupot_object_code": obj,
             "name": name, "legal_basis": legal, "active": True}
    if cat:
        cat.write(cvals)
        cat_updated += 1
    else:
        cat = Category.create(cvals)
        cat_created += 1

    note = ("Tarif fleksibel — isi manual per transaksi (P3B/DGT)."
            if flexible else "")

    # One rule per company (account_id domain is company-scoped).
    for comp in companies:
        acc = env["account.account"].with_company(comp).search(
            [("code", "=", r["coa_code"].strip()),
             ("company_ids", "in", comp.id)], limit=1)
        if not acc:
            log("SKIP rule %s/%s: COA %s missing in %s"
                % (code, comp.name, r["coa_code"], comp.name))
            continue
        rule = Rule.search([("category_id", "=", cat.id),
                            ("company_id", "=", comp.id)], limit=1)
        rvals = {"category_id": cat.id, "company_id": comp.id,
                 "name": name, "tarif": tarif, "account_id": acc.id,
                 "notes": note, "active": True}
        if rule:
            rule.write(rvals)
            rule_updated += 1
        else:
            Rule.create(rvals)
            rule_created += 1

env.cr.commit()  # noqa: F821
log("categories: +%d created / %d updated" % (cat_created, cat_updated))
log("rules:      +%d created / %d updated" % (rule_created, rule_updated))
log("done.")
