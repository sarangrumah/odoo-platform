# Revert the qty/price column swap on PO/T/EBR/2026/08/00132 .. 00149 -- prd_levis_begbal.
#
# On 06-Aug-2026 06:22-07:15 user 118 (martha.ritonga@erajaya.com) uploaded 18 purchase
# orders through the native base_import with the Quantity and Unit Price columns swapped:
#
#     product 002GV00010OS   product_qty 413011   price_unit 1.0    (should be qty 1 @ 413.011)
#     product 002GW00000OS   product_qty 698987   price_unit 2.0    (should be qty 2 @ 698.987)
#
# State before this script runs:
#     18 purchase orders, state 'purchase'      PO/T/EBR/2026/08/00132 .. 00149
#     17 receipts still 'assigned'              nothing touched stock yet
#      1 receipt  27917/IN/00001 'done'         200 moves, 124.233.901 pcs into location 104
#      0 vendor bills (qty_invoiced = 0 everywhere), 0 valuation journal entries
#     fiscalyear_lock_date = 2026-06-30, so August is open and the reversal books today
#
# This script undoes STOCK + GL + COST -- it does not decide the fate of the orders
# themselves (cancel-and-re-import vs fix-in-place is the client's call):
#
#     1. cancel the receipts that were never validated
#     2. return the validated receipt in full (native stock.return.picking wizard), so the
#        124M pcs leave the warehouse again and qty_received nets back to zero
#     3. reverse the 200 GR-VAL entries the receipt posted (Rp 191.294.913)
#     4. restore the standard_price the receipt destroyed
#
# On 2 and 3 -- why the return alone is NOT enough:
#   The receipt booked Dr Inventory / Cr GR-IR for move.value = qty x price_unit =
#   191.294.913 (the swap keeps the extended amount intact, so the MONETARY total was
#   coincidentally right). The categories are FIFO, so the receipt then dragged
#   standard_price down to near zero -- e.g. 00501373603232 went from 1.588.688 to 14,99
#   because 1.588.688 pcs "arrived" at Rp 1 next to the 14 pcs already on hand. A plain
#   return values the outgoing move at that WRECKED cost (1.425.707.029 in total), which
#   over-reverses the GL by ~1,23 miliar. So the return runs with the GR-journal suppressed
#   (the switch is flipped inside this transaction only -- other sessions never see it,
#   MVCC keeps the uncommitted value private, and it is restored before commit) and the
#   original entries are reversed explicitly instead.
#
# On 4 -- recovering the pre-import cost exactly. FIFO moving average gives
#     cost_now = (qty_before * C + qty_in * p) / (qty_before + qty_in)
# and qty_before (on hand once the return is done), qty_in and p (= move.value / qty) are
# all known, so C = (cost_now * (qty_before + qty_in) - qty_in * p) / qty_before. Products
# that held no stock before the receipt have no C to recover -- for those the intended unit
# price is the value that landed in the Quantity column of the PO line, and they are logged.
#
# The done receipt is reversed with a RETURN, not deleted: unlink() on done move lines calls
# _update_reserved_quantity(-qty) and drives the quant reserved_quantity negative
# (see 82_purge_rtv_00005.py for the SQL-purge recipe if the client ever wants the history
# erased instead of reversed).
#
#   docker exec -i -e SWAP_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/85_revert_po_qty_price_swap.py
#
# Env flags:  SWAP_DRY=1     -> report and roll back (default; 0 = commit)
#             SWAP_FIRST     -> first PO name in the range (default PO/T/EBR/2026/08/00132)
#             SWAP_LAST      -> last  PO name in the range (default PO/T/EBR/2026/08/00149)
import os

from odoo import _, fields

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[swap-revert] " + m)

COMPANY_ID = 1
DRY = os.environ.get("SWAP_DRY", "1") == "1"
FIRST = os.environ.get("SWAP_FIRST", "PO/T/EBR/2026/08/00132")
LAST = os.environ.get("SWAP_LAST", "PO/T/EBR/2026/08/00149")

EXPECT_ORDERS = 18
EXPECT_CREATE_UID = 118
# swap signature: a qty this large paired with a unit price this small is a pasted price
SIG_QTY_MIN = 1000.0
SIG_PRICE_MAX = 100.0

cr = env.cr
company = env["res.company"].browse(COMPANY_ID)

# ---------------------------------------------------------------- guards ---
orders = env["purchase.order"].search(
    [("name", ">=", FIRST), ("name", "<=", LAST), ("company_id", "=", COMPANY_ID)],
    order="name",
)
if len(orders) != EXPECT_ORDERS:
    raise SystemExit("expected %d orders in %s..%s, found %d -- aborting" % (EXPECT_ORDERS, FIRST, LAST, len(orders)))

log("orders: %s" % ", ".join(orders.mapped("name")))

uids = set(orders.mapped("create_uid").ids)
if uids != {EXPECT_CREATE_UID}:
    raise SystemExit("expected all orders created by uid %s, found %s -- aborting" % (EXPECT_CREATE_UID, uids))

# every order must actually carry the swap, otherwise the range is wrong
for order in orders:
    lines = order.order_line.filtered(lambda l: not l.display_type)
    bad = lines.filtered(lambda l: l.product_qty >= SIG_QTY_MIN and l.price_unit <= SIG_PRICE_MAX)
    if len(bad) != len(lines):
        raise SystemExit(
            "%s: %d/%d lines match the swap signature -- range is wrong, aborting" % (order.name, len(bad), len(lines))
        )
log("all %d orders carry the qty/price swap on every line" % len(orders))

# The team cancels some of these by hand while this runs; those need nothing from us.
cancelled = orders.filtered(lambda o: o.state == "cancel")
if cancelled:
    log("already cancelled by the team, skipped: %s" % ", ".join(cancelled.mapped("name")))
orders = orders - cancelled
if not orders:
    raise SystemExit("every order in the range is already cancelled -- nothing to do")

invoiced = orders.order_line.filtered(lambda l: l.qty_invoiced)
if invoiced:
    raise SystemExit("orders already have invoiced qty on lines %s -- handle the bills first" % invoiced.ids[:10])
bills = env["account.move"].search([("invoice_origin", "in", orders.mapped("name"))])
if bills:
    raise SystemExit("vendor bills exist for these orders (%s) -- aborting" % bills.mapped("name"))

pickings = env["stock.picking"].search([("id", "in", orders.picking_ids.ids)], order="id")
done = pickings.filtered(lambda p: p.state == "done")
open_ = pickings.filtered(lambda p: p.state not in ("done", "cancel"))
already_cancelled = pickings.filtered(lambda p: p.state == "cancel")
log(
    "receipts: %d total -- %d done (%s), %d open, %d cancelled"
    % (len(pickings), len(done), ", ".join(done.mapped("name")) or "-", len(open_), len(already_cancelled))
)

if done.mapped("return_ids"):
    raise SystemExit("the done receipt already has returns %s -- aborting" % done.mapped("return_ids").ids)

# The validated receipt booked one GR-VAL entry per move (Dr inventory / Cr GR-IR clearing).
# Their MONETARY total is coincidentally right -- the swap keeps qty x price constant -- so the
# only GL damage is the unit cost behind it. The return must reverse them to the last rupiah.
val_jes = env["account.move"].search(
    [("ref", "in", ["GR-VAL:%s" % m for m in done.move_ids.ids]), ("company_id", "=", COMPANY_ID)]
)
# account.code is company-dependent in Odoo 19 -- read it with the company in context
val_accounts = val_jes.line_ids.account_id.with_company(company)
if val_jes:
    if set(val_jes.mapped("state")) != {"posted"}:
        raise SystemExit("valuation entries are not all posted -- aborting")
    log(
        "valuation entries: %d posted, total Dr %s over accounts %s"
        % (
            len(val_jes),
            round(sum(val_jes.line_ids.mapped("debit")), 2),
            ", ".join(sorted(val_accounts.mapped("code"))),
        )
    )
if company.restrictive_audit_trail:
    log("NOTE: restrictive_audit_trail is on -- the reversal adds entries, it cannot erase them")


# --------------------------------------------------------------- snapshot ---
def quants_by_usage():
    cr.execute(
        """select l.usage, coalesce(sum(q.quantity),0), coalesce(sum(q.reserved_quantity),0)
             from stock_quant q join stock_location l on l.id=q.location_id
            group by l.usage order by l.usage"""
    )
    return {r[0]: (round(float(r[1]), 2), round(float(r[2]), 2)) for r in cr.fetchall()}


def received():
    orders.order_line.invalidate_recordset(["qty_received"])
    return round(sum(orders.order_line.mapped("qty_received")), 2)


def balances():
    """Posted balance of every account the receipt's valuation entries touched."""
    if not val_accounts:
        return {}
    cr.execute(
        """select l.account_id, coalesce(sum(l.debit-l.credit),0)
             from account_move_line l join account_move m on m.id=l.move_id
            where m.state='posted' and l.company_id=%s and l.account_id in %s
            group by l.account_id""",
        (COMPANY_ID, tuple(val_accounts.ids)),
    )
    return {r[0]: round(float(r[1]), 2) for r in cr.fetchall()}


before = {"quants": quants_by_usage(), "received": received(), "gl": balances()}
log("before quants (qty, reserved) per usage: %s" % before["quants"])
log("before qty_received over the orders: %s" % before["received"])
log("before GL: %s" % {a.code: before["gl"].get(a.id, 0.0) for a in val_accounts})

# ------------------------------------------------- 1. cancel open receipts ---
if open_:
    open_.action_cancel()
    log("cancelled %d open receipts: %s" % (len(open_), ", ".join(open_.mapped("name"))))
else:
    log("no open receipts to cancel")

# ------------------------------------------- 2. return the validated receipt ---
# Snapshot what the receipt did per product BEFORE returning it: qty in, unit price used,
# and the cost it left behind. Needed to rebuild standard_price in step 4.
SUPPRESS_PARAM = "custom_levis_localization.suppress_gr_journal"
Param = env["ir.config_parameter"].sudo()

recv = {}
for move in done.move_ids.filtered(lambda m: m.state == "done"):
    qty, val = move.product_qty, move.value
    entry = recv.setdefault(move.product_id.id, {"qty": 0.0, "val": 0.0})
    entry["qty"] += qty
    entry["val"] += val
for pid, entry in recv.items():
    product = env["product.product"].browse(pid).with_company(company)
    entry["price"] = entry["val"] / entry["qty"] if entry["qty"] else 0.0
    entry["cost_now"] = product.standard_price
log(
    "receipt touched %d products, %s pcs, value %s"
    % (len(recv), round(sum(e["qty"] for e in recv.values()), 2), round(sum(e["val"] for e in recv.values()), 2))
)

returns = env["stock.picking"]
suppress_before = Param.get_param(SUPPRESS_PARAM, "0")
Param.set_param(SUPPRESS_PARAM, "1")  # private to this transaction, restored below
try:
    for picking in done:
        wizard = (
            env["stock.return.picking"]
            .with_context(active_id=picking.id, active_model="stock.picking")
            .create({"picking_id": picking.id})
        )
        for line in wizard.product_return_moves:
            line.quantity = line.move_id.quantity
        ret = wizard._create_return()
        ret.move_ids.write({"picked": True})
        for move in ret.move_ids:
            move.quantity = move.product_uom_qty
        ret.button_validate()
        ret.invalidate_recordset(["state"])
        if ret.state != "done":
            raise SystemExit("return %s ended in state %s -- aborting" % (ret.name, ret.state))
        returns |= ret
        log(
            "returned %s -> %s (%d moves, %s pcs) state=%s"
            % (picking.name, ret.name, len(ret.move_ids), round(sum(ret.move_ids.mapped("quantity")), 2), ret.state)
        )
finally:
    Param.set_param(SUPPRESS_PARAM, suppress_before)
    log("suppress_gr_journal restored to %r" % suppress_before)

stray = env["account.move"].search(
    [("ref", "in", ["GR-RET-VAL:%s" % m for m in returns.move_ids.ids]), ("company_id", "=", COMPANY_ID)]
)
if stray:
    raise SystemExit("the return posted %d GR-RET-VAL entries despite the switch -- aborting" % len(stray))

env.flush_all()
env.invalidate_all()

# --------------------------------------- 3. reverse the receipt's GL entries ---
if val_jes:
    reversals = val_jes._reverse_moves(
        [
            {"date": fields.Date.context_today(env["account.move"]), "ref": _("Reversal of %s", je.ref)}
            for je in val_jes
        ],
        cancel=True,
    )
    if len(reversals) != len(val_jes):
        raise SystemExit("expected %d reversals, got %d -- aborting" % (len(val_jes), len(reversals)))
    if set(reversals.mapped("state")) != {"posted"}:
        raise SystemExit("some reversals are not posted -- aborting")
    log("reversed %d GR-VAL entries (Rp %s)" % (len(reversals), round(sum(val_jes.line_ids.mapped("debit")), 2)))
    env.flush_all()

# ------------------------------------------------ 4. restore standard_price ---
fallback = []
for pid, entry in sorted(recv.items()):
    product = env["product.product"].browse(pid).with_company(company)
    qty_before = round(product.qty_available, 6)
    if qty_before > 0:
        cost = (entry["cost_now"] * (qty_before + entry["qty"]) - entry["qty"] * entry["price"]) / qty_before
    else:
        # no stock before the receipt -> nothing to average back out of; fall back to the
        # unit price that the upload put in the Quantity column
        pol = env["purchase.order.line"].search([("order_id", "in", orders.ids), ("product_id", "=", pid)], limit=1)
        cost = pol.product_qty if pol else entry["cost_now"]
        fallback.append((product.default_code, cost))
    product.standard_price = cost

env.flush_all()
env.invalidate_all()
if fallback:
    log("no pre-receipt stock, cost taken from the PO line: %s" % fallback)

# --------------------------------------------------------------- 3. verify ---
after = {"quants": quants_by_usage(), "received": received(), "gl": balances()}
log("after  quants (qty, reserved) per usage: %s" % after["quants"])
log("after  qty_received over the orders: %s" % after["received"])
log("after  GL: %s" % {a.code: after["gl"].get(a.id, 0.0) for a in val_accounts})

problems = []
# the receipt's own posting must be gone and nothing else may have moved, so every account
# has to land exactly one receipt-worth lower than it was
for acc in val_accounts:
    booked = round(sum(l.debit - l.credit for l in val_jes.line_ids.filtered(lambda l: l.account_id.id == acc.id)), 2)
    was, now = before["gl"].get(acc.id, 0.0), after["gl"].get(acc.id, 0.0)
    expected = round(was - booked, 2)
    log("GL %s: %s -> %s (expected %s, receipt had booked %s)" % (acc.code, was, now, expected, booked))
    if now != expected:
        problems.append("GL %s (%s) is %s, expected %s" % (acc.code, acc.display_name, now, expected))
if after["received"] != 0.0:
    problems.append("qty_received did not net to zero: %s" % after["received"])

expected_internal = round(before["quants"].get("internal", (0.0, 0.0))[0] - before["received"], 2)
got_internal = after["quants"].get("internal", (0.0, 0.0))[0]
if got_internal != expected_internal:
    problems.append("internal stock is %s, expected %s" % (got_internal, expected_internal))

cr.execute(
    "select count(*) from stock_quant where quantity < 0 and location_id in (select id from stock_location where usage='internal')"
)
n_neg = cr.fetchone()[0]
if n_neg:
    problems.append("%s internal quants went negative" % n_neg)
cr.execute("select count(*) from stock_quant where reserved_quantity < 0")
n_res = cr.fetchone()[0]
if n_res:
    problems.append("%s quants have negative reserved_quantity" % n_res)

# the restored cost must land on the real supplier price -- which is exactly the number the
# upload dropped into the Quantity column, so the two are cross-checked against each other
cost_off = []
for pid, entry in sorted(recv.items()):
    product = env["product.product"].browse(pid).with_company(company)
    pol = env["purchase.order.line"].search([("order_id", "in", orders.ids), ("product_id", "=", pid)], limit=1)
    intended = pol.product_qty if pol else 0.0
    if intended and abs(product.standard_price - intended) > max(1.0, intended * 0.01):
        cost_off.append((product.default_code, round(product.standard_price, 2), intended))
log(
    "standard_price restored for %d products (range %s .. %s)"
    % (
        len(recv),
        round(min(env["product.product"].browse(p).with_company(company).standard_price for p in recv), 2),
        round(max(env["product.product"].browse(p).with_company(company).standard_price for p in recv), 2),
    )
)
if cost_off:
    log("cost differs >1%% from the PO unit price on %d products, first 10: %s" % (len(cost_off), cost_off[:10]))

still_open = env["stock.picking"].search([("id", "in", pickings.ids), ("state", "not in", ("cancel", "done"))])
if still_open:
    problems.append("receipts still open: %s" % still_open.mapped("name"))

new_jes = env["account.move"].search(
    [("ref", "in", ["GR-RET-VAL:%s" % m for m in returns.move_ids.ids]), ("company_id", "=", COMPANY_ID)]
)
if new_jes:
    log("NOTE: the return produced valuation entries %s -- review before committing" % new_jes.mapped("name"))

if problems:
    for p in problems:
        log("PROBLEM: " + p)
    cr.rollback()
    raise SystemExit("verification failed -- rolled back, nothing was changed")

log("verification OK -- stock is back to the pre-import baseline")
log("the 18 orders are LEFT AS-IS (state 'purchase', qty_received 0) pending the client's")
log("decision: cancel + re-import (option A) or reset-to-draft + swap back (option B)")

if DRY:
    cr.rollback()
    log("SWAP_DRY=1 -> rolled back, database untouched")
else:
    cr.commit()
    log("committed")
