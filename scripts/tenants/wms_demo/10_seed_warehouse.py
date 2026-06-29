# -*- coding: utf-8 -*-
"""
demo_wms / 10 — Warehouse topology for "JD Sport Cikupa".

Run inside the container:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
        < scripts/tenants/wms_demo/10_seed_warehouse.py

Builds the storage structure the JD Sport requirement deck assumes:
  * 1 warehouse (JDC) with a 2-step receipt route (Input -> Stock) so the
    putaway engine has something to slot.
  * Storage TYPES  = zones under WH/Stock  (GR dock, HD palletised racking,
    PICK forward-pick shelving, PACK outbound staging).
  * Storage SECTIONS = brand sub-zones inside PICK (NIKE / ADIDAS / PUMA).
  * Storage BINS = leaf internal locations, each barcoded + given a volume
    capacity so by_volume / nearest_empty putaway rules can score them.

Idempotent: guarded by ir.config_parameter marker; re-running is a no-op.
External IDs are written under the ``wms_demo`` namespace so later scripts and
50_config_wms.py can resolve locations by xid.
"""

env = env  # provided by `odoo shell`
log = lambda m: print("[10-wh] " + m)

NS = "wms_demo"
MARKER = "wms_demo.warehouse_seeded"

if env["ir.config_parameter"].sudo().get_param(MARKER):
    log("ABORT: warehouse already seeded (marker set). Clear it to re-run.")
else:
    Loc = env["stock.location"]
    Wh = env["stock.warehouse"]
    IMD = env["ir.model.data"]

    def xid_set(name, model, res_id):
        existing = IMD.search([("module", "=", NS), ("name", "=", name)], limit=1)
        if existing:
            existing.res_id = res_id
            return
        IMD.create({"module": NS, "name": name, "model": model,
                    "res_id": res_id, "noupdate": True})

    def xid_get(name):
        rec = IMD.search([("module", "=", NS), ("name", "=", name)], limit=1)
        return rec.res_id if rec else False

    # ------------------------------------------------------------------
    # 1. Warehouse — 2-step receipt so putaway has an Input->Stock leg.
    # ------------------------------------------------------------------
    wh = Wh.search([("code", "=", "JDC")], limit=1)
    if not wh:
        wh = Wh.create({"name": "JD Sport Cikupa", "code": "JDC"})
        log("created warehouse JD Sport Cikupa (JDC)")
    # 2-step in so received goods land in Input, then a putaway move to Stock.
    wh.write({"reception_steps": "two_steps"})
    xid_set("wh_jdc", "stock.warehouse", wh.id)
    stock_loc = wh.lot_stock_id
    xid_set("loc_stock", "stock.location", stock_loc.id)
    if wh.wh_input_stock_loc_id:
        xid_set("loc_input", "stock.location", wh.wh_input_stock_loc_id.id)

    # ------------------------------------------------------------------
    # 2. Storage TYPES (zones) under WH/Stock.
    # ------------------------------------------------------------------
    def ensure_loc(name, parent_id, xid, barcode=None, vol=0.0, kind="internal"):
        rid = xid_get(xid)
        if rid:
            return Loc.browse(rid)
        loc = Loc.create({
            "name": name,
            "location_id": parent_id,
            "usage": kind,
            "barcode": barcode or False,
            "volume_capacity_m3": vol,
        })
        xid_set(xid, "stock.location", loc.id)
        return loc

    zones = {
        "GR":   ("GR Dock (Goods Receipt)",       "zone_gr"),
        "HD":   ("HD Palletised Racking",         "zone_hd"),
        "PICK": ("Forward Pick Area",             "zone_pick"),
        "PACK": ("Pack & Ship Staging",           "zone_pack"),
    }
    zone_locs = {}
    for code, (label, xid) in zones.items():
        zone_locs[code] = ensure_loc(label, stock_loc.id, xid, barcode=f"JDC-{code}")
    log("storage types (zones): %s" % ", ".join(zones))

    # ------------------------------------------------------------------
    # 3. Storage SECTIONS (brands) inside the PICK zone.
    # ------------------------------------------------------------------
    sections = {"NIKE": "sec_nike", "ADIDAS": "sec_adidas", "PUMA": "sec_puma"}
    section_locs = {}
    for brand, xid in sections.items():
        section_locs[brand] = ensure_loc(
            brand, zone_locs["PICK"].id, xid, barcode=f"JDC-PICK-{brand}")
    log("storage sections (brands) under PICK: %s" % ", ".join(sections))

    # ------------------------------------------------------------------
    # 4. Storage BINS.
    #    HD  = pallet racking bins (large volume).
    #    PICK/<brand> = shelf bins (small volume), barcoded for scan picking.
    # ------------------------------------------------------------------
    # HD pallet bins: HD-A-01 .. HD-A-06 (palletised, big capacity)
    for i in range(1, 7):
        code = f"HD-A-{i:02d}"
        ensure_loc(code, zone_locs["HD"].id, f"bin_{code.lower().replace('-', '_')}",
                   barcode=f"JDC-{code}", vol=2.0)
    # PICK shelf bins per brand: <BRAND>-01 .. <BRAND>-04
    for brand in sections:
        for i in range(1, 5):
            code = f"{brand[:3]}-{i:02d}"
            ensure_loc(code, section_locs[brand].id,
                       f"bin_{code.lower().replace('-', '_')}",
                       barcode=f"JDC-{code}", vol=0.25)
    # GR staging bin + PACK staging bin
    ensure_loc("GR-IN-01", zone_locs["GR"].id, "bin_gr_in_01", barcode="JDC-GR-IN-01", vol=5.0)
    ensure_loc("PACK-01", zone_locs["PACK"].id, "bin_pack_01", barcode="JDC-PACK-01", vol=5.0)
    log("bins created: 6 HD + 12 PICK (3 brands x 4) + GR-IN-01 + PACK-01")

    env["ir.config_parameter"].sudo().set_param(MARKER, "1")
    env.cr.commit()
    log("DONE — warehouse topology committed.")
