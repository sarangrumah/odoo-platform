# Re-import the June 2026 X24DN retail sales into a levis DB (run via odoo shell).
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http < scripts/tenants/levis/35_reimport_x24.py
#
# Assumes 20_reset_txn.py has already wiped the previous POS/GL artefacts and that
# 34_coa_categ_tree.py has aligned the product categories with the COA, so that the
# lazy-created non-merchandise products (tailoring services, paid paperbags) now land on
# Gross Sales-Labor / Gross Sales-Others instead of the company fallback account.
#
# The X24 orders are dated in June, so a fiscalyear lock date on/before 2026-06-30 would
# silently bump them to today: lift it for the run and ALWAYS restore the original.
#
# Env: X24_PATH (default /tmp/levis/X24DN_Jun2026.xlsx)
import base64
import os

env = env  # noqa: F821  (injected by odoo shell)
log_ = lambda m: print("[x24] " + m)

PATH = os.environ.get("X24_PATH", "/tmp/levis/X24DN_Jun2026.xlsx")
COMPANY_ID = 1

company = env["res.company"].browse(COMPANY_ID)
profile = env["retail.import.profile"].search([("code", "=", "levis_x24")], limit=1)
if not profile:
    raise SystemExit("profile levis_x24 not found")

icp = env["ir.config_parameter"].sudo()
for p in ("x24_post_enabled", "x24_close_sessions", "x24_decouple_payment", "x24_strict_product"):
    log_("flag retail_import.%s = %s" % (p, icp.get_param("retail_import." + p)))

raw = open(PATH, "rb").read()
log_("file=%s bytes=%d" % (PATH, len(raw)))

_orig_lock = company.fiscalyear_lock_date
if _orig_lock:
    log_("lifting fiscalyear_lock_date %s for the import (will restore)" % _orig_lock)
    company.sudo().write({"fiscalyear_lock_date": False})

try:
    Log = env["retail.import.log"].sudo()
    rec = Log.create({
        "profile_id": profile.id,
        "filename": os.path.basename(PATH),
        "file_hash": Log.compute_hash(raw),
        "state": "queued",
    })
    rec.store_source(base64.b64encode(raw), os.path.basename(PATH))
    env.cr.commit()
    log_("log #%s created, running executor synchronously ..." % rec.id)
    env["retail.import.executor"].run(rec)
    log_("log #%s state=%s lines=%s skipped=%s errors=%s"
         % (rec.id, rec.state, rec.line_count, rec.records_skipped, rec.error_count))
    if rec.error_message:
        log_("error_message: %s" % rec.error_message[:300])
finally:
    if _orig_lock:
        company.sudo().write({"fiscalyear_lock_date": _orig_lock})
        log_("restored fiscalyear_lock_date -> %s" % _orig_lock)
    env.cr.commit()

log_("==== DONE ====")
