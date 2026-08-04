# -*- coding: utf-8 -*-
"""52_config_orderpoints.py — native SKU-level replenishment (reordering rules).

Run:  docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms \
          --http-port=8171 --gevent-port=8172 \
          < scripts/tenants/wms_demo/52_config_orderpoints.py

Complements — does not replace — ``custom_wms_to_engine``:

* the TO engine replenishes a *pick bin from a donor bin* inside the
  warehouse (low-water mark, bin-to-bin);
* a ``stock.warehouse.orderpoint`` replenishes the *warehouse from the
  supplier* (min/max per SKU, scheduler creates the RFQ).

Requirement sheet item 8 asks for both. This script fills in what the demo
lacked: a Buy route + vendor pricelist per SKU, one reordering rule per
storable product on JDC/Stock, and a scheduler run to prove RFQs appear.

Idempotent — existing rules are updated, not duplicated.
"""

import logging

from odoo import fields

_logger = logging.getLogger(__name__)

env = env  # noqa: F821 - provided by odoo shell

# Min/max per product category, in units. Footwear moves slower and costs
# more per pair than apparel, so it carries a tighter buffer.
PROFILE = {
    "Footwear": (24.0, 72.0),
    "Apparel": (40.0, 120.0),
    "_default": (10.0, 30.0),
}
LEAD_TIME_DAYS = 7

wh = env["stock.warehouse"].search([("code", "=", "JDC")], limit=1)
assert wh, "warehouse JDC not found — run 10_seed_warehouse.py first"
company = wh.company_id
stock_loc = wh.lot_stock_id

buy_route = env["stock.route"].search([("name", "ilike", "Buy")], limit=1)
vendor = env["res.partner"].search([("supplier_rank", ">", 0), ("name", "ilike", "Sport")], limit=1) or env[
    "res.partner"
].search([("supplier_rank", ">", 0)], limit=1)
assert vendor, "no supplier partner found"

products = env["product.product"].search([("is_storable", "=", True), ("type", "=", "consu")])

Orderpoint = env["stock.warehouse.orderpoint"]
SupplierInfo = env["product.supplierinfo"]

created = updated = sellers = 0
for product in products:
    # Serial-tracked goods (the IMEI device) are high-value and counted one
    # by one — they take the low default buffer, not the apparel volume.
    categ_name = "_default" if product.tracking == "serial" else (product.categ_id.name or "")
    minimum, maximum = PROFILE.get(categ_name, PROFILE["_default"])

    # 1. The product must be buyable and have a vendor, or the scheduler
    #    raises "no supplier defined" instead of creating an RFQ.
    vals = {}
    if not product.purchase_ok:
        vals["purchase_ok"] = True
    if buy_route and buy_route not in product.route_ids:
        vals["route_ids"] = [(4, buy_route.id)]
    if vals:
        product.product_tmpl_id.write(vals)

    if not product.seller_ids:
        SupplierInfo.create(
            {
                "partner_id": vendor.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "min_qty": 1.0,
                "price": product.standard_price or 100000.0,
                "delay": LEAD_TIME_DAYS,
                "company_id": company.id,
            }
        )
        sellers += 1

    # 2. One reordering rule per SKU on the warehouse stock location.
    op = Orderpoint.search(
        [
            ("product_id", "=", product.id),
            ("location_id", "=", stock_loc.id),
            ("company_id", "=", company.id),
        ],
        limit=1,
    )
    # NB: Odoo 19 dropped `qty_multiple` (rounding now goes through
    # `replenishment_uom_id`); passing it raises "Invalid field".
    op_vals = {
        "product_min_qty": minimum,
        "product_max_qty": maximum,
        "trigger": "auto",
    }
    if op:
        op.write(op_vals)
        updated += 1
    else:
        Orderpoint.create(
            dict(
                op_vals,
                product_id=product.id,
                location_id=stock_loc.id,
                warehouse_id=wh.id,
                company_id=company.id,
            )
        )
        created += 1

print(
    f"[52-orderpoints] {created} rules created, {updated} updated, "
    f"{sellers} vendor pricelist lines added (vendor {vendor.name}, "
    f"lead time {LEAD_TIME_DAYS}d)"
)

# 3. Prove it: run the procurement scheduler and report what it raised.
po_before = set(env["purchase.order"].search([]).ids)
# Odoo 19: run_scheduler lives on stock.rule, not procurement.group
# (procurement.group is no longer a registered model here).
env["stock.rule"].run_scheduler()
new_pos = env["purchase.order"].search([("id", "not in", list(po_before))])

below = Orderpoint.search([("location_id", "=", stock_loc.id)]).filtered(lambda o: o.qty_on_hand < o.product_min_qty)
print(
    f"[52-orderpoints] {len(below)} SKUs below their minimum; scheduler raised "
    f"{len(new_pos)} purchase order(s): " + ", ".join(f"{p.name} ({len(p.order_line)} lines)" for p in new_pos[:5])
)
for op in Orderpoint.search([("location_id", "=", stock_loc.id)], limit=5):
    print(
        f"    {op.product_id.default_code or op.product_id.name}: on hand "
        f"{op.qty_on_hand:g}, min {op.product_min_qty:g}, max {op.product_max_qty:g}, "
        f"to order {op.qty_to_order:g}"
    )

env["ir.config_parameter"].sudo().set_param(
    "wms_demo.orderpoints_seeded", fields.Date.context_today(env.user).isoformat()
)
env.cr.commit()
print("[52-orderpoints] DONE — committed.")
