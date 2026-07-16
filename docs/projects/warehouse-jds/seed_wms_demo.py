# -*- coding: utf-8 -*-
# WMS demo seed for presentation screenshots (run inside `odoo shell -d erp_dev`)
# Each feature block runs inside a savepoint so one failure can't roll back the rest.
from datetime import timedelta
from odoo import fields

log = []
def note(msg):
    log.append(msg)
    print("[seed]", msg)

company = env.company
admin = env.ref("base.user_admin")

def safe(label, fn):
    try:
        with env.cr.savepoint():
            fn()
        note("OK %s" % label)
    except Exception as e:
        note("SKIP %s: %s" % (label, e))

# ---------------------------------------------------------------- warehouse + locations
WH = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
if not WH:
    WH = env["stock.warehouse"].create({"name": "Main Warehouse", "code": "WH", "company_id": company.id})
stock_loc = WH.lot_stock_id

def get_loc(name, parent, vol=0.0):
    L = env["stock.location"].search([("name", "=", name), ("location_id", "=", parent.id)], limit=1)
    if not L:
        L = env["stock.location"].create({"name": name, "location_id": parent.id, "usage": "internal"})
    if vol and "volume_capacity_m3" in L._fields:
        L.volume_capacity_m3 = vol
    return L

zoneA = get_loc("Zone A - Fast Movers", stock_loc)
zoneB = get_loc("Zone B - Bulk Reserve", stock_loc)
staging = get_loc("Outbound Staging", stock_loc)
bins = {}
for code, vol, zone in [
    ("A-01-01", 2.5, zoneA), ("A-01-02", 2.5, zoneA), ("A-02-01", 3.0, zoneA),
    ("B-01-01", 8.0, zoneB), ("B-02-01", 8.0, zoneB), ("B-03-01", 8.0, zoneB),
]:
    bins[code] = get_loc(code, zone, vol=vol)
note("locations: %d bins + 3 zones" % len(bins))

# ---------------------------------------------------------------- products (Levi's themed)
def make_product(name, abc, vol, track, price):
    P = env["product.product"].search([("name", "=", name)], limit=1)
    if P:
        return P
    vals = {"name": name, "type": "consu", "list_price": price, "standard_price": round(price * 0.55, 2), "volume": vol}
    if "is_storable" in env["product.template"]._fields:
        vals["is_storable"] = True
    if track:
        vals["tracking"] = "lot"
    P = env["product.product"].create(vals)
    if "abc_class" in P._fields:
        try:
            P.abc_class = abc
        except Exception as e:
            note("abc_class set failed for %s: %s" % (name, e))
    return P

specs = [
    ("Levi's 501 Original 32x32", "A", 0.004, True, 1099000),
    ("Levi's Trucker Jacket - M", "A", 0.012, True, 1499000),
    ("Levi's 511 Slim 34x34", "B", 0.004, True, 999000),
    ("Levi's Graphic Tee - L", "C", 0.002, False, 399000),
    ("Levi's Leather Belt 95cm", "B", 0.001, False, 459000),
    ("Levi's Sherpa Trucker - XL", "C", 0.014, False, 1799000),
]
products = [make_product(*s) for s in specs]
note("products: %d" % len(products))

def make_lot(product, name, exp_days=None):
    L = env["stock.lot"].search([("name", "=", name), ("product_id", "=", product.id)], limit=1)
    if not L:
        L = env["stock.lot"].create({"name": name, "product_id": product.id, "company_id": company.id})
    if exp_days is not None and "expiration_date" in L._fields:
        L.expiration_date = fields.Datetime.now() + timedelta(days=exp_days)
    return L

def set_qty(product, location, qty, lot=None):
    env["stock.quant"]._update_available_quantity(product, location, qty, lot_id=lot)

lot_501 = make_lot(products[0], "LOT-501-2606", exp_days=400)
lot_jkt = make_lot(products[1], "LOT-TRK-2605", exp_days=5)
lot_511 = make_lot(products[2], "LOT-511-2604", exp_days=300)
for p, loc, qty, lot in [
    (products[0], bins["A-01-01"], 48, lot_501),
    (products[1], bins["A-02-01"], 12, lot_jkt),
    (products[2], bins["A-01-02"], 30, lot_511),
    (products[3], bins["B-01-01"], 200, None),
    (products[4], bins["B-02-01"], 5, None),
    (products[5], bins["B-03-01"], 60, None),
]:
    safe("quant %s" % p.name, lambda p=p, loc=loc, qty=qty, lot=lot: set_qty(p, loc, qty, lot))
note("on-hand quants seeded")

# ---------------------------------------------------------------- 1) PUTAWAY strategy + rules
def seed_putaway_strategy():
    PStrat = env["custom.wms.putaway.strategy"]
    PRule = env["custom.wms.putaway.rule"]
    strat = PStrat.search([("warehouse_id", "=", WH.id)], limit=1)
    if not strat:
        strat = PStrat.create({
            "name": "Main WH - ZWME001 (6-Tier)", "warehouse_id": WH.id,
            "rule_set": "zwme001_6tier", "auto_apply_suggestions": False, "company_id": company.id,
        })
    if not strat.rule_ids:
        rule_defs = [
            ("T1 - Fixed home bin (501)", 1, "fixed_location", bins["A-01-01"], None, None),
            ("T2 - Fast movers near dock", 2, "by_abc_velocity", zoneA, "A", None),
            ("T3 - Nearest empty in Zone A", 3, "nearest_empty", zoneA, None, None),
            ("T4 - Volume fit to bulk", 4, "by_volume", zoneB, None, None),
            ("T5 - Ambient temperature zone", 5, "by_temperature", zoneB, None, "ambient"),
            ("T6 - Site rule (Python)", 6, "custom_python", None, None, None),
        ]
        for nm, tier, kind, target, abc, temp in rule_defs:
            v = {"name": nm, "tier": tier, "kind": kind, "strategy_id": strat.id, "company_id": company.id}
            if target:
                v["target_location_id"] = target.id
            if abc:
                v["abc_class"] = abc
            if temp:
                v["temperature_zone"] = temp
            if kind == "custom_python":
                v["custom_python"] = "(candidate_locations[:1].id, 80) if candidate_locations else (False, 0)"
            if kind in ("by_abc_velocity", "nearest_empty", "by_volume"):
                v["target_location_domain"] = "[('usage','=','internal')]"
            PRule.create(v)
    note("putaway strategy + %d rules" % len(strat.rule_ids))
safe("putaway strategy", seed_putaway_strategy)

# ---------------------------------------------------------------- 1b) Inbound receipt + putaway suggestions
def seed_putaway_suggestions():
    PSug = env["custom.wms.putaway.suggestion"]
    if PSug.search([]):
        return
    strat = env["custom.wms.putaway.strategy"].search([("warehouse_id", "=", WH.id)], limit=1)
    rule0 = strat.rule_ids[:1] if strat else env["custom.wms.putaway.rule"]
    supplier = env.ref("stock.stock_location_suppliers")
    pick = env["stock.picking"].create({
        "picking_type_id": WH.in_type_id.id, "location_id": supplier.id,
        "location_dest_id": stock_loc.id, "origin": "PO Levi's SS26 Inbound",
    })
    lines_map = []
    for prod, qty, loc in [
        (products[0], 48, bins["A-01-01"]), (products[1], 12, bins["A-02-01"]),
        (products[2], 30, bins["A-01-02"]), (products[5], 60, bins["B-03-01"]),
        (products[3], 200, bins["B-01-01"]),
    ]:
        env["stock.move"].create({
            "product_id": prod.id, "product_uom_qty": qty,
            "product_uom": prod.uom_id.id, "picking_id": pick.id,
            "location_id": supplier.id, "location_dest_id": stock_loc.id,
        })
        lines_map.append((prod, loc, qty))
    pick.action_confirm()
    pick.action_assign()
    sug_meta = [
        (96, "Fixed location", "applied"), (95, "ABC velocity (A)", "applied"),
        (88, "Nearest empty: A-01-02", "pending"), (72, "Volume fit: 6.2 m3 free", "pending"),
        (55, "ABC velocity (C)", "overridden"),
    ]
    for (prod, loc, qty), (score, reason, status) in zip(lines_map, sug_meta):
        mv = pick.move_ids.filtered(lambda m: m.product_id == prod)[:1]
        ml = mv.move_line_ids[:1]
        if not ml:
            continue
        PSug.create({
            "name": "Putaway " + prod.name, "move_line_id": ml.id, "picking_id": pick.id,
            "suggested_location_id": loc.id, "original_dest_location_id": stock_loc.id,
            "rule_id": rule0.id if rule0 else False, "score": score, "reason": reason,
            "status": status, "company_id": company.id,
        })
    note("inbound receipt %s + %d suggestions" % (pick.name, PSug.search_count([])))
safe("putaway suggestions", seed_putaway_suggestions)

# ---------------------------------------------------------------- 2) CYCLE COUNT plan + session + lines
def seed_cycle_count():
    Plan = env["custom.cycle.count.plan"]
    Sess = env["custom.cycle.count.session"]
    Line = env["custom.cycle.count.line"]
    plan = Plan.search([("warehouse_id", "=", WH.id)], limit=1)
    if not plan:
        plan = Plan.create({
            "name": "Weekly ABC Count - Zone A", "warehouse_id": WH.id, "frequency": "weekly",
            "method": "abc_velocity", "target_count_per_period": 50, "state": "active", "company_id": company.id,
        })
    if Sess.search([("plan_id", "=", plan.id)]):
        return
    sess = Sess.create({"plan_id": plan.id, "scheduled_date": fields.Date.context_today(env.user)})
    sess.assigned_user_ids = [(6, 0, [admin.id])]
    line_defs = [
        (bins["A-01-01"], products[0], lot_501, 48, 48, "approved"),
        (bins["A-02-01"], products[1], lot_jkt, 12, 10, "counted"),
        (bins["A-01-02"], products[2], lot_511, 30, 33, "counted"),
        (bins["B-01-01"], products[3], None, 200, 188, "recount_required"),
        (bins["B-02-01"], products[4], None, 5, 5, "approved"),
        (bins["B-03-01"], products[5], None, 60, None, "pending"),
    ]
    for loc, prod, lot, exp, cnt, status in line_defs:
        v = {"session_id": sess.id, "location_id": loc.id, "product_id": prod.id,
             "expected_qty": exp, "status": status, "counter_user_id": admin.id}
        if lot:
            v["lot_id"] = lot.id
        if cnt is not None:
            v["counted_qty"] = cnt
            v["counted_at"] = fields.Datetime.now()
        Line.create(v)
    sess.state = "reviewing"
    sess.started_at = fields.Datetime.now()
    note("cycle count: plan + session %s with %d lines" % (sess.name, len(sess.line_ids)))
safe("cycle count", seed_cycle_count)

# ---------------------------------------------------------------- 3) TRANSFER ORDER rules + orders
def seed_transfer_orders():
    TRule = env["custom.to.rule"]
    TO = env["custom.transfer.order"]
    if not TRule.search([]):
        for nm, trig, extra in [
            ("Replenish fast bins (low-water)", "low_water_mark", {"low_water_qty": 10.0}),
            ("Pull near-expiry to QA", "expiry_approaching", {"expiry_days_ahead": 7}),
            ("Consolidate half-bins", "zone_consolidation", {}),
            ("Pre-stage today's shipments", "picking_replenishment", {}),
            ("Manual ad-hoc move", "manual", {}),
        ]:
            v = {"name": nm, "trigger": trig, "warehouse_id": WH.id, "company_id": company.id,
                 "source_location_domain": "[('usage','=','internal')]",
                 "target_location_domain": "[('usage','=','internal')]"}
            v.update(extra)
            TRule.create(v)
    if not TO.search([]):
        rule0 = TRule.search([], limit=1)
        to_defs = [
            (bins["B-02-01"], bins["A-01-01"], products[0], lot_501, 24, "proposed"),
            (bins["B-03-01"], bins["A-02-01"], products[5], None, 18, "in_progress"),
            (bins["A-02-01"], staging, products[1], lot_jkt, 12, "done"),
            (bins["B-01-01"], bins["A-01-02"], products[3], None, 50, "proposed"),
        ]
        for src, tgt, prod, lot, qty, state in to_defs:
            v = {"source_location_id": src.id, "target_location_id": tgt.id, "product_id": prod.id,
                 "planned_qty": qty, "state": state, "rule_id": rule0.id, "company_id": company.id}
            if lot:
                v["lot_id"] = lot.id
            if state in ("in_progress", "done"):
                v["picker_id"] = admin.id
            if state == "done":
                v["actual_qty"] = qty
            TO.create(v)
    note("TO: %d rules, %d orders" % (TRule.search_count([]), TO.search_count([])))
safe("transfer orders", seed_transfer_orders)

# ---------------------------------------------------------------- 4) HHT devices + scan logs
def seed_hht():
    Dev = env["hht.device"]
    SLog = env["hht.scan.log"]
    if not Dev.search([]):
        now = fields.Datetime.now()
        for nm, sn, mdl, cidr in [
            ("Receiving Dock - Bay 1", "TC52-SN10231", "zebra_tc52", "10.20.0.0/24"),
            ("Picking Cart 7", "TC72-SN44518", "zebra_tc72", "10.20.0.0/24"),
            ("Cycle Count - Floor", "CT40-SN77120", "honeywell_ct40", ""),
            ("Supervisor Phone (PWA)", "BRW-9fa2c1", "generic_browser", ""),
        ]:
            d = Dev.create({"name": nm, "device_id": sn, "model": mdl, "enabled": True,
                            "allowed_cidrs": cidr, "user_id": admin.id})
            d.write({"last_seen_at": now, "last_action_at": now,
                     "last_action_summary": "receipt LOT-501-2606 x12 @ A-01-01"})
    if not SLog.search([]):
        d1 = Dev.search([("model", "=", "zebra_tc52")], limit=1)
        d2 = Dev.search([("model", "=", "zebra_tc72")], limit=1)
        d3 = Dev.search([("model", "=", "honeywell_ct40")], limit=1)
        for dev, bc, act, loc, qty, res in [
            (d1, "0104006381999903101200", "receipt", bins["A-01-01"], 12, "ok"),
            (d1, "0104006381999903", "lookup", False, 0, "ok"),
            (d2, "0104006382001501", "issue", bins["A-01-02"], 3, "ok"),
            (d2, "0104006382001501", "transfer", bins["A-02-01"], 6, "ok"),
            (d3, "BADCODE-XYZ", "count", bins["B-01-01"], 0, "error"),
            (d3, "0104006383007701", "count", bins["B-02-01"], 5, "ok"),
        ]:
            if not dev:
                continue
            v = {"device_id": dev.id, "barcode": bc, "action": act, "qty": qty,
                 "result": res, "client_ip": "10.20.0.37"}
            if loc:
                v["location_id"] = loc.id
            if res == "error":
                v["error_message"] = "Unknown barcode format - no GS1 AI match"
            SLog.create(v)
    note("hht: %d devices, %d scan logs" % (Dev.search_count([]), SLog.search_count([])))
safe("hht", seed_hht)

# ---------------------------------------------------------------- 5) BARCODE scan session
def seed_barcode():
    BSess = env["custom.barcode.scan.session"]
    BLine = env["custom.barcode.scan.line"]
    if BSess.search([]):
        return
    pick = env["stock.picking"].create({
        "picking_type_id": WH.int_type_id.id, "location_id": zoneB.id,
        "location_dest_id": zoneA.id, "origin": "Replenishment Wave R-0042",
    })
    bs = BSess.create({"name": "Scan - Wave R-0042", "picking_id": pick.id,
                       "operator_id": admin.id, "state": "scanning"})
    for prod, lot, bc, qty in [
        (products[0], lot_501, "0104006381999903101200", 12),
        (products[2], lot_511, "0104006382001501101100", 6),
        (products[3], None, "4006383007701", 24),
    ]:
        v = {"session_id": bs.id, "product_id": prod.id, "raw_barcode": bc, "quantity": qty}
        if lot:
            v["lot_id"] = lot.id
        if "x_gs1_parsed" in BLine._fields:
            v["x_gs1_parsed"] = "{'gtin':'04006381999903','lot':'%s','qty':%d}" % ((lot.name if lot else ""), qty)
        BLine.create(v)
    note("barcode session: %d lines" % len(bs.line_ids))
safe("barcode session", seed_barcode)

# ---------------------------------------------------------------- 6) QUALITY point + check + alert + capa
def seed_quality():
    QP = env["quality.point"]
    QC = env["quality.check"]
    QA = env["quality.alert"]
    CAPA = env["custom.quality.capa"]
    if QP.search([]):
        return
    qp1 = QP.create({"name": "Incoming - Stitching & Fabric Grade", "operation": "incoming",
                     "check_kind": "pass_fail", "frequency": "every", "product_id": products[0].id})
    qp2 = QP.create({"name": "Incoming - Measure Inseam (cm)", "operation": "incoming",
                     "check_kind": "measure", "frequency": "random", "product_id": products[2].id,
                     "measure_min": 80.0, "measure_max": 82.0})
    QP.create({"name": "Outgoing - Final Pack Audit", "operation": "outgoing",
               "check_kind": "visual", "frequency": "periodic", "product_id": products[1].id})
    QC.create({"point_id": qp1.id, "state": "pass", "user_id": admin.id,
               "note": "Stitching OK, fabric grade A.", "performed_at": fields.Datetime.now()})
    c_fail = QC.create({"point_id": qp2.id, "state": "fail", "user_id": admin.id, "measure_value": 78.5,
                        "note": "Inseam below tolerance (78.5 < 80).", "performed_at": fields.Datetime.now()})
    alert = QA.create({"name": "NCR - Inseam out of tolerance", "check_id": c_fail.id,
                       "product_id": products[2].id, "state": "investigating"})
    c_fail.write({"alert_id": alert.id})
    CAPA.create({"name": "CAPA-0001", "alert_id": alert.id, "action_type": "corrective",
                 "description": "Recalibrate cutting jig; quarantine affected lot; re-inspect supplier batch.",
                 "responsible_id": admin.id, "deadline": fields.Date.context_today(env.user), "state": "in_progress"})
    note("quality: %d points, %d checks, %d alerts, %d capas" % (
        QP.search_count([]), QC.search_count([]), QA.search_count([]), CAPA.search_count([])))
safe("quality", seed_quality)

print("\n========== WMS SEED SUMMARY ==========")
for m in log:
    print(" -", m)
print("=====================================")
