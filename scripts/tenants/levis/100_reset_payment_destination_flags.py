# Reset ``l10n_allow_payment_destination`` back to the four accounts script 75
# flags, turning it OFF everywhere else. Run via odoo shell:
#
#   docker exec -i -e PD_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/100_reset_payment_destination_flags.py
#
# WHY
# ---
# The flag widens the Destination Account domain on Payment beyond the native
# receivable/payable set. It is meant for a handful of advance / deposit
# accounts. On 18-Aug-2026 prd_levis_begbal carried it on 704 of 705 accounts
# (prd_levis and rnd_levis: 4 of ~694), i.e. someone ticked the whole chart --
# revenue, COGS and equity accounts included -- which leaves no guard at all on
# where a payment can land.
#
# This script is the counterpart of 75_flag_payment_destination_accounts.py:
# 75 only ever adds, this one subtracts back to the allowlist. Accounting can
# still tick individual accounts afterwards from the Chart of Accounts form --
# that is the supported way to extend the list, and re-running this would undo
# it, so widen ALLOWED here rather than in the UI if the addition is permanent.
#
# Env flags:
#   PD_DRY=1    -> report what would change, roll back (recommended first pass)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[paydest-reset] " + m)

DRY = os.environ.get("PD_DRY") == "1"
COMPANY_ID = 1

# Same four codes as script 75 -- keep the two lists in step.
ALLOWED = [
    "1115100001",  # Down Payment - Trade
    "1115600001",  # Advance from intercompanies (related party)
    "1115200001",  # Advance for payment of operational expenses
    "1211100004",  # Security Deposit
]

Acc = env["account.account"].with_company(COMPANY_ID).with_context(active_test=False)

allowed = Acc.search([("code", "in", ALLOWED)])
missing = sorted(set(ALLOWED) - {a.code for a in allowed})
if missing:
    log("WARNING: codes not found in this DB: %s" % ", ".join(missing))

flagged = Acc.search([("l10n_allow_payment_destination", "=", True)])
to_clear = flagged - allowed
to_set = allowed.filtered(lambda a: not a.l10n_allow_payment_destination)

log("currently flagged: %d" % len(flagged))
log("to switch OFF:     %d" % len(to_clear))
log("to switch ON:      %d" % len(to_set))

# Print every account being switched off, grouped by account type, so the
# reviewer can see whether anything deliberate is being lost.
by_type = {}
for a in to_clear:
    by_type.setdefault(a.account_type, []).append(a)
for atype in sorted(by_type):
    accounts = sorted(by_type[atype], key=lambda a: a.code or "")
    log("  --- %s (%d) ---" % (atype, len(accounts)))
    for a in accounts:
        log("      OFF %s  %s" % (a.code, (a.name or "")[:52]))

if to_clear:
    to_clear.l10n_allow_payment_destination = False
if to_set:
    to_set.l10n_allow_payment_destination = True

remaining = Acc.search([("l10n_allow_payment_destination", "=", True)])
log("==== flagged after: %d ====" % len(remaining))
for a in remaining:
    log("  ON: %s  %s" % (a.code, (a.name or "")[:52]))

if DRY:
    env.cr.rollback()
    log("DRY RUN -- rolled back")
else:
    env.cr.commit()
    log("committed")
