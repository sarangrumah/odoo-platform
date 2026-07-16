"""Apply Levi's X20 opening on-hand stock as inventory adjustments (run in CONTAINER).

    docker cp "docs/projects/levis/X20_Current_Onhand_Inventory_Report- For current inventory.csv" \
        odoo19-platform-odoo-mgmt:/tmp/levis/X20.csv
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d levis --no-http < scripts/tenants/levis/05_load_x20.py

Standalone Track A equivalent of retail.import.executor._load_x20 — lets opening stock
load at go-live without the module / image rebuild (X20 is CSV, no openpyxl needed).

ONE-SHOT: re-running would DOUBLE on-hand. Guarded by a marker ir.config_parameter.
Prereqs: products (02) and warehouses (04) loaded first.
"""

import csv
import os
import sys

CSV_DIR = os.environ.get("LEVIS_CSV_DIR", "/tmp/levis")
NS = "levis"
MARKER = "levis.x20_opening_stock_applied"

# X20 real columns (0-based): 15=STORE_CODE,18=ITEM_ID,22=EAN,28=ONHAND_QTY
C_STORE, C_ITEM, C_EAN, C_QTY = 15, 18, 22, 28


def log(m):
    sys.stderr.write(m + "\n")
    sys.stderr.flush()


if env["ir.config_parameter"].sudo().get_param(MARKER):
    log("ABORT: X20 opening stock already applied (marker set). Clear the parameter to override.")
else:
    def safe_xid(prefix, value):
        return prefix + "".join(c if c.isalnum() else "_" for c in str(value)).upper()

    def wh_location(code):
        ext = env["ir.model.data"].search(
            [("module", "=", NS), ("name", "=", safe_xid("wh_", code)), ("model", "=", "stock.warehouse")],
            limit=1,
        )
        return env["stock.warehouse"].browse(ext.res_id).lot_stock_id if ext else False

    Product = env["product.product"]
    loc_cache, bc_cache, code_cache = {}, {}, {}
    applied = skipped = 0
    errors = []

    path = os.path.join(CSV_DIR, "X20.csv")
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f))

    n = 0
    for i, row in enumerate(rows, start=1):
        if i == 1 or len(row) <= C_QTY:
            continue
        store = str(row[C_STORE]).strip()
        if not store.isdigit():
            continue
        try:
            qty = float(str(row[C_QTY]).replace(",", "").strip() or 0)
        except ValueError:
            qty = 0
        if qty <= 0:
            continue
        if store not in loc_cache:
            loc_cache[store] = wh_location(store)
        loc = loc_cache[store]
        if not loc:
            errors.append(f"row {i}: store {store} -> no warehouse")
            continue
        ean = str(row[C_EAN]).strip()
        item = str(row[C_ITEM]).strip()
        prod = False
        if ean:
            if ean not in bc_cache:
                bc_cache[ean] = Product.search([("barcode", "=", ean)], limit=1)
            prod = bc_cache[ean]
        if not prod and item:
            if item not in code_cache:
                code_cache[item] = Product.search([("default_code", "=", item)], limit=1)
            prod = code_cache[item]
        if not prod:
            skipped += 1
            errors.append(f"row {i}: no product ean={ean} item={item}")
            continue
        try:
            q = env["stock.quant"].with_context(inventory_mode=True).create(
                {"product_id": prod.id, "location_id": loc.id, "inventory_quantity": qty}
            )
            q.action_apply_inventory()
            applied += 1
        except Exception as e:
            errors.append(f"row {i}: {prod.default_code}: {e}")
        n += 1
        if n % 500 == 0:
            env.cr.commit()
            log(f"  applied={applied} skipped={skipped} errors={len(errors)} ...")

    env["ir.config_parameter"].sudo().set_param(MARKER, "1")
    env.cr.commit()
    log(f"X20 done: applied={applied} skipped={skipped} errors={len(errors)}")
    for e in errors[:30]:
        log("  " + e)
