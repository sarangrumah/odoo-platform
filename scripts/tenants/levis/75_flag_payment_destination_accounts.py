# Flag the advance/deposit accounts so they can be picked as a payment
# Destination Account (sheet items #9 / #10). ADD-ONLY, idempotent -- run via odoo shell:
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/75_flag_payment_destination_accounts.py
#
# The domain on the payment form (custom_levis_localization) allows the native
# receivable/payable set PLUS any account with l10n_allow_payment_destination=True.
# Accounting can also tick the flag by hand from the Chart of Accounts form.
#
# Env flags:
#   PD_DRY=1    -> report what would change, roll back
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[paydest] " + m)

DRY = os.environ.get("PD_DRY") == "1"
COMPANY_ID = 1

CODES = [
    "1115100001",  # Down Payment - Trade
    "1115600001",  # Advance from intercompanies (related party)
    "1115200001",  # Advance for payment of operational expenses
    "1211100004",  # Security Deposit
]

Acc = env["account.account"].with_company(COMPANY_ID).with_context(active_test=False)
accounts = Acc.search([("code", "in", CODES)])
found = {a.code for a in accounts}
missing = sorted(set(CODES) - found)
if missing:
    log("WARNING: codes not found in this DB: %s" % ", ".join(missing))

changed = 0
for a in accounts:
    if not a.l10n_allow_payment_destination:
        a.l10n_allow_payment_destination = True
        changed += 1
        log("  flagged %s  %s" % (a.code, (a.name or "")[:48]))
    else:
        log("  already flagged %s  %s" % (a.code, (a.name or "")[:48]))

log("==== flagged now: %d (changed %d) ====" % (len(accounts), changed))
for a in Acc.search([("l10n_allow_payment_destination", "=", True)]):
    log("  ON: %s  %s" % (a.code, (a.name or "")[:48]))

if DRY:
    env.cr.rollback()
    log("DRY RUN -- rolled back")
else:
    env.cr.commit()
    log("committed")
