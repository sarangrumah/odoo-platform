# Remove the June-2026 AR adjustment entries created by 69_ar_adjustments_juni.py.
#
# Why deletion and not a reversal: the client asked that June not move at all. A
# reversal restores the balances but still leaves the turnover and 152 extra GL lines
# in a closed period, which is exactly what they did not want. Deletion is only safe
# because these entries are hours old -- nothing reconciled against them and they hold
# the last numbers of the June sequence, so no gap is left behind. Verify both before
# running: the script refuses if either stops being true.
#
# Pair it with a re-run of 69 dated in the open period:
#
#   docker exec -i odoo19-platform-odoo odoo shell -d <db> --no-http \
#       < scripts/tenants/levis/78_undo_ar_adjustments_juni.py
#   docker exec -i -e ADJ_POST=1 -e ADJ_DATE=2026-07-01 -e ADJ_CUTOFF=2026-06-30 \
#       odoo19-platform-odoo odoo shell -d <db> --no-http \
#       < scripts/tenants/levis/69_ar_adjustments_juni.py
#
# Env flags:  UNDO_DRY=1  -> report what would be deleted, roll back
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[ar-undo] " + m)

COMPANY_ID = 1
REF_PREFIX = "EBR-ADJ-AR-JUNI-2026"

DRY = os.environ.get("UNDO_DRY") == "1"

company = env["res.company"].browse(COMPANY_ID)
moves = env["account.move"].search(
    [("ref", "like", REF_PREFIX + "%"), ("company_id", "=", company.id)]
)
if not moves:
    raise SystemExit("no %s* entries found -- nothing to undo" % REF_PREFIX)
log("found %d entries: %s" % (len(moves), ", ".join(sorted(moves.mapped("ref")))))

# --- guard 1: nothing may be reconciled against these lines -----------------
lines = moves.line_ids
env.cr.execute(
    """select count(*) from account_partial_reconcile
        where debit_move_id = any(%s) or credit_move_id = any(%s)""",
    (lines.ids, lines.ids),
)
partials = env.cr.fetchone()[0]
full = len(lines.filtered(lambda l: l.full_reconcile_id))
if partials or full:
    raise SystemExit(
        "refusing: %d partial / %d full reconciliations point at these lines" % (partials, full)
    )
log("reconciliation check: clean (0 partial, 0 full)")

# --- guard 2: each entry must be the last of its own sequence prefix --------
for move in moves:
    if not move.name or move.name == "/":
        continue
    prefix = move.name.rsplit("/", 1)[0] + "/"
    # the other entries in this batch are going away too, so they cannot block it
    later = env["account.move"].search_count(
        [
            ("name", "=like", prefix + "%"),
            ("name", ">", move.name),
            ("journal_id", "=", move.journal_id.id),
            ("company_id", "=", company.id),
            ("id", "not in", moves.ids),
        ]
    )
    if later:
        raise SystemExit(
            "refusing: %s has %d entries after it in %s -- deleting would leave a gap"
            % (move.name, later, prefix)
        )
log("sequence check: every entry is the last of its period prefix")

for move in moves:
    log("will delete %s (%s, %s, %d lines)"
        % (move.name, move.ref, move.date, len(move.line_ids)))

saved_lock = company.fiscalyear_lock_date
if saved_lock:
    company.sudo().write({"fiscalyear_lock_date": False})
    log("fiscalyear_lock_date %s -> cleared (restored at end)" % saved_lock)
try:
    moves.button_draft()
    log("reset to draft")
    moves.unlink()
    log("deleted")
finally:
    if saved_lock:
        company.sudo().write({"fiscalyear_lock_date": saved_lock})
        log("fiscalyear_lock_date restored to %s" % saved_lock)

left = env["account.move"].search_count(
    [("ref", "like", REF_PREFIX + "%"), ("company_id", "=", company.id)]
)
log("remaining %s* entries: %d" % (REF_PREFIX, left))

if DRY:
    env.cr.rollback()
    log("UNDO_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
