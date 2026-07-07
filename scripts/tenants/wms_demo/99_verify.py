# -*- coding: utf-8 -*-
"""
demo_wms / 99 — verification. Prints a readiness summary for the WMS demo.

Run:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
        < scripts/tenants/wms_demo/99_verify.py
"""

env = env  # provided by `odoo shell`
p = lambda m: print("[verify] " + m)


def xid_get(name):
    rec = env["ir.model.data"].search([("module", "=", "wms_demo"), ("name", "=", name)], limit=1)
    return rec.res_id if rec else False


wh = env["stock.warehouse"].browse(xid_get("wh_jdc"))
p("Warehouse: %s" % (wh.display_name if wh else "MISSING"))

bins = env["stock.location"].search_count([("usage", "=", "internal"), ("barcode", "like", "JDC-")])
p("Barcoded internal bins/zones: %d" % bins)

prods = env["product.template"].search([("barcode", "like", "899%")])
p(
    "Products w/ EAN13: %d (lot-tracked: %d, expiry-enabled: %d)"
    % (
        len(prods),
        len(prods.filtered(lambda t: t.tracking == "lot")),
        len(prods.filtered(lambda t: t.use_expiration_date)),
    )
)

po = env["purchase.order"].browse(xid_get("po_gr_demo"))
if po:
    p(
        "Inbound PO %s state=%s, receipts=%s"
        % (po.name, po.state, ", ".join("%s:%s" % (pk.name, pk.state) for pk in po.picking_ids))
    )

so = env["sale.order"].browse(xid_get("so_pick_demo"))
if so:
    p(
        "Outbound SO %s state=%s, deliveries=%s"
        % (so.name, so.state, ", ".join("%s:%s" % (pk.name, pk.state) for pk in so.picking_ids))
    )

strat = env["custom.wms.putaway.strategy"].search([("warehouse_id", "=", wh.id)]) if wh else None
if strat:
    p("Putaway strategy: %s (%d rules, set=%s)" % (strat.name, len(strat.rule_ids), strat.rule_set))

plan = env["custom.cycle.count.plan"].search([("warehouse_id", "=", wh.id)]) if wh else None
if plan:
    sess = plan.session_ids
    p("Cycle count plan: %s (sessions=%d, lines=%d)" % (plan.name, len(sess), sum(sess.mapped("line_count"))))

torule = env["custom.to.rule"].search([("warehouse_id", "=", wh.id)]) if wh else None
if torule:
    p("Transfer-order rules: %s" % ", ".join(torule.mapped("name")))

b2b = env["stock.picking"].browse(xid_get("bin2bin_picking"))
if b2b:
    p(
        "Bin-to-bin internal transfer: %s (%s -> %s) state=%s"
        % (b2b.name, b2b.location_id.name, b2b.location_dest_id.name, b2b.state)
    )

quants = env["stock.quant"].search_count([("location_id.usage", "=", "internal"), ("quantity", ">", 0)])
p("On-hand quants: %d" % quants)
p("--- demo_wms verification complete ---")
