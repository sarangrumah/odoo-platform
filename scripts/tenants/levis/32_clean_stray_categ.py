# Remove Odoo demo-noise product categories (and their products) that are NOT part
# of the Levi's EBR catalog (run via: odoo shell -d demo_levis).
# Targets: Furniture/Office/Outdoor/Home Construction/Non-Trade/Rental.
# Idempotent: skips anything already gone. Delete if unreferenced, else archive
# (same delete-else-deactivate pattern as 30_fix_coa.py).
env = env
log = lambda m: print("[clean] " + m)

STRAY = {'Furniture', 'Office', 'Outdoor', 'Home Construction', 'Non-Trade', 'Rental'}
Category = env['product.category']
Template = env['product.template']

cats = Category.search([('name', 'in', list(STRAY))])
log("stray categories found: %s" % cats.mapped('name'))

# ---- 1. remove products in those categories (templates -> cascade variants) ----
tmpl = Template.search([('categ_id', 'in', cats.ids)])
log("templates to remove: %d" % len(tmpl))
deleted = archived = 0
for t in tmpl:
    try:
        t.with_context(force_delete=True).unlink()
        deleted += 1
    except Exception as e:
        env.cr.rollback()
        try:
            Template.browse(t.id).active = False
            archived += 1
        except Exception as e2:
            env.cr.rollback()
            log("PRODUCT FAIL %s: %s" % (t.id, e2))
    env.cr.commit()
log("products: deleted=%d archived=%d" % (deleted, archived))

# ---- 2. remove the categories (children before parents) ----
def depth(c):
    d, p = 0, c.parent_id
    while p:
        d += 1
        p = p.parent_id
    return d

cdeleted = carchived = 0
for c in sorted(cats, key=depth, reverse=True):
    nm = c.name
    try:
        c.unlink()
        cdeleted += 1
    except Exception:
        env.cr.rollback()
        try:
            Category.browse(c.id).active = False
            carchived += 1
        except Exception as e:
            env.cr.rollback()
            log("CATEG FAIL %s: %s" % (nm, e))
    env.cr.commit()
log("categories: deleted=%d archived=%d" % (cdeleted, carchived))

# ---- verify ----
left = Category.with_context(active_test=False).search([('name', 'in', list(STRAY))])
log("==== VERIFY ====")
log("stray categories still present (active or archived): %s" % left.mapped('name'))
log("stray categories still ACTIVE: %s" % Category.search([('name', 'in', list(STRAY))]).mapped('name'))
log("==== DONE ====")
