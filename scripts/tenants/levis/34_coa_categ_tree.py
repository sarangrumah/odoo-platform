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


STJ = env["account.journal"].search([("code", "=", "STJ")], limit=1) or \
      env["account.journal"].search([("type", "=", "general")], limit=1)

# ---- 1. COA revenue buckets -> root category definition -------------------------
# val/grir are None for the service bucket: labour has no inventory and no COA
# counterpart (there is no 6117/1113…17/21031091…17 account).
BUCKETS = {
    "Textile":                     dict(inc="5120010001", exp="6120010001", val="1113100021", grir="2103109121"),
    "Footwear":                    dict(inc="5120010002", exp="6120010002", val="1113100022", grir="2103109122"),
    "Accessories":                 dict(inc="5120010003", exp="6120010003", val="1113100023", grir="2103109123"),
    "Miscellaneous":               dict(inc="5120010004", exp="6120010004", val="1113100024", grir="2103109124"),
    "Wholesale":                   dict(inc="5120020000", exp="6120020000", val="1113100025", grir="2103109125"),
    "E-commerce":                  dict(inc="5120030000", exp="6120030000", val="1113100026", grir="2103109126"),
    "Clearance":                   dict(inc="5120040000", exp="6120040000", val="1113100027", grir="2103109127"),
    "Distributor":                 dict(inc="5120050000", exp="6120050000", val="1113100028", grir="2103109128"),
    "Merchandise (non-commercial)": dict(inc="5198000000", exp="6198000000", val="1113100098", grir="2103109198"),
    "Others":                      dict(inc="5199000000", exp="6199000000", val="1113100099", grir="2103109199"),
    "Labor (Service)":             dict(inc="5117000000", exp="6199000000", val=None, grir=None),
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
    "Textile": ["MENS TOPS", "MENS BOTTOMS", "WOMENS TOPS", "WOMENS BOTTOMS",
                "BOYS TOPS", "BOYS BOTTOMS", "DRESSES", "SKIRTS", "SWEATERS", "SWEATSHIRTS"],
    "Footwear": ["MENS FOOTWEAR", "WOMENS FOOTWEAR"],
    "Accessories": ["MENS ACCESSORIES", "WOMENS ACCESSORIES", "BOYS ACCESSORIES",
                    "BAGS", "BELTS", "HEADGEAR"],
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
    if m["val"]:
        vals.update({
            "property_valuation": "real_time",
            "property_cost_method": "fifo",
            "property_stock_valuation_account_id": acc(m["val"]).id,
            "account_stock_variation_id": acc(m["grir"]).id,
            "property_stock_journal": STJ.id,
        })
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
# Scope strictly to the x24prod_ xid namespace. Other uncategorised templates exist
# (mis-parsed "OLS SES - <store>" rows, PROXY placeholders, manual purchase products);
# they are never sold at POS, so guessing a revenue bucket for them would be wrong --
# they are reported below instead.
xids = env["ir.model.data"].search([
    ("module", "=", "levis"), ("name", "like", "x24prod_%"), ("model", "=", "product.product"),
])
prods = env["product.product"].browse(xids.mapped("res_id")).exists()
filed = {"Labor (Service)": 0, "Others": 0}
for p in prods:
    code = (p.default_code or "").strip().upper()
    bucket = "Labor (Service)" if code.startswith("TS") else "Others"
    if p.product_tmpl_id.categ_id.id != roots[bucket].id:
        p.product_tmpl_id.categ_id = roots[bucket].id
    filed[bucket] += 1
log("x24 non-merch products filed: %s" % filed)

# ---- verify ---------------------------------------------------------------------
log("==== VERIFY ====")
unmapped = Categ.search_count([("property_account_income_categ_id", "=", False)])
log("categories without income account: %d" % unmapped)
orphans = env["product.template"].search([("categ_id", "=", False)])
log("templates still without category: %d (never sold at POS; left untouched)" % len(orphans))
for t in orphans[:8]:
    log("  orphan: %-36s %s" % ((t.default_code or "-")[:36], (t.name or "")[:40]))
sold_orphan = env["pos.order.line"].search_count([("product_id.categ_id", "=", False)])
log("POS lines pointing at an uncategorised product: %d (must be 0)" % sold_orphan)
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
