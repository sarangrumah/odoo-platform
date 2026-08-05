# Purge RTV/2026/00005 -- a mis-entered Return to Vendor in prd_levis_begbal.
#
# On 05-Aug-2026 08:18-08:21 the team keyed one PO Return while logged in as the shared
# Administrator account (am.ademaryadi@gmail.com, res_users id 2). The document was wrong
# and the owner decided to erase it completely rather than leave a cancelled trail.
#
# What already happened before this script runs:
#   RTV/2026/00005 (id 5, state done)
#     picking 287 32818/OUT/00002  done    move 26930  -1 pcs out of 32818/Stock
#     picking 288 14702/OUT/00002  cancel  move 26931  no effect
#     picking 289 32818/IN/00026   done    move 26932  +1 pcs back (manual undo by the team)
#     JE 33102 STJ/2026/08/8698 posted  ref GR-RET-VAL:26930  Dr 2103109121 / Cr 1113100021
#     JE 33121 STJ/2026/08/8699 posted  ref GR-VAL:26932      Dr 1113100021 / Cr 2103109121
#   The draft credit note was already deleted by the team (no in_refund exists).
#
# So stock and GL are ALREADY neutral -- the two journals cancel out and the unit is back
# on hand. This script only removes the leftover documents, and in doing so restores the
# returnable qty of POL 20210, which move 26930 had permanently consumed via
# origin_returned_move_id.
#
#   docker exec -i -e RTV_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/82_purge_rtv_00005.py
#
# Env flags:  RTV_DRY=1        -> report and roll back (default)
#             RTV_ID           -> override the po return id (default 5)
#             RTV_RESET_SEQ=1  -> roll ir.sequence custom.po.return back (default 1)
#
# NOTE on stock: the pickings/moves/move-lines are removed with raw SQL, not the ORM.
# stock.move.line.unlink() calls _update_reserved_quantity(-qty) for lines whose source is
# an internal location, which would drive reserved_quantity of the 32818/Stock quant to -1.
# The quants are already correct (26930 and 26932 cancel out), so they must not be touched.
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[purge-rtv] " + m)

COMPANY_ID = 1
RTV_ID = int(os.environ.get("RTV_ID", "5"))
DRY = os.environ.get("RTV_DRY", "1") == "1"
RESET_SEQ = os.environ.get("RTV_RESET_SEQ", "1") == "1"

EXPECT_NAME = "RTV/2026/00005"
EXPECT_DATE = "2026-08-05"
EXPECT_CREATE_UID = 2
EXPECT_AMOUNT = 1016674.00
EXPECT_PRODUCT = 386113
VALUATION_ACC = "1113100021"  # Inventories-textile
VARIATION_ACC = "2103109121"  # GR/IR Clearing-Third Parties-textile

company = env["res.company"].browse(COMPANY_ID)
cr = env.cr

# ---------------------------------------------------------------- guards ---
rtv = env["custom.po.return"].browse(RTV_ID).exists()
if not rtv:
    raise SystemExit("po return %s not found -- nothing to do" % RTV_ID)

others = env["custom.po.return"].search([("id", "!=", RTV_ID), ("state", "=", "done")])
if others:
    raise SystemExit(
        "other validated returns exist (%s) -- this script handles one record only"
        % ", ".join(others.mapped("name"))
    )

if rtv.name != EXPECT_NAME:
    raise SystemExit("expected name %s, found %s -- aborting" % (EXPECT_NAME, rtv.name))
if rtv.state != "done":
    raise SystemExit("expected state done, found %s -- aborting" % rtv.state)
if str(rtv.date) != EXPECT_DATE:
    raise SystemExit("expected date %s, found %s -- aborting" % (EXPECT_DATE, rtv.date))
if rtv.create_uid.id != EXPECT_CREATE_UID:
    raise SystemExit(
        "expected create_uid %s, found %s (%s) -- aborting"
        % (EXPECT_CREATE_UID, rtv.create_uid.id, rtv.create_uid.login)
    )

allocations = rtv.allocation_ids
if len(allocations) != 2:
    raise SystemExit("expected 2 allocations, found %d -- aborting" % len(allocations))
total = round(sum(allocations.mapped("amount")), 2)
if total != EXPECT_AMOUNT:
    raise SystemExit("expected total %s, found %s -- aborting" % (EXPECT_AMOUNT, total))

source_move_ids = sorted(set(allocations.mapped("move_id").ids))
return_move_ids = sorted(set(allocations.mapped("return_move_id").ids))
pol_ids = sorted(set(allocations.mapped("purchase_line_id").ids))

# The manual undo receipt is not referenced by the RTV -- find it through the chain.
undo_move_ids = sorted(
    env["stock.move"]
    .search([("origin_returned_move_id", "in", return_move_ids)])
    .ids
)
move_ids = sorted(set(return_move_ids + undo_move_ids))
picking_ids = sorted(
    set(env["stock.move"].browse(move_ids).mapped("picking_id").ids)
)

log("RTV %s id=%s state=%s date=%s by=%s" % (rtv.name, rtv.id, rtv.state, rtv.date, rtv.create_uid.login))
log("source receipt moves: %s   POL: %s" % (source_move_ids, pol_ids))
log("moves to delete:      %s" % move_ids)
log("pickings to delete:   %s" % picking_ids)

if len(move_ids) != 3 or len(picking_ids) != 3:
    raise SystemExit("expected 3 moves and 3 pickings, found %s / %s -- aborting" % (move_ids, picking_ids))

products = set(env["stock.move"].browse(move_ids).mapped("product_id").ids)
if products != {EXPECT_PRODUCT}:
    raise SystemExit("expected only product %s, found %s -- aborting" % (EXPECT_PRODUCT, products))

# Nothing else may hang off these pickings.
strays = env["stock.move"].search([("picking_id", "in", picking_ids), ("id", "not in", move_ids)])
if strays:
    raise SystemExit("pickings carry unrelated moves %s -- aborting" % strays.ids)

# --- the two valuation journal entries -------------------------------------
refs = ["GR-RET-VAL:%s" % m for m in return_move_ids] + ["GR-VAL:%s" % m for m in undo_move_ids]
jes = env["account.move"].search([("ref", "in", refs), ("company_id", "=", COMPANY_ID)])
log("valuation entries: %s" % [(j.id, j.name, j.ref, j.state) for j in jes])
if len(jes) != 2:
    raise SystemExit("expected 2 valuation entries for %s, found %d -- aborting" % (refs, len(jes)))
if set(jes.mapped("state")) != {"posted"}:
    raise SystemExit("valuation entries are not all posted -- aborting")
je_net = round(sum(jes.mapped("line_ids").mapped("debit")) - sum(jes.mapped("line_ids").mapped("credit")), 2)
if je_net != 0.0:
    raise SystemExit("valuation entries do not net to zero (%s) -- aborting" % je_net)
if company.restrictive_audit_trail:
    raise SystemExit("restrictive_audit_trail is on -- posted entries may not be deleted")

je_ids = jes.ids
credit_notes = allocations.mapped("credit_note_id")
if credit_notes:
    raise SystemExit("allocations still point at credit notes %s -- handle those first" % credit_notes.ids)

# --------------------------------------------------------------- snapshot ---
_accounts = {
    a.code: a
    for a in env["account.account"].with_company(company).search([("code", "in", [VALUATION_ACC, VARIATION_ACC])])
}


def bal(code):
    acc = _accounts.get(code)
    if not acc:
        return 0.0
    cr.execute(
        """select coalesce(sum(l.debit-l.credit),0) from account_move_line l
           join account_move m on m.id=l.move_id
          where m.state='posted' and l.account_id=%s and l.company_id=%s""",
        (acc.id, company.id),
    )
    return round(float(cr.fetchone()[0]), 2)


def quants():
    cr.execute(
        """select l.complete_name, q.quantity, q.reserved_quantity
             from stock_quant q join stock_location l on l.id=q.location_id
            where q.product_id=%s order by l.complete_name""",
        (EXPECT_PRODUCT,),
    )
    return {r[0]: (round(float(r[1]), 2), round(float(r[2]), 2)) for r in cr.fetchall()}


def pol_state():
    pols = env["purchase.order.line"].browse(pol_ids)
    pols.invalidate_recordset()
    return {
        p.id: (
            round(p.qty_received, 2),
            round(p.x_custom_returned_qty, 2),
            round(p.x_custom_returnable_qty, 2),
        )
        for p in pols
    }


before = {"quants": quants(), "pol": pol_state(), VALUATION_ACC: bal(VALUATION_ACC), VARIATION_ACC: bal(VARIATION_ACC)}
log("before quants: %s" % before["quants"])
log("before POL (qty_received, returned, returnable): %s" % before["pol"])
log("before GL: %s=%s  %s=%s" % (VALUATION_ACC, before[VALUATION_ACC], VARIATION_ACC, before[VARIATION_ACC]))

# ------------------------------------------------------- 1. journal entries ---
# seq 8698/8699 are not the last of the STJ/2026/08/ chain, so force_delete is needed to
# get past _unlink_forbid_parts_of_chain. This leaves a permanent numbering gap.
jes.button_draft()
jes.with_context(force_delete=True).unlink()
log("deleted valuation entries %s (STJ sequence gap left behind on purpose)" % je_ids)

# ------------------------------------------------------------ 2. RTV record ---
rtv_line_ids = rtv.line_ids.ids
allocations.unlink()
rtv.write({"state": "cancel"})  # _unlink_except_done only blocks state == done
rtv.line_ids.unlink()
rtv.unlink()
log("deleted po return %s, lines %s" % (RTV_ID, rtv_line_ids))

env.flush_all()

# -------------------------------------------------------- 3. stock documents ---
# Raw SQL on purpose -- see the note in the header. Sweep every FK that points at the
# moves/pickings first, then delete the rows themselves.
cr.execute(
    """select c.relname, a.attname
         from pg_constraint con
         join pg_class c on c.oid = con.conrelid
         join pg_attribute a on a.attrelid = c.oid and a.attnum = any(con.conkey)
        where con.contype = 'f' and con.confrelid = %s::regclass""",
    ("stock_move",),
)
move_refs = [(t, col) for (t, col) in cr.fetchall()]
cr.execute(
    """select c.relname, a.attname
         from pg_constraint con
         join pg_class c on c.oid = con.conrelid
         join pg_attribute a on a.attrelid = c.oid and a.attnum = any(con.conkey)
        where con.contype = 'f' and con.confrelid = %s::regclass""",
    ("stock_picking",),
)
picking_refs = [(t, col) for (t, col) in cr.fetchall()]

# stock_move.picking_id / stock_picking.id are dropped together at the end.
SELF = {("stock_move", "picking_id"), ("stock_move", "origin_returned_move_id"), ("stock_picking", "return_id")}

for table, col in sorted(move_refs + picking_refs):
    if (table, col) in SELF:
        continue
    ids = move_ids if (table, col) in move_refs else picking_ids
    cr.execute("select count(*) from %s where %s in %%s" % (table, col), (tuple(ids),))
    n = cr.fetchone()[0]
    if not n:
        continue
    cr.execute("delete from %s where %s in %%s" % (table, col), (tuple(ids),))
    log("swept %s rows from %s.%s" % (n, table, col))

# The wizard rows that produced the returns still point at the *source* receipt moves.
cr.execute(
    "delete from stock_return_picking_line where move_id in %s returning wizard_id",
    (tuple(source_move_ids + move_ids),),
)
wizard_ids = sorted({r[0] for r in cr.fetchall() if r[0]})
if wizard_ids:
    cr.execute("delete from stock_return_picking where id in %s", (tuple(wizard_ids),))
    log("removed return wizards %s" % wizard_ids)

# Break the return chain -- this is what gives POL 20210 its returnable qty back.
cr.execute(
    "update stock_move set origin_returned_move_id = null where id in %s or origin_returned_move_id in %s",
    (tuple(move_ids), tuple(move_ids)),
)
cr.execute("update stock_picking set return_id = null where id in %s or return_id in %s", (tuple(picking_ids), tuple(picking_ids)))
cr.execute("delete from stock_move where id in %s", (tuple(move_ids),))
log("deleted stock moves %s" % move_ids)
cr.execute("delete from stock_picking where id in %s", (tuple(picking_ids),))
log("deleted stock pickings %s" % picking_ids)

env.invalidate_all()

# purchase.order.line.qty_received is a stored compute fed by these moves.
pols = env["purchase.order.line"].browse(pol_ids)
pols.modified(["move_ids"])
env.flush_all()

# ---------------------------------------------------------- 4. RTV sequence ---
seq = env["ir.sequence"].search([("code", "=", "custom.po.return")], limit=1)
if seq and RESET_SEQ:
    old_next = seq.number_next_actual
    if env["custom.po.return"].search_count([]) == 0:
        seq.sudo().write({"number_next_actual": 1})
        log("ir.sequence custom.po.return number_next %s -> 1" % old_next)
    else:
        log("other returns exist -- leaving ir.sequence at %s" % old_next)

# --------------------------------------------------------------- 5. verify ---
after = {"quants": quants(), "pol": pol_state(), VALUATION_ACC: bal(VALUATION_ACC), VARIATION_ACC: bal(VARIATION_ACC)}
log("after  quants: %s" % after["quants"])
log("after  POL (qty_received, returned, returnable): %s" % after["pol"])
log("after  GL: %s=%s  %s=%s" % (VALUATION_ACC, after[VALUATION_ACC], VARIATION_ACC, after[VARIATION_ACC]))

problems = []
if after["quants"] != before["quants"]:
    problems.append("quants changed: %s -> %s" % (before["quants"], after["quants"]))
for code in (VALUATION_ACC, VARIATION_ACC):
    if after[code] != before[code]:
        problems.append("GL %s changed: %s -> %s" % (code, before[code], after[code]))
for pid in pol_ids:
    if after["pol"][pid][0] != before["pol"][pid][0]:
        problems.append("POL %s qty_received changed: %s -> %s" % (pid, before["pol"][pid][0], after["pol"][pid][0]))
    if after["pol"][pid][1] != 0.0:
        problems.append("POL %s still shows returned qty %s" % (pid, after["pol"][pid][1]))

for model, table in (
    ("custom.po.return", "custom_po_return"),
    ("custom.po.return.line", "custom_po_return_line"),
    ("custom.po.return.allocation", "custom_po_return_allocation"),
):
    cr.execute("select count(*) from %s" % table)
    n = cr.fetchone()[0]
    log("%s rows left: %s" % (table, n))
    if n:
        problems.append("%s still has %s rows" % (table, n))

cr.execute("select count(*) from stock_move where id in %s", (tuple(move_ids),))
if cr.fetchone()[0]:
    problems.append("stock moves survived")
cr.execute("select count(*) from stock_picking where id in %s", (tuple(picking_ids),))
if cr.fetchone()[0]:
    problems.append("stock pickings survived")
cr.execute("select count(*) from account_move where id in %s", (tuple(je_ids),))
if cr.fetchone()[0]:
    problems.append("journal entries survived")
cr.execute(
    "select count(*) from stock_move where origin_returned_move_id in %s", (tuple(source_move_ids),)
)
n = cr.fetchone()[0]
log("returns still hanging off source receipts %s: %s" % (source_move_ids, n))
if n:
    problems.append("source receipt moves still carry returns")

if problems:
    for p in problems:
        log("PROBLEM: " + p)
    cr.rollback()
    raise SystemExit("verification failed -- rolled back, nothing was changed")

log("verification OK")

if DRY:
    cr.rollback()
    log("RTV_DRY=1 -> rolled back, database untouched")
else:
    cr.commit()
    log("committed")
