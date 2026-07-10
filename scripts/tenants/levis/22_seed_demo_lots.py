# Seed demo_levis (lot-tracked, real_time/FIFO valuation) with transactions.
# Stage 1: cost(60%), customers, stock-on-hand(lots), purchases->bill->payment,
# sales->invoice->payment, manual JE. POS in 23_seed_pos_lots.py.
import uuid
from datetime import date

env = env
log = lambda m: print("[seed] " + m)

if env["sale.order"].search_count([]) or env["purchase.order"].search_count([]):
    log("transactions already present - aborting")
else:
    company = env["res.company"].browse(1)
    env["ir.config_parameter"].sudo().set_param("database.uuid", str(uuid.uuid4()))
    env["ir.config_parameter"].sudo().set_param("database.secret", str(uuid.uuid4()))
    D1, D2 = date(2026, 6, 5), date(2026, 6, 12)
    BANK = env["account.journal"].search([("type", "=", "bank")], limit=1)
    PRODUCT_IDS = [195132, 195136, 195141, 195145, 195155, 195165, 195170, 385974]
    products = env["product.product"].browse(PRODUCT_IDS).exists()

    # cost = 60% of sale price (variant level) so margins/valuation are realistic
    for p in products:
        p.standard_price = round(p.lst_price * 0.6)
    log("cost set on %d products" % len(products))

    def lot_for(p):
        L = env["stock.lot"].search([("product_id", "=", p.id)], limit=1)
        if not L:
            L = env["stock.lot"].create(
                {"name": "LOT-%s" % (p.default_code or p.id), "product_id": p.id, "company_id": company.id}
            )
        return L

    def validate_picking(picking, incoming=False):
        picking.action_assign()
        for mv in picking.move_ids:
            if not mv.move_line_ids:
                vals = {
                    "move_id": mv.id,
                    "picking_id": picking.id,
                    "product_id": mv.product_id.id,
                    "location_id": mv.location_id.id,
                    "location_dest_id": mv.location_dest_id.id,
                    "quantity": mv.product_uom_qty,
                    "product_uom_id": mv.product_uom.id,
                }
                env["stock.move.line"].create(vals)
            for ml in mv.move_line_ids:
                if not ml.quantity:
                    ml.quantity = mv.product_uom_qty
                if mv.product_id.tracking != "none" and not ml.lot_id and not ml.lot_name:
                    if incoming:
                        ml.lot_name = "PO-%s" % (mv.product_id.default_code or mv.product_id.id)
                    else:
                        ml.lot_id = lot_for(mv.product_id).id
                if "picked" in ml._fields:
                    ml.picked = True
            if "picked" in mv._fields:
                mv.picked = True
        res = picking.button_validate()
        if isinstance(res, dict) and res.get("res_model"):
            w = env[res["res_model"]].with_context(res.get("context", {})).browse(res.get("res_id"))
            if w and hasattr(w, "process"):
                w.process()
        return picking.state

    def pay(moves, pay_date):
        env["account.payment.register"].with_context(active_model="account.move", active_ids=moves.ids).create(
            {"journal_id": BANK.id, "payment_date": pay_date}
        ).action_create_payments()

    # A. customers
    customers = env["res.partner"]
    for d in [("Andi Wijaya", False), ("Toko Sinar Jaya", True), ("PT Mitra Ritel Nusantara", True)]:
        customers |= env["res.partner"].create(
            {"name": d[0], "is_company": d[1], "customer_rank": 1, "country_id": env.ref("base.id").id}
        )
    log("customers: %d" % len(customers))
    env.cr.commit()

    # B. stock on hand (one lot per product, placed in WH + 3 stores)
    n = 0
    for p in products:
        L = lot_for(p)
        for loc in [5, 20, 26, 32]:
            qty = 200 if loc == 5 else 100
            q = (
                env["stock.quant"]
                .with_context(inventory_mode=True)
                .create({"product_id": p.id, "location_id": loc, "lot_id": L.id, "inventory_quantity": qty})
            )
            q.action_apply_inventory()
            n += 1
    log("stock quants (lots) applied: %d" % n)
    env.cr.commit()

    # C. purchases -> receipt(lot) -> bill -> payment
    vendors = env["res.partner"].search([("supplier_rank", ">", 0)], limit=2)
    made = []
    for vi, vendor in enumerate(vendors):
        lines = [
            (0, 0, {"product_id": p.id, "product_qty": 40, "price_unit": round(p.lst_price * 0.55)})
            for p in products[vi * 3 : vi * 3 + 3]
        ]
        po = env["purchase.order"].create({"partner_id": vendor.id, "date_order": D1, "order_line": lines})
        po.button_confirm()
        for pk in po.picking_ids:
            validate_picking(pk, incoming=True)
        po.action_create_invoice()
        bill = po.invoice_ids.filtered(lambda m: m.state == "draft")
        bill.invoice_date = D1
        bill.action_post()
        pay(bill, D2)
        made.append(po.name)
    log("purchases: %s" % made)
    env.cr.commit()

    # D. sales -> delivery(lot) -> invoice -> payment
    somade = []
    for i, cust in enumerate(customers):
        lines = [(0, 0, {"product_id": p.id, "product_uom_qty": 3 + i}) for p in products[i * 2 : i * 2 + 2]]
        so = env["sale.order"].create({"partner_id": cust.id, "date_order": D1, "order_line": lines})
        so.action_confirm()
        for pk in so.picking_ids:
            validate_picking(pk, incoming=False)
        inv = so._create_invoices()
        inv.invoice_date = D2
        inv.action_post()
        pay(inv, D2)
        somade.append(so.name)
    log("sales: %s" % somade)
    env.cr.commit()

    # E. manual accounting entry
    misc = env["account.journal"].search([("type", "=", "general"), ("code", "=", "MISC")], limit=1)
    exp = env["account.account"].with_company(1).search([("code", "=", "7214001000")], limit=1)
    cash = env["account.account"].with_company(1).search([("code", "=", "1102000001")], limit=1)
    if misc and exp and cash:
        je = env["account.move"].create(
            {
                "journal_id": misc.id,
                "date": D2,
                "ref": "Demo accrual - office rental",
                "line_ids": [
                    (0, 0, {"account_id": exp.id, "name": "Office rental Jun", "debit": 1500000, "credit": 0}),
                    (0, 0, {"account_id": cash.id, "name": "Cash out", "debit": 0, "credit": 1500000}),
                ],
            }
        )
        je.action_post()
        log("manual JE: %s" % je.name)
    env.cr.commit()

    log("==== STAGE1 SUMMARY ====")
    for m in ["res.partner", "purchase.order", "sale.order", "account.move", "account.payment", "stock.lot"]:
        log("%-16s : %d" % (m, env[m].search_count([])))
    log("==== DONE ====")
