# Add EBR accounts that are missing from a levis DB -- ADD ONLY (run via odoo shell).
#   docker cp scripts/tenants/levis/ebr_coa.csv odoo19-platform-odoo:/tmp/ebr_coa.csv
#   docker exec -i odoo19-platform-odoo odoo shell -d demo_levis --no-http < scripts/tenants/levis/29_add_missing_coa.py
#
# 30_fix_coa.py is the full reconciler: it also REMOVES accounts absent from the EBR list and
# renames the ones it keeps. That is the right tool when standing a tenant up, but far too broad
# when all you need is to close a small gap (e.g. 34_coa_categ_tree.py refuses to run without
# 5117000000 "Gross Sales-Labor (Service)"). This script only creates what is missing and never
# touches an existing account.
#
# Env flags:
#   COA_DRY=1   -> report what would be created, roll back
import csv
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[coa+] " + m)

CSV_PATH = os.environ.get("COA_PATH", "/tmp/ebr_coa.csv")
DRY = os.environ.get("COA_DRY") == "1"
COMPANY_ID = 1

Acc = env["account.account"].with_company(COMPANY_ID)

ebr = {}
with open(CSV_PATH) as f:
    for row in csv.DictReader(f):
        c = (row["code"] or "").strip()
        if c:
            ebr[c] = ((row["name"] or "").strip(), (row["account_type"] or "").strip())
log("EBR target accounts: %d" % len(ebr))

have = {a.code for a in Acc.search([]) if a.code}
missing = sorted(set(ebr) - have)
log("already present: %d, missing: %d" % (len(have), len(missing)))

created = 0
for code in missing:
    name, atype = ebr[code]
    Acc.create({"code": code, "name": name, "account_type": atype, "company_ids": [(4, COMPANY_ID)]})
    created += 1
    log("  created %s  %-42s [%s]" % (code, name[:42], atype))

log("==== VERIFY ====")
have2 = {a.code for a in Acc.with_context(active_test=False).search([]) if a.code}
still = sorted(set(ebr) - have2)
log("accounts created: %d, still missing: %d %s" % (created, len(still), still[:6]))

if DRY:
    env.cr.rollback()
    log("COA_DRY=1 -> rolled back, nothing committed")
else:
    env.cr.commit()
    log("committed")
log("==== DONE ====")
