# Normalise stock_move.value on the bad receipt and its return -- prd_levis_begbal.
#
# Residue of the 06-Aug-2026 qty/price swap (see 85/86). When PO/T/EBR/2026/08/00132 was
# reset to draft and reconfirmed, Odoo re-valued the already-done moves of receipt
# 27917/IN/00001 against the standard_price that 85 had restored: 413.011 x 413.011 per line,
# Rp 98.701.163.756.661 on the receipt and the same on its return.
#
# Nothing in the GL moved -- no account.move was created -- and the two sides mirror each
# other, so net reporting, GR/IR and on-hand value are all correct. Only a GROSS report
# ("value received in August") would read 98,7 trillion.
#
# The client chose to line the field up with what the GL actually saw: quantity x price_unit,
# i.e. Rp 191.294.913 per side -- the exact amount the GR-VAL entries booked and the reversals
# took back out. The return mirrors its origin move.
#
# stock.move.value is a plain stored Monetary column (stock_account/models/stock_move.py:24),
# not a compute, and it carries no link to any journal entry, so this write touches the GL in
# no way at all. The script proves that by comparing GL balances before and after.
#
#   docker exec -i -e VAL_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/88_normalize_swap_move_values.py
#
# Env flags:  VAL_DRY=1     -> report and roll back (default; 0 = commit)
#             VAL_PICKING   -> the receipt to normalise (default 319)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[value-fix] " + m)

COMPANY_ID = 1
DRY = os.environ.get("VAL_DRY", "1") == "1"
PICKING_ID = int(os.environ.get("VAL_PICKING", "319"))

EXPECT_MOVES = 200
EXPECT_GL_VALUE = 191294913.00  # what the GR-VAL entries booked, and the reversals took back

cr = env.cr

# ---------------------------------------------------------------- guards ---
picking = env["stock.picking"].browse(PICKING_ID).exists()
if not picking:
    raise SystemExit("picking %s not found -- aborting" % PICKING_ID)
if picking.state != "done":
    raise SystemExit("picking %s is %s, expected done -- aborting" % (picking.name, picking.state))

moves = picking.move_ids.filtered(lambda m: m.state == "done")
if len(moves) != EXPECT_MOVES:
    raise SystemExit("expected %d done moves, found %d -- aborting" % (EXPECT_MOVES, len(moves)))

returns = env["stock.move"].search([("origin_returned_move_id", "in", moves.ids)])
if len(returns) != len(moves):
    raise SystemExit("expected %d return moves, found %d -- aborting" % (len(moves), len(returns)))

# what the GL actually booked for this receipt
gl_value = round(sum(m.quantity * m.price_unit for m in moves), 2)
if gl_value != EXPECT_GL_VALUE:
    raise SystemExit("quantity x price_unit is %s, expected %s -- aborting" % (gl_value, EXPECT_GL_VALUE))

val_jes = env["account.move"].search(
    [("ref", "in", ["GR-VAL:%s" % m for m in moves.ids]), ("company_id", "=", COMPANY_ID)]
)
booked = round(sum(val_jes.line_ids.mapped("debit")), 2)
if booked != gl_value:
    raise SystemExit("GR-VAL entries booked %s but quantity x price_unit is %s -- aborting" % (booked, gl_value))
log("GR-VAL entries booked Rp %s over %d entries -- that is the target value" % (booked, len(val_jes)))


# --------------------------------------------------------------- snapshot ---
def gl_snapshot():
    cr.execute(
        """select l.account_id, coalesce(sum(l.debit-l.credit),0)
             from account_move_line l join account_move m on m.id=l.move_id
            where m.state='posted' and l.company_id=%s group by l.account_id""",
        (COMPANY_ID,),
    )
    return {r[0]: round(float(r[1]), 2) for r in cr.fetchall()}


def quants_by_usage():
    cr.execute(
        """select l.usage, coalesce(sum(q.quantity),0)
             from stock_quant q join stock_location l on l.id=q.location_id group by l.usage"""
    )
    return {r[0]: round(float(r[1]), 2) for r in cr.fetchall()}


before = {"gl": gl_snapshot(), "quants": quants_by_usage(), "moves": env["account.move"].search_count([])}
log(
    "before: receipt Rp %s, return Rp %s"
    % (round(sum(moves.mapped("value")), 2), round(sum(returns.mapped("value")), 2))
)

# ---------------------------------------------------------------- 1. write ---
for move in moves:
    move.value = round(move.quantity * move.price_unit, 2)
# the return mirrors its origin, so the pair still nets to zero
for ret in returns:
    ret.value = ret.origin_returned_move_id.value

env.flush_all()
env.invalidate_all()

# --------------------------------------------------------------- 2. verify ---
problems = []
recv_total = round(sum(moves.mapped("value")), 2)
ret_total = round(sum(returns.mapped("value")), 2)
log("after:  receipt Rp %s, return Rp %s" % (recv_total, ret_total))

if recv_total != gl_value:
    problems.append("receipt value is %s, expected %s" % (recv_total, gl_value))
if ret_total != gl_value:
    problems.append("return value is %s, expected %s" % (ret_total, gl_value))

after = {"gl": gl_snapshot(), "quants": quants_by_usage(), "moves": env["account.move"].search_count([])}
if after["gl"] != before["gl"]:
    changed = [a for a in set(before["gl"]) | set(after["gl"]) if before["gl"].get(a) != after["gl"].get(a)]
    problems.append("GL balances moved on accounts %s -- must not happen" % changed[:10])
else:
    log("GL unchanged across every account in the company")
if after["moves"] != before["moves"]:
    problems.append("account.move count changed: %s -> %s" % (before["moves"], after["moves"]))
if after["quants"] != before["quants"]:
    problems.append("quants changed: %s -> %s" % (before["quants"], after["quants"]))
else:
    log("stock unchanged: %s" % after["quants"])

if problems:
    for p in problems:
        log("PROBLEM: " + p)
    cr.rollback()
    raise SystemExit("verification failed -- rolled back, nothing was changed")

log("verification OK -- move value now mirrors the Rp %s the GL booked and reversed" % gl_value)

if DRY:
    cr.rollback()
    log("VAL_DRY=1 -> rolled back, database untouched")
else:
    cr.commit()
    log("committed")
