# Reconcile the chart of accounts to the authoritative EBR list (run via odoo shell).
# Reads /tmp/ebr_coa.csv (code,name,account_type). For the company (id=1):
#  - ADD accounts present in EBR but missing in the DB
#  - REMOVE accounts present in the DB but NOT in EBR (Arka/AIM/rental/generic-Erajaya),
#    EXCEPT operational/system accounts needed by POS/journals (kept). Delete if unreferenced,
#    else deactivate.
#  - ALIGN names of kept accounts to the EBR label.
import csv

env = env
log = lambda m: print("[coa] " + m)
Acc = env["account.account"].with_company(1)

# ---- load EBR target ----
ebr = {}
with open("/tmp/ebr_coa.csv") as f:
    for row in csv.DictReader(f):
        c = row["code"].strip()
        if c:
            ebr[c] = (row["name"].strip(), row["account_type"].strip())
log("EBR target accounts: %d" % len(ebr))

# ---- current accounts ----
cur = {a.code: a for a in Acc.search([]) if a.code}
log("current DB accounts: %d" % len(cur))

es, ds = set(ebr), set(cur)
to_add = sorted(es - ds)
to_remove = sorted(ds - es)
to_keep = sorted(es & ds)

# ---- operational/system accounts to PRESERVE even if absent from EBR template ----
KEEP_NAMES = {
    "Liquidity Transfer",
    "Bank",
    "Bank Suspense Account",
    "Outstanding Receipts",
    "Outstanding Payments",
    "Cash Difference Gain",
    "Cash Difference Loss",
    "Cash Discount Gain",
    "Cash Discount Loss",
}


def is_operational(acc):
    n = acc.name or ""
    return (
        n.startswith("Cash - OLS")
        or n in KEEP_NAMES
        or n.startswith("Bank Mandiri - 0000")
        or n.startswith("BNI - 0000")
    )


# ---- 1. ADD missing EBR accounts ----
created = 0
for code in to_add:
    name, atype = ebr[code]
    try:
        Acc.create({"code": code, "name": name, "account_type": atype})
        created += 1
    except Exception as e:
        log("ADD FAIL %s %s: %s" % (code, name, e))
        env.cr.rollback()
log("added accounts: %d / %d" % (created, len(to_add)))
env.cr.commit()

# ---- 2. REMOVE non-EBR accounts (skip operational) ----
deleted = deactivated = preserved = 0
removed_detail = []
for code in to_remove:
    acc = cur[code]
    if is_operational(acc):
        preserved += 1
        continue
    nm = acc.name
    try:
        acc.with_context(force_delete=True).unlink()
        deleted += 1
        removed_detail.append(("del", code, nm))
    except Exception:
        env.cr.rollback()
        acc = env["account.account"].with_company(1).browse(acc.id)
        try:
            acc.active = False
            deactivated += 1
            removed_detail.append(("deact", code, nm))
        except Exception as e:
            env.cr.rollback()
            log("REMOVE FAIL %s %s: %s" % (code, nm, e))
    env.cr.commit()
log("removed: deleted=%d deactivated=%d preserved_operational=%d" % (deleted, deactivated, preserved))

# ---- 3. ALIGN kept account names to EBR ----
renamed = 0
for code in to_keep:
    acc = cur[code]
    target = ebr[code][0]
    if acc.name != target:
        acc.name = target
        renamed += 1
log("renamed kept accounts to EBR label: %d" % renamed)
env.cr.commit()

# ---- verify ----
final = {a.code: a for a in env["account.account"].with_company(1).search([]) if a.code}
log("==== VERIFY ====")
log("active accounts now: %d" % len(final))
missing = sorted(set(ebr) - set(final))
log("EBR accounts still missing: %d %s" % (len(missing), missing[:10]))
extra = sorted(set(final) - set(ebr))
extra_nonop = [c for c in extra if not is_operational(final[c])]
log("non-EBR accounts still active (should be only operational): %d" % len(extra))
log("  of which NON-operational (unexpected): %d %s" % (len(extra_nonop), extra_nonop[:10]))
log("rental accounts remaining: %s" % [c for c in final if "rental" in (final[c].name or "").lower()])
env.cr.commit()
