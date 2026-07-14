# Idempotent product-category -> EBR COA mapper (run via: odoo shell -d demo_levis).
# Safety net for categories created AFTER 31_config.py ran: only touches categories
# that are missing any required account mapping. Reuses 31_config.py's branch logic
# (textile/footwear/accessories/misc; unknown roots fall back to 'misc').
env = env
log = lambda m: print("[map] " + m)
Acc = env["account.account"].with_company(1)


def acc(code):
    a = Acc.search([("code", "=", code)], limit=1)
    if not a:
        raise Exception("account %s not found" % code)
    return a


ACCMAP = {
    "textile": dict(inc="5120010001", exp="6120010001", val="1113100021", inp="2103109121"),
    "footwear": dict(inc="5120010002", exp="6120010002", val="1113100022", inp="2103109122"),
    "accessories": dict(inc="5120010003", exp="6120010003", val="1113100023", inp="2103109123"),
    "misc": dict(inc="5120010004", exp="6120010004", val="1113100024", inp="2103109124"),
}
STJ = env["account.journal"].search([("code", "=", "STJ")], limit=1) or env["account.journal"].search(
    [("type", "=", "general")], limit=1
)
RES = {b: {k: acc(c) for k, c in m.items()} for b, m in ACCMAP.items()}


def root_name(cat):
    c = cat
    while c.parent_id:
        c = c.parent_id
    return (c.name or "").upper()


# After 34_coa_categ_tree.py the root IS the COA bucket, so read it directly. The
# name-sniffing fallback below only fires on trees that predate that script.
COA_ROOTS = {"TEXTILE": "textile", "FOOTWEAR": "footwear", "ACCESSORIES": "accessories", "MISCELLANEOUS": "misc"}
# X101 roots that carry no MENS/WOMENS/BOYS prefix.
TEXTILE_ROOTS = ("DRESSES", "SKIRTS", "SWEATERS", "SWEATSHIRTS")
ACCESSORY_ROOTS = ("BAGS", "BELTS", "HEADGEAR")


def branch(rn):
    if rn in COA_ROOTS:
        return COA_ROOTS[rn]
    if "FOOTWEAR" in rn:
        return "footwear"
    if "ACCESSORIES" in rn:
        return "accessories"
    if "BOTTOMS" in rn or "TOPS" in rn:
        return "textile"
    if rn in TEXTILE_ROOTS:
        return "textile"
    if rn in ACCESSORY_ROOTS:
        return "accessories"
    return "misc"


def incomplete(cc):
    return not (
        cc.property_account_income_categ_id
        and cc.property_account_expense_categ_id
        and cc.property_stock_valuation_account_id
        and cc.account_stock_variation_id
        and cc.property_stock_journal
        and cc.property_valuation == "real_time"
    )


cats = env["product.category"].search([])
from collections import Counter

bc = Counter()
fixed = 0
for cat in cats:
    cc = cat.with_company(1)
    if not incomplete(cc):
        continue
    b = branch(root_name(cat))
    bc[b] += 1
    m = RES[b]
    cc.write(
        {
            "property_account_income_categ_id": m["inc"].id,
            "property_account_expense_categ_id": m["exp"].id,
            "property_valuation": "real_time",
            "property_cost_method": "fifo",
            "property_stock_valuation_account_id": m["val"].id,
            "account_stock_variation_id": m["inp"].id,
            "property_stock_journal": STJ.id,
        }
    )
    fixed += 1
log("categories fixed: %d by branch %s" % (fixed, dict(bc)))
env.cr.commit()

# ---- verify ----
still = [c.name for c in env["product.category"].search([]) if incomplete(c.with_company(1))]
log("==== VERIFY ====")
log("categories still incomplete: %d %s" % (len(still), still[:10]))
log("==== DONE ====")
