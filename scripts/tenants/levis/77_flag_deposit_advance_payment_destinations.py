# Open the payment "Destination Account" picker to the whole deposit / advance
# family (follow-up on 75_flag_payment_destination_accounts.py).
#
# Script 75 flagged only 4 accounts, so a payment against e.g. 1211100009
# "Other Deposit" showed "No records". Accounting asked for the whole deposit and
# advance group -- prefixes 1115 (down payment / advance, asset_prepayments) and
# 1211 (deposits, asset_non_current) -- rather than the entire chart (script 76).
# ADD-ONLY and idempotent: it never clears a flag outside the group.
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/77_flag_deposit_advance_payment_destinations.py
#
# Env flags:
#   PD_DRY=1     -> report what would change, roll back
#   PD_UNDO=1    -> clear the flag on this group again (script-75 shortlist stays on)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[paydest-deposit] " + m)

DRY = os.environ.get("PD_DRY") == "1"
UNDO = os.environ.get("PD_UNDO") == "1"

PREFIXES = ("1115", "1211")

# Kept flagged even when undoing -- these are the script-75 shortlist.
SHORTLIST = {
    "1115100001",  # Down Payment - Trade
    "1115600001",  # Advance from intercompanies (related party)
    "1115200001",  # Advance for payment of operational expenses
    "1211100004",  # Security Deposit
}

Acc = env["account.account"].with_company(1).with_context(active_test=False)
group = Acc.search([]).filtered(lambda a: (a.code or "").startswith(PREFIXES))
log("deposit/advance accounts found: %d" % len(group))

if UNDO:
    drop = group.filtered(lambda a: a.l10n_allow_payment_destination and a.code not in SHORTLIST)
    for a in drop:
        log("  clearing %s  %s" % (a.code, (a.name or "")[:48]))
    drop.l10n_allow_payment_destination = False
    log("UNDO: cleared %d" % len(drop))
else:
    todo = group.filtered(lambda a: not a.l10n_allow_payment_destination)
    for a in todo:
        log("  flagging %s  %s" % (a.code, (a.name or "")[:48]))
    todo.l10n_allow_payment_destination = True
    log("flagged %d new account(s); already on: %d" % (len(todo), len(group) - len(todo)))

on = Acc.search([("l10n_allow_payment_destination", "=", True)])
log("==== total flagged now: %d ====" % len(on))
for a in on.sorted("code"):
    log("  ON: %s  %s" % (a.code, (a.name or "")[:48]))

if DRY:
    env.cr.rollback()
    log("DRY RUN -- rolled back")
else:
    env.cr.commit()
    log("committed")
