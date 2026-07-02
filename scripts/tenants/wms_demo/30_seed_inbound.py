# -*- coding: utf-8 -*-
"""
demo_wms / 30 — Inbound: vendor + confirmed PO -> open receipt for GR scanning.

Run:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
        < scripts/tenants/wms_demo/30_seed_inbound.py

Sets up the EAN-SCAN-GR demo (deck slides "INBOUND / EAN SCAN GR / PUTAWAY"):
  * Vendor "PT Sport Global Distribusi".
  * A confirmed purchase.order against the JDC warehouse -> generates a
    receipt (incoming) picking sitting in 'assigned'/'confirmed'. That picking
    is what the operator opens on the handheld (custom_barcode scan session) to
    scan EAN, validate qty vs PO, capture batch/expiry on the lot, and confirm.
  * Putaway then runs on receipt validation (custom_wms_putaway hook) to slot
    goods from Input into HD / PICK bins.

Idempotent: aborts if a wms_demo PO already exists.
"""

env = env  # provided by `odoo shell`
log = lambda m: print("[30-in] " + m)

NS = "wms_demo"
MARKER = "wms_demo.inbound_seeded"


def xid_get(name):
    rec = env["ir.model.data"].search(
        [("module", "=", NS), ("name", "=", name)], limit=1)
    return rec.res_id if rec else False


if env["ir.config_parameter"].sudo().get_param(MARKER):
    log("ABORT: inbound already seeded (marker set). Clear it to re-run.")
else:
    Partner = env["res.partner"]
    PO = env["purchase.order"]
    Tmpl = env["product.template"]
    IMD = env["ir.model.data"]

    wh = env["stock.warehouse"].browse(xid_get("wh_jdc"))
    if not wh:
        raise Exception("Run 10_seed_warehouse.py first (warehouse missing).")

    # Vendor -----------------------------------------------------------
    vendor = Partner.search([("name", "=", "PT Sport Global Distribusi")], limit=1)
    if not vendor:
        vendor = Partner.create({
            "name": "PT Sport Global Distribusi",
            "company_type": "company",
            "supplier_rank": 1,
            "email": "vendor@sportglobal.example",
        })
        IMD.create({"module": NS, "name": "vendor_sport_global",
                    "model": "res.partner", "res_id": vendor.id, "noupdate": True})
        log("vendor created: PT Sport Global Distribusi")

    # Pick a handful of footwear products for the receipt --------------
    codes = ["NK-PEG-42", "AD-ULT-42", "PM-RSX-42", "NK-CRT-41"]
    qtys = {"NK-PEG-42": 60, "AD-ULT-42": 48, "PM-RSX-42": 36, "NK-CRT-41": 24}
    lines = []
    for code in codes:
        tmpl = Tmpl.search([("default_code", "=", code)], limit=1)
        if not tmpl:
            continue
        variant = tmpl.product_variant_id
        lines.append((0, 0, {
            "product_id": variant.id,
            "product_qty": qtys[code],
            "price_unit": tmpl.standard_price or 100000,
        }))

    po = PO.create({
        "partner_id": vendor.id,
        "picking_type_id": wh.in_type_id.id,
        "order_line": lines,
    })
    IMD.create({"module": NS, "name": "po_gr_demo",
                "model": "purchase.order", "res_id": po.id, "noupdate": True})
    po.button_confirm()
    log("PO %s confirmed (%d lines) — receipt picking(s): %s"
        % (po.name, len(lines), ", ".join(po.picking_ids.mapped("name")) or "none"))

    env["ir.config_parameter"].sudo().set_param(MARKER, "1")
    env.cr.commit()
    log("DONE — open the receipt on the handheld to demo EAN-SCAN GR.")
