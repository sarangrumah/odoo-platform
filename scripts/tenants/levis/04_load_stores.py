"""Create one stock.warehouse per Levi's store (run in CONTAINER).

    docker cp scripts/tenants/levis/out_stores.csv odoo19-platform-odoo-mgmt:/tmp/levis/
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d levis --no-http < scripts/tenants/levis/04_load_stores.py

Creates all 24 Store-Master stores. External IDs (module="levis"):
  - wh_name_<NAME_SLUG>  : always set (the only universal key — names are all we have
                           for stores whose codes the customer has not yet provided).
  - wh_<STORE_CODE>      : ALSO set when the store code is known, so the module's X20/
                           X24 loaders (which resolve `wh_<storecode>`) work. Re-run this
                           script after the customer supplies missing codes to backfill
                           the code aliases (idempotent).

Warehouse `code` (<=5 chars): the numeric store code when known, else `W<NNN>`.
"""

import csv
import os
import sys

CSV_DIR = os.environ.get("LEVIS_CSV_DIR", "/tmp/levis")
NS = "levis"


def safe_xid(prefix, value):
    return prefix + "".join(c if c.isalnum() else "_" for c in str(value)).upper()


def xid_get(name, model):
    ext = env["ir.model.data"].search(
        [("module", "=", NS), ("name", "=", name), ("model", "=", model)], limit=1
    )
    return ext.res_id if ext else False


def xid_set(name, model, res_id):
    if not xid_get(name, model):
        env["ir.model.data"].create(
            {"module": NS, "name": name, "model": model, "res_id": res_id, "noupdate": True}
        )


with open(os.path.join(CSV_DIR, "out_stores.csv"), encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

created = existing = aliased = 0
for idx, r in enumerate(rows, start=1):
    name = (r["store_name"] or f"Store {idx}").strip()
    code = (r.get("store_code") or "").strip()
    name_xid = safe_xid("wh_name_", name)
    wh_id = xid_get(name_xid, "stock.warehouse")
    if wh_id:
        existing += 1
    else:
        wh_code = (code[:5] if code.isdigit() else f"W{idx:03d}")[:5]
        wh = env["stock.warehouse"].create({"name": name[:100], "code": wh_code})
        xid_set(name_xid, "stock.warehouse", wh.id)
        if wh.partner_id:
            xid_set(safe_xid("whpartner_name_", name), "res.partner", wh.partner_id.id)
        wh_id = wh.id
        created += 1
        env.cr.commit()
    # backfill the code alias whenever a code is known
    if code.isdigit():
        before = xid_get(safe_xid("wh_", code), "stock.warehouse")
        xid_set(safe_xid("wh_", code), "stock.warehouse", wh_id)
        if not before:
            aliased += 1
            env.cr.commit()

sys.stderr.write(
    f"Warehouses: created={created} existing={existing} code_aliases_added={aliased} total={len(rows)}\n"
)
sys.stderr.flush()
