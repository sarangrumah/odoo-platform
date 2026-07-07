# -*- coding: utf-8 -*-
"""
demo_wms / 50 — WMS configuration: putaway strategy, cycle count, TO rules.

Run:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
        < scripts/tenants/wms_demo/50_config_wms.py

Wires the three custom WMS engines to the JDC topology so each deck flow is
demonstrable out of the box:

  PUTAWAY (custom_wms_putaway)  — one ZWME001 6-tier strategy:
     Tier 1 fixed_location : Footwear -> HD palletised racking.
     Tier 2 by_abc_velocity: A-class fast movers -> NIKE pick section.
     Tier 3 by_volume      : best volumetric fit inside PICK.
     Tier 4 nearest_empty  : next empty bin within PICK (same section family).
     Tier 5 nearest_empty  : next empty bin within HD.
     Tier 6 nearest_empty  : any internal bin (last-resort next empty bin).

  STOCK OPNAME (custom_wms_cycle_count) — a by-zone plan scoped to PICK, plus
     an immediately-started session so the handheld scan-count flow + New Item /
     New Remark + variance approval can be shown live.

  BIN-TO-BIN (custom_wms_to_engine) — a low-water-mark replenishment rule
     (HD -> PICK) and a manual transfer order, both materialising stock.move
     internal transfers that the handheld confirms (scan source bin, scan dest).

Idempotent: guarded by marker.
"""

env = env  # provided by `odoo shell`
log = lambda m: print("[50-cfg] " + m)

NS = "wms_demo"
MARKER = "wms_demo.wms_configured"


def xid_get(name):
    rec = env["ir.model.data"].search([("module", "=", NS), ("name", "=", name)], limit=1)
    return rec.res_id if rec else False


if env["ir.config_parameter"].sudo().get_param(MARKER):
    log("ABORT: WMS already configured (marker set). Clear it to re-run.")
else:
    wh = env["stock.warehouse"].browse(xid_get("wh_jdc"))
    if not wh:
        raise Exception("Run 10_seed_warehouse.py first (warehouse missing).")

    zone_hd = xid_get("zone_hd")
    zone_pick = xid_get("zone_pick")
    sec_nike = xid_get("sec_nike")
    cat_foot = xid_get("cat_footwear")

    Strategy = env["custom.wms.putaway.strategy"]
    Rule = env["custom.wms.putaway.rule"]

    # ------------------------------------------------------------------
    # 1. Putaway strategy — ZWME001 6-tier.
    # ------------------------------------------------------------------
    strat = Strategy.search([("warehouse_id", "=", wh.id)], limit=1)
    if not strat:
        strat = Strategy.create(
            {
                "name": "JDC ZWME001 Putaway",
                "warehouse_id": wh.id,
                "rule_set": "zwme001_6tier",
                "auto_apply_suggestions": False,  # surface low-confidence for HHT review
            }
        )
    if not strat.rule_ids:
        Rule.create(
            [
                {
                    "name": "T1 Footwear -> HD racking",
                    "strategy_id": strat.id,
                    "tier": 1,
                    "kind": "fixed_location",
                    "target_location_id": zone_hd,
                    "product_domain": "[('categ_id', 'child_of', %d)]" % cat_foot,
                },
                {
                    "name": "T2 A-class -> NIKE pick",
                    "strategy_id": strat.id,
                    "tier": 2,
                    "kind": "by_abc_velocity",
                    "abc_class": "A",
                    "target_location_id": sec_nike,
                },
                {
                    "name": "T3 Volume fit in PICK",
                    "strategy_id": strat.id,
                    "tier": 3,
                    "kind": "by_volume",
                    "target_location_domain": "[('location_id', 'child_of', %d)]" % zone_pick,
                },
                {
                    "name": "T4 Next empty in PICK",
                    "strategy_id": strat.id,
                    "tier": 4,
                    "kind": "nearest_empty",
                    "target_location_domain": "[('id', 'child_of', %d)]" % zone_pick,
                },
                {
                    "name": "T5 Next empty in HD",
                    "strategy_id": strat.id,
                    "tier": 5,
                    "kind": "nearest_empty",
                    "target_location_domain": "[('id', 'child_of', %d)]" % zone_hd,
                },
                {"name": "T6 Any next empty bin", "strategy_id": strat.id, "tier": 6, "kind": "nearest_empty"},
            ]
        )
        log("putaway strategy '%s' created with 6 tiers" % strat.name)

    # ------------------------------------------------------------------
    # 2. Cycle count (Stock Opname) plan + a started session.
    # ------------------------------------------------------------------
    Plan = env["custom.cycle.count.plan"]
    plan = Plan.search([("warehouse_id", "=", wh.id)], limit=1)
    if not plan:
        plan = Plan.create(
            {
                "name": "JDC PICK Zone Opname",
                "warehouse_id": wh.id,
                "frequency": "weekly",
                "method": "by_zone",
                "scope_zone_ids": [(6, 0, [zone_pick])],
                "target_count_per_period": 30,
            }
        )
        env["ir.model.data"].create(
            {
                "module": NS,
                "name": "cc_plan_pick",
                "model": "custom.cycle.count.plan",
                "res_id": plan.id,
                "noupdate": True,
            }
        )
        # Materialise one session now so the demo has counting lines ready.
        wiz = env["custom.cycle.count.start.wizard"].create({"plan_id": plan.id})
        wiz.action_start()
        sess = plan.session_ids[:1]
        if sess:
            sess.action_start()
        log("cycle count plan + started session (%d lines)" % (sess.line_count if sess else 0))

    # ------------------------------------------------------------------
    # 3. Bin-to-bin: HD -> PICK replenishment.
    #    NOTE: the runtime deployed under /opt may still carry the pre-73cf11d
    #    3-arg safe_eval bug in custom.to.rule. To stay robust we create the
    #    rule WITHOUT location domains (the domain constraint is skipped when
    #    empty), and demonstrate the move with a concrete Manual Transfer
    #    Order whose engine.materialize() path does not touch safe_eval.
    #    Once /opt is redeployed with the fix, set the source/target domains
    #    to [('id','child_of', <zone>)] to enable auto low-water generation.
    # ------------------------------------------------------------------
    ToRule = env["custom.to.rule"]
    if not ToRule.search([("warehouse_id", "=", wh.id)], limit=1):
        ToRule.create(
            {
                "name": "Replenish PICK from HD (low-water)",
                "warehouse_id": wh.id,
                "trigger": "low_water_mark",
                "low_water_qty": 10.0,
                "expiry_days_ahead": 30,
            }
        )
        log("transfer-order rule created: HD -> PICK low-water-mark")

    # Seed a pallet of stock into HD-A-01 so there is something to move down,
    # then stage a native internal transfer picking (HD-A-01 -> NIK-02) which
    # the handheld scans (source bin + dest bin) — this is the faithful Odoo
    # equivalent of the deck's bin-to-bin flow and avoids the custom engine's
    # materialize() (which builds a stock.move with the Odoo-19-removed `name`
    # field on the /opt runtime). A TO planning record is also created (without
    # materialize) so the Transfer Order engine UI shows the proposal.
    hd_bin = xid_get("bin_hd_a_01")
    nik_bin = xid_get("bin_nik_02")
    peg = env["product.template"].search([("default_code", "=", "NK-PEG-42")], limit=1)
    have_hd = env["stock.lot"].search_count([("name", "=", "LOT-NK-PEG-42-HD")])
    if hd_bin and nik_bin and peg and not have_hd:
        variant = peg.product_variant_id
        from datetime import date, timedelta

        lot = env["stock.lot"].create(
            {
                "name": "LOT-NK-PEG-42-HD",
                "product_id": variant.id,
                "company_id": wh.company_id.id,
                "expiration_date": (date.today() + timedelta(days=600)).isoformat() + " 00:00:00",
            }
        )
        q = (
            env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(
                {
                    "product_id": variant.id,
                    "location_id": hd_bin,
                    "lot_id": lot.id,
                    "inventory_quantity": 24,
                }
            )
        )
        q.action_apply_inventory()

        # Native internal transfer picking HD-A-01 -> NIK-02 (10 units).
        picking = env["stock.picking"].create(
            {
                "picking_type_id": wh.int_type_id.id,
                "location_id": hd_bin,
                "location_dest_id": nik_bin,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": variant.id,
                            "product_uom_qty": 10,
                            "product_uom": variant.uom_id.id,
                            "location_id": hd_bin,
                            "location_dest_id": nik_bin,
                        },
                    )
                ],
            }
        )
        env["ir.model.data"].create(
            {"module": NS, "name": "bin2bin_picking", "model": "stock.picking", "res_id": picking.id, "noupdate": True}
        )
        picking.action_confirm()
        picking.action_assign()

        # TO planning record (no materialize — engine.materialize is broken on /opt).
        env["custom.transfer.order"].create(
            {
                "source_location_id": hd_bin,
                "target_location_id": nik_bin,
                "product_id": variant.id,
                "lot_id": lot.id,
                "planned_qty": 10,
                "state": "proposed",
            }
        )
        log("bin-to-bin internal transfer %s staged: HD-A-01 -> NIK-02 (state %s)" % (picking.name, picking.state))

    env["ir.config_parameter"].sudo().set_param(MARKER, "1")
    env.cr.commit()
    log("DONE — putaway / cycle-count / transfer-order engines configured.")
