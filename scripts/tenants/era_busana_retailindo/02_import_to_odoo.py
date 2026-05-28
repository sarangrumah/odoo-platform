"""Import categories, attributes, templates, variants into Odoo tenant DB.

Runs INSIDE odoo-mgmt container via:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d era_busana_retailindo --no-http < 02_import_to_odoo.py

Reads CSVs from /mnt/scripts/tenants/era_busana_retailindo/ (mounted from host).
Uses Odoo ORM with batched commits for performance on 159k SKUs.

Strategy:
  1. product.category — 3-level tree (CATEGORY > CLASS > SUBCLASS).
  2. product.attribute — Size + Inseam, with all distinct values.
  3. product.template — 14,885 templates with attribute_line_ids.
     Odoo will auto-generate cartesian product variants.
  4. product.product — match auto-generated variants by (template, size, inseam)
     and update default_code + barcode from our SKU table.
"""
import csv
import logging
import os
import sys
import time

_logger = logging.getLogger("era_import")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logger.addHandler(h)

CSV_DIR = "/tmp/era"

# `env` is provided by odoo shell

def log(msg):
    _logger.info(msg)
    sys.stderr.flush()


def commit():
    env.cr.commit()


# ============================================================
# 1. CATEGORIES
# ============================================================
log("=== STEP 1: Categories ===")
t0 = time.time()
xid_to_id = {}  # category xid -> product.category id
with open(os.path.join(CSV_DIR, "out_categories.csv"), encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
# Two passes: parents first (sorted by xid prefix l1, l2, l3)
for pass_prefix in ("cat_l1_", "cat_l2_", "cat_l3_"):
    batch = []
    for r in rows:
        if not r["xid"].startswith(pass_prefix):
            continue
        if r["xid"] in xid_to_id:
            continue
        # Check if already exists by xid via ir.model.data
        ext = env["ir.model.data"].search(
            [("module", "=", "era_busana"), ("name", "=", r["xid"]), ("model", "=", "product.category")],
            limit=1,
        )
        if ext:
            xid_to_id[r["xid"]] = ext.res_id
            continue
        parent_id = xid_to_id.get(r["parent_xid"]) if r["parent_xid"] else False
        cat = env["product.category"].create({"name": r["name"], "parent_id": parent_id})
        env["ir.model.data"].create(
            {"module": "era_busana", "name": r["xid"], "model": "product.category", "res_id": cat.id, "noupdate": True}
        )
        xid_to_id[r["xid"]] = cat.id
    commit()
log(f"Categories: {len(xid_to_id)} created/loaded in {time.time() - t0:.1f}s")

# ============================================================
# 2. ATTRIBUTES (Size + Inseam) with all values
# ============================================================
log("=== STEP 2: Attributes ===")
t0 = time.time()
# Create or fetch attributes
attr_by_name = {}
for attr_name in ("Size", "Inseam"):
    attr = env["product.attribute"].search([("name", "=", attr_name)], limit=1)
    if not attr:
        attr = env["product.attribute"].create(
            {
                "name": attr_name,
                "create_variant": "always",
                "display_type": "radio",
            }
        )
    attr_by_name[attr_name] = attr

# Load values
attr_value_id = {}  # (attr_name, value) -> product.attribute.value id
with open(os.path.join(CSV_DIR, "out_attributes.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        attr = attr_by_name[r["attribute"]]
        v = env["product.attribute.value"].search(
            [("attribute_id", "=", attr.id), ("name", "=", r["value"])], limit=1
        )
        if not v:
            v = env["product.attribute.value"].create({"attribute_id": attr.id, "name": r["value"]})
        attr_value_id[(r["attribute"], r["value"])] = v.id
commit()
log(f"Attributes: 2 + {len(attr_value_id)} values in {time.time() - t0:.1f}s")

# ============================================================
# 3. TEMPLATES
# ============================================================
log("=== STEP 3: Templates ===")
t0 = time.time()

# Load template->attribute mapping
tmpl_attrs = {}  # tmpl_xid -> {"Size": [v1, v2], "Inseam": [...]}
with open(os.path.join(CSV_DIR, "out_template_attrlines.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        tmpl_attrs.setdefault(r["tmpl_xid"], {}).setdefault(r["attribute"], []).append(r["value"])

# Process templates in batches
tmpl_xid_to_id = {}
BATCH_TMPL = 200

# Pre-load existing
existing = env["ir.model.data"].search([("module", "=", "era_busana"), ("model", "=", "product.template")])
for ext in existing:
    tmpl_xid_to_id[ext.name] = ext.res_id
log(f"  existing templates already loaded: {len(tmpl_xid_to_id)}")

with open(os.path.join(CSV_DIR, "out_templates.csv"), encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
log(f"  total templates to process: {len(rows)}")

processed = 0
for batch_start in range(0, len(rows), BATCH_TMPL):
    batch = rows[batch_start : batch_start + BATCH_TMPL]
    for r in batch:
        if r["tmpl_xid"] in tmpl_xid_to_id:
            continue
        categ_id = xid_to_id.get(r["categ_xid"])
        attr_lines = []
        for attr_name, values in tmpl_attrs.get(r["tmpl_xid"], {}).items():
            attr = attr_by_name[attr_name]
            value_ids = [attr_value_id[(attr_name, v)] for v in values if (attr_name, v) in attr_value_id]
            if value_ids:
                attr_lines.append((0, 0, {"attribute_id": attr.id, "value_ids": [(6, 0, value_ids)]}))
        vals = {
            "name": r["name"] or r["default_code"],
            "default_code": r["default_code"],
            "list_price": float(r["list_price"] or 0),
            "type": "consu",
            "sale_ok": True,
            "purchase_ok": True,
        }
        if categ_id:
            vals["categ_id"] = categ_id
        if attr_lines:
            vals["attribute_line_ids"] = attr_lines
        tmpl = env["product.template"].create(vals)
        env["ir.model.data"].create(
            {
                "module": "era_busana",
                "name": r["tmpl_xid"],
                "model": "product.template",
                "res_id": tmpl.id,
                "noupdate": True,
            }
        )
        tmpl_xid_to_id[r["tmpl_xid"]] = tmpl.id
    commit()
    processed += len(batch)
    if processed % 1000 == 0 or processed == len(rows):
        log(f"  templates created: {processed}/{len(rows)} ({(time.time() - t0):.1f}s)")
log(f"Templates: {len(tmpl_xid_to_id)} total in {time.time() - t0:.1f}s")

# ============================================================
# 4. VARIANTS — set SKU + barcode on auto-generated variants
# ============================================================
log("=== STEP 4: Variant matching (SKU + barcode) ===")
t0 = time.time()

# Build lookup from product.attribute.value name -> id for fast match
size_val_id = {v: i for (a, v), i in attr_value_id.items() if a == "Size"}
inseam_val_id = {v: i for (a, v), i in attr_value_id.items() if a == "Inseam"}

matched = 0
unmatched = 0
processed = 0
BATCH_VAR = 2000

with open(os.path.join(CSV_DIR, "out_variants.csv"), encoding="utf-8") as f:
    var_rows = list(csv.DictReader(f))
log(f"  total variants to match: {len(var_rows)}")

# Group variants by template for efficient lookup
by_tmpl = {}
for r in var_rows:
    by_tmpl.setdefault(r["tmpl_xid"], []).append(r)

tmpl_keys = list(by_tmpl.keys())
for batch_start in range(0, len(tmpl_keys), 100):
    batch_tmpl_xids = tmpl_keys[batch_start : batch_start + 100]
    tmpl_ids = [tmpl_xid_to_id[x] for x in batch_tmpl_xids if x in tmpl_xid_to_id]
    if not tmpl_ids:
        continue
    # Fetch all variants for these templates with their attribute combinations
    variants = env["product.product"].search([("product_tmpl_id", "in", tmpl_ids)])
    # Build lookup: (tmpl_id, frozenset(value_ids)) -> product.product
    var_index = {}
    for v in variants:
        combo = frozenset(v.product_template_variant_value_ids.product_attribute_value_id.ids)
        var_index[(v.product_tmpl_id.id, combo)] = v

    # Match each variant row
    for tmpl_xid in batch_tmpl_xids:
        tmpl_id = tmpl_xid_to_id.get(tmpl_xid)
        if not tmpl_id:
            unmatched += len(by_tmpl[tmpl_xid])
            continue
        for r in by_tmpl[tmpl_xid]:
            wanted_vals = set()
            if r["size"]:
                vid = size_val_id.get(r["size"])
                if vid:
                    wanted_vals.add(vid)
            if r["inseam"]:
                vid = inseam_val_id.get(r["inseam"])
                if vid:
                    wanted_vals.add(vid)
            combo = frozenset(wanted_vals)
            v = var_index.get((tmpl_id, combo))
            if v:
                # Update only if changed
                updates = {}
                if v.default_code != r["sku"]:
                    updates["default_code"] = r["sku"]
                if r["gtin"] and v.barcode != r["gtin"]:
                    updates["barcode"] = r["gtin"]
                if updates:
                    try:
                        v.write(updates)
                        matched += 1
                    except Exception as e:
                        # Possibly duplicate barcode — log and skip barcode
                        if "barcode" in updates:
                            try:
                                v.write({k: vv for k, vv in updates.items() if k != "barcode"})
                                matched += 1
                            except Exception:
                                unmatched += 1
                        else:
                            unmatched += 1
                else:
                    matched += 1
            else:
                unmatched += 1
            processed += 1
    commit()
    if processed % 10000 < 100:
        log(f"  variants matched: {matched}, unmatched: {unmatched} ({processed}/{len(var_rows)}, {time.time() - t0:.1f}s)")

log(
    f"Variants done: matched={matched}, unmatched={unmatched}, total_processed={processed} in {time.time() - t0:.1f}s"
)

log("=== IMPORT COMPLETE ===")
log(
    f"Summary: categories={len(xid_to_id)}, templates={len(tmpl_xid_to_id)}, "
    f"variants_matched={matched}, variants_unmatched={unmatched}"
)
