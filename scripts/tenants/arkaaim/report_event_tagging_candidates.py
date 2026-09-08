# -*- coding: utf-8 -*-
"""List what could still be attached to an event, with the evidence, and write nothing.

WHY A SEPARATE REPORT
---------------------
``backfill_event_analytic.py`` tags what it can prove and refuses the rest. What
it refuses then disappears from view: the run says "648 line(s) in 143
document(s), no evidence" and stops. That is the correct behaviour for a script
that writes, and useless for the person who has to decide.

This one writes NOTHING. It sorts the leftovers into the three questions a human
actually has to answer, quotes the evidence next to each, and says which of them
can even affect the Profit & Loss per Event.

THE THREE BUCKETS
-----------------
1. **Traceable to a known event, but not by rules a script may trust.** A
   purchase-order note that names a show in words the event's own name does not
   contain ("BALI DANONE" vs "Danone - Nutribaby Royal Plus Launching"), or an
   invoice line whose description carries the venue and the show date while the
   header's show date says something else. Real evidence, human judgement.
2. **Naming a show that does not exist in the system at all.** No sales order,
   no analytic account, nothing to point at. Someone has to say what the show
   was before anything can be tagged.
3. **Overhead.** Payroll, tax, bank charges, the general journal — no document
   ties them to one show, and no amount of reading will produce one. These do
   NOT belong here: they belong to Accounting > Overhead Allocation
   (``custom.arka.event.allocation``), which spreads them by a stated rule.

WHAT IT DELIBERATELY DOES NOT REPORT
------------------------------------
**Down-payment lines.** They post to ``2108100001 Advances from customers``, a
balance-sheet account, and the down-payment invoice and the deduction on the
settlement net to zero. On prd_arkaaim that is seven lines — which look alarming
in a raw "untagged revenue" query and are nothing at all: analytic on a liability
line never reaches the P&L per Event. The report counts them, with their balance,
so nobody has to rediscover that.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < report_event_tagging_candidates.py

Read-only. There is no COMMIT knob, on purpose: acting on this is
``backfill_event_analytic.py``'s job, once a human has settled the mapping.
"""

import re

env = self.env  # noqa: F821  (provided by odoo shell)

companies = env["res.company"].sudo().search([("x_custom_event_tracking_enabled", "=", True)])
events = env["account.analytic.account"].sudo().search([("x_custom_event_key", "!=", False)])

print("=" * 112)
print("Event tagging — what is left, and the evidence   [db=%s]" % env.cr.dbname)
print("=" * 112)
print("companies tracking events : %s" % (", ".join(companies.mapped("name")) or "NONE"))
print("events known to the system:")
for event in events.sorted("x_custom_event_show_date"):
    print("   %-4s %s" % (event.id, event.name))


def plain(text):
    """Markup and newlines out, so a note or a description prints on one line."""
    text = re.sub(r"<[^>]*>", " ", text or "")
    text = text.replace("&nbsp;", " ")
    return " ".join(text.split())


# ---------------------------------------------------------------- untagged lines
lines = (
    env["account.move.line"]
    .sudo()
    .search(
        [
            ("company_id", "in", companies.ids),
            ("display_type", "=", "product"),
            ("parent_state", "=", "posted"),
            ("analytic_distribution", "=", False),
        ]
    )
)
downpayment = lines.filtered("is_downpayment")
lines -= downpayment

pl = lines.filtered(lambda l: l.account_id.account_type.startswith(("income", "expense")))
bs = lines - pl

print("\n" + "=" * 112)
print("SCALE")
print("=" * 112)
print("  untagged posted product lines      : %d" % (len(lines) + len(downpayment)))
print(
    "    of which down-payment lines      : %-5d %16.2f  (liability account — cannot reach the P&L per Event)"
    % (len(downpayment), sum(downpayment.mapped("balance")))
)
print(
    "    of which profit & loss lines     : %-5d %16.2f  <- the only ones tagging changes"
    % (len(pl), sum(pl.mapped("balance")))
)
print("    of which balance-sheet lines     : %-5d %16.2f" % (len(bs), sum(bs.mapped("balance"))))

# ------------------------------------------------------- 1. traceable by a human
print("\n" + "=" * 112)
print("1. TRACEABLE TO A KNOWN EVENT — evidence a script may not act on by itself")
print("=" * 112)

candidates = []
for order in (
    env["purchase.order"]
    .sudo()
    .search(
        [
            ("company_id", "in", companies.ids),
            ("state", "in", ("purchase", "done")),
            ("x_custom_event_name", "=", False),
        ]
    )
):
    note = plain(order.note)
    if not note:
        continue
    hits = events.filtered(lambda e: any(w in note.upper() for w in (e.name or "").upper().split(" - ")[0].split()))
    candidates.append((order, note, hits))

for order, note, hits in candidates:
    print(
        "\n  %s   %s   %s   %s"
        % (order.name, order.date_order.date(), order.partner_id.name[:34], "{:>16,.2f}".format(order.amount_untaxed))
    )
    print("     note      : %s" % note[:92])
    if hits:
        for event in hits:
            print("     candidate : [%s] %s" % (event.id, event.name))
    else:
        print("     candidate : NONE — this show is not in the system")

traced = env["account.move.line"].sudo().browse()
for line in pl:
    text = plain(line.name)
    hits = events.filtered(
        lambda e: e.x_custom_event_show_date and e.x_custom_event_show_date.strftime("%d.%m.%y") in text
    )
    if not hits:
        continue
    traced |= line
    print("\n  %s   line %s   %s" % (line.move_id.name, line.id, "{:>16,.2f}".format(-line.balance)))
    print("     account   : %s %s" % (line.account_id.with_company(line.company_id).code, line.account_id.name))
    print("     line says : %s" % text[:92])
    print("     header show date says: %s" % (line.move_id.x_custom_show_date or "-"))
    for event in hits:
        print("     candidate : [%s] %s" % (event.id, event.name))

# --------------------------------------------------------------- 3. overhead
print("\n" + "=" * 112)
print("3. OVERHEAD — no document ties these to one show; use Overhead Allocation, not tagging")
print("=" * 112)
# The candidates of bucket 1 are excluded: they DO have evidence, and counting
# them here as well would tell Finance to allocate what it is about to tag.
buckets = {}
for line in pl - traced:
    key = (line.move_id.journal_id.code, line.move_id.move_type)
    amount, count = buckets.get(key, (0.0, 0))
    buckets[key] = (amount + line.balance, count + 1)
print("  %-10s %-14s %8s %20s" % ("journal", "type", "lines", "balance"))
for (code, move_type), (amount, count) in sorted(buckets.items(), key=lambda kv: -abs(kv[1][0])):
    print("  %-10s %-14s %8d %20.2f" % (code, move_type, count, amount))

print("\n" + "=" * 112)
print("Nothing was written. To act on bucket 1, put the mapping into the purchase order's")
print("event fields (or the sales order), then re-run backfill_event_analytic.py.")
print("=" * 112)
