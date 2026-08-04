# -*- coding: utf-8 -*-
"""80_poc_scenario.py — end-to-end WMS POC on demo_wms, by transaction category.

Run:  docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms \
          --no-http < scripts/tenants/wms_demo/80_poc_scenario.py

Walks the twelve categories a WMS implementation is signed off against, in
the order the goods actually move:

    A. Add Warehouse                 G. Delivery Order (Outbound)
    B. Add Location                  H. Picking (Out)
    C. Storage Categories            I. Cycle Counting
    D. Putaway (strategy/rules)      J. Print Label
    E. PO (Inbound)                  K. Scrap
    F. Internal Transfer             L. Reporting (PDF + XLSX, barcoded)

Each step runs against real records — no mocks — and prints
PASS / PARTIAL / FAIL with the evidence it used. Reporting artefacts (PDFs
and XLSX workbooks) are written to ``ARTIFACT_DIR`` so they can be opened and
checked by eye.

Idempotent: the warehouse and its configuration are created once and reused;
every run creates a fresh transaction batch tagged ``POC<nn>``.
"""

import base64
import logging
import os
from datetime import date, timedelta

from odoo import fields

logging.getLogger("odoo.addons.custom_wms_putaway").setLevel(logging.ERROR)

#: Where the printable evidence lands (inside the Odoo container).
ARTIFACT_DIR = "/var/lib/odoo/poc_wms"

RESULTS = []


def record(code, title, verdict, evidence):
    RESULTS.append((code, title, verdict, evidence))
    print(f"[{code}] {verdict:<7} {title} :: {evidence}")


def step(code, title):
    """Run a step, turning any exception into a FAIL rather than a crash."""

    def deco(fn):
        try:
            verdict, evidence = fn()
        except Exception as exc:  # noqa: BLE001 - a broken step is a FAIL, not a crash
            import traceback

            traceback.print_exc()
            verdict, evidence = "FAIL", f"{type(exc).__name__}: {exc}"
        record(code, title, verdict, evidence)
        return fn

    return deco


def save(name: str, data: bytes) -> str:
    """Write an artefact and return its path (for the evidence string)."""
    os.makedirs(RUN_DIR, exist_ok=True)
    path = os.path.join(RUN_DIR, name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


# ======================================================================
# Setup
# ======================================================================
env = env  # noqa: F821 - provided by odoo shell
ICP = env["ir.config_parameter"].sudo()

run_no = int(ICP.get_param("wms_poc.run", "0")) + 1
ICP.set_param("wms_poc.run", str(run_no))
TAG = f"POC{run_no:02d}"
# Namespaced by database: the filestore volume is shared between tenants, so
# a run on a second database would otherwise overwrite the first one's
# evidence pack (both start numbering at POC01).
RUN_DIR = os.path.join(ARTIFACT_DIR, env.cr.dbname, TAG)

company = env.company
Report = env["ir.actions.report"]
Product = env["product.product"]
Location = env["stock.location"]

print(f"\n===== WMS POC run {TAG} on {env.cr.dbname} (company {company.name}) =====\n")

# Multi-location, storage categories and advanced routing must be on or the
# putaway/storage-category records are invisible in the UI (and some of them
# are not even creatable).
for xmlid in (
    "stock.group_stock_multi_locations",
    "stock.group_stock_storage_categories",
    "stock.group_stock_adv_location",
    "stock.group_production_lot",
    "stock.group_stock_multi_warehouses",
    "stock.group_stock_lot_print_gs1",
):
    group = env.ref(xmlid, raise_if_not_found=False)
    if group and env.user not in group.user_ids:
        group.sudo().write({"user_ids": [(4, env.user.id)]})

# The count-approval and QC steps are group-gated; the shell runs as
# __system__, which does not inherit groups granted through security.xml.
for xmlid in (
    "custom_wms_cycle_count.group_cycle_count_supervisor",
    "custom_wms_inbound_qc.group_wms_qc_inspector",
):
    group = env.ref(xmlid, raise_if_not_found=False)
    if group and env.user not in group.user_ids:
        group.sudo().write({"user_ids": [(4, env.user.id)]})


# ======================================================================
# A. Warehouse
# ======================================================================
warehouse = env["stock.warehouse"].search([("code", "=", "POC")], limit=1)


@step("A", "Add Warehouse (2-step receipt, 2-step delivery)")
def _a():
    global warehouse
    created = False
    if not warehouse:
        warehouse = env["stock.warehouse"].create(
            {
                "name": "POC Distribution Centre",
                "code": "POC",
                "company_id": company.id,
            }
        )
        created = True
    # Two-step in and two-step out: receipt lands in Input so putaway has a
    # leg to slot, and the outbound splits into PICK (internal) + OUT
    # (delivery) so "Picking (Out)" is a step of its own.
    warehouse.write({"reception_steps": "two_steps", "delivery_steps": "pick_ship"})
    types = {t.code: t for t in env["stock.picking.type"].search([("warehouse_id", "=", warehouse.id)])}
    return (
        "PASS",
        "%s %s (%s) — reception=%s delivery=%s, %s operation types"
        % (
            "created" if created else "reused",
            warehouse.name,
            warehouse.code,
            warehouse.reception_steps,
            warehouse.delivery_steps,
            len(types),
        ),
    )


stock_loc = warehouse.lot_stock_id
input_loc = warehouse.wh_input_stock_loc_id
pick_type_in = env["stock.picking.type"].search(
    [("warehouse_id", "=", warehouse.id), ("code", "=", "incoming")], limit=1
)
pick_type_int = env["stock.picking.type"].search(
    [("warehouse_id", "=", warehouse.id), ("code", "=", "internal")], limit=1
)


# ======================================================================
# B. Locations
# ======================================================================
ZONES = [
    # (key, name, barcode-prefix, bin count, volume m3, walk sequence base)
    ("BULK", "Bulk Pallet", "POC-BLK", 6, 2.0, 100),
    ("PICK", "Forward Pick", "POC-PCK", 6, 0.5, 200),
    ("PACK", "Pack & Ship", "POC-PAK", 1, 5.0, 300),
]
zones = {}
bins = {}


@step("B", "Add Location (zones + barcoded bins)")
def _b():
    created = 0
    for key, name, prefix, count, volume, walk in ZONES:
        zone = Location.search(
            [("name", "=", name), ("location_id", "=", stock_loc.id), ("company_id", "=", company.id)],
            limit=1,
        )
        if not zone:
            zone = Location.create(
                {
                    "name": name,
                    "location_id": stock_loc.id,
                    "usage": "view",
                    "company_id": company.id,
                }
            )
            created += 1
        zones[key] = zone
        bins[key] = Location.browse()
        for idx in range(1, count + 1):
            code = "%s-%02d" % (prefix, idx)
            bin_loc = Location.search([("barcode", "=", code), ("company_id", "=", company.id)], limit=1)
            if not bin_loc:
                bin_loc = Location.create(
                    {
                        "name": code,
                        "location_id": zone.id,
                        "usage": "internal",
                        "barcode": code,
                        "company_id": company.id,
                        "volume_capacity_m3": volume,
                        "wms_walk_sequence": walk + idx,
                    }
                )
                created += 1
            bins[key] |= bin_loc
    total = sum(len(b) for b in bins.values())
    missing = [b.complete_name for zone_bins in bins.values() for b in zone_bins if not b.barcode]
    verdict = "PASS" if not missing else "PARTIAL"
    return verdict, "%s zone(s), %s bin(s), %s newly created, all barcoded=%s" % (
        len(zones),
        total,
        created,
        not missing,
    )


# ======================================================================
# C. Storage categories
# ======================================================================
storage_categories = {}


@step("C", "Storage Categories (+ per-package-type capacity)")
def _c():
    StorageCategory = env["stock.storage.category"]
    Capacity = env["stock.storage.category.capacity"]
    PackageType = env["stock.package.type"]

    pallet = PackageType.search([("name", "=", "POC Pallet")], limit=1) or PackageType.create(
        {
            "name": "POC Pallet",
            "packaging_length": 1200,
            "width": 1000,
            "height": 1500,
            "base_weight": 25.0,
            "max_weight": 800.0,
            "company_id": company.id,
        }
    )
    carton = PackageType.search([("name", "=", "POC Carton")], limit=1) or PackageType.create(
        {
            "name": "POC Carton",
            "packaging_length": 600,
            "width": 400,
            "height": 400,
            "base_weight": 1.0,
            "max_weight": 25.0,
            "company_id": company.id,
        }
    )

    spec = [
        # (name, allow_new_product, max_weight, [(package type, qty)], zone key)
        ("POC Bulk — Pallet Only", "same", 1600.0, [(pallet, 2)], "BULK"),
        ("POC Pick — Mixed Carton", "mixed", 300.0, [(carton, 12)], "PICK"),
        ("POC Pack — Staging", "mixed", 500.0, [(carton, 40)], "PACK"),
    ]
    for name, allow, max_weight, capacities, zone_key in spec:
        categ = StorageCategory.search([("name", "=", name)], limit=1)
        if not categ:
            categ = StorageCategory.create(
                {"name": name, "allow_new_product": allow, "max_weight": max_weight, "company_id": company.id}
            )
            for package_type, qty in capacities:
                Capacity.create({"storage_category_id": categ.id, "package_type_id": package_type.id, "quantity": qty})
        storage_categories[zone_key] = categ
        # Stamp every bin of the zone so the native putaway rules can filter on it.
        bins[zone_key].write({"storage_category_id": categ.id})

    stamped = sum(len(b.filtered("storage_category_id")) for b in bins.values())
    return "PASS", "%s categories, %s capacity line(s), %s bins stamped" % (
        len(storage_categories),
        Capacity.search_count([("storage_category_id", "in", [c.id for c in storage_categories.values()])]),
        stamped,
    )


# ======================================================================
# Products (needed from the inbound step onwards)
# ======================================================================
categ_bulk = env["product.category"].search([("name", "=", "POC Bulk Goods")], limit=1) or env[
    "product.category"
].create({"name": "POC Bulk Goods"})
categ_fast = env["product.category"].search([("name", "=", "POC Fast Movers")], limit=1) or env[
    "product.category"
].create({"name": "POC Fast Movers"})

PRODUCTS = [
    # (default_code, name, barcode(EAN13), tracking, abc, category, cost)
    ("POC-A-001", "POC Running Shoe A", "8991234500017", "lot", "A", categ_fast, 350000.0),
    ("POC-B-002", "POC Training Tee B", "8991234500024", "lot", "B", categ_fast, 120000.0),
    ("POC-C-003", "POC Bulk Sock Pack C", "8991234500031", "none", "C", categ_bulk, 45000.0),
    ("POC-S-004", "POC Smart Band (Serial)", "8991234500048", "serial", "A", categ_fast, 890000.0),
]
products = {}
for code, name, barcode, tracking, abc, categ, cost in PRODUCTS:
    product = Product.search([("default_code", "=", code)], limit=1)
    if not product:
        product = Product.create(
            {
                "name": name,
                "default_code": code,
                "barcode": barcode,
                "type": "consu",
                "is_storable": True,
                "tracking": tracking,
                "categ_id": categ.id,
                "standard_price": cost,
                "list_price": cost * 1.6,
                "abc_class": abc,
                "weight": 0.8,
                "volume": 0.01,
            }
        )
    else:
        product.write({"standard_price": cost, "abc_class": abc, "tracking": tracking})
    products[code] = product

if "use_expiration_date" in Product._fields:
    products["POC-A-001"].product_tmpl_id.write({"use_expiration_date": True, "expiration_time": 720})


# ======================================================================
# D. Putaway — native rules + WMS strategy, rules and suggestions
# ======================================================================
strategy = None


@step("D", "Putaway: strategies, rules and suggestions")
def _d():
    global strategy
    # --- native Odoo putaway: product category -> zone, filtered by storage category
    PutawayRule = env["stock.putaway.rule"]
    native = 0
    for categ, zone_key in ((categ_bulk, "BULK"), (categ_fast, "PICK")):
        existing = PutawayRule.search(
            [
                ("category_id", "=", categ.id),
                ("location_in_id", "=", stock_loc.id),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        if not existing:
            PutawayRule.create(
                {
                    "category_id": categ.id,
                    "location_in_id": stock_loc.id,
                    "location_out_id": zones[zone_key].id,
                    "storage_category_id": storage_categories[zone_key].id,
                    "company_id": company.id,
                }
            )
            native += 1

    # --- WMS strategy: the tiered engine that produces the suggestions
    Strategy = env["custom.wms.putaway.strategy"]
    Rule = env["custom.wms.putaway.rule"]
    strategy = Strategy.search([("warehouse_id", "=", warehouse.id)], limit=1)
    if not strategy:
        strategy = Strategy.create(
            {
                "name": "POC Tiered Putaway",
                "warehouse_id": warehouse.id,
                "company_id": company.id,
                # Suggestions stay visible for handheld review instead of
                # being applied silently — that is the point of the demo.
                "auto_apply_suggestions": False,
            }
        )
    if not strategy.rule_ids:
        Rule.create(
            [
                {
                    "name": "T1 — Fast movers to Forward Pick",
                    "strategy_id": strategy.id,
                    "tier": 1,
                    "kind": "fixed_location",
                    "target_location_id": bins["PICK"][0].id,
                    "product_categ_ids": [(6, 0, [categ_fast.id])],
                    "company_id": company.id,
                },
                {
                    "name": "T2 — A-class by ABC velocity in Pick",
                    "strategy_id": strategy.id,
                    "tier": 2,
                    "kind": "by_abc_velocity",
                    "abc_class": "A",
                    "target_location_domain": "[('id', 'in', %s)]" % bins["PICK"].ids,
                    "company_id": company.id,
                },
                {
                    "name": "T3 — Volume fit in Bulk",
                    "strategy_id": strategy.id,
                    "tier": 3,
                    "kind": "by_volume",
                    "target_location_domain": "[('id', 'in', %s)]" % bins["BULK"].ids,
                    "company_id": company.id,
                },
                {
                    "name": "T4 — Nearest empty bin, anywhere",
                    "strategy_id": strategy.id,
                    "tier": 4,
                    "kind": "nearest_empty",
                    "target_location_domain": "[('id', 'in', %s)]" % (bins["BULK"] | bins["PICK"]).ids,
                    "company_id": company.id,
                },
            ]
        )
    return "PASS", "%s native rule(s) created, strategy '%s' with %s tier(s), auto_apply=%s" % (
        native,
        strategy.name,
        len(strategy.rule_ids),
        strategy.auto_apply_suggestions,
    )


# ======================================================================
# E. PO — inbound
# ======================================================================
purchase_order = None
receipt = None
internal_putaway = None
lots = {}


@step("E", "PO (Inbound): confirm -> receive -> putaway leg")
def _e():
    global purchase_order, receipt, internal_putaway
    vendor = env["res.partner"].search([("name", "=", "PT POC Supplier Utama")], limit=1) or env["res.partner"].create(
        {"name": "PT POC Supplier Utama", "supplier_rank": 1, "company_id": False}
    )

    purchase_order = env["purchase.order"].create(
        {
            "partner_id": vendor.id,
            "company_id": company.id,
            "picking_type_id": pick_type_in.id,
            "origin": TAG,
            "order_line": [
                (0, 0, {"product_id": products["POC-A-001"].id, "product_qty": 60, "price_unit": 350000.0}),
                (0, 0, {"product_id": products["POC-B-002"].id, "product_qty": 40, "price_unit": 120000.0}),
                (0, 0, {"product_id": products["POC-C-003"].id, "product_qty": 100, "price_unit": 45000.0}),
                (0, 0, {"product_id": products["POC-S-004"].id, "product_qty": 3, "price_unit": 890000.0}),
            ],
        }
    )
    purchase_order.button_confirm()
    receipt = purchase_order.picking_ids.filtered(lambda p: p.picking_type_id.code == "incoming")
    if not receipt:
        return "FAIL", "PO %s confirmed but produced no receipt" % purchase_order.name

    # Receive everything: lot-tracked lines get a batch + expiry, the serial
    # line gets one move line per unit (that is what the scanner produces).
    for move in receipt.move_ids:
        product = move.product_id
        if product.tracking == "serial":
            move.move_line_ids.unlink()
            for unit in range(int(move.product_uom_qty)):
                serial = env["stock.lot"].create(
                    {"name": "%s-SN%03d" % (TAG, unit + 1), "product_id": product.id, "company_id": company.id}
                )
                env["stock.move.line"].create(
                    {
                        "move_id": move.id,
                        "picking_id": receipt.id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "location_id": move.location_id.id,
                        "location_dest_id": move.location_dest_id.id,
                        "lot_id": serial.id,
                        "quantity": 1.0,
                    }
                )
        elif product.tracking == "lot":
            lot = env["stock.lot"].create(
                {
                    "name": "%s-%s" % (TAG, product.default_code),
                    "product_id": product.id,
                    "company_id": company.id,
                }
            )
            if "expiration_date" in lot._fields:
                lot.expiration_date = fields.Datetime.now() + timedelta(days=365)
            lots[product.default_code] = lot
            move.move_line_ids.unlink()
            env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "picking_id": receipt.id,
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "lot_id": lot.id,
                    "quantity": move.product_uom_qty,
                }
            )
        else:
            move.quantity = move.product_uom_qty
    receipt.move_ids.picked = True
    receipt.button_validate()

    # Two-step reception: the second leg (Input -> Stock) is the putaway move.
    internal_putaway = env["stock.picking"].search(
        [
            ("origin", "=", purchase_order.name),
            ("picking_type_id.code", "=", "internal"),
            ("state", "not in", ("done", "cancel")),
        ],
        limit=1,
    )
    suggestions = env["custom.wms.putaway.suggestion"].search_count([("picking_id", "=", receipt.id)])
    return (
        "PASS" if receipt.state == "done" and internal_putaway else "PARTIAL",
        "PO %s -> receipt %s (%s), %s move(s), putaway leg %s, %s suggestion(s)"
        % (
            purchase_order.name,
            receipt.name,
            receipt.state,
            len(receipt.move_ids),
            internal_putaway.name if internal_putaway else "MISSING",
            suggestions,
        ),
    )


# ======================================================================
# F. Internal transfer — the putaway leg, then a bin-to-bin replenishment
# ======================================================================
bin2bin = None


@step("F", "Internal Transfer (putaway leg + bin-to-bin)")
def _f():
    global bin2bin
    slotted = []
    if internal_putaway:
        internal_putaway.action_assign()
        # Slot each line into the zone its product category belongs to.
        for line in internal_putaway.move_line_ids:
            zone_key = "BULK" if line.product_id.categ_id == categ_bulk else "PICK"
            target = bins[zone_key][0]
            line.location_dest_id = target.id
            line.quantity = line.quantity or line.move_id.product_uom_qty
            slotted.append("%s->%s" % (line.product_id.default_code, target.barcode))
        internal_putaway.move_ids.picked = True
        internal_putaway.button_validate()

    # Bin-to-bin: move half of the fast mover from its slot to a second Pick bin.
    source_bin = bins["PICK"][0]
    dest_bin = bins["PICK"][1]
    quant = env["stock.quant"].search(
        [("location_id", "=", source_bin.id), ("product_id", "=", products["POC-A-001"].id)], limit=1
    )
    qty = max((quant.quantity or 0.0) / 2.0, 1.0)
    bin2bin = env["stock.picking"].create(
        {
            "picking_type_id": pick_type_int.id,
            "location_id": source_bin.id,
            "location_dest_id": dest_bin.id,
            "origin": "%s bin-to-bin" % TAG,
            "company_id": company.id,
            "move_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": products["POC-A-001"].id,
                        "product_uom_qty": qty,
                        "product_uom": products["POC-A-001"].uom_id.id,
                        "location_id": source_bin.id,
                        "location_dest_id": dest_bin.id,
                        "company_id": company.id,
                    },
                )
            ],
        }
    )
    bin2bin.action_confirm()
    bin2bin.action_assign()
    for line in bin2bin.move_line_ids:
        line.quantity = line.quantity or qty
    bin2bin.move_ids.picked = True
    bin2bin.button_validate()

    return (
        "PASS" if bin2bin.state == "done" else "PARTIAL",
        "putaway leg %s slotted [%s]; bin-to-bin %s %s->%s qty %.2f (%s)"
        % (
            internal_putaway.name if internal_putaway else "-",
            ", ".join(slotted) or "-",
            bin2bin.name,
            source_bin.barcode,
            dest_bin.barcode,
            qty,
            bin2bin.state,
        ),
    )


# ======================================================================
# G + H. Outbound — SO -> PICK (internal) -> OUT (delivery)
# ======================================================================
sale_order = None
pick_out = None
delivery = None


@step("G", "Delivery Order (Outbound): SO -> outbound chain reserved")
def _g():
    global sale_order, pick_out
    customer = env["res.partner"].search([("name", "=", "PT POC Retail Nusantara")], limit=1) or env[
        "res.partner"
    ].create({"name": "PT POC Retail Nusantara", "customer_rank": 1, "company_id": False})

    sale_order = env["sale.order"].create(
        {
            "partner_id": customer.id,
            "company_id": company.id,
            "warehouse_id": warehouse.id,
            "origin": TAG,
            "order_line": [
                (0, 0, {"product_id": products["POC-A-001"].id, "product_uom_qty": 10}),
                (0, 0, {"product_id": products["POC-C-003"].id, "product_uom_qty": 20}),
            ],
        }
    )
    sale_order.action_confirm()
    pick_out = sale_order.picking_ids.filtered(lambda p: p.picking_type_id.code == "internal")
    pick_out.action_assign()
    # In pick_ship the OUT leg comes from a *push* rule on POC/Output, so it
    # does not exist yet — it is created when the pick is validated (step H).
    return (
        "PASS" if pick_out and pick_out.state in ("assigned", "confirmed") else "PARTIAL",
        "SO %s -> pick %s (%s), %s line(s) reserved from %s; OUT leg pushed on pick validation"
        % (
            sale_order.name,
            pick_out.name if pick_out else "MISSING",
            pick_out.state if pick_out else "-",
            len(pick_out.move_line_ids),
            ", ".join(sorted({l.location_id.barcode or l.location_id.name for l in pick_out.move_line_ids})) or "-",
        ),
    )


@step("H", "Picking (Out): pick to staging, then ship the delivery order")
def _h():
    global delivery
    if not pick_out:
        return "FAIL", "no PICK step — check that delivery_steps is pick_ship"
    pick_out.action_assign()
    picked = []
    for line in pick_out.move_line_ids:
        line.quantity = line.quantity or line.move_id.product_uom_qty
        picked.append(
            "%s x%.0f from %s" % (line.product_id.default_code, line.quantity, line.location_id.barcode or "?")
        )
    pick_out.move_ids.picked = True
    pick_out.button_validate()

    # The push rule has now materialised the delivery order.
    delivery = pick_out.move_ids.move_dest_ids.picking_id.filtered(lambda p: p.picking_type_id.code == "outgoing")
    if not delivery:
        return "PARTIAL", "pick %s=%s but no OUT leg was pushed" % (pick_out.name, pick_out.state)
    delivery.action_assign()
    for line in delivery.move_line_ids:
        line.quantity = line.quantity or line.move_id.product_uom_qty
    delivery.move_ids.picked = True
    delivery.button_validate()

    return (
        "PASS" if pick_out.state == "done" and delivery.state == "done" else "PARTIAL",
        "pick %s=%s [%s]; delivery %s=%s via %s"
        % (
            pick_out.name,
            pick_out.state,
            "; ".join(picked) or "-",
            delivery.name,
            delivery.state,
            delivery.location_id.complete_name,
        ),
    )


# ======================================================================
# I. Cycle counting
# ======================================================================
count_session = None


@step("I", "Cycle Counting: plan -> session -> count -> approve")
def _i():
    global count_session
    plan = env["custom.cycle.count.plan"].search(
        [("name", "=", "POC Pick Zone Count"), ("warehouse_id", "=", warehouse.id)], limit=1
    )
    if not plan:
        plan = env["custom.cycle.count.plan"].create(
            {
                "name": "POC Pick Zone Count",
                "warehouse_id": warehouse.id,
                "company_id": company.id,
                "method": "by_zone",
                "frequency": "weekly",
                "scope_zone_ids": [(6, 0, [zones["PICK"].id, zones["BULK"].id])],
                "target_count_per_period": 20,
            }
        )

    wizard = env["custom.cycle.count.start.wizard"].create(
        {"plan_id": plan.id, "scheduled_date": date.today(), "target_count": 10}
    )
    wizard.action_start()
    count_session = env["custom.cycle.count.session"].search([("plan_id", "=", plan.id)], order="id desc", limit=1)
    if not count_session or not count_session.line_ids:
        return "PARTIAL", "session %s created with no lines (no quants in scope?)" % (
            count_session.name if count_session else "-"
        )
    if count_session.state == "draft":
        count_session.action_start()

    # Count every line: all correct except one, deliberately short by 2 so the
    # variance-approval path is exercised. It has to be a line that actually
    # holds stock, or "expected - 2" clamps to 0 and no variance is produced.
    countable = count_session.line_ids.filtered(lambda l: (l.expected_qty or 0.0) >= 2.0)
    variance_line = countable[0] if countable else count_session.line_ids[0]
    for line in count_session.line_ids:
        delta = -2.0 if line == variance_line else 0.0
        line.action_count(max((line.expected_qty or 0.0) + delta, 0.0))

    count_session.action_review()
    for line in count_session.line_ids:
        line.action_approve()
    count_session.action_close()

    return (
        "PASS" if count_session.state == "closed" else "PARTIAL",
        "session %s: %s line(s), %s variance(s) worth %.2f, state=%s"
        % (
            count_session.name,
            count_session.line_count,
            count_session.variance_count,
            count_session.variance_value or 0.0,
            count_session.state,
        ),
    )


# ======================================================================
# J. Print label
# ======================================================================
@step("J", "Print Label (product labels + barcode scan sheet)")
def _j():
    artefacts = []
    wizard = env["custom.wms.label.wizard"].create(
        {
            "product_ids": [(6, 0, [p.id for p in products.values()])],
            "qty_source": "manual",
            "qty_per_product": 2,
            "label_kind": "price_tag",
            "barcode_kind": "Code128",
        }
    )
    action = wizard.action_print()
    data = action.get("data") if isinstance(action, dict) else None
    pdf, _fmt = Report._render_qweb_pdf("custom_wms_docs.report_wms_product_label", wizard.product_ids.ids, data=data)
    artefacts.append(save("J1_product_labels.pdf", pdf))

    # Scan sheet: every package + product barcode of the shipment (falling
    # back to the receipt when the outbound leg did not complete).
    shipment = delivery or receipt
    if shipment:
        pdf, _fmt = Report._render_qweb_pdf("custom_wms_docs.report_wms_barcode_list", shipment.ids)
        artefacts.append(save("J2_barcode_list_%s.pdf" % shipment.name.replace("/", "-"), pdf))

    return "PASS", "%s label(s) + scan sheet -> %s" % (
        len(wizard.product_ids) * wizard.qty_per_product,
        ", ".join(os.path.basename(a) for a in artefacts),
    )


# ======================================================================
# K. Scrap
# ======================================================================
scraps = None


@step("K", "Scrap: write off damaged stock from a bin")
def _k():
    global scraps
    scrap_records = env["stock.scrap"].browse()
    for code, qty in (("POC-B-002", 3.0), ("POC-C-003", 5.0)):
        product = products[code]
        quant = env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("location_id", "child_of", stock_loc.id),
                ("quantity", ">", qty),
            ],
            limit=1,
        )
        if not quant:
            continue
        scrap = env["stock.scrap"].create(
            {
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "scrap_qty": qty,
                "location_id": quant.location_id.id,
                "lot_id": quant.lot_id.id if quant.lot_id else False,
                "origin": "%s damaged on receipt" % TAG,
                "company_id": company.id,
            }
        )
        scrap.action_validate()
        scrap_records |= scrap
    if not scrap_records:
        return "FAIL", "no quant with enough qty to scrap"
    scraps = scrap_records
    pdf, _fmt = Report._render_qweb_pdf("custom_wms_reports.report_wms_scrap_note", scrap_records.ids)
    path = save("K1_scrap_note.pdf", pdf)
    return "PASS", "%s scrap order(s) %s (%s), note -> %s" % (
        len(scrap_records),
        ", ".join(scrap_records.mapped("name")),
        ", ".join(set(scrap_records.mapped("state"))),
        os.path.basename(path),
    )


# ======================================================================
# L. Reporting — PDF + XLSX, both barcoded
# ======================================================================
@step("L1", "Reporting — PDF documents (barcode at header + line level)")
def _l1():
    documents = [
        ("custom_wms_docs.report_wms_picking_list", receipt, "L1a_picking_list_receipt"),
        ("custom_wms_docs.report_wms_picking_list", pick_out, "L1b_picking_list_pickout"),
        ("custom_wms_docs.report_wms_packing_list", delivery, "L1c_packing_list_delivery"),
        ("custom_wms_reports.report_wms_stock_take", count_session, "L1d_stock_take"),
        ("custom_wms_reports.report_wms_scrap_note", scraps, "L1e_scrap_note"),
    ]
    written = []
    failed = []
    for report_name, records, filename in documents:
        if not records:
            failed.append("%s (no record)" % filename)
            continue
        try:
            pdf, _fmt = Report._render_qweb_pdf(report_name, records.ids)
            written.append("%s (%.0f kB)" % (save("%s.pdf" % filename, pdf), len(pdf) / 1024.0))
        except Exception as exc:  # noqa: BLE001
            failed.append("%s: %s" % (filename, exc))
    verdict = "PASS" if not failed else ("PARTIAL" if written else "FAIL")
    return verdict, "%s PDF(s) in %s%s" % (
        len(written),
        RUN_DIR,
        "; FAILED: " + ", ".join(failed) if failed else "",
    )


@step("L2", "Reporting — XLSX exports with embedded barcodes")
def _l2():
    import io
    import zipfile

    models = [
        ("custom.wms.transfer.report", [("company_id", "=", company.id)]),
        ("custom.wms.stock.summary.report", [("warehouse_id", "=", warehouse.id)]),
        ("custom.wms.stock.take.report", [("session_id", "=", count_session.id)] if count_session else []),
        ("custom.wms.purchase.return.report", []),
        ("custom.wms.scrap.report", [("company_id", "=", company.id)]),
    ]
    written = []
    empty = []
    for model, domain in models:
        records = env[model].search(domain, limit=500)
        if not records:
            empty.append(model)
            continue
        action = records.action_export_xlsx()
        attachment = env["ir.attachment"].browse(int(action["url"].split("/")[-1].split("?")[0]))
        data = base64.b64decode(attachment.datas)
        path = save(attachment.name, data)
        images = len([n for n in zipfile.ZipFile(io.BytesIO(data)).namelist() if n.startswith("xl/media/")])
        written.append("%s (%s rows, %s barcode img)" % (os.path.basename(path), len(records), images))
    verdict = "PASS" if written and not empty else ("PARTIAL" if written else "FAIL")
    return verdict, "%s; no data: %s" % ("; ".join(written), ", ".join(empty) or "none")


@step("L3", "Reporting — on-screen analysis (list + pivot read back)")
def _l3():
    checks = []
    # _read_group, not read_group: the latter is deprecated in Odoo 19 and
    # prints a warning stack that reads like a crash in the scenario log.
    transfers = env["custom.wms.transfer.report"]._read_group(
        [("company_id", "=", company.id), ("state", "=", "done")],
        groupby=["transfer_kind"],
        aggregates=["done_qty:sum"],
    )
    checks.append("transfers " + ", ".join("%s=%.0f" % (kind, qty or 0) for kind, qty in transfers))
    summary = env["custom.wms.stock.summary.report"]._read_group(
        [("warehouse_id", "=", warehouse.id)], aggregates=["quantity:sum", "value:sum"]
    )
    if summary:
        checks.append("on-hand %.0f units worth %.0f" % (summary[0][0] or 0, summary[0][1] or 0))
    scrap_group = env["custom.wms.scrap.report"]._read_group(
        [("company_id", "=", company.id)], aggregates=["scrap_qty:sum", "scrap_value:sum"]
    )
    if scrap_group:
        checks.append("scrap %.0f units worth %.0f" % (scrap_group[0][0] or 0, scrap_group[0][1] or 0))
    return "PASS", "; ".join(checks)


# ======================================================================
# Verdict
# ======================================================================
env.cr.commit()

print("\n" + "=" * 78)
print(f"WMS POC {TAG} — summary")
print("=" * 78)
for code, title, verdict, evidence in RESULTS:
    print(f"  [{code:<2}] {verdict:<7} {title}")
counts = {}
for _c, _t, verdict, _e in RESULTS:
    counts[verdict] = counts.get(verdict, 0) + 1
print("-" * 78)
print("  " + ", ".join("%s=%s" % (k, v) for k, v in sorted(counts.items())))
print("  artefacts: %s (inside the odoo container)" % RUN_DIR)
print("=" * 78 + "\n")
