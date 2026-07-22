# -*- coding: utf-8 -*-
"""
demo_wms / 51 — native Odoo 19 slotting configuration (P0).

Run:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d rnd_wms --no-http \
        < scripts/tenants/wms_demo/51_config_native_slotting.py

Why this script exists
----------------------
The custom putaway engine used to carry its own capacity model while Odoo 19 CE
already ships the canonical one — and none of it was configured. This script
fills in the *native* records first, so the engine has real data to reason
about, then layers the supplementary WMS fields on top:

  stock.package.type       PxLxT + tare + max weight of each handling unit
  stock.storage.category   weight ceiling + per-package-type capacity per bin
  stock.putaway.rule       native category-based routing, per company
  product.category         removal strategy = FEFO (expiry-driven picking)
  stock.location           bin geometry, walk order, category reservation,
                           inbound quarantine flags

Requires 10_seed_warehouse.py to have run (locations resolved by xid).
Idempotent: guarded by an ir.config_parameter marker.
"""

env = env  # provided by `odoo shell`
log = lambda m: print("[51-native] " + m)

NS = "wms_demo"
MARKER = "wms_demo.native_slotting_configured"

IMD = env["ir.model.data"]


def xid_get(name):
    rec = IMD.search([("module", "=", NS), ("name", "=", name)], limit=1)
    return rec.res_id if rec else False


def xid_set(name, model, res_id):
    existing = IMD.search([("module", "=", NS), ("name", "=", name)], limit=1)
    if existing:
        existing.res_id = res_id
        return
    IMD.create({"module": NS, "name": name, "model": model, "res_id": res_id, "noupdate": True})


def loc(xid):
    rid = xid_get(xid)
    return env["stock.location"].browse(rid) if rid else env["stock.location"]


if env["ir.config_parameter"].sudo().get_param(MARKER):
    log("ABORT: native slotting already configured (marker set). Clear it to re-run.")
else:
    wh = env["stock.warehouse"].browse(xid_get("wh_jdc"))
    if not wh:
        raise Exception("Run 10_seed_warehouse.py first (warehouse missing).")
    company = wh.company_id

    # ==================================================================
    # 1. Feature groups — packages + advanced locations must be on, else
    #    the native menus and the package fields stay invisible.
    # ==================================================================
    groups = [
        "stock.group_stock_multi_locations",
        "stock.group_adv_location",
        "stock.group_tracking_lot",  # stock.package (handling units)
        "stock.group_production_lot",  # lots/serials, needed for FEFO
    ]
    internal_users = env.ref("base.group_user")
    enabled = []
    for xmlid in groups:
        grp = env.ref(xmlid, raise_if_not_found=False)
        if grp and internal_users not in grp.implied_ids:
            grp.sudo().write({"implied_ids": [(4, internal_users.id)]})
            enabled.append(xmlid.split(".")[-1])
    log("feature groups enabled: %s" % (", ".join(enabled) or "(already on)"))

    # ==================================================================
    # 2. stock.package.type — the handling units. This is requirement 3's
    #    "dimensi packaging: PxLxT + berat packaging", natively modelled.
    # ==================================================================
    PkgType = env["stock.package.type"]
    # name -> (length, width, height in mm, tare kg, max gross kg)
    PACKAGE_TYPES = {
        "Shoebox": (340.0, 220.0, 130.0, 0.12, 5.0),
        "Carton S": (400.0, 300.0, 200.0, 0.35, 15.0),
        "Carton M": (600.0, 400.0, 300.0, 0.60, 25.0),
        "Carton L": (800.0, 600.0, 500.0, 1.10, 40.0),
        "Pallet EUR": (1200.0, 800.0, 1500.0, 25.0, 1000.0),
    }
    pkg_types = {}
    for name, (length, width, height, tare, maxw) in PACKAGE_TYPES.items():
        xid = "pkgtype_" + name.lower().replace(" ", "_")
        rid = xid_get(xid)
        rec = PkgType.browse(rid) if rid else PkgType.search([("name", "=", name)], limit=1)
        vals = {
            "name": name,
            "packaging_length": length,
            "width": width,
            "height": height,
            "base_weight": tare,
            "max_weight": maxw,
            "barcode": "PKG-" + name.upper().replace(" ", "-"),
            "company_id": company.id,
        }
        if rec:
            rec.write(vals)
        else:
            rec = PkgType.create(vals)
        xid_set(xid, "stock.package.type", rec.id)
        pkg_types[name] = rec
    log("package types: %s" % ", ".join(pkg_types))

    # ==================================================================
    # 3. stock.storage.category — weight ceiling + how many handling units
    #    each class of bin accepts. Requirement 5's weight gate.
    # ==================================================================
    StorageCat = env["stock.storage.category"]
    Capacity = env["stock.storage.category.capacity"]
    # name -> (max_weight kg, allow_new_product, {package type: qty})
    STORAGE_CATS = {
        "HD Pallet Rack": (1200.0, "mixed", {"Pallet EUR": 1, "Carton L": 6}),
        "Pick Shelf": (80.0, "mixed", {"Shoebox": 24, "Carton S": 6}),
        "Staging Floor": (2000.0, "mixed", {"Pallet EUR": 4, "Carton M": 40}),
    }
    storage_cats = {}
    for name, (maxw, allow, caps) in STORAGE_CATS.items():
        xid = "storagecat_" + name.lower().replace(" ", "_")
        rid = xid_get(xid)
        rec = StorageCat.browse(rid) if rid else StorageCat.search([("name", "=", name)], limit=1)
        vals = {"name": name, "max_weight": maxw, "allow_new_product": allow, "company_id": company.id}
        if rec:
            rec.write(vals)
        else:
            rec = StorageCat.create(vals)
        xid_set(xid, "stock.storage.category", rec.id)
        for pkg_name, qty in caps.items():
            ptype = pkg_types[pkg_name]
            existing = Capacity.search(
                [("storage_category_id", "=", rec.id), ("package_type_id", "=", ptype.id)], limit=1
            )
            if existing:
                existing.quantity = qty
            else:
                Capacity.create(
                    {"storage_category_id": rec.id, "package_type_id": ptype.id, "quantity": qty}
                )
        storage_cats[name] = rec
    log("storage categories: %s" % ", ".join(storage_cats))

    # ==================================================================
    # 4. Bin geometry, walk order, storage category, weight.
    #    Walk sequence models the physical route: dock -> pick face -> HD.
    # ==================================================================
    dock = loc("bin_gr_in_01")
    zone_hd, zone_pick, zone_pack = loc("zone_hd"), loc("zone_pick"), loc("zone_pack")

    # (xid, storage category, LxWxH mm, walk seq)
    HD_GEOMETRY = (1300.0, 900.0, 1600.0)
    PICK_GEOMETRY = (600.0, 400.0, 350.0)

    walk = 100
    dock.write({"wms_walk_sequence": 10})
    for i in range(1, 5):
        for brand in ("nik", "adi", "pum"):
            bin_loc = loc("bin_%s_%02d" % (brand, i))
            if not bin_loc:
                continue
            walk += 10
            bin_loc.write(
                {
                    "storage_category_id": storage_cats["Pick Shelf"].id,
                    "wms_length_mm": PICK_GEOMETRY[0],
                    "wms_width_mm": PICK_GEOMETRY[1],
                    "wms_height_mm": PICK_GEOMETRY[2],
                    "wms_max_weight_kg": 80.0,
                    "wms_walk_sequence": walk,
                }
            )
    for i in range(1, 7):
        bin_loc = loc("bin_hd_a_%02d" % i)
        if not bin_loc:
            continue
        walk += 10
        bin_loc.write(
            {
                "storage_category_id": storage_cats["HD Pallet Rack"].id,
                "wms_length_mm": HD_GEOMETRY[0],
                "wms_width_mm": HD_GEOMETRY[1],
                "wms_height_mm": HD_GEOMETRY[2],
                "wms_max_weight_kg": 1200.0,
                "wms_walk_sequence": walk,
            }
        )
    pack_bin = loc("bin_pack_01")
    if pack_bin:
        pack_bin.write(
            {
                "storage_category_id": storage_cats["Staging Floor"].id,
                "wms_walk_sequence": walk + 100,
            }
        )
    log("bin geometry + walk order applied (dock=10 .. pack=%d)" % (walk + 100))

    # ==================================================================
    # 5. Category reservation (requirement 4) — Footwear owns HD racking,
    #    Apparel owns the pick face. Multi-company safe: the rules and the
    #    reservation both carry company_id.
    # ==================================================================
    cat_foot = env["product.category"].browse(xid_get("cat_footwear"))
    cat_appa = env["product.category"].browse(xid_get("cat_apparel"))
    if cat_foot and zone_hd:
        zone_hd.write({"wms_allowed_categ_ids": [(6, 0, [cat_foot.id])], "wms_enforce_categ": False})
    if cat_appa and zone_pick:
        # Pick face carries both brands' apparel and footwear singles, so the
        # reservation is left open here on purpose — enabling it is a one-liner.
        zone_pick.write({"wms_allowed_categ_ids": [(5, 0, 0)]})
    log("category reservation: HD -> %s" % (cat_foot.display_name if cat_foot else "(none)"))

    # ==================================================================
    # 6. NATIVE putaway rules (stock.putaway.rule). These route by product
    #    category and are enforced by Odoo itself, independent of the custom
    #    engine — belt and braces.
    # ==================================================================
    PutawayRule = env["stock.putaway.rule"]
    native_rules = []
    for categ, target, sc in (
        (cat_foot, zone_hd, storage_cats["HD Pallet Rack"]),
        (cat_appa, zone_pick, storage_cats["Pick Shelf"]),
    ):
        if not categ or not target:
            continue
        existing = PutawayRule.search(
            [
                ("category_id", "=", categ.id),
                ("location_in_id", "=", wh.lot_stock_id.id),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        vals = {
            "category_id": categ.id,
            "location_in_id": wh.lot_stock_id.id,
            "location_out_id": target.id,
            "storage_category_id": sc.id,
            "company_id": company.id,
            "sublocation": "closest_location",
        }
        if existing:
            existing.write(vals)
            native_rules.append(existing)
        else:
            native_rules.append(PutawayRule.create(vals))
    log("native putaway rules: %d" % len(native_rules))

    # ==================================================================
    # 7. FEFO (requirement 8). product_expiry is installed and the demo lots
    #    carry expiration_date, so FEFO is the correct strategy; the parent
    #    category gets FIFO as the safe default for non-expiring goods.
    # ==================================================================
    # NOTE: removal_strategy_id is a Many2one to product.removal, NOT a
    # Selection — assigning the string 'fefo' raises "Wrong value for ...".
    Removal = env["product.removal"]

    def removal(method):
        rec = Removal.search([("method", "=", method)], limit=1)
        if not rec:
            raise Exception("Removal strategy '%s' not found — is `stock` fully installed?" % method)
        return rec

    cat_root = env["product.category"].browse(xid_get("cat_root"))
    if cat_root:
        cat_root.removal_strategy_id = removal("fifo").id
    for categ in (cat_foot, cat_appa):
        if categ:
            categ.removal_strategy_id = removal("fefo").id
    log(
        "removal strategy: %s=fifo, Footwear/Apparel=fefo"
        % (cat_root.display_name if cat_root else "root")
    )

    # ==================================================================
    # 8. Default handling unit per product, so the engine can compute PxLxT
    #    and gross weight before anything is physically packed.
    # ==================================================================
    tmpl_defaults = {
        "cat_footwear": ("Shoebox", 1.0),
        "cat_apparel": ("Carton S", 12.0),
    }
    touched = 0
    for cat_xid, (pkg_name, per_hu) in tmpl_defaults.items():
        categ = env["product.category"].browse(xid_get(cat_xid))
        if not categ:
            continue
        products = env["product.template"].search([("categ_id", "child_of", categ.id)])
        products.write(
            {"wms_package_type_id": pkg_types[pkg_name].id, "wms_units_per_package": per_hu}
        )
        touched += len(products)
    log("default handling unit set on %d product templates" % touched)

    # ==================================================================
    # 9. Inbound quarantine + QC gate (requirements 2 and 6).
    #    The warehouse is 2-step receipt, so WH/Input IS the quarantine:
    #    goods land there, cannot be reserved for outbound, and only a QC
    #    pass releases the Input -> Stock leg.
    # ==================================================================
    input_loc = loc("loc_input") or wh.wh_input_stock_loc_id
    zone_gr = loc("zone_gr")
    qc_ready = False
    if "wms_is_qc_area" in env["stock.location"]._fields:
        for quarantine in (input_loc, zone_gr):
            if quarantine:
                quarantine.write({"wms_is_qc_area": True, "wms_block_reservation": True})
        if input_loc:
            wh.in_type_id.write({"wms_qc_required": True, "wms_qc_location_id": input_loc.id})
            qc_ready = True
        log("inbound quarantine armed on %s" % (input_loc.display_name if input_loc else "-"))
    else:
        log("SKIPPED inbound QC — custom_wms_inbound_qc is not installed on this database.")

    # ==================================================================
    # 10. Retire the two custom rules the native model now covers better,
    #     and add dimension/weight tiers to the existing strategy.
    # ==================================================================
    strat = env["custom.wms.putaway.strategy"].search([("warehouse_id", "=", wh.id)], limit=1)
    if strat:
        Rule = env["custom.wms.putaway.rule"]
        by_name = {r.name: r for r in strat.rule_ids}
        # Tier 3 was "volume fit" against the legacy m3 field; make it a real
        # dimensional fit now that package types carry PxLxT.
        t3 = by_name.get("T3 Volume fit in PICK")
        if t3:
            t3.write({"kind": "by_dimension"})
        # Give nearest-empty an actual origin so distance scoring is real.
        for name in ("T4 Next empty in PICK", "T5 Next empty in HD", "T6 Any next empty bin"):
            rule = by_name.get(name)
            if rule and dock:
                rule.write({"dock_location_id": dock.id})
        # Declarative category filter beats the safe_eval domain string.
        t1 = by_name.get("T1 Footwear -> HD racking")
        if t1 and cat_foot:
            t1.write({"product_categ_ids": [(6, 0, [cat_foot.id])], "product_domain": False})
        if not by_name.get("T3b Weight headroom in HD") and zone_hd:
            Rule.create(
                {
                    "name": "T3b Weight headroom in HD",
                    "strategy_id": strat.id,
                    "tier": 3,
                    "sequence": 20,
                    "kind": "by_weight",
                    "target_location_domain": "[('id', 'child_of', %d)]" % zone_hd.id,
                    "dock_location_id": dock.id if dock else False,
                }
            )
        log("custom strategy '%s' retuned to the native model" % strat.name)

    env["ir.config_parameter"].sudo().set_param(MARKER, "1")
    env["ir.config_parameter"].sudo().set_param("custom_wms_putaway.auto_apply_threshold", "90")
    env.cr.commit()
    log("DONE — native slotting configured (QC gate: %s)." % ("on" if qc_ready else "not installed"))
