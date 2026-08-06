# Validate the 15 receipts issued after the PO qty/price swap was repaired -- prd_levis_begbal.
#
# Third and last step of the 06-Aug-2026 incident (see 85_revert_po_qty_price_swap.py and
# 86_fix_po_qty_price_swap.py). 86 reconfirmed PO/T/EBR/2026/08/00132..00146 with the columns
# the right way round, which issued fresh receipts for 3.046 pcs. This script receives them
# IN FULL and checks that the goods-receipt journal lands where it should.
#
# Receiving in full is a business assertion -- the goods physically arrived. If a delivery is
# short, the warehouse must do it in the UI with the real counts instead of running this.
#
# Expected effect: 3.046 pcs into stock, one GR-VAL entry per move
#   Dr Inventories-textile      1.716.816.107 / Cr GR/IR Clearing-textile
#   Dr Inventories-accessories     79.733.346 / Cr GR/IR Clearing-accessories
# for Rp 1.796.549.453 -- exactly the value of the orders. The GR/IR credit is cleared later
# when the vendor bills come in.
#
#   docker exec -i -e RECV_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/87_receive_fixed_po_receipts.py
#
# Env flags:  RECV_DRY=1   -> report and roll back (default; 0 = commit)
#             RECV_FIRST   -> first PO name (default PO/T/EBR/2026/08/00132)
#             RECV_LAST    -> last  PO name (default PO/T/EBR/2026/08/00146)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[receive] " + m)

COMPANY_ID = 1
DRY = os.environ.get("RECV_DRY", "1") == "1"
FIRST = os.environ.get("RECV_FIRST", "PO/T/EBR/2026/08/00132")
LAST = os.environ.get("RECV_LAST", "PO/T/EBR/2026/08/00146")

EXPECT_PICKINGS = 15

cr = env.cr
company = env["res.company"].browse(COMPANY_ID)

# ---------------------------------------------------------------- guards ---
orders = env["purchase.order"].search(
    [("name", ">=", FIRST), ("name", "<=", LAST), ("company_id", "=", COMPANY_ID), ("state", "=", "purchase")],
    order="name",
)
if not orders:
    raise SystemExit("no confirmed orders in %s..%s -- aborting" % (FIRST, LAST))

# 86 must have run: no line may still look like a swapped one, or we would receive nonsense.
swapped = orders.order_line.filtered(
    lambda l: not l.display_type and l.product_qty >= 1000.0 and 0 < l.price_unit <= 100.0
)
if swapped:
    raise SystemExit("%d order lines still carry the qty/price swap -- run 86 first, aborting" % len(swapped))

pickings = env["stock.picking"].search([("id", "in", orders.picking_ids.ids), ("state", "=", "assigned")], order="id")
if len(pickings) != EXPECT_PICKINGS:
    raise SystemExit("expected %d ready receipts, found %d -- aborting" % (EXPECT_PICKINGS, len(pickings)))

# Every move must already be reserved in full; a short reservation would silently create a
# backorder and the receipt would only be partial.
short = pickings.move_ids.filtered(lambda m: m.quantity != m.product_uom_qty)
if short:
    raise SystemExit(
        "%d moves are not reserved in full (e.g. move %s: %s of %s) -- aborting"
        % (len(short), short[0].id, short[0].quantity, short[0].product_uom_qty)
    )

demand = round(sum(pickings.move_ids.mapped("product_uom_qty")), 2)
expected_value = round(
    sum(m.product_uom_qty * m.purchase_line_id.price_unit for m in pickings.move_ids if m.purchase_line_id), 2
)
log(
    "receipts ready: %d (%s), %s pcs, value Rp %s"
    % (len(pickings), ", ".join(pickings.mapped("name")), demand, expected_value)
)


# --------------------------------------------------------------- snapshot ---
def quants_by_usage():
    cr.execute(
        """select l.usage, coalesce(sum(q.quantity),0)
             from stock_quant q join stock_location l on l.id=q.location_id
            group by l.usage order by l.usage"""
    )
    return {r[0]: round(float(r[1]), 2) for r in cr.fetchall()}


def balances(account_ids):
    if not account_ids:
        return {}
    cr.execute(
        """select l.account_id, coalesce(sum(l.debit-l.credit),0)
             from account_move_line l join account_move m on m.id=l.move_id
            where m.state='posted' and l.company_id=%s and l.account_id in %s
            group by l.account_id""",
        (COMPANY_ID, tuple(account_ids)),
    )
    return {r[0]: round(float(r[1]), 2) for r in cr.fetchall()}


# valuation + GR/IR accounts of every category being received
accounts = env["account.account"]
for categ in pickings.move_ids.product_id.categ_id.with_company(company):
    val = categ.property_stock_valuation_account_id
    accounts |= val | val.account_stock_variation_id
accounts = accounts.with_company(company)

before = {"quants": quants_by_usage(), "gl": balances(accounts.ids)}
log("before stock: %s" % before["quants"])
log("before GL: %s" % {a.code: before["gl"].get(a.id, 0.0) for a in accounts})

# ------------------------------------------------------------- 1. validate ---
for picking in pickings:
    picking.button_validate()
    picking.invalidate_recordset(["state"])
    if picking.state != "done":
        raise SystemExit("%s ended in state %s -- aborting" % (picking.name, picking.state))
log("validated %d receipts" % len(pickings))

env.flush_all()
env.invalidate_all()

# --------------------------------------------------------------- 2. verify ---
problems = []

backorders = env["stock.picking"].search([("backorder_id", "in", pickings.ids)])
if backorders:
    problems.append("backorders were created: %s" % backorders.mapped("name"))

received = round(sum(orders.order_line.mapped("qty_received")), 2)
if received != demand:
    problems.append("qty_received is %s, expected %s" % (received, demand))

after = {"quants": quants_by_usage(), "gl": balances(accounts.ids)}
log("after  stock: %s" % after["quants"])
log("after  GL: %s" % {a.code: after["gl"].get(a.id, 0.0) for a in accounts})

expected_internal = round(before["quants"].get("internal", 0.0) + demand, 2)
if after["quants"].get("internal", 0.0) != expected_internal:
    problems.append("internal stock is %s, expected %s" % (after["quants"].get("internal"), expected_internal))

# the GR journals must move the valuation accounts up and the GR/IR accounts down by the
# same amount, and that amount must be the value of the orders
val_jes = env["account.move"].search(
    [("ref", "in", ["GR-VAL:%s" % m for m in pickings.move_ids.ids]), ("company_id", "=", COMPANY_ID)]
)
booked = round(sum(val_jes.line_ids.mapped("debit")), 2)
log("goods-receipt journals: %d entries, Rp %s" % (len(val_jes), booked))
if len(val_jes) != len(pickings.move_ids):
    problems.append("expected %d GR-VAL entries, found %d" % (len(pickings.move_ids), len(val_jes)))
if set(val_jes.mapped("state")) - {"posted"}:
    problems.append("not every GR-VAL entry is posted")
if booked != expected_value:
    problems.append("booked Rp %s, expected Rp %s" % (booked, expected_value))

for acc in accounts:
    delta = round(after["gl"].get(acc.id, 0.0) - before["gl"].get(acc.id, 0.0), 2)
    moved = round(sum(l.debit - l.credit for l in val_jes.line_ids.filtered(lambda l: l.account_id.id == acc.id)), 2)
    log("GL %s (%s): %+.2f" % (acc.code, acc.display_name, delta))
    if delta != moved:
        problems.append("GL %s moved %s but the GR journals only account for %s" % (acc.code, delta, moved))

cr.execute(
    "select count(*) from stock_quant where quantity < 0 and location_id in "
    "(select id from stock_location where usage='internal')"
)
if cr.fetchone()[0]:
    problems.append("internal quants went negative")

if problems:
    for p in problems:
        log("PROBLEM: " + p)
    cr.rollback()
    raise SystemExit("verification failed -- rolled back, nothing was changed")

log("verification OK -- %s pcs received, Rp %s booked to inventory against GR/IR" % (demand, booked))
log("GR/IR stays credited until the vendor bills are posted")

if DRY:
    cr.rollback()
    log("RECV_DRY=1 -> rolled back, database untouched")
else:
    cr.commit()
    log("committed")
