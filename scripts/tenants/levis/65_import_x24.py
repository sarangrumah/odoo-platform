# Import an X24DN retail-sales file synchronously (bypassing queue_job, which crash-loops on
# cloned levis DBs). Creates a retail.import.log, stores the source, and runs the executor inline.
#
#   docker cp <file>.xlsx odoo19-platform-odoo:/tmp/levis/X24DN.xlsx
#   docker exec -i -e X24_FILE=/tmp/levis/X24DN.xlsx odoo19-platform-odoo \
#       odoo shell -d prd_levis --no-http < scripts/tenants/levis/65_import_x24.py
#
# Prerequisites (see the deploy sequence): products present (64_clone_x24_products.py), config
# flags aligned (x24_post_enabled/close_sessions/decouple_payment/discount_reclass/strict).
import base64
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[x24] " + m)

PATH = os.environ.get("X24_FILE", "/tmp/levis/X24DN_begbal.xlsx")
FORCE = os.environ.get("X24_FORCE") == "1"

profile = env["retail.import.profile"].search([("file_type", "=", "x24")], limit=1)
if not profile:
    raise SystemExit("no x24 profile")

with open(PATH, "rb") as f:
    raw = f.read()
b64 = base64.b64encode(raw)
filename = os.path.basename(PATH)

Log = env["retail.import.log"].sudo()
file_hash = Log.compute_hash(raw)
dup = Log.find_duplicate(file_hash)
if dup and not FORCE:
    raise SystemExit("file already imported (log #%s); set X24_FORCE=1 to override" % dup.id)

rec = Log.create({"profile_id": profile.id, "filename": filename, "file_hash": file_hash, "state": "queued"})
rec.store_source(b64, filename)
log("log #%s created for %s (%d bytes)" % (rec.id, filename, len(raw)))

env["retail.import.executor"].run(rec)  # synchronous

rec.invalidate_recordset()
log(
    "state=%s lines=%s created=%s matched=%s skipped=%s errors=%s"
    % (rec.state, rec.line_count, rec.records_created, rec.records_matched, rec.records_skipped, rec.error_count)
)
if rec.error_message:
    log("message: %s" % (rec.error_message or "")[:500])
env.cr.commit()
log("committed")
