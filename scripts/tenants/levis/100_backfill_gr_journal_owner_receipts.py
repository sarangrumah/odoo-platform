# Post the missing goods-receipt journals on prd_levis_begbal -- August 2026.
#
# Tail of the 27-Aug-2026 Assign-Owner clean-up (see the owner-fix note): 43 receipts were
# validated while stock_picking.owner_id carried a partner, so _should_exclude_for_valuation()
# left stock_move.value NULL and custom_levis_localization's _levis_book_valuation_entry()
# bailed out on its "if not amount" guard -- no GR journal was ever written. The clean-up
# refilled the value through _set_value(), which by design never calls _create_account_move(),
# so the GL never caught up: GR/IR carries the bill debits with no receipt credit behind them.
#
# This script books the entries that _levis_post_gr_journal() would have booked, one per
# stock.move, Dr <category valuation account> / Cr <its account_stock_variation_id>, for
# move.value (purchase price net of recoverable PPN), stamped with the store's Operating-Unit
# analytic on both legs -- byte-for-byte the shape of the existing GR-VAL entries. The only
# departure from the model method is the date: it uses fields.Date.context_today(), which today
# would land every entry in September, so the date is taken from each receipt instead.
#
#   docker exec -i -e GR_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/100_backfill_gr_journal_owner_receipts.py
#
# Env flags:  GR_DRY=1       -> report and roll back (default; 0 = commit)
#             GR_FROM        -> window start, default 2026-08-01
#             GR_TO          -> window end (exclusive), default 2026-09-01
#             GR_PICKINGS    -> comma-separated stock.picking ids to restrict to
#             GR_LIMIT       -> stop after N receipts (0 = all)
#
# Idempotent: a move that already has an account.move with ref GR-VAL:<id> is skipped, so a
# re-run after a partial commit picks up exactly where it stopped. Commits per receipt, never
# one big transaction -- the PPN-included correction held a 22-minute row lock on prd by
# batching everything into one commit; do not repeat that.
import os

from odoo import fields  # noqa: F401  (kept for parity with the model method)

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[gr-backfill] " + m)  # noqa: E731

COMPANY_ID = 1
DRY = os.environ.get("GR_DRY", "1") == "1"
DATE_FROM = os.environ.get("GR_FROM", "2026-08-01")
DATE_TO = os.environ.get("GR_TO", "2026-09-01")
LIMIT = int(os.environ.get("GR_LIMIT", "0"))
ONLY = [int(x) for x in os.environ.get("GR_PICKINGS", "").replace(" ", "").split(",") if x]

GR_REF = "GR-VAL:%s"

company = env["res.company"].browse(COMPANY_ID)
env = env(context=dict(env.context, allowed_company_ids=[COMPANY_ID]))
cr = env.cr

# ---------------------------------------------------------------- guards ---
lock = company.fiscalyear_lock_date
if lock and fields.Date.to_date(DATE_FROM) <= lock:
    raise SystemExit(f"fiscalyear_lock_date {lock} covers {DATE_FROM} -- unlock or move the window")

# ------------------------------------------------------------- selection ---
# Vendor goods receipts, done in the window, that carry a value but no GR journal.
moves = env["stock.move"].search(
    [
        ("company_id", "=", COMPANY_ID),
        ("state", "=", "done"),
        ("date", ">=", DATE_FROM),
        ("date", "<", DATE_TO),
        ("location_id.usage", "=", "supplier"),
        ("picking_id", "!=", False),
    ],
    order="picking_id, id",
)
if ONLY:
    moves = moves.filtered(lambda m: m.picking_id.id in ONLY)

AccountMove = env["account.move"]
existing = set(AccountMove.search([("company_id", "=", COMPANY_ID), ("ref", "=like", "GR-VAL:%")]).mapped("ref"))
todo = moves.filtered(lambda m: m.value and GR_REF % m.id not in existing)

by_picking = {}
for move in todo:
    by_picking.setdefault(move.picking_id, env["stock.move"])
    by_picking[move.picking_id] |= move

log(f"window {DATE_FROM} .. {DATE_TO}, dry-run={DRY}")
log(
    f"{len(moves)} vendor receipt moves, {len(todo)} without a GR journal "
    f"across {len(by_picking)} receipts, Rp {sum(todo.mapped('value')):,.2f}"
)
if not todo:
    raise SystemExit("nothing to do")


# GR/IR balances before, per clearing account -- proof of what moved.
def grir_balances():
    env.cr.execute(
        """
        select aml.account_id, round(sum(aml.balance), 2)
          from account_move_line aml
          join account_move am on am.id = aml.move_id
         where am.state = 'posted' and aml.company_id = %s
           and aml.account_id in (
               select distinct account_stock_variation_id from account_account
                where account_stock_variation_id is not null)
         group by 1 order by 1
        """,
        (COMPANY_ID,),
    )
    return dict(env.cr.fetchall())


before = grir_balances()

# ------------------------------------------------------------------ post ---
posted = 0
amount_total = 0.0
skipped = []

for n, (picking, picking_moves) in enumerate(by_picking.items(), start=1):
    if LIMIT and n > LIMIT:
        break
    entry_date = fields.Date.context_today(picking, picking.date_done or picking.scheduled_date)
    vals_list = []
    picking_amount = 0.0
    for move in picking_moves:
        categ = move.product_id.categ_id.with_company(company)
        if categ.property_valuation != "real_time":
            skipped.append((move.id, "category not real_time"))
            continue
        val_acc = categ.property_stock_valuation_account_id
        var_acc = categ.account_stock_variation_id
        ptype = move.picking_id.l10n_purchase_type
        if ptype:
            mapping = env["levis.purchase.account.map"]._get_map(company, ptype)
            if mapping and mapping.grir_account_id:
                var_acc = mapping.grir_account_id
        journal = categ.property_stock_journal or company.account_stock_journal_id
        if not (val_acc and var_acc and journal):
            skipped.append((move.id, "valuation account or journal missing"))
            continue
        amount = move.value
        if not amount or company.currency_id.is_zero(amount):
            skipped.append((move.id, "zero value"))
            continue
        ou = move.picking_id.picking_type_id.warehouse_id.l10n_ou_analytic_id
        analytic = {str(ou.id): 100.0} if ou else False
        label = f"Goods Receipt {picking.name or ''}"
        picking_amount += amount
        vals_list.append(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "company_id": COMPANY_ID,
                "date": entry_date,
                "ref": GR_REF % move.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": val_acc.id,
                            "name": label,
                            "debit": amount if amount > 0 else 0.0,
                            "credit": -amount if amount < 0 else 0.0,
                            "analytic_distribution": analytic,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": var_acc.id,
                            "name": label,
                            "debit": -amount if amount < 0 else 0.0,
                            "credit": amount if amount > 0 else 0.0,
                            "analytic_distribution": analytic,
                        },
                    ),
                ],
            }
        )
    if not vals_list:
        continue
    entries = AccountMove.create(vals_list)
    entries.action_post()
    draft = entries.filtered(lambda m: m.state != "posted")
    if draft:
        raise SystemExit(f"{picking.name}: {len(draft)} entries stayed draft -- check auto_post/date")
    posted += len(entries)
    amount_total += picking_amount
    log(f"{picking.name} {entry_date}: {len(entries)} entries, Rp {picking_amount:,.2f}")
    if not DRY:
        cr.commit()

after = grir_balances()

log(f"posted {posted} entries, Rp {amount_total:,.2f}")
if skipped:
    log(f"skipped {len(skipped)} moves: {skipped[:10]}")
for acc_id in sorted(set(before) | set(after)):
    delta = after.get(acc_id, 0.0) - before.get(acc_id, 0.0)
    if delta:
        acc = env["account.account"].browse(acc_id)
        log(f"  GR/IR {acc.code} {acc.display_name}: {delta:,.2f}")

if DRY:
    cr.rollback()
    log("DRY RUN -- rolled back, nothing was written")
else:
    cr.commit()
    log("committed")
