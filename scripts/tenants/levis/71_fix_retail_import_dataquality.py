"""Remediate data-quality defects left by earlier X101 retail imports.

Fixes the three anomalies the going-forward code now prevents (see
custom_retail_import: retail_import_profile._clean_str sentinel scrub +
retail_import_executor._load_x101):

  1. STORABLE   — flip X101 merchandise templates to is_storable=True (Odoo 19
                  tracks storability on is_storable, not type). The "Original
                  cut" tailoring service (config-driven keywords/codes) becomes
                  type='service' instead.
  2. #N/A CATS  — reassign products off spurious sentinel categories (a real
                  product.category literally named "#N/A" etc. from an
                  =VLOOKUP error) onto the default "All" category, then
                  delete/archive the empty sentinel categories.
  3. ZERO PRICE — report (do NOT auto-change) X101 templates with list_price<=0
                  so Finance can correct them at source and re-import.

Idempotent. DRY-RUN by default; set RETAIL_FIX_APPLY=1 to write.

    docker exec -e RETAIL_FIX_APPLY=1 -i odoo19-platform-odoo \
        odoo shell -d rnd_levis --no-http \
        < scripts/tenants/levis/71_fix_retail_import_dataquality.py

Env:
  RETAIL_FIX_APPLY   "1"/"true" to apply; anything else = dry-run (default).
  RETAIL_NS          import namespace (default "levis") — the ir.model.data
                     module the X101 tmpl_* external IDs live under.
"""

import os
import sys

env = env  # noqa: F821  (injected by `odoo shell`)
log = lambda m: sys.stderr.write("[fixdq] " + m + "\n") or sys.stderr.flush()

APPLY = str(os.environ.get("RETAIL_FIX_APPLY", "")).lower() in ("1", "true", "yes")
NS = os.environ.get("RETAIL_NS", "levis")
log("mode=%s namespace=%s" % ("APPLY" if APPLY else "DRY-RUN", NS))

Template = env["product.template"]
Category = env["product.category"]
IMD = env["ir.model.data"]

# Same sentinel set as retail_import_profile._ERROR_SENTINELS (kept in sync).
SENTINELS = {"#N/A", "N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "NULL"}

# Same service detection as executor._x101_service_matchers (config-driven).
icp = env["ir.config_parameter"].sudo()
# EMPTY default: substring keywords like "TAILOR" false-match merchandise
# ("TAILORED BUSTIER", "TAILORED CLASSIC" shirts). Everything is storable
# merchandise unless an exact service code/keyword is configured.
KEYWORDS = [k.strip().upper() for k in
            (icp.get_param("retail_import.service_category_keywords", "") or "").split(",") if k.strip()]
CODES = {c.strip().upper() for c in
         (icp.get_param("retail_import.service_product_codes", "") or "").split(",") if c.strip()}


def is_service(tmpl):
    if CODES and str(tmpl.default_code or "").strip().upper() in CODES:
        return True
    if not KEYWORDS:
        return False
    hay = ("%s %s" % (tmpl.categ_id.complete_name or "", tmpl.name or "")).upper()
    return any(kw in hay for kw in KEYWORDS)


def commit():
    if APPLY:
        env.cr.commit()


# ---- collect the X101 templates by external ID (module=NS, name=tmpl_*) ----
imd_rows = IMD.search([("module", "=", NS), ("model", "=", "product.template"),
                       ("name", "=like", "tmpl\\_%")])
x101_ids = imd_rows.mapped("res_id")
x101 = Template.browse(x101_ids).exists()
log("X101 templates found via %s.tmpl_*: %d" % (NS, len(x101)))

# ==================================================================
# 1. STORABLE / SERVICE
# ==================================================================
to_storable = to_service = 0
# Bucket first, then bulk-write per batch (31k per-record commits is far too slow).
svc_ids = [t.id for t in x101 if is_service(t) and t.type != "service"]
merch = x101.filtered(lambda t: not is_service(t) and not t.is_storable)
merch_consu = [t.id for t in merch if t.type == "consu"]        # just flip is_storable
merch_other = [t.id for t in merch if t.type != "consu"]        # also coerce type
to_service = len(svc_ids)
to_storable = len(merch)


def _bulk(ids, vals, label):
    if not ids:
        return
    if not APPLY:
        return
    for i in range(0, len(ids), 500):
        chunk = env["product.template"].browse(ids[i:i + 500])
        try:
            chunk.write(vals)
            env.cr.commit()
        except Exception as e:  # fall back per-record so one bad row can't stall the batch
            env.cr.rollback()
            for t in chunk:
                try:
                    t.write(vals)
                    env.cr.commit()
                except Exception as e2:
                    env.cr.rollback()
                    log("  %s FAIL %s: %s" % (label, t.default_code, e2))


_bulk(merch_consu, {"is_storable": True}, "STORABLE")
_bulk(merch_other, {"is_storable": True, "type": "consu"}, "STORABLE")
_bulk(svc_ids, {"type": "service"}, "SERVICE")
log("storable: %d flipped to is_storable=True | service: %d set to type=service"
    % (to_storable, to_service))

# ==================================================================
# 2. #N/A (sentinel) CATEGORIES
# ==================================================================
# match by exact sentinel name (case-insensitive) — do NOT ilike '#', which would
# catch legitimate names containing '#'.
all_cats = Category.with_context(active_test=False).search([])
bad_cats = all_cats.filtered(lambda c: (c.name or "").strip().upper() in SENTINELS)
log("sentinel categories found: %s" % (bad_cats.mapped("name") or "none"))

fallback = env.ref("product.product_category_all", raise_if_not_found=False)
reassigned = cdeleted = carchived = 0
if bad_cats and not fallback:
    log("  WARN no product.product_category_all fallback; skipping category cleanup")
elif bad_cats:
    prods = Template.with_context(active_test=False).search([("categ_id", "in", bad_cats.ids)])
    log("  products on sentinel categories: %d -> reassign to %r" % (len(prods), fallback.name))
    if APPLY and prods:
        prods.write({"categ_id": fallback.id})
        reassigned = len(prods)
    commit()

    def _depth(c):
        d, p = 0, c.parent_id
        while p:
            d, p = d + 1, p.parent_id
        return d

    for c in sorted(bad_cats, key=_depth, reverse=True):
        nm = c.name
        try:
            if APPLY:
                c.unlink()
            cdeleted += 1
        except Exception:
            env.cr.rollback()
            try:
                if APPLY:
                    Category.browse(c.id).active = False
                carchived += 1
            except Exception as e:
                env.cr.rollback()
                log("  CATEG FAIL %s: %s" % (nm, e))
        commit()
log("categories: products_reassigned=%d deleted=%d archived=%d"
    % (reassigned, cdeleted, carchived))

# ==================================================================
# 3. ZERO / MISSING PRICE  (report only)
# ==================================================================
zero_price = x101.filtered(lambda t: not t.list_price or t.list_price <= 0)
log("zero/missing-price X101 templates: %d" % len(zero_price))
for t in zero_price[:50]:
    log("  price<=0: %s (%s)" % (t.default_code, t.name))
if len(zero_price) > 50:
    log("  ... and %d more" % (len(zero_price) - 50))

# ---- summary ----
log("==== SUMMARY (%s) ====" % ("APPLIED" if APPLY else "DRY-RUN — nothing written"))
log("  storable flipped     : %d" % to_storable)
log("  service reclassified : %d" % to_service)
log("  sentinel cats        : reassigned=%d deleted=%d archived=%d"
    % (reassigned, cdeleted, carchived))
log("  zero-price to review : %d" % len(zero_price))
log("==== DONE ====")
