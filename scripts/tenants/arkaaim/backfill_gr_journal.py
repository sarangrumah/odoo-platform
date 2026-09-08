# -*- coding: utf-8 -*-
"""Raise the missing GR/IR accrual for receipts validated before the feature existed.

THE GAP
-------
``custom_arka_aim_purchase_type`` 19.0.1.1.0 books ``Dr Inventory / Cr GR-IR``
when a vendor receipt is validated. Receipts validated BEFORE that went live
(8 Sep 2026) booked nothing, so on prd_arkaaim 39 done receipt lines worth
Rp 910.200.000 never touched an account.

That gap is not cosmetic, because the BILL side is already live: the routing in
``account_move_line._arka_grir_account`` fires for any PO line that has a done
receipt of a real-time category, so a bill arriving today for one of those old
receipts debits GR/IR — with no accrual to relieve, leaving a dangling debit in
the clearing account. Filling the accrual is what makes the two halves agree.

WHAT IT REFUSES TO DO, AND WHY THAT MATTERS MOST
------------------------------------------------
**A receipt whose vendor bill has already POSTED is skipped.** That bill booked
the cost straight to expense the old way, so the cost is already in the P&L.
Accruing it now would book it a second time. On prd_arkaaim that is 15 of the 39
lines (Rp 341.000.000, billed by BILL/2026/08/0001 and /0002 into
``7101007000 Exhibition`` and ``7215005000 Office Equipment Insurance``).

Routing those 15 through inventory after the fact is a different decision — an
account reclassification of an already-reported month, not a missing accrual —
and it belongs to Finance, not to this script.

WHAT IT POSTS
-------------
Nothing of its own: it calls ``stock.move._arka_post_gr_journal()``, the very
code an ordinary receipt runs. So the entry, its ``ARKA-GR-VAL:<move id>`` ref,
its idempotency and its account resolution are identical to a live receipt's,
and re-running this script posts nothing twice.

Entries are dated **today**, in the open period, never back on the receipt date:
the point is to state the accrual now, not to reopen a month that has been
reported.

ONE CONSEQUENCE TO EXPECT
-------------------------
An accrual for a show whose revenue is ALREADY recognised is charged straight
out to COGS — net ``Dr COGS / Cr GR-IR`` — which is exactly right for a show
already performed and invoiced whose vendor has not billed yet. The preview says
which lines will do that.

The charge-out is deliberately held back until every accrual is posted, then run
ONCE per event, so a show gets one charge-out entry instead of one per receipt
line. (Posting 24 accruals one at a time would otherwise leave 8 entries behind
for a single show, each moving one line's worth.) The bookkeeping is identical;
the general ledger is simply readable.

A line carrying NO event analytic is reported separately: its value will sit in
inventory with no event to release it, because the charge-out is driven by the
event. Tag the purchase order with its event first if you want it to flow.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < backfill_gr_journal.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to post.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to post the accruals
ONLY_PICKINGS = ()  # restrict to these picking names; empty = every eligible receipt
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Move = env["stock.move"].sudo()
AccountMove = env["account.move"].sudo()

moves = Move.search(
    [
        ("state", "=", "done"),
        ("location_id.usage", "=", "supplier"),
    ],
    order="id",
)
if ONLY_PICKINGS:
    moves = moves.filtered(lambda m: m.picking_id.name in ONLY_PICKINGS)

print("=" * 108)
print("GR/IR backfill — %s   [db=%s]" % ("COMMIT" if COMMIT else "PREVIEW", env.cr.dbname))
print("=" * 108)
print("%d done vendor receipt line(s) on this database" % len(moves))


def posted_bill(move):
    """The posted vendor bill(s) already covering this receipt line, if any."""
    if not move.purchase_line_id:
        return AccountMove.browse()
    lines = (
        env["account.move.line"]
        .sudo()
        .search(
            [
                ("purchase_line_id", "=", move.purchase_line_id.id),
                ("parent_state", "=", "posted"),
                ("move_id.move_type", "in", ("in_invoice", "in_refund")),
            ]
        )
    )
    return lines.move_id


eligible, billed, already, blocked = [], [], [], []

for move in moves:
    ref = move._GR_JOURNAL_REF % move.id
    if AccountMove.search_count([("ref", "=", ref), ("company_id", "=", move.company_id.id)]):
        already.append(move)
        continue
    bill = posted_bill(move)
    if bill:
        billed.append((move, bill))
        continue
    categ = move.product_id.categ_id.with_company(move.company_id)
    if categ.property_valuation != "real_time":
        blocked.append((move, "category %s is periodic" % categ.complete_name))
        continue
    grir = env["arka.purchase.account.map"]._grir_account(move.company_id, move.picking_id.l10n_purchase_type, categ)
    if not grir:
        blocked.append((move, "no GR/IR account mapped for this stream"))
        continue
    eligible.append(move)

print("\n  %-6s %-22s %-46s %16s  %s" % ("move", "receipt", "product", "value", "event"))
total = 0.0
untagged = 0.0
instant_cogs = 0.0
for move in eligible:
    distribution = move.purchase_line_id.analytic_distribution or {}
    events = (
        env["account.analytic.account"]
        .sudo()
        .browse([int(part) for key in distribution for part in str(key).split(",") if part.isdigit()])
        .exists()
    )
    events = events.filtered(lambda a: a.x_custom_event_key)
    label = events[:1].name or "(TANPA EVENT)"
    recognised = any(e._custom_event_revenue_recognised(move.company_id) for e in events)
    total += move.value
    if not events:
        untagged += move.value
    elif recognised:
        instant_cogs += move.value
        label += "  [pendapatan diakui -> langsung ke COGS]"
    print(
        "  %-6s %-22s %-46s %16.2f  %s"
        % (move.id, move.picking_id.name or "-", (move.product_id.name or "")[:46], move.value, label[:70])
    )

print("\n  " + "-" * 104)
print("  %d line(s) to accrue, %.2f" % (len(eligible), total))
if instant_cogs:
    print("      of which %.2f is charged straight to COGS (its show is already invoiced)" % instant_cogs)
if untagged:
    print("      of which %.2f carries NO event — it will sit in inventory until the PO is tagged" % untagged)

if billed:
    print("\n  SKIPPED — vendor bill already posted, the cost is already in the P&L:")
    total_billed = sum(m.value for m, _b in billed)
    for move, bill in billed:
        print(
            "    %-6s %-22s %-40s %14.2f  %s"
            % (
                move.id,
                move.picking_id.name or "-",
                (move.product_id.name or "")[:40],
                move.value,
                ", ".join(sorted(set(bill.mapped("name")))),
            )
        )
    print("    %d line(s), %.2f — accruing these would book the cost twice." % (len(billed), total_billed))
if already:
    print("\n  ALREADY ACCRUED: %d line(s) — nothing to do." % len(already))
if blocked:
    print("\n  NOT POSTABLE:")
    for move, why in blocked:
        print("    %-6s %-22s %s" % (move.id, move.picking_id.name or "-", why))

if COMMIT and eligible:
    from odoo.addons.custom_arka_show_date.models.event_chargeout import CHARGEOUT_CTX

    posted = env["stock.move"].sudo().browse([m.id for m in eligible])
    # Hold the charge-out back while the accruals go in, so one show ends up with
    # one charge-out entry rather than one per receipt line.
    posted.with_context(**{CHARGEOUT_CTX: True})._arka_post_gr_journal()
    print("\n  POSTED. Accruals created:")
    for move in eligible:
        entry = AccountMove.search([("ref", "=", move._GR_JOURNAL_REF % move.id)], limit=1)
        print("    move %-6s -> %s" % (move.id, entry.name or "(none)"))

    print("\n  Charge-out, once per event:")
    seen = set()
    for move in eligible:
        company = move.company_id
        distribution = move.purchase_line_id.analytic_distribution or {}
        ids = [int(part) for key in distribution for part in str(key).split(",") if part.isdigit()]
        for event in env["account.analytic.account"].sudo().browse(ids).exists():
            if not event.x_custom_event_key or (event.id, company.id) in seen:
                continue
            seen.add((event.id, company.id))
            if not event._custom_event_revenue_recognised(company):
                print("    %-52s revenue not recognised — stays in inventory" % (event.name or "")[:52])
                continue
            entry = event._custom_event_chargeout(company)
            print("    %-52s -> %s" % ((event.name or "")[:52], entry.name or "(nothing to charge)"))
    env.cr.commit()
elif eligible:
    print("\n  set COMMIT = True to post the %d accrual(s)" % len(eligible))

print("=" * 108)
