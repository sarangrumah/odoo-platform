# -*- coding: utf-8 -*-
"""
demo_wms / 40 — On-hand stock (lots) + customer SO -> open delivery for pick&pack.

Run:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
        < scripts/tenants/wms_demo/40_seed_outbound.py

Two purposes:
  1. Seed opening on-hand into the PICK brand bins, each with a tracked lot
     (batch) + expiration date. This gives FEFO picking, cycle count, and
     bin-to-bin transfers real quants to work with.
  2. Create a confirmed sale.order -> a delivery (outgoing) picking that
     reserves against those bins. That picking drives the EAN-SCAN PICK&PACK
     demo on the handheld (scan EAN, validate qty/location, pack, PGI).

Idempotent: guarded by marker; opening stock applied once.
"""

env = env  # provided by `odoo shell`
log = lambda m: print("[40-out] " + m)

NS = "wms_demo"
MARKER = "wms_demo.outbound_seeded"


def xid_get(name):
    rec = env["ir.model.data"].search([("module", "=", NS), ("name", "=", name)], limit=1)
    return rec.res_id if rec else False


if env["ir.config_parameter"].sudo().get_param(MARKER):
    log("ABORT: outbound already seeded (marker set). Clear it to re-run.")
else:
    Tmpl = env["product.template"]
    Lot = env["stock.lot"]
    Quant = env["stock.quant"]
    Partner = env["res.partner"]
    SO = env["sale.order"]
    IMD = env["ir.model.data"]

    wh = env["stock.warehouse"].browse(xid_get("wh_jdc"))
    if not wh:
        raise Exception("Run 10_seed_warehouse.py first (warehouse missing).")

    # brand prefix -> PICK bin external id (first shelf bin of the section)
    BRAND_BIN = {"NK": "bin_nik_01", "AD": "bin_adi_01", "PM": "bin_pum_01"}
    from datetime import date, timedelta

    exp = (date.today() + timedelta(days=540)).isoformat()

    OPENING = {  # default_code -> qty
        "NK-PEG-42": 40,
        "NK-CRT-41": 30,
        "AD-ULT-42": 35,
        "AD-SMB-43": 25,
        "PM-RSX-42": 20,
        "NK-TEE-M": 100,
        "AD-TIR-M": 80,
        "PM-HOD-L": 50,
    }

    placed = 0
    for code, qty in OPENING.items():
        tmpl = Tmpl.search([("default_code", "=", code)], limit=1)
        if not tmpl:
            continue
        variant = tmpl.product_variant_id
        prefix = code[:2]
        bin_id = xid_get(BRAND_BIN.get(prefix))
        if not bin_id:
            continue
        # one batch lot per product, with expiration date
        lot = Lot.create(
            {
                "name": f"LOT-{code}-A",
                "product_id": variant.id,
                "company_id": wh.company_id.id,
                "expiration_date": exp + " 00:00:00",
            }
        )
        quant = Quant.with_context(inventory_mode=True).create(
            {
                "product_id": variant.id,
                "location_id": bin_id,
                "lot_id": lot.id,
                "inventory_quantity": qty,
            }
        )
        quant.action_apply_inventory()
        placed += 1
    log("opening stock applied for %d products (lot + expiry, in PICK bins)" % placed)

    # Customer + SO ----------------------------------------------------
    cust = Partner.search([("name", "=", "Toko Sport Retail Cikupa")], limit=1)
    if not cust:
        cust = Partner.create(
            {
                "name": "Toko Sport Retail Cikupa",
                "company_type": "company",
                "customer_rank": 1,
            }
        )
        IMD.create(
            {"module": NS, "name": "cust_toko_sport", "model": "res.partner", "res_id": cust.id, "noupdate": True}
        )

    so_lines = []
    for code, q in [("NK-PEG-42", 6), ("AD-ULT-42", 4), ("NK-TEE-M", 10)]:
        tmpl = Tmpl.search([("default_code", "=", code)], limit=1)
        if not tmpl:
            continue
        so_lines.append(
            (
                0,
                0,
                {
                    "product_id": tmpl.product_variant_id.id,
                    "product_uom_qty": q,
                },
            )
        )
    so = SO.create(
        {
            "partner_id": cust.id,
            "warehouse_id": wh.id,
            "order_line": so_lines,
        }
    )
    IMD.create({"module": NS, "name": "so_pick_demo", "model": "sale.order", "res_id": so.id, "noupdate": True})
    so.action_confirm()
    pickings = so.picking_ids
    log(
        "SO %s confirmed — delivery picking(s): %s (state: %s)"
        % (so.name, ", ".join(pickings.mapped("name")) or "none", ", ".join(set(pickings.mapped("state"))) or "n/a")
    )

    env["ir.config_parameter"].sudo().set_param(MARKER, "1")
    env.cr.commit()
    log("DONE — open the delivery on the handheld to demo EAN-SCAN PICK & PACK.")
