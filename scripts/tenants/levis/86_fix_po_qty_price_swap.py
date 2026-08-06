# Swap the Quantity and Unit Price columns back on PO/T/EBR/2026/08/00132 .. 00146 --
# prd_levis_begbal.
#
# Companion to 85_revert_po_qty_price_swap.py, which already neutralised the damage the
# 06-Aug-2026 upload did to stock, GL and product cost. What that script deliberately left
# alone is the content of the orders themselves; the client chose to repair them in place
# rather than cancel and re-import, so the PO numbers stay unbroken.
#
# Per line the fix is simply product_qty <-> price_unit. The extended amount is unaffected
# (the swap keeps qty x price constant), so no order changes value: 89.090.807 pcs @ Rp 1..9
# becomes ~9 pcs @ Rp 1..9 million for the same Rp 186.379.117.
#
# Each order is reset to draft, its lines are rewritten, and it is confirmed again -- which
# issues a fresh receipt with sane quantities. The cancelled receipts from the bad round and,
# for 00132, the validated receipt plus its return stay in the history on purpose: they are
# the audit trail of what happened.
#
# Both fields are written in ONE write() per line, so the new guard
# (purchase.order.line._check_levis_qty_price_swap, localization 19.0.1.25.0) sees the
# corrected pair and lets it through -- and would block the script if the swap were applied
# the wrong way round. That guard is the verification, not an obstacle.
#
#   docker exec -i -e FIX_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/86_fix_po_qty_price_swap.py
#
# Env flags:  FIX_DRY=1     -> report and roll back (default; 0 = commit)
#             FIX_FIRST     -> first PO name (default PO/T/EBR/2026/08/00132)
#             FIX_LAST      -> last  PO name (default PO/T/EBR/2026/08/00146)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[swap-fix] " + m)

COMPANY_ID = 1
DRY = os.environ.get("FIX_DRY", "1") == "1"
FIRST = os.environ.get("FIX_FIRST", "PO/T/EBR/2026/08/00132")
LAST = os.environ.get("FIX_LAST", "PO/T/EBR/2026/08/00146")

EXPECT_ORDERS = 15
# swap signature, same thresholds 85 used: this qty next to that unit price is a pasted price
SIG_QTY_MIN = 1000.0
SIG_PRICE_MAX = 100.0

cr = env.cr

# ---------------------------------------------------------------- guards ---
orders = env["purchase.order"].search(
    [("name", ">=", FIRST), ("name", "<=", LAST), ("company_id", "=", COMPANY_ID)],
    order="name",
)
if len(orders) != EXPECT_ORDERS:
    raise SystemExit("expected %d orders in %s..%s, found %d -- aborting" % (EXPECT_ORDERS, FIRST, LAST, len(orders)))

todo = orders.filtered(lambda o: o.state != "cancel")
skipped = orders - todo
if skipped:
    log("cancelled already, skipped: %s" % ", ".join(skipped.mapped("name")))
if not todo:
    raise SystemExit("every order in the range is cancelled -- nothing to do")

# 85 must have run first: nothing may still be received or invoiced, or the swap-back would
# leave the receipt/bill quantities inconsistent with the order.
for order in todo:
    lines = order.order_line.filtered(lambda l: not l.display_type)
    bad = lines.filtered(lambda l: l.product_qty >= SIG_QTY_MIN and l.price_unit <= SIG_PRICE_MAX)
    if len(bad) != len(lines):
        raise SystemExit(
            "%s: %d/%d lines match the swap signature -- range is wrong, aborting" % (order.name, len(bad), len(lines))
        )
    if any(lines.mapped("qty_received")) or any(lines.mapped("qty_invoiced")):
        raise SystemExit("%s still has received/invoiced qty -- run 85 first, aborting" % order.name)

bills = env["account.move"].search([("invoice_origin", "in", todo.mapped("name"))])
if bills:
    raise SystemExit("vendor bills exist for these orders (%s) -- aborting" % bills.mapped("name"))

open_pickings = env["stock.picking"].search(
    [("id", "in", todo.picking_ids.ids), ("state", "not in", ("cancel", "done"))]
)
if open_pickings:
    raise SystemExit("open receipts still hang off these orders: %s -- aborting" % open_pickings.mapped("name"))

log("orders to fix: %s" % ", ".join(todo.mapped("name")))

# --------------------------------------------------------------- snapshot ---
before = {
    o.id: {
        "state": o.state,
        "untaxed": round(o.amount_untaxed, 2),
        "qty": round(sum(o.order_line.mapped("product_qty")), 2),
        "price": round(sum(o.order_line.mapped("price_unit")), 2),
        "lines": len(o.order_line),
    }
    for o in todo
}
log(
    "before: %s pcs over %d lines, Rp %s"
    % (
        round(sum(v["qty"] for v in before.values()), 2),
        sum(v["lines"] for v in before.values()),
        round(sum(v["untaxed"] for v in before.values()), 2),
    )
)

# --------------------------------------------------------------- 1. swap ---
sample = []
for order in todo:
    order.button_draft()
    for line in order.order_line:
        if line.display_type:
            continue
        qty, price = line.product_qty, line.price_unit
        if len(sample) < 5:
            sample.append((order.name, line.product_id.default_code, qty, price))
        # one write, so the guard evaluates the corrected pair
        line.write({"product_qty": price, "price_unit": qty})
    order.button_confirm()
    order.invalidate_recordset(["state"])
    if order.state != before[order.id]["state"]:
        raise SystemExit(
            "%s ended in state %s, was %s -- aborting" % (order.name, order.state, before[order.id]["state"])
        )

env.flush_all()
env.invalidate_all()

for name, code, qty, price in sample:
    log("  %s  %s: %s pcs @ %s  ->  %s pcs @ %s" % (name, code, qty, price, price, qty))

# --------------------------------------------------------------- 2. verify ---
problems = []
for order in todo:
    was = before[order.id]
    now_qty = round(sum(order.order_line.mapped("product_qty")), 2)
    now_price = round(sum(order.order_line.mapped("price_unit")), 2)
    if round(order.amount_untaxed, 2) != was["untaxed"]:
        problems.append("%s value changed: %s -> %s" % (order.name, was["untaxed"], round(order.amount_untaxed, 2)))
    if now_qty != was["price"] or now_price != was["qty"]:
        problems.append(
            "%s columns not cleanly swapped: qty %s (want %s), price %s (want %s)"
            % (order.name, now_qty, was["price"], now_price, was["qty"])
        )
    if len(order.order_line) != was["lines"]:
        problems.append("%s line count changed: %s -> %s" % (order.name, was["lines"], len(order.order_line)))
    still_bad = order.order_line.filtered(
        lambda l: not l.display_type and l.product_qty >= SIG_QTY_MIN and l.price_unit <= SIG_PRICE_MAX
    )
    if still_bad:
        problems.append("%s still has %d swapped lines" % (order.name, len(still_bad)))

new_pickings = env["stock.picking"].search(
    [("id", "in", todo.picking_ids.ids), ("state", "not in", ("cancel", "done"))]
)
log(
    "fresh receipts issued: %d (%s pcs)"
    % (len(new_pickings), round(sum(new_pickings.move_ids.mapped("product_uom_qty")), 2))
)
log(
    "after: %s pcs over %d lines, Rp %s"
    % (
        round(sum(todo.order_line.mapped("product_qty")), 2),
        len(todo.order_line),
        round(sum(todo.mapped("amount_untaxed")), 2),
    )
)

if problems:
    for p in problems:
        log("PROBLEM: " + p)
    cr.rollback()
    raise SystemExit("verification failed -- rolled back, nothing was changed")

log("verification OK -- quantities and prices are the right way round, order values unchanged")

if DRY:
    cr.rollback()
    log("FIX_DRY=1 -> rolled back, database untouched")
else:
    cr.commit()
    log("committed")
