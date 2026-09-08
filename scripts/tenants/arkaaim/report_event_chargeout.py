# -*- coding: utf-8 -*-
"""Show, per event, what is still sitting in inventory and what would be charged out.

WHAT THIS IS FOR
----------------
``custom_arka_show_date`` 19.0.1.10.0 charges a show's cost out of inventory the
moment the show's revenue is recognised, and it does that from the posting of a
move -- the customer invoice, or a goods receipt arriving after it. That covers
everything from the day it is installed forward. It does not, by itself, reach:

* an event whose revenue was recognised BEFORE the feature was installed, whose
  cost is therefore still sitting in inventory with nothing left to trigger it;
* an event a user wants to look at before month-end, without posting anything.

This script is both: a read-only picture by default, and a catch-up when asked.

WHAT IT READS
-------------
For every event analytic account, per ARKA-AIM company:

* **In inventory** -- the balance still carried on the real-time categories'
  valuation accounts for that event, weighted by the analytic percentage. This
  is exactly what a charge-out would move.
* **Revenue** -- posted income lines carrying the event. Positive means the show
  has been invoiced, which is the condition the charge-out waits for.
* **Charged out** -- what previous runs already moved to expense.

WHAT COMMIT DOES
----------------
Only what the automatic trigger would have done: charge out the inventory of the
events whose revenue is already recognised. An event with no revenue yet is
listed and left alone -- charging its cost early is exactly the mismatch the
whole design avoids. Entries are dated TODAY, not on the old invoice, so a
closed period is never reopened.

Nothing here is destructive and nothing double-charges: the charge-out credits
the same accounts it reads, so a second run finds a zero balance and posts
nothing.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < report_event_chargeout.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to charge out.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to post the catch-up entries
ONLY_EVENT_IDS = ()  # restrict to these analytic account ids; empty = all events
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

plan = env.ref("custom_arka_show_date.analytic_plan_arka_event", raise_if_not_found=False)
if not plan:
    raise SystemExit("custom_arka_show_date is not installed on this database")

domain = [("plan_id", "=", plan.id)]
if ONLY_EVENT_IDS:
    domain.append(("id", "in", list(ONLY_EVENT_IDS)))
events = env["account.analytic.account"].sudo().search(domain, order="x_custom_event_show_date, id")
companies = env["res.company"].sudo().search([("x_custom_event_tracking_enabled", "=", True)], order="id")

print("=" * 104)
print("Show-cost charge-out — %s   [db=%s]" % ("COMMIT" if COMMIT else "PREVIEW", env.cr.dbname))
print("=" * 104)
if not companies:
    print("!! no company has Event Tracking enabled — nothing to do.")
if not events:
    print("!! no event analytic account on this database.")

posted = 0
total_moved = 0.0

for company in companies:
    print("\n--- company %s — %s" % (company.id, company.name))
    pairs = env["account.analytic.account"].sudo()._custom_event_inventory_accounts(company)
    if not pairs:
        print("    !! no real-time product category with a valuation account — nothing can be charged out")
        continue
    for inventory, expense in pairs.items():
        print(
            "    %s %s  ->  %s %s"
            % (
                inventory.with_company(company).code,
                inventory.name,
                expense.with_company(company).code or "-",
                expense.name or "NO EXPENSE ACCOUNT",
            )
        )
    print("\n    %-52s %16s %16s %10s" % ("event", "in inventory", "revenue", "action"))
    for event in events:
        pending = event._custom_event_chargeout(company, dry_run=True)
        amount = sum(pending.values())
        revenue = -sum(event._custom_event_amounts(company, account_type="income%").values())
        if not amount and not revenue:
            continue  # this company has nothing to do with this show
        recognised = company.currency_id.compare_amounts(revenue, 0.0) > 0
        if not amount:
            action = "flat"
        elif not recognised:
            action = "wait"  # cost accrued, show not invoiced yet
        else:
            action = "CHARGE"
        print("    %-52s %16.2f %16.2f %10s" % ((event.name or "")[:52], amount, revenue, action))
        if action == "CHARGE":
            total_moved += amount
            if COMMIT:
                entry = event._custom_event_chargeout(company)
                if entry:
                    posted += 1
                    print("        -> %s" % entry.name)

print("\n" + "=" * 104)
if COMMIT:
    print("%d entry/entries posted, %.2f moved out of inventory" % (posted, total_moved))
    env.cr.commit()
else:
    print("%.2f would be charged out — set COMMIT = True to post it" % total_moved)
print("=" * 104)
