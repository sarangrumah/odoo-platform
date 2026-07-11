# Backfill prd_levis with the X101 garment variants that X24DN needs but prd_levis lacks,
# cloned from prd_levis_begbal (the parity reference).
#
#   docker cp scripts/tenants/levis/clone_products.json odoo19-platform-odoo:/tmp/levis/clone_products.json
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis --no-http < scripts/tenants/levis/64_clone_x24_products.py
#
# Why: prd_levis never received the multi-GTIN X101 re-import that begbal did, so 34 ITEM CODEs
# (182 sized variants) sold in June 2026 are absent from its master. Under strict-product mode
# those park ~525 (12%) of transactions. This creates exactly those 182 products so the X24DN
# import reproduces begbal (0 parked).
#
# Each product is a standalone consumable carrying the begbal default_code + main barcode +
# every GTIN alias (product.barcode), filed under the SAME category (matched by complete_name,
# which already exists on prd_levis). Attributes/templates are NOT replicated: X24 resolves by
# default_code/barcode only, and accounting routes by category. Idempotent by default_code.
#
# Env: CLONE_DRY=1 -> build & report, roll back.
import json
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[clone] " + m)

JSON_PATH = "/tmp/levis/clone_products.json"
DRY = os.environ.get("CLONE_DRY") == "1"

Product = env["product.product"]
Template = env["product.template"]
Category = env["product.category"]
Barcode = env["product.barcode"] if "product.barcode" in env else None

with open(JSON_PATH) as f:
    prods = json.load(f)
log("input products: %d  (product.barcode model: %s)" % (len(prods), bool(Barcode)))

# category cache by complete_name
_cat = {}


def resolve_category(name):
    if name not in _cat:
        c = Category.search([("complete_name", "=", name)], limit=1)
        _cat[name] = c.id if c else False
    return _cat[name]


created = skipped_exist = alias_added = no_cat = 0
missing_cats = set()

for p in prods:
    dc = p["default_code"]
    existing = Product.search([("default_code", "=", dc)], limit=1)
    if existing:
        skipped_exist += 1
        prod = existing
    else:
        cat_id = resolve_category(p["category"])
        if not cat_id:
            missing_cats.add(p["category"])
            no_cat += 1
            continue
        vals = {
            "name": p["name"] or dc,
            "default_code": dc,
            "type": p.get("type") or "consu",
            "categ_id": cat_id,
            "sale_ok": True,
            "purchase_ok": True,
            "company_id": False,
        }
        if p.get("barcode"):
            # avoid a duplicate-barcode clash: only set if free
            if not Product.search_count([("barcode", "=", p["barcode"])]):
                vals["barcode"] = p["barcode"]
        tmpl = Template.create(vals)
        prod = tmpl.product_variant_id
        created += 1

    # barcode aliases (idempotent)
    if Barcode is not None:
        want = set(a for a in p.get("aliases", []) if a)
        if p.get("barcode"):
            want.add(p["barcode"])
        have = set(Barcode.search([("product_id", "=", prod.id)]).mapped("barcode"))
        for bc in sorted(want - have):
            if Barcode.search_count([("barcode", "=", bc)]):
                continue  # alias already owned by another product; leave it
            Barcode.create({"product_id": prod.id, "barcode": bc})
            alias_added += 1

    if (created + skipped_exist) % 50 == 0:
        log("... processed %d" % (created + skipped_exist))

log(
    "==== created=%d already_existed=%d aliases_added=%d no_category=%d ===="
    % (created, skipped_exist, alias_added, no_cat)
)
if missing_cats:
    log("MISSING categories: %s" % sorted(missing_cats))

if DRY:
    env.cr.rollback()
    log("CLONE_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
