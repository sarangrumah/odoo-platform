# Close the Bank Suspense legs a clearing run leaves behind.
#
#   REC_MONTH=2026-08 [REC_COMMIT=1] docker exec -i odoo19-platform-odoo \
#     odoo shell -d prd_levis_begbal --no-http < 107_reconcile_bank_suspense.py
#
# WHY THIS EXISTS
# ---------------
# A bank statement line always books Dr/Cr the bank account against the journal's
# suspense account -- the bank leg is already direct, the suspense leg is the
# not-yet-known counterpart. The clearing run (105_clearing_agustus.py and its
# July predecessor) posts the counterpart as GLJV entries hitting that same
# suspense account, so the GL nets to zero, but it only reconciles the POS
# receivable accounts. The suspense legs stay open, and Odoo keeps every one of
# those statement lines in "to reconcile" -- which is what blocks the close.
#
# July was closed as ONE full-reconcile group of 3.283 lines. This does the same
# for whatever month it is pointed at, and refuses when the month does not net to
# zero (i.e. the clearing for it has not been run yet -- September, at time of
# writing, is Rp 193,2 juta short).
#
# Env:
#   REC_MONTH=YYYY-MM   month to close (required)
#   REC_ACCOUNT=code    suspense account code (default 1103000002)
#   REC_COMMIT=1        write (default: report only, rolled back)
import os
from datetime import date
from calendar import monthrange

MONTH = os.environ.get("REC_MONTH") or ""
CODE = os.environ.get("REC_ACCOUNT") or "1103000002"
COMMIT = os.environ.get("REC_COMMIT") == "1"

if not MONTH:
    raise SystemExit("REC_MONTH=YYYY-MM is required")
year, mon = (int(p) for p in MONTH.split("-"))
start = date(year, mon, 1)
end = date(year, mon, monthrange(year, mon)[1])

company = env["res.company"].search([], limit=1)
# account.code is company-dependent in Odoo 19: read it with_company.
account = env["account.account"].with_company(company).search([("code", "=", CODE)], limit=1)
if not account:
    raise SystemExit("account %s not found" % CODE)

AML = env["account.move.line"]
domain = [
    ("account_id", "=", account.id),
    ("parent_state", "=", "posted"),
    ("reconciled", "=", False),
    ("date", ">=", start),
    ("date", "<=", end),
]
lines = AML.search(domain)
net = round(sum(lines.mapped("balance")), 2)

print("=" * 72)
print("Bank suspense reconcile %s -- %s" % (MONTH, "COMMIT" if COMMIT else "PREVIEW"))
print("account : %s %s" % (CODE, account.name))
print("lines   : %s" % len(lines))
print("net     : %.2f" % net)
print("=" * 72)

if not lines:
    raise SystemExit("nothing open -- already closed.")
if net:
    raise SystemExit(
        "REFUSING: %s does not net to zero. The clearing run for this month is "
        "incomplete; reconciling now would leave a partial." % MONTH
    )

lines.reconcile()
env.flush_all()

left = AML.search_count(domain)
statements = env["account.bank.statement.line"].search([("date", ">=", start), ("date", "<=", end)])
open_st = len(statements.filtered(lambda r: not r.is_reconciled))
print("suspense lines still open : %s" % left)
print("statement lines           : %s, still open %s" % (len(statements), open_st))

if COMMIT:
    env.cr.commit()
    print("\nCOMMITTED.")
else:
    env.cr.rollback()
    print("\nPREVIEW only -- rolled back. Re-run with REC_COMMIT=1.")
