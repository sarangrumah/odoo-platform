# Align the product-category tree with the EBR COA revenue buckets (run via odoo shell).
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http < scripts/tenants/levis/34_coa_categ_tree.py
#
# Why: X101 builds a merchandising tree (MENS TOPS / WOMENS BOTTOMS / ...) that carries no
# link to the COA, and the X24 lazy-create path files non-merchandise lines (tailoring
# services, paid paperbags) under NO category at all -- so their revenue silently lands on
# the company fallback account 5199000000 "Gross Sales-Others".
#
# This script:
#   1. creates one root category per COA revenue bucket (Textile / Footwear / Accessories /
#      Miscellaneous / Wholesale / E-commerce / Clearance / Distributor / Merchandise /
#      Others / Labor (Service)),
#   2. re-parents the X101 merchandising roots under the matching COA root,
#   3. maps income / expense / valuation / GR-IR on EVERY category from its COA root,
#   4. files the lazy-created X24 non-merchandise products: code prefix "TS" (tailoring,
#      i.e. Original Cut / hemming / repair / patches) -> Labor (Service) 5117000000,
#      everything else (paid paperbags BGNM*) -> Others 5199000000.
#
# Idempotent: re-running only rewrites values that already differ.
#
# Env flags:
#   CATEG_DRY=1   -> build & report, roll back instead of committing
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[categ] " + m)

COMPANY_ID = 1
DRY = os.environ.get("CATEG_DRY") == "1"

company = env["res.company"].browse(COMPANY_ID)
Acc = env["account.account"].with_company(company)
Categ = env["product.category"].with_company(company)
log("company=%s dry=%s" % (company.name, DRY))

_code2acc = {a.code: a for a in Acc.search([]) if a.code}


def acc(code):
    a = _code2acc.get(code)
    if not a:
        raise KeyError("account code %s not found (run 30_fix_coa.py first)" % code)
    return a


STJ = env["account.journal"].search([("code", "=", "STJ")], limit=1) or env["account.journal"].search(
    [("type", "=", "general")], limit=1
)

# ---- 1. COA revenue buckets -> root category definition -------------------------
# val/grir are None for the service bucket: labour has no inventory and no COA
# counterpart (there is no 6117/1113…17/21031091…17 account).
#
# disc/ret are the contra-revenue accounts the retail import books X24DN's
# NET DISCOUNT AMOUNT and X48's customer returns to (custom_retail_import).
# The COA has no per-channel discount account for wholesale / e-commerce /
# clearance / distributor / others, so those share the generic
# 5220000000 "sales discounts & rebates allowed-Sports & Apparel".
BUCKETS = {
    "Textile": dict(
        inc="5120010001", exp="6120010001", val="1113100021", grir="2103109121", disc="5220000001", ret="5320010001"
    ),
    "Footwear": dict(
        inc="5120010002", exp="6120010002", val="1113100022", grir="2103109122", disc="5220000002", ret="5320010002"
    ),
    "Accessories": dict(
        inc="5120010003", exp="6120010003", val="1113100023", grir="2103109123", disc="5220000003", ret="5320010003"
    ),
    "Miscellaneous": dict(
        inc="5120010004", exp="6120010004", val="1113100024", grir="2103109124", disc="5220000004", ret="5320010004"
    ),
    "Wholesale": dict(
        inc="5120020000", exp="6120020000", val="1113100025", grir="2103109125", disc="5220000000", ret="5320020000"
    ),
    "E-commerce": dict(
        inc="5120030000", exp="6120030000", val="1113100026", grir="2103109126", disc="5220000000", ret="5320030000"
    ),
    "Clearance": dict(
        inc="5120040000", exp="6120040000", val="1113100027", grir="2103109127", disc="5220000000", ret="5320040000"
    ),
    "Distributor": dict(
        inc="5120050000", exp="6120050000", val="1113100028", grir="2103109128", disc="5220000000", ret="5320050000"
    ),
    "Merchandise (non-commercial)": dict(
        inc="5198000000", exp="6198000000", val="1113100098", grir="2103109198", disc="5298000000", ret="5398000000"
    ),
    "Others": dict(
        inc="5199000000", exp="6199000000", val="1113100099", grir="2103109199", disc="5220000000", ret="5399000000"
    ),
    "Labor (Service)": dict(
        inc="5117000000", exp="6199000000", val=None, grir=None, disc="5217000000", ret="5317000000"
    ),
}

roots = {}
for name in BUCKETS:
    r = Categ.search([("name", "=", name), ("parent_id", "=", False)], limit=1)
    if not r:
        r = Categ.create({"name": name})
        log("created root %s (id=%s)" % (name, r.id))
    roots[name] = r

# ---- 2. re-parent the X101 merchandising roots ----------------------------------
REPARENT = {
    "Textile": [
        "MENS TOPS",
        "MENS BOTTOMS",
        "WOMENS TOPS",
        "WOMENS BOTTOMS",
        "BOYS TOPS",
        "BOYS BOTTOMS",
        "DRESSES",
        "SKIRTS",
        "SWEATERS",
        "SWEATSHIRTS",
    ],
    "Footwear": ["MENS FOOTWEAR", "WOMENS FOOTWEAR"],
    "Accessories": ["MENS ACCESSORIES", "WOMENS ACCESSORIES", "BOYS ACCESSORIES", "BAGS", "BELTS", "HEADGEAR"],
    "Miscellaneous": ["Deliveries"],
}
moved = 0
for bucket, names in REPARENT.items():
    for nm in names:
        c = Categ.search([("name", "=", nm), ("parent_id", "=", False)], limit=1)
        if c and c.id != roots[bucket].id:
            c.parent_id = roots[bucket].id
            moved += 1
            log("re-parented %-20s -> %s" % (nm, bucket))
log("re-parented categories: %d" % moved)


def coa_root(cat):
    """Walk up to the COA bucket root; returns its name or None."""
    c = cat
    while c.parent_id:
        c = c.parent_id
    return c.name if c.name in BUCKETS else None


# ---- 3. map accounts on every category from its COA root ------------------------
fixed = 0
for cat in Categ.search([]):
    bucket = coa_root(cat)
    if not bucket:
        continue  # Odoo seed roots (Goods/Expenses/Services/Food) keep their own mapping
    m = BUCKETS[bucket]
    cc = cat.with_company(company)
    vals = {
        "property_account_income_categ_id": acc(m["inc"]).id,
        "property_account_expense_categ_id": acc(m["exp"]).id,
    }
    # Only present once custom_retail_import >= 19.0.0.10.0 is installed.
    if "property_account_sales_discount_categ_id" in Categ._fields:
        vals["property_account_sales_discount_categ_id"] = acc(m["disc"]).id
        vals["property_account_sales_return_categ_id"] = acc(m["ret"]).id
    if m["val"]:
        vals.update(
            {
                "property_valuation": "real_time",
                "property_cost_method": "fifo",
                "property_stock_valuation_account_id": acc(m["val"]).id,
                "account_stock_variation_id": acc(m["grir"]).id,
                "property_stock_journal": STJ.id,
            }
        )
    else:
        vals["property_valuation"] = "periodic"
    delta = {k: v for k, v in vals.items() if (cc[k].id if hasattr(cc[k], "id") else cc[k]) != v}
    if delta:
        cc.write(delta)
        fixed += 1
log("categories (re)mapped: %d" % fixed)

# ---- 4. file the lazy-created X24 non-merchandise products ----------------------
# Identified by their xid namespace (module 'levis', name 'x24prod_*'); they are created
# without a categ_id, which is exactly what routes their revenue to Gross Sales-Others.
# Scope strictly to the x24prod_ xid namespace AND to codes we can positively identify as
# non-merchandise. When strict-product mode is off the same lazy-create path also invents
# products for unmatched *garments* (rnd_levis has ~578 of them), and filing those under
# "Others" would misstate their revenue/COGS/valuation. Anything we cannot classify is left
# alone and reported. Other uncategorised templates (mis-parsed "OLS SES - <store>" rows,
# PROXY placeholders, manual purchase products) are likewise untouched.
SERVICE_PREFIXES = ("TS",)  # tailoring: Original Cut, hemming, repair, patches
OTHER_PREFIXES = ("BGNM",)  # paid carrier bags

# The non-service bucket is config, not a constant: custom_retail_import resolves the same
# ir.config_parameter when it lazy-creates the product, so hardcoding "Others" here would
# silently re-file on the next run whatever the importer had just filed elsewhere.
icp = env["ir.config_parameter"].sudo()
_other_id = int(icp.get_param("retail_import.x24_np_category_id", 0) or 0)
other_root = Categ.browse(_other_id) if _other_id and Categ.browse(_other_id).exists() else roots["Others"]
service_root = roots["Labor (Service)"]
log("x24 non-merch buckets: service=%s other=%s" % (service_root.complete_name, other_root.complete_name))

xids = env["ir.model.data"].search(
    [
        ("module", "=", "levis"),
        ("name", "like", "x24prod_%"),
        ("model", "=", "product.product"),
    ]
)
prods = env["product.product"].browse(xids.mapped("res_id")).exists()
filed = {service_root.complete_name: 0, other_root.complete_name: 0}
unclassified = []
for p in prods:
    code = (p.default_code or "").strip().upper()
    if code.startswith(SERVICE_PREFIXES):
        target = service_root
    elif code.startswith(OTHER_PREFIXES):
        target = other_root
    else:
        unclassified.append(code or p.display_name)
        continue
    if p.product_tmpl_id.categ_id.id != target.id:
        p.product_tmpl_id.categ_id = target.id
    filed[target.complete_name] += 1
log("x24 non-merch products filed: %s" % filed)
if unclassified:
    log("x24 lazy products NOT classified (left as-is, likely unmatched garments): %d" % len(unclassified))
    log("  sample: %s" % ", ".join(unclassified[:8]))

# ---- verify ---------------------------------------------------------------------
log("==== VERIFY ====")
unmapped = Categ.search([("property_account_income_categ_id", "=", False)])
log("categories without income account: %d %s" % (len(unmapped), [c.complete_name for c in unmapped[:8]]))
orphans = env["product.template"].search([("categ_id", "=", False)])
log("templates still without category: %d (left untouched)" % len(orphans))
for t in orphans[:5]:
    log("  orphan: %-36s %s" % ((t.default_code or "-")[:36], (t.name or "")[:40]))
# A sold product with no category books its revenue to the company fallback income
# account. Script 34 cannot fix that -- those SKUs need to be matched to the X101
# master (or strict-product mode enabled) -- so surface it loudly rather than guess.
sold_orphan = env["pos.order.line"].search_count([("product_id.categ_id", "=", False)])
if sold_orphan:
    log(
        "WARNING: %d POS lines point at an uncategorised product -> their revenue falls back "
        "to the company income account. Match those SKUs to X101; do NOT bucket them here." % sold_orphan
    )
else:
    log("POS lines pointing at an uncategorised product: 0")
for name, r in sorted(roots.items()):
    n = Categ.search_count([("id", "child_of", r.id)])
    pr = env["product.template"].search_count([("categ_id", "child_of", r.id)])
    log("  %-28s categs=%-4d templates=%d" % (name, n, pr))

if DRY:
    env.cr.rollback()
    log("CATEG_DRY=1 -> rolled back, nothing committed")
else:
    env.cr.commit()
    log("committed")
log("==== DONE ====")
