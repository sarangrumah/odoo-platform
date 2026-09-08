# -*- coding: utf-8 -*-
"""List the receipts whose bill posted before the GR/IR journal existed. Change nothing.

WHAT THESE LINES ARE
--------------------
``backfill_gr_journal.py`` accrued the old receipts that had never been billed,
and deliberately skipped those whose vendor bill had ALREADY posted: that bill
booked the cost straight to expense the old way, so accruing it again would book
it twice. This report is the list it skipped, so the decision about them can be
made on evidence rather than on a count.

WHAT A RECLASSIFICATION WOULD AND WOULD NOT BUY
-----------------------------------------------
It is worth being precise, because the intuition "these never went through
inventory, so the books are wrong" is only half true:

* **Attribution is NOT missing.** Every one of these lines already carries its
  event's analytic distribution, and the account it sits on is an expense
  account. The Profit & Loss per Event therefore already counts this cost
  against the right show. Nothing is hiding in Unassigned.
* **What differs is only WHICH expense account holds it** — the account the
  vendor bill chose, rather than the COGS account the goods-receipt route would
  have reached through inventory.

So a reclassification here is a presentation change to a month that has already
been reported, not a correction of a wrong number. That is a Finance decision,
and this script deliberately cannot make it: there is no COMMIT knob.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < report_billed_receipts.py

Read-only.
"""

env = self.env  # noqa: F821  (provided by odoo shell)

Move = env["stock.move"].sudo()
AccountMove = env["account.move"].sudo()

moves = Move.search([("state", "=", "done"), ("location_id.usage", "=", "supplier")], order="id")

print("=" * 118)
print("Receipts already billed before the GR/IR journal existed   [db=%s]" % env.cr.dbname)
print("=" * 118)

rows = []
for move in moves:
    if not move.purchase_line_id:
        continue
    if AccountMove.search_count(
        [("ref", "=", move._GR_JOURNAL_REF % move.id), ("company_id", "=", move.company_id.id)]
    ):
        continue  # accrued by the backfill — not one of these
    bill_lines = (
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
    if not bill_lines:
        continue
    rows.append((move, bill_lines))

if not rows:
    print("\n  none — every done receipt either carries its accrual or has no posted bill.")

print("\n  %-6s %-20s %-42s %15s  %-18s %-11s %s" % ("move", "receipt", "product", "value", "bill", "account", "event"))

total = 0.0
per_account = {}
per_event = {}
untagged = []
for move, bill_lines in rows:
    line = bill_lines[:1]
    account = line.account_id
    event_names = []
    for key in line.analytic_distribution or {}:
        for part in str(key).split(","):
            if part.isdigit():
                event = env["account.analytic.account"].sudo().browse(int(part)).exists()
                if event and event.x_custom_event_key:
                    event_names.append(event.name)
    label = event_names[0] if event_names else "(TIDAK ber-analytic)"
    if not event_names:
        untagged.append(move)
    total += move.value
    code = account.with_company(move.company_id).code
    per_account[code] = per_account.get(code, 0.0) + move.value
    per_event[label] = per_event.get(label, 0.0) + move.value
    print(
        "  %-6s %-20s %-42s %15.2f  %-18s %-11s %s"
        % (
            move.id,
            move.picking_id.name or "-",
            (move.product_id.name or "")[:42],
            move.value,
            ", ".join(sorted(set(bill_lines.mapped("move_id.name"))))[:18],
            code,
            label[:40],
        )
    )

print("\n  " + "-" * 114)
print("  %d line(s), %.2f" % (len(rows), total))
print("\n  by expense account the cost actually sits on:")
for code, amount in sorted(per_account.items()):
    print("    %-12s %16.2f" % (code, amount))
print("\n  by event (this is what the P&L per Event already shows):")
for label, amount in sorted(per_event.items(), key=lambda kv: -kv[1]):
    print("    %-52s %16.2f" % (label[:52], amount))

print("\n" + "=" * 118)
if untagged:
    print("  %d line(s) carry NO event — for those, attribution really is missing:" % len(untagged))
    for move in untagged:
        print("    %-6s %-20s %s" % (move.id, move.picking_id.name or "-", move.product_id.name))
else:
    print("  Every line above already carries its event, on an expense account.")
    print("  The Profit & Loss per Event already counts this cost against the right show;")
    print("  a reclassification would only move it to another expense account, in a month")
    print("  that has already been reported. Nothing here is a missing number.")
print("=" * 118)
print("Read-only: nothing was written, and this script has no COMMIT knob.")
