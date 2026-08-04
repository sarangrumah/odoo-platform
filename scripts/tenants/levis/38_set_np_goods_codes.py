# Register the non-merchandise TS codes that are actually GOODS, not tailoring services
# (run via odoo shell, once per levis DB).
#   docker exec -i odoo19-platform-odoo odoo shell -d <db> --no-http < scripts/tenants/levis/38_set_np_goods_codes.py
#
# Why: the X24 lazy-create path files every non-merchandise line whose code starts with a
# service prefix ("TS") under Labor (Service). But Levi's issues TS codes to sold goods too
# -- Fodable Cup, Levi's Pin, TAB, Patches M/L, BUTTON/PCS -- whose revenue belongs in
# Miscellaneous (x24_np_category_id), not the tailoring bucket. custom_retail_import >=
# 19.0.0.15.0 reads retail_import.x24_np_goods_codes (comma-separated exact codes) and
# routes those to x24_np_category_id via _x24_np_category.
#
# This only sets configuration data. A lazy-created product is categorised at CREATION,
# so an already-imported DB also needs 20_reset_txn.py (drops the lazy products) + a
# re-import for the GL to follow -- this script alone does not move any journal.
#
# Idempotent: rewrites the param only if it differs.
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[np_goods] " + m)

# The six goods observed in the Jun-2026 X24DN with a TS code (Rp 8.243.227 of revenue),
# plus the two patches found in Jul/Aug-2026 (TS1000413 Patches S, TS1000415 PATCH DARAHKU
# BIRU SINGLE, Rp 2.792.790 -- already moved to Miscellaneous on prd_levis_begbal by
# levis.categ.reclass CATREC/2026/0002; listing them here stops the next import from
# filing new ones under Labor (Service) again).
# Override per-tenant via env if the list ever grows.
DEFAULT = "TS1000382,TS1000418,TS1000283,TS1000402,TS1000431,TS1000174,TS1000413,TS1000415"
CODES = os.environ.get("NP_GOODS_CODES", DEFAULT)

icp = env["ir.config_parameter"].sudo()
KEY = "retail_import.x24_np_goods_codes"
current = icp.get_param(KEY)
if current == CODES:
    log("already set (%s) -- nothing to do" % CODES)
else:
    icp.set_param(KEY, CODES)
    log("set %s = %s (was %r)" % (KEY, CODES, current))

# Show where the param routes, so the operator can confirm the target category exists.
cid = int(icp.get_param("retail_import.x24_np_category_id", 0) or 0)
categ = env["product.category"].browse(cid) if cid else env["product.category"]
log("x24_np_category_id = %s -> %s" % (cid or "(unset)", categ.complete_name if categ.exists() else "(missing!)"))
log("==== DONE ====")
