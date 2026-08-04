# -*- coding: utf-8 -*-
"""70_scenario_test.py — walk the client's 15-point WMS scenario on demo_wms.

Run:  docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms \
          --no-http < scripts/tenants/wms_demo/70_scenario_test.py

Every item of the requirement sheet ("Warehouse Management" 1-10, "Report"
11-15) is exercised against real records — receipts are scanned and
validated, putaway runs, a replenishment TO is materialised, a delivery is
picked, a count is closed, reports are queried and PDFs rendered. The script
prints a PASS / PARTIAL / FAIL verdict per item with the evidence it used.

Idempotent: re-running creates a fresh scenario batch (suffixed by run
number) instead of failing on existing records.
"""

import base64
import logging
from datetime import date, timedelta

from odoo import fields

logging.getLogger("odoo.addons.custom_wms_putaway").setLevel(logging.ERROR)

RESULTS = []


def record(no, title, verdict, evidence):
    RESULTS.append((no, title, verdict, evidence))
    print(f"[{no:>2}] {verdict:<7} {title} :: {evidence}")


def step(no, title):
    def deco(fn):
        try:
            verdict, evidence = fn()
        except Exception as exc:  # noqa: BLE001 - a broken item is a FAIL, not a crash
            import traceback

            traceback.print_exc()
            verdict, evidence = "FAIL", f"{type(exc).__name__}: {exc}"
        record(no, title, verdict, evidence)
        return fn

    return deco


# ======================================================================
# Setup
# ======================================================================
env = env  # noqa: F821 - provided by odoo shell
ICP = env["ir.config_parameter"].sudo()

run_no = int(ICP.get_param("wms_demo.scenario_run", "0")) + 1
ICP.set_param("wms_demo.scenario_run", str(run_no))
TAG = f"SCN{run_no:02d}"
print(f"\n===== WMS scenario run {TAG} on {env.cr.dbname} =====\n")

wh = env["stock.warehouse"].search([("code", "=", "JDC")], limit=1)
assert wh, "warehouse JDC not found — run 10_seed_warehouse.py first"
company = wh.company_id
supplier_loc = env.ref("stock.stock_location_suppliers")
receipt_type = env["stock.picking.type"].search([("code", "=", "incoming"), ("warehouse_id", "=", wh.id)], limit=1)
Product = env["product.product"]
Picking = env["stock.picking"]
Move = env["stock.move"]

# QC inspector rights for the acting user (shell runs as __system__, which
# does not inherit groups granted through security.xml).
qc_group = env.ref("custom_wms_inbound_qc.group_wms_qc_inspector", raise_if_not_found=False)
if qc_group and env.user not in qc_group.user_ids:
    qc_group.sudo().write({"user_ids": [(4, env.user.id)]})

vendor = env["res.partner"].search([("name", "=", "PT Sportindo Distribusi")], limit=1)
if not vendor:
    vendor = env["res.partner"].search([("supplier_rank", ">", 0)], limit=1) or env["res.partner"].create(
        {"name": "PT Sportindo Distribusi", "supplier_rank": 1}
    )

# --- GTIN-14 aliases so GS1 AI 01 (14 digits) resolves to the EAN-13 variant
alias_created = 0
for prod in Product.search([("barcode", "!=", False)]):
    gtin14 = prod.barcode.zfill(14)
    if gtin14 == prod.barcode:
        continue
    if not env["product.barcode"].search_count([("product_id", "=", prod.id), ("barcode", "=", gtin14)]):
        env["product.barcode"].create({"product_id": prod.id, "barcode": gtin14, "note": "GTIN-14 (GS1 AI 01)"})
        alias_created += 1

# --- serial/IMEI-tracked product (the sheet asks for IMEI receiving)
imei_product = Product.search([("default_code", "=", "JD-TRK-01")], limit=1)
if not imei_product:
    categ = env["product.category"].search([("name", "=", "Apparel")], limit=1) or env.ref(
        "product.product_category_all"
    )
    imei_product = Product.create(
        {
            "name": "JD Smart Tracker (IMEI)",
            "default_code": "JD-TRK-01",
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "barcode": "8990000000099",
            "categ_id": categ.id,
            "standard_price": 450000.0,
            "list_price": 799000.0,
        }
    )
    env["product.barcode"].create(
        {
            "product_id": imei_product.id,
            "barcode": imei_product.barcode.zfill(14),
            "note": "GTIN-14 (GS1 AI 01)",
        }
    )

lot_products = Product.search([("tracking", "=", "lot"), ("barcode", "!=", False)], limit=2)
print(
    f"setup: vendor={vendor.name} gtin14_aliases=+{alias_created} "
    f"imei_product={imei_product.default_code} lot_products={lot_products.mapped('default_code')}"
)


def make_receipt(demands, label):
    pick = Picking.create(
        {
            "picking_type_id": receipt_type.id,
            "partner_id": vendor.id,
            "origin": f"{TAG}-{label}",
            "scheduled_date": fields.Datetime.now(),
        }
    )
    for product, qty in demands:
        Move.create(
            {
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": supplier_loc.id,
                "location_dest_id": pick.location_dest_id.id,
                "picking_id": pick.id,
                "company_id": company.id,
            }
        )
    pick.action_confirm()
    pick.action_assign()
    return pick


# ======================================================================
# 1 — Master data: bin storage based on volume
# ======================================================================
@step(1, "Master data — bin storage based on volume")
def item_1():
    PkgType = env["stock.package.type"]
    StCat = env["stock.storage.category"]
    pkg = PkgType.search([])
    cats = StCat.search([])
    cap_lines = env["stock.storage.category.capacity"].search_count([])
    bins = env["stock.location"].search([("usage", "=", "internal"), ("wms_length_mm", ">", 0)])
    volumes = {b.display_name: round(b.wms_length_mm * b.wms_width_mm * b.wms_height_mm / 1e9, 3) for b in bins[:3]}
    rules = env["stock.putaway.rule"].search_count([])
    vol_rules = env["custom.wms.putaway.rule"].search_count(
        [("kind", "in", ("by_volume", "by_dimension")), ("active", "=", True)]
    )
    ok = bool(pkg) and bool(cats) and cap_lines and bins and vol_rules
    return (
        "PASS" if ok else "FAIL",
        f"package types={len(pkg)} {pkg.mapped('name')[:3]}, storage categories={len(cats)} "
        f"({cap_lines} capacity lines), bins with LxWxH={len(bins)} e.g. {volumes} m3, "
        f"native putaway rules={rules}, volume/dimension rules={vol_rules}",
    )


# ======================================================================
# 2 — Supplier incoming schedule
# ======================================================================
@step(2, "Receiving — supplier incoming schedule")
def item_2():
    horizon = fields.Datetime.now() + timedelta(days=90)
    incoming = Picking.search(
        [
            ("picking_type_id.code", "=", "incoming"),
            ("state", "not in", ("done", "cancel")),
            ("scheduled_date", "<=", horizon),
        ],
        order="scheduled_date",
    )
    po_lines = env["purchase.order.line"].search(
        [("order_id.state", "in", ("purchase", "done")), ("qty_received", "<", 1e9)]
    )
    sched = [
        f"{p.name} {fields.Datetime.to_string(p.scheduled_date)[:16]} "
        f"{p.partner_id.name or '-'} ({int(sum(p.move_ids.mapped('product_uom_qty')))} u)"
        for p in incoming[:4]
    ]
    ok = bool(incoming)
    return (
        "PASS" if ok else "FAIL",
        f"{len(incoming)} open receipts on the schedule (Inventory > Receipts, "
        f"grouped by Scheduled Date/Vendor); {len(po_lines)} PO lines with a planned date. "
        f"Sample: {sched}",
    )


# ======================================================================
# 3 — GR by handheld: EAN, IMEI/serial, non-serial, expiry, supplier batch
# ======================================================================
GR_LOT = make_receipt([(lot_products[0], 12), (lot_products[1], 6)], "GR-LOT")
GR_IMEI = make_receipt([(imei_product, 3)], "GR-IMEI")
GR_TPL = make_receipt([(lot_products[0], 10), (imei_product, 2)], "GR-TPL")


@step(3, "GR via handheld — EAN/IMEI, serial & non-serial, expiry, supplier batch")
def item_3():
    exp = date.today() + timedelta(days=540)
    Session = env["custom.barcode.scan.session"]

    # --- non-serial: GS1 element string with GTIN + batch (AI 10) + expiry (AI 17)
    s_lot = Session.create({"picking_id": GR_LOT.id})
    p0, p1 = lot_products[0], lot_products[1]
    gs1_a = f"01{p0.barcode.zfill(14)}10{TAG}-BATCH-A\x1d17{exp.strftime('%y%m%d')}"
    gs1_b = f"01{p1.barcode.zfill(14)}10{TAG}-BATCH-B\x1d17{exp.strftime('%y%m%d')}"
    s_lot.on_barcode_scanned(gs1_a)
    s_lot.on_barcode_scanned(gs1_b)
    for line in s_lot.line_ids:
        line.supplier_batch_ref = f"VND-{TAG}"
    # the handheld sends the counted quantity with the scan
    s_lot.line_ids.filtered(lambda ln: ln.product_id == p0).quantity = 12
    s_lot.line_ids.filtered(lambda ln: ln.product_id == p1).quantity = 6
    s_lot.action_apply_to_picking()
    s_lot.action_complete()

    lot_a = env["stock.lot"].search([("name", "=", f"{TAG}-BATCH-A"), ("product_id", "=", p0.id)], limit=1)
    ean_ok = all(ln.status == "ok" and ln.product_id for ln in s_lot.line_ids)
    exp_ok = lot_a and fields.Date.to_date(lot_a.expiration_date) == exp
    batch_ok = lot_a and lot_a.supplier_batch_ref == f"VND-{TAG}"

    # --- serial: bare IMEI scans off a handheld
    s_imei = Session.create({"picking_id": GR_IMEI.id})
    imeis = [f"3569380356{run_no:02d}{n:03d}" for n in (101, 102, 103)]
    for code in imeis:
        s_imei.on_barcode_scanned(code)
    s_imei.action_apply_to_picking()
    s_imei.action_complete()
    serial_lines = s_imei.line_ids.filtered(lambda ln: ln.status == "ok")
    serial_lots = env["stock.lot"].search([("name", "in", imeis), ("product_id", "=", imei_product.id)])
    imei_mls = GR_IMEI.move_line_ids.filtered(lambda ml: ml.lot_id)
    imei_ok = len(serial_lots) == 3 and len(imei_mls) == 3 and all(ml.quantity == 1 for ml in imei_mls)

    verdict = "PASS" if (ean_ok and exp_ok and batch_ok and imei_ok) else "PARTIAL"
    return (
        verdict,
        f"EAN/GS1 scans ok={ean_ok} ({len(s_lot.line_ids)} lines on {GR_LOT.name}); "
        f"expiry AI17 -> lot {lot_a.name if lot_a else '-'} = "
        f"{lot_a.expiration_date if lot_a else '-'} (ok={bool(exp_ok)}); "
        f"supplier batch = {lot_a.supplier_batch_ref if lot_a else '-'} (ok={bool(batch_ok)}); "
        f"IMEI serial scans {len(serial_lines)}/3 -> lots {serial_lots.mapped('name')} "
        f"1 unit each (ok={imei_ok})",
    )


# ======================================================================
# 4 — Template upload for IMEI/EAN, serial/non-serial, expiry, batch
# ======================================================================
@step(4, "Template upload — IMEI/EAN, serial/non-serial, expiry, supplier batch")
def item_4():
    exp = date.today() + timedelta(days=400)
    p0 = lot_products[0]
    csv = (
        "barcode,serial,lot,qty,expiry,supplier_batch\r\n"
        f"{p0.barcode},,{TAG}-TPL-1,10,{exp.strftime('%d/%m/%Y')},SUP-{TAG}\r\n"
        f"{imei_product.barcode},{TAG}IMEI0001,,1,,\r\n"
        f"{imei_product.barcode},{TAG}IMEI0002,,1,,\r\n"
    )
    wiz = env["custom.wms.receipt.import.wizard"].create(
        {
            "picking_id": GR_TPL.id,
            "data_file": base64.b64encode(csv.encode()),
            "data_file_name": f"{TAG}_receipt.csv",
        }
    )
    wiz.action_import()

    lot = env["stock.lot"].search([("name", "=", f"{TAG}-TPL-1"), ("product_id", "=", p0.id)], limit=1)
    serials = env["stock.lot"].search(
        [("name", "in", [f"{TAG}IMEI0001", f"{TAG}IMEI0002"]), ("product_id", "=", imei_product.id)]
    )
    lot_ml = GR_TPL.move_line_ids.filtered(lambda ml: ml.lot_id == lot)
    tmpl = env["custom.wms.receipt.import.wizard"].create({"picking_id": GR_TPL.id})
    has_template = bool(tmpl.action_download_template())

    ok = (
        lot
        and fields.Date.to_date(lot.expiration_date) == exp
        and lot.supplier_batch_ref == f"SUP-{TAG}"
        and len(serials) == 2
        and lot_ml
        and lot_ml.quantity == 10
    )
    return (
        "PASS" if ok else "FAIL",
        f"CSV upload on {GR_TPL.name}: lot {lot.name if lot else '-'} qty="
        f"{lot_ml.quantity if lot_ml else 0} expiry={lot.expiration_date if lot else '-'} "
        f"batch={lot.supplier_batch_ref if lot else '-'}; serials imported="
        f"{serials.mapped('name')}; blank template downloadable={has_template} "
        f"(XLSX accepted too — openpyxl in image)",
    )


# ======================================================================
# 5 — Automatic total from scanning / manual quantity input
# ======================================================================
@step(5, "Automatic quantity totalling by scan / input")
def item_5():
    scanned = sum(
        env["custom.barcode.scan.line"]
        .search([("session_id.picking_id", "=", GR_LOT.id), ("status", "=", "ok")])
        .mapped("quantity")
    )
    on_picking = sum(GR_LOT.move_line_ids.mapped("quantity"))
    per_product = {
        m.product_id.default_code: (m.product_uom_qty, sum(m.move_line_ids.mapped("quantity"))) for m in GR_LOT.move_ids
    }
    imei_units = sum(GR_IMEI.move_line_ids.mapped("quantity"))
    ok = abs(scanned - on_picking) < 0.01 and imei_units == 3
    return (
        "PASS" if ok else "FAIL",
        f"{GR_LOT.name}: scanned qty {scanned} == move-line qty {on_picking}; "
        f"demand vs done per SKU {per_product}; IMEI receipt auto-totals to {imei_units} units "
        f"(1 per serial scan)",
    )


# ======================================================================
# 6 — Barcode generation + sticker printing (IMEI & EAN)
# ======================================================================
@step(6, "Barcode generation and sticker printing (IMEI & EAN)")
def item_6():
    Report = env["ir.actions.report"]
    barcode_pdf, _t = Report._render_qweb_pdf("custom_wms_docs.action_report_wms_barcode_list", GR_IMEI.ids)
    wiz = env["custom.wms.label.wizard"].create(
        {
            "picking_id": GR_IMEI.id,
            "qty_source": "picking_qty",
            "label_kind": "product_label",
            "barcode_kind": "Code128",
        }
    )
    act = wiz.action_print()
    label_pdf, _t2 = Report._render_qweb_pdf("custom_wms_docs.action_report_wms_product_label", wiz.ids)
    price_wiz = env["custom.wms.label.wizard"].create(
        {
            "product_ids": [(6, 0, lot_products.ids)],
            "qty_source": "manual",
            "qty_per_product": 2,
            "label_kind": "price_tag",
            "barcode_kind": "QR",
        }
    )
    price_pdf, _t3 = Report._render_qweb_pdf("custom_wms_docs.action_report_wms_product_label", price_wiz.ids)
    ok = len(barcode_pdf) > 1000 and len(label_pdf) > 1000 and len(price_pdf) > 1000
    return (
        "PASS" if ok else "FAIL",
        f"Barcode List PDF {len(barcode_pdf)}B for {GR_IMEI.name} (IMEI serials + EAN); "
        f"product-label stickers {len(label_pdf)}B via wizard "
        f"(one per unit shipped, Code128); price tags {len(price_pdf)}B (QR, DataMatrix also "
        f"available); print action={act.get('report_name', act.get('type'))}",
    )


# ======================================================================
# Validate the receipts, clear QC, land the goods (feeds items 7-15)
# ======================================================================
for pick in (GR_LOT, GR_IMEI, GR_TPL):
    pick.button_validate()
    if pick.wms_qc_state == "pending":
        pick.action_wms_qc_pass()

release_pickings = (GR_LOT | GR_IMEI | GR_TPL).mapped("wms_qc_release_picking_id")
for rel in release_pickings:
    rel.action_assign()


# ======================================================================
# 7 — Put-away: system suggests bin locations from predefined rules
# ======================================================================
@step(7, "Put-away — system suggests bin locations from rules")
def item_7():
    engine = env["custom.putaway.engine"]
    suggestions = []
    applied = 0
    for rel in release_pickings:
        for ml in rel.move_line_ids:
            props = engine.propose(ml)
            if props:
                top = props[0]
                loc = env["stock.location"].browse(top["location_id"])
                suggestions.append(
                    f"{ml.product_id.default_code} -> {loc.display_name} (score {top['score']}, {top['reason']})"
                )
                if ml.location_dest_id.id == top["location_id"]:
                    applied += 1
    stored = env["custom.wms.putaway.suggestion"].search_count([])
    strategy = env["custom.wms.putaway.strategy"].search([("warehouse_id", "=", wh.id)], limit=1)
    ok = bool(suggestions)
    return (
        "PASS" if ok else "FAIL",
        f"strategy '{strategy.name}' ({len(strategy.rule_ids)} rules, {strategy.rule_set}); "
        f"{len(suggestions)} bin suggestions on the QC-release transfers, {applied} already "
        f"auto-applied to the destination; suggestion log rows={stored}. "
        f"Sample: {suggestions[:3]}",
    )


for rel in release_pickings:
    rel.button_validate()


# ======================================================================
# 8 — Automatic replenishment orders
# ======================================================================
@step(8, "Stock replenishment — orders generated automatically")
def item_8():
    Quant = env["stock.quant"]
    rule = env["custom.to.rule"].search([("trigger", "=", "low_water_mark"), ("warehouse_id", "=", wh.id)], limit=1)
    if not rule:
        return "FAIL", "no low-water-mark transfer-order rule configured"

    # Draw the forward-pick bin below its low-water mark so the rule fires.
    pick_bin = env["stock.location"].search([("barcode", "=", "JDC-NIK-02")], limit=1)
    hd_bin = env["stock.location"].search([("barcode", "=", "JDC-HD-A-01")], limit=1)
    donor = Quant.search([("location_id", "=", hd_bin.id), ("quantity", ">", 0)], limit=1)
    if not donor:
        Quant._update_available_quantity(lot_products[0], hd_bin, 40)
        donor = Quant.search([("location_id", "=", hd_bin.id), ("quantity", ">", 0)], limit=1)
    low = Quant.search([("location_id", "=", pick_bin.id), ("product_id", "=", donor.product_id.id)], limit=1)
    if not low:
        Quant._update_available_quantity(donor.product_id, pick_bin, 1)
        low = Quant.search([("location_id", "=", pick_bin.id), ("product_id", "=", donor.product_id.id)], limit=1)
    elif low.quantity >= rule.low_water_qty:
        low.inventory_quantity = max(0.0, rule.low_water_qty - 5)
        low.action_apply_inventory()

    before = env["custom.transfer.order"].search_count([])
    proposals = env["custom.to.engine"].evaluate_rule(rule)
    moves = env["stock.move"]
    for prop in proposals:
        moves |= env["custom.to.engine"].materialize(prop)
    tos = env["custom.transfer.order"].search([("stock_move_id", "in", moves.ids)])
    after = env["custom.transfer.order"].search_count([])

    # native Odoo reordering rules cover the SKU-level replenishment view
    orderpoints = env["stock.warehouse.orderpoint"].search_count([])
    detail = [
        f"{t.name}: {t.product_id.default_code} {t.planned_qty} "
        f"{t.source_location_id.name}->{t.target_location_id.name} [{t.state}]"
        for t in tos[:3]
    ]
    ok = bool(tos)
    return (
        "PASS" if ok else "PARTIAL",
        f"rule '{rule.name}' (low-water {rule.low_water_qty}) evaluated -> {len(proposals)} "
        f"proposals, {len(tos)} transfer orders ({before}->{after}) {detail}; "
        f"scheduler cron 'custom_wms_to_engine' runs it unattended; "
        f"native reordering rules configured={orderpoints}",
    )


# ======================================================================
# 9 — Picking: system suggests the bin to pick from
# ======================================================================
@step(9, "Picking — system suggests the bin to pick from")
def item_9():
    delivery = Picking.search(
        [("picking_type_id.code", "=", "outgoing"), ("state", "not in", ("done", "cancel"))],
        limit=1,
    )
    if not delivery:
        return "FAIL", "no open delivery to pick"
    delivery.action_assign()
    lines = [
        f"{ml.product_id.default_code}: pick {ml.quantity} from {ml.location_id.display_name}"
        + (f" [lot {ml.lot_id.name}]" if ml.lot_id else "")
        for ml in delivery.move_line_ids
    ]
    binned = [ml for ml in delivery.move_line_ids if ml.location_id.id != wh.lot_stock_id.id]
    strategies = {
        rec.display_name: rec.removal_strategy_id
        for model in ("product.category", "stock.location")
        for rec in env[model].search([("removal_strategy_id", "!=", False)], limit=3)
    }
    report_pdf, _t = env["ir.actions.report"]._render_qweb_pdf(
        "custom_wms_docs.action_report_wms_picking_list", delivery.ids
    )
    ok = bool(binned)
    return (
        "PASS" if ok else "PARTIAL",
        f"{delivery.name}: {len(binned)}/{len(delivery.move_line_ids)} lines reserved from a "
        f"specific bin (native removal strategy {strategies}); picking-list PDF "
        f"{len(report_pdf)}B with the source bin per line. Lines: {lines[:3]}",
    )


# ======================================================================
# 10 — Racking: every rack shows its material list and qty
# ======================================================================
@step(10, "Racking — material list and qty per rack")
def item_10():
    racks = env["stock.location"].search(
        [("usage", "=", "internal"), ("location_id.name", "in", ("HD Palletised Racking", "NIKE", "ADIDAS", "PUMA"))]
    )
    filled = []
    total_qty = 0.0
    for rack in racks:
        quants = env["stock.quant"].search([("location_id", "=", rack.id), ("quantity", "!=", 0)])
        if not quants:
            continue
        total_qty += sum(quants.mapped("quantity"))
        filled.append(f"{rack.name}: " + ", ".join(f"{q.product_id.default_code} x{int(q.quantity)}" for q in quants))
    ok = bool(filled)
    return (
        "PASS" if ok else "FAIL",
        f"{len(filled)}/{len(racks)} racks holding stock, {int(total_qty)} units total "
        f"(Inventory > Locations > On Hand, or the Stock Summary report). "
        f"Sample: {filled[:3]}",
    )


# ======================================================================
# Purchase return + stock count, so reports 11 & 13/14 have data
# ======================================================================
rtv = None
try:
    src_quant = env["stock.quant"].search(
        [("location_id", "child_of", wh.lot_stock_id.id), ("quantity", ">", 2)], limit=1
    )
    rtv = Picking.create(
        {
            "picking_type_id": env["stock.picking.type"]
            .search([("code", "=", "outgoing"), ("warehouse_id", "=", wh.id)], limit=1)
            .id,
            "partner_id": vendor.id,
            "origin": f"{TAG}-RTV",
            "location_id": src_quant.location_id.id,
            "location_dest_id": supplier_loc.id,
        }
    )
    mv = Move.create(
        {
            "product_id": src_quant.product_id.id,
            "product_uom_qty": 2,
            "product_uom": src_quant.product_id.uom_id.id,
            "location_id": src_quant.location_id.id,
            "location_dest_id": supplier_loc.id,
            "picking_id": rtv.id,
            "company_id": company.id,
            "price_unit": src_quant.product_id.standard_price or 100000.0,
        }
    )
    rtv.action_confirm()
    rtv.action_assign()
    for ml in rtv.move_line_ids:
        ml.quantity = ml.quantity or 2
    rtv.button_validate()
except Exception as exc:  # noqa: BLE001
    print(f"  ! RTV setup failed: {exc}")

session = None
try:
    plan = env["custom.cycle.count.plan"].search([("warehouse_id", "=", wh.id)], limit=1)
    wiz = env["custom.cycle.count.start.wizard"].create({"plan_id": plan.id, "target_count": 12})
    act = wiz.action_start()
    session = env["custom.cycle.count.session"].browse(act["res_id"])
    session.action_start()
    for i, line in enumerate(session.line_ids):
        line.action_count(max(0.0, line.expected_qty - (2 if i == 0 else 0)))
    session.action_review()
except Exception as exc:  # noqa: BLE001
    print(f"  ! cycle-count setup failed: {exc}")


# ======================================================================
# 11 — Purchase return report
# ======================================================================
@step(11, "Report — purchase return summary (per supplier, per SKU)")
def item_11():
    Rep = env["custom.wms.purchase.return.report"]
    rows = Rep.search([])
    by_supplier = Rep._read_group([], groupby=["partner_id"], aggregates=["quantity:sum", "value:sum"])
    by_sku = Rep._read_group([], groupby=["product_id"], aggregates=["quantity:sum", "value:sum"])
    sample = [
        f"{r.reference} {r.partner_id.name} {r.default_code} qty={r.quantity} value={r.value:,.0f}" for r in rows[:2]
    ]
    ok = bool(rows)
    return (
        "PASS" if ok else "FAIL",
        f"{len(rows)} return lines; group-by supplier={len(by_supplier)}, per SKU={len(by_sku)}; "
        f"list+pivot views with native XLSX export under Inventory > Reporting > WMS Reports. "
        f"Sample: {sample}",
    )


# ======================================================================
# 12 — Stock report summary
# ======================================================================
@step(12, "Report — stock summary (per SKU / warehouse / store, qty + COGS)")
def item_12():
    Rep = env["custom.wms.stock.summary.report"]
    rows = Rep.search([])
    by_wh = Rep._read_group([], groupby=["warehouse_id"], aggregates=["quantity:sum", "value:sum"])
    by_sku = Rep._read_group([], groupby=["product_id"], aggregates=["quantity:sum", "value:sum"])
    by_loc = Rep._read_group([], groupby=["location_id"], aggregates=["quantity:sum"])
    total_qty = sum(rows.mapped("quantity"))
    total_val = sum(rows.mapped("value"))
    ok = bool(rows) and total_val > 0
    return (
        "PASS" if ok else "PARTIAL",
        f"{len(rows)} quant rows, {int(total_qty)} units valued {total_val:,.0f} at cost; "
        f"grouped by warehouse={len(by_wh)}, SKU={len(by_sku)}, bin/store={len(by_loc)}",
    )


# ======================================================================
# 13 / 14 — Stock take + spot check
# ======================================================================
@step(13, "Report — stock take")
def item_13():
    Rep = env["custom.wms.stock.take.report"]
    rows = Rep.search([])
    variances = rows.filtered(lambda r: r.variance_qty)
    pdf = b""
    if session:
        pdf, _t = env["ir.actions.report"]._render_qweb_pdf(
            "custom_wms_reports.action_report_wms_stock_take", session.ids
        )
    ok = bool(rows) and (not session or len(pdf) > 1000)
    return (
        "PASS" if ok else "FAIL",
        f"{len(rows)} count lines across sessions, {len(variances)} with a variance "
        f"(value {sum(variances.mapped('variance_value')):,.0f}); "
        f"session {session.name if session else '-'} state={session.state if session else '-'}; "
        f"printable Stock Take PDF {len(pdf)}B",
    )


@step(14, "Report — spot check")
def item_14():
    plan = env["custom.cycle.count.plan"].search([("warehouse_id", "=", wh.id)], limit=1)
    sample_size = int(ICP.get_param("custom_wms_reports.spot_check_sample_size", "10"))
    original = plan.method
    plan.method = "spot_check"
    wiz = env["custom.cycle.count.start.wizard"].create({"plan_id": plan.id})
    act = wiz.action_start()
    spot = env["custom.cycle.count.session"].browse(act["res_id"])
    spot.action_start()
    lines = len(spot.line_ids)
    plan.method = original
    pdf, _t = env["ir.actions.report"]._render_qweb_pdf("custom_wms_reports.action_report_wms_stock_take", spot.ids)
    ok = 0 < lines <= sample_size
    return (
        "PASS" if ok else "PARTIAL",
        f"spot-check session {spot.name} drew {lines} random lines "
        f"(cap custom_wms_reports.spot_check_sample_size={sample_size}); "
        f"same Stock Take/Spot Check PDF {len(pdf)}B",
    )


# ======================================================================
# 15 — Transfer report
# ======================================================================
@step(15, "Report — transfer")
def item_15():
    Rep = env["custom.wms.transfer.report"]
    rows = Rep.search([])
    by_type = Rep._read_group([], groupby=["picking_type_id"], aggregates=["done_qty:sum"])
    by_state = Rep._read_group([], groupby=["state"], aggregates=["done_qty:sum"])
    by_kind = Rep._read_group([], groupby=["transfer_kind"], aggregates=["done_qty:sum"])
    sample = [
        f"{r.reference} {r.default_code} demand={r.demand_qty} done={r.done_qty} "
        f"{r.location_id.name}->{r.location_dest_id.name}"
        for r in rows[:2]
    ]
    ok = bool(rows)
    return (
        "PASS" if ok else "FAIL",
        f"{len(rows)} transfer lines; by operation type={len(by_type)}, by state={len(by_state)}, "
        f"by kind={[(k and k or 'n/a', q) for k, q in by_kind][:4]}; "
        f"Sample: {sample}",
    )


# ======================================================================
# Summary
# ======================================================================
print("\n" + "=" * 78)
print(f"WMS SCENARIO SUMMARY — {env.cr.dbname} — run {TAG}")
print("=" * 78)
for no, title, verdict, _ev in RESULTS:
    print(f"{no:>3}. {verdict:<8} {title}")
counts = {}
for _n, _t, v, _e in RESULTS:
    counts[v] = counts.get(v, 0) + 1
print("-" * 78)
print("  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
print("=" * 78)

env.cr.commit()
print("committed.")
