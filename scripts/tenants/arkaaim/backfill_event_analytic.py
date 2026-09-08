# -*- coding: utf-8 -*-
"""Attach transactions booked before 19.0.1.7.0 to their event.

From 1.7.0 on, confirming a sales or purchase order stamps the event's analytic
account on its lines, and the invoice or bill inherits it. Everything booked
before that carries nothing, so the Profit & Loss per Event shows those amounts
in **Unassigned**. This walks back over what is already in the database and
tags whatever can be traced to an event *with evidence*.

Evidence, strongest first
-------------------------
1. **The sales order.** It carries the event fields, so an order line, and any
   invoice line linked to it, belong to that event beyond doubt.
2. **The purchase order.** Before 1.7.0 the event survived there only as free
   text in the header note ("SOEKARNO CUP - SURABAYA", "MERDEKA RUN - MONAS").
   A note is matched to an event only when EVERY word of the event's name
   appears in it and exactly ONE event matches; the matched event is then
   written into the order's proper fields so it stops being free text.
3. **The move's own event fields**, for documents already stamped by 1.7.0.
4. **The move's show date**, but only when exactly one event falls on that date.

Anything with no evidence is listed and left alone. In particular, a purchase
order whose note names a show that was never entered as a sales order has no
event to point at: inventing one from "OPERRATIONAL DRONE SHOW - DANONE BALI"
would enter the typo into the chart of accounts, and the second Danone order
worded differently would create a second event for the same show. Those belong
to whoever knows the shows.

What it never does
------------------
* Overwrite an analytic distribution somebody set by hand.
* Touch a company that has not enabled event tracking.
* Move an amount between accounts, change a balance, or re-post anything.
  Analytic distribution is a dimension on the line, not an accounting entry.

Verify the lock dates before running: this writes to posted journal items.
Empty lock dates on both ARKA companies are why it can run at all.

Usage
-----
    odoo shell -d <db> ... < backfill_event_analytic.py          # apply
    APPLY=0 odoo shell -d <db> ... < backfill_event_analytic.py  # plan only
"""

import os
import re

APPLY = os.environ.get("APPLY", "1") != "0"

Sale = env["sale.order"].sudo()
Purchase = env["purchase.order"].sudo()
Move = env["account.move"].sudo()

companies = env["res.company"].sudo().search([("x_custom_event_tracking_enabled", "=", True)])
print("companies with event tracking:", companies.mapped("display_name") or "NONE — nothing to do")


def words(text):
    """Comparable words of a name or note: no markup, no punctuation, upper case."""
    text = re.sub(r"<[^>]*>", " ", text or "")
    text = text.replace("&nbsp;", " ")
    return {word for word in re.split(r"[^0-9A-Za-z]+", text.upper()) if word}


# ---------------------------------------------------------------------------
# The events we know about: every sales order that carries event data.
# ---------------------------------------------------------------------------
sources = Sale.search(
    [("company_id", "in", companies.ids), ("state", "!=", "cancel"), ("x_custom_event_name", "!=", False)]
)
events = {}  # label -> {"order": sale.order, "words": set, "date": date}
for order in sources:
    label = order._custom_event_label()
    if label and label not in events:
        events[label] = {
            "order": order,
            "words": words(order.x_custom_event_name),
            "date": order.x_custom_show_date,
        }

print("")
print("Known events (from sales orders):")
for label, event in events.items():
    print("  %-56s show=%s" % (label[:56], event["date"]))
if not events:
    print("  (none — nothing can be traced)")


def event_order_from_note(note):
    """The one event whose every name word appears in this note, or None."""
    note_words = words(note)
    if not note_words:
        return None
    hits = [event["order"] for event in events.values() if event["words"] and event["words"] <= note_words]
    return hits[0] if len(hits) == 1 else None


def event_order_from_show_date(show_date):
    """The one event on this date, or None."""
    if not show_date:
        return None
    hits = [event["order"] for event in events.values() if event["date"] == show_date]
    return hits[0] if len(hits) == 1 else None


# ---------------------------------------------------------------------------
# 1. Purchase orders: promote the note to real event fields.
# ---------------------------------------------------------------------------
print("")
print("=" * 78)
print("PURCHASE ORDERS — event read out of the header note")
po_planned, po_unmatched = [], []
for order in Purchase.search([("company_id", "in", companies.ids), ("state", "!=", "cancel")]):
    if order.x_custom_event_name or order.x_custom_show_date:
        continue
    source = event_order_from_note(order.note)
    if source:
        po_planned.append((order, source))
    elif words(order.note):
        po_unmatched.append(order)

for order, source in po_planned:
    print("  %-22s note -> %s" % (order.name, source._custom_event_label()))
if not po_planned:
    print("  (nothing to promote)")
if po_unmatched:
    print("  no event matches these notes — someone who knows the shows must decide:")
    for order in po_unmatched:
        print("    %-22s %s" % (order.name, " ".join(sorted(words(order.note)))[:60]))

if APPLY:
    for order, source in po_planned:
        order.write(
            {
                "x_custom_event_name": source.x_custom_event_name,
                "x_custom_event_location": source.x_custom_event_location,
                "x_custom_show_date": source.x_custom_show_date,
            }
        )

# The two stages below have to see the promotion above even on a dry run —
# otherwise the plan reports far less than an apply would actually do, which is
# the one thing a dry run must never get wrong.
promoted = {order.id: source for order, source in po_planned}


def purchase_event_source(order):
    """The event this purchase order belongs to: its own fields, or the one
    stage 1 read out of its note."""
    if order.x_custom_event_name:
        return order
    return promoted.get(order.id)


# ---------------------------------------------------------------------------
# 2. Order lines: stamp the analytic account.
# ---------------------------------------------------------------------------
print("")
print("=" * 78)
print("ORDER LINES — analytic distribution")
stamped_orders = 0
purchases = Purchase.search([("company_id", "in", companies.ids), ("state", "!=", "cancel")])
for model, records in (("sale.order", sources), ("purchase.order", purchases)):
    for order in records:
        source = order if model == "sale.order" else purchase_event_source(order)
        if not source:
            continue
        untagged = order._custom_event_taggable_lines().filtered(lambda line: not line.analytic_distribution)
        if not untagged:
            continue
        print("  %-14s %-22s %s line(s) -> %s" % (model, order.name, len(untagged), source._custom_event_label()))
        stamped_orders += 1
        if APPLY:
            # A confirmed sales order is locked here ("Auto Lock Confirmed
            # Sales Orders" is on), and core refuses to write Analytic
            # Distribution on a locked order. Unlock, stamp, lock again —
            # exactly what an operator would do through Action ▸ Unlock, and
            # nothing about the order's accounting changes in between.
            was_locked = order._name == "sale.order" and order.locked
            if was_locked:
                order.locked = False
            order._custom_event_apply_analytic()
            if was_locked:
                order.locked = True
if not stamped_orders:
    print("  (nothing to stamp)")

# ---------------------------------------------------------------------------
# 3. Journal items: trace each one back to its event.
# ---------------------------------------------------------------------------
print("")
print("=" * 78)
print("JOURNAL ITEMS — analytic distribution, by evidence")
lines = (
    env["account.move.line"]
    .sudo()
    .search(
        [
            ("company_id", "in", companies.ids),
            ("display_type", "=", "product"),
            ("parent_state", "!=", "cancel"),
            ("analytic_distribution", "=", False),
            # Same exclusion the live path makes: a down-payment line posts to
            # the DP liability account, and the DP invoice and the deduction on
            # the settlement net to zero. Analytic there is noise on a balance
            # sheet account, and the P&L per Event would not show it anyway.
            ("is_downpayment", "=", False),
        ]
    )
)
print("untagged product journal items:", len(lines))

by_evidence = {"sale order": [], "purchase order": [], "move event fields": [], "show date": []}
untraceable = env["account.move.line"].sudo().browse()
for line in lines:
    source = None
    evidence = None
    sale_line = line.sale_line_ids[:1] if "sale_line_ids" in line._fields else None
    if sale_line and sale_line.order_id.x_custom_event_name:
        source, evidence = sale_line.order_id, "sale order"
    elif line.purchase_line_id and purchase_event_source(line.purchase_line_id.order_id):
        source, evidence = purchase_event_source(line.purchase_line_id.order_id), "purchase order"
    elif line.move_id.x_custom_event_name:
        source, evidence = line.move_id, "move event fields"
    else:
        source = event_order_from_show_date(line.move_id.x_custom_show_date)
        evidence = "show date" if source else None
    if source and source._custom_event_label():
        by_evidence[evidence].append((line, source))
    else:
        untraceable |= line

for evidence, items in by_evidence.items():
    if not items:
        continue
    print("  via %s: %s line(s)" % (evidence, len(items)))
    seen = {}
    for line, source in items:
        seen.setdefault((line.move_id.name, source._custom_event_label()), 0)
        seen[(line.move_id.name, source._custom_event_label())] += 1
    for (move_name, label), count in sorted(seen.items()):
        print("    %-26s %2s line(s) -> %s" % (move_name, count, label[:44]))

print("  no evidence, left alone: %s line(s) in %s document(s)" % (len(untraceable), len(untraceable.move_id)))

if APPLY:
    written = 0
    for evidence, items in by_evidence.items():
        for line, source in items:
            distribution = source._custom_event_analytic_distribution()
            if distribution:
                line.analytic_distribution = distribution
                written += 1
    # Give the documents their event fields too, so the per-Show report and the
    # form both show what the analytic now says.
    for evidence, items in by_evidence.items():
        if evidence in ("sale order", "purchase order"):
            for line, source in items:
                move = line.move_id
                if not move.x_custom_event_name:
                    move.write(
                        {
                            "x_custom_event_name": source.x_custom_event_name,
                            "x_custom_event_location": source.x_custom_event_location,
                            "x_custom_show_date": move.x_custom_show_date or source.x_custom_show_date,
                        }
                    )
    env.cr.commit()
    print("")
    print(
        "APPLIED: %s purchase order(s) given event fields, %s order(s) stamped, %s journal item(s) tagged"
        % (len(po_planned), stamped_orders, written)
    )
else:
    print("")
    print("PLAN ONLY — nothing written (APPLY=0)")

# ---------------------------------------------------------------------------
# Where the P&L per Event stands afterwards.
# ---------------------------------------------------------------------------
print("")
print("=" * 78)
env.cr.execute(
    """
    SELECT count(*) FILTER (WHERE aml.analytic_distribution IS NOT NULL) AS tagged,
           count(*)                                                     AS total
      FROM account_move_line aml
      JOIN account_move am ON am.id = aml.move_id
     WHERE aml.display_type = 'product'
       AND am.state <> 'cancel'
       AND aml.company_id IN %s
    """,
    (tuple(companies.ids) or (0,),),
)
tagged, total = env.cr.fetchone()
print("product journal items now tagged: %s of %s" % (tagged, total))
