# Open the payment "Destination Account" picker to the WHOLE chart of accounts
# (follow-up on sheet items #9 / #10 -- see 75_flag_payment_destination_accounts.py).
#
# Script 75 flagged only the 4 advance/deposit accounts. Accounting asked for the
# full COA list, so this flips l10n_allow_payment_destination=True on every
# account. ADD-ONLY and idempotent -- it never clears a flag.
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/76_open_all_payment_destination_accounts.py
#
# Env flags:
#   PD_DRY=1     -> report what would change, roll back
#   PD_UNDO=1    -> revert to the script-75 short list (clears everything else)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[paydest-all] " + m)

DRY = os.environ.get("PD_DRY") == "1"
UNDO = os.environ.get("PD_UNDO") == "1"

SHORTLIST = [
    "1115100001",  # Down Payment - Trade
    "1115600001",  # Advance from intercompanies (related party)
    "1115200001",  # Advance for payment of operational expenses
    "1211100004",  # Security Deposit
]

Acc = env["account.account"].with_context(active_test=False)
all_accounts = Acc.search([])
log("chart of accounts: %d" % len(all_accounts))

if UNDO:
    keep = all_accounts.filtered(lambda a: a.code in SHORTLIST)
    drop = (all_accounts - keep).filtered("l10n_allow_payment_destination")
    drop.l10n_allow_payment_destination = False
    keep.l10n_allow_payment_destination = True
    log("UNDO: cleared %d, kept %d" % (len(drop), len(keep)))
else:
    todo = all_accounts.filtered(lambda a: not a.l10n_allow_payment_destination)
    todo.l10n_allow_payment_destination = True
    log("flagged %d new account(s); already on: %d"
        % (len(todo), len(all_accounts) - len(todo)))

on = Acc.search_count([("l10n_allow_payment_destination", "=", True)])
log("==== total flagged now: %d / %d ====" % (on, len(all_accounts)))

if DRY:
    env.cr.rollback()
    log("DRY RUN -- rolled back")
else:
    env.cr.commit()
    log("committed")
