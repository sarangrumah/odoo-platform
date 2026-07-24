"""Normalise the Levi's Operating-Unit dimension on an existing DB.

After this runs the "Operating Unit" analytic plan holds exactly 24 ACTIVE
accounts: ``EBR - HEAD OFFICE`` plus the 23 live stores. Everything else in the
plan is archived, never deleted.

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/tenants/levis/41_normalize_ou.py

Dry-run by default (``RUN_DRY=1``): prints the plan and rolls back.

Stores are keyed by ``stock.warehouse.code`` — the store number the retail
import (X24/X101) joins on. Codes are NEVER touched, because they drive the
location names (``14696/Stock``), the picking sequences (``14696/IN/``) and the
import's store lookup. Only the human-readable *name* changes, and it changes in
every place a name was copied at seeding time:

  * ``stock.warehouse.name``     — core cascades this to the routes, the stock
    rules and the 8 stock sequences (``_update_name_and_code``), but NOT to the
    POS picking sequence, which is fixed up here.
  * ``account.analytic.account`` — the Operating Unit itself.
  * ``account.journal``          — the per-store purchase journal.
  * ``pos.config``               — the store's point of sale.

Head Office: the default ``WH`` warehouse becomes ``EBR - HEAD OFFICE`` and is
re-pointed at the company-level HO analytic (``res_company.l10n_ho_analytic_id``)
that ``seed_trade_ou`` already created, so the duplicate ``My Company`` analytic
can be archived.

Archived stores are renamed and wired up exactly like live ones first, so they
can be reactivated later without any further configuration.

This script stops at the configuration boundary. The per-store POS **cash journal**,
its check-number sequence and the already-issued POS documents (``pos.session``,
``pos.order`` and the accounting ``ref``/``memo`` fields that copied a session name)
still carry the seed-time names. Run ``43_align_pos_naming.py`` afterwards to bring
those in line.
"""

import os
import sys

DRY = os.environ.get("RUN_DRY", "1") not in ("0", "false", "False")

HO_CODE = "WH"
HO_NAME = "EBR - HEAD OFFICE"
HO_NEW_CODE = "EBR"

# warehouse code -> canonical store name (the 23 live stores)
STORES = {
    "S1469": "OLS SES - TUNJUNGAN PLAZA 3",
    "34885": "OLS SES - BANDUNG INDAH PLAZA",
    "14699": "OLS SES - PONDOK INDAH MALL 2",
    "14696": "OLS SES - PONDOK INDAH MALL 1",
    "14701": "OLS SES - KELAPA GADING MALL",
    "14702": "OLS SES - SENAYAN CITY",
    "14705": "OLS SES - TRANS STUDIO MALL BANDUNG",
    "19185": "OLS SES - CENTRAL PARK",
    "22547": "OLS SES - LOTTE SHOPPING AVENUE",
    "22986": "OLS SES - GRAND METROPOLITAN BEKASI",
    "24832": "OLS SES - AEON BSD CITY",
    "25845": "OLS SES - PARIS VAN JAVA",
    "26908": "OLS SES - PAKUWON MALL SURABAYA",
    "27917": "OLS SES - TRANS STUDIO CIBUBUR",
    "29267": "OLS SES - GALAXY MALL 3",
    "29838": "OLS SES - METROPOLITAN MALL BEKASI",
    "30061": "OLS SES - MALL OF INDONESIA",
    "32818": "OLS SES - PLAZA SENAYAN",
    "33595": "OLS SES - GANDARIA CITY",
    "33637": "OLS SES - SUMMARECON MALL BANDUNG",
    "27648": "OLS SES - PACIFIC PLACE MALL",
    "33267": "OLS SES - PASKAL BANDUNG",
    # Absent from the official store list but trades daily in the X24DN files,
    # so it must stay postable (_ri_assert_stores_postable).
    "14703": "OLS SES - GRAND INDONESIA",
}

# Stores absent from the official list AND absent from the sales files.
# Configured like the live ones, then archived.
ARCHIVED_STORES = {}

# Warehouses that are not an Operating Unit at all (seeding artefacts).
STRAY_CODES = ["PI021"]

env = env  # noqa: F821  injected by `odoo shell`
log = []


def _wh(code):
    return env["stock.warehouse"].with_context(active_test=False).search([("code", "=", code)], limit=1)


def _rename(record, field, value):
    """Write ``value`` on ``record.field`` when it differs. Returns True if written."""
    if not record or record[field] == value:
        return False
    record.write({field: value})
    log.append("  %-28s %s -> %s" % (record._name, record.id, value))
    return True


def _rename_store(wh, name):
    """Rename a warehouse and every record that copied its name at seed time."""
    # Core's write() cascades the name to routes, rules and the 8 stock
    # sequences. It deliberately runs before super(), reading the OLD name, so
    # this must be the first write.
    _rename(wh, "name", name)
    # point_of_sale extends _get_sequence_values with pos_type_id but core's
    # _update_name_and_code only rewrites the 8 stock sequences, so the POS
    # picking sequence keeps the stale name. Fix it explicitly.
    if wh.pos_type_id.sequence_id:
        _rename(wh.pos_type_id.sequence_id.sudo(), "name", "%s Picking POS" % name)
    _rename(wh.l10n_ou_analytic_id, "name", name)
    _rename(wh.l10n_purchase_journal_id, "name", "Pembelian - %s" % name)
    for config in env["pos.config"].with_context(active_test=False).search([("warehouse_id", "=", wh.id)]):
        _rename(config, "name", name)


def _archive(record):
    if not record or not record.active:
        return False
    record.write({"active": False})
    log.append("  ARCHIVE %-20s %s %s" % (record._name, record.id, record.display_name))
    return True


def _archive_warehouse(wh, parking_type):
    """Archive ``wh`` (cascading to its picking types, locations, rules, routes).

    ``stock.warehouse.write({'active': False})`` re-reads its picking types with
    ``active_test=False``; ``point_of_sale``'s ``_check_active`` constraint
    inherits that context and so still sees an ALREADY-ARCHIVED pos.config
    pointing at the operation type, and refuses. ``picking_type_id`` is required
    on pos.config, so it cannot simply be cleared.

    Park the archived config's operation type on ``parking_type`` (the Head
    Office's outgoing type) for the duration of the warehouse write, then hand it
    back. The config keeps its full configuration and its own operation type, so
    reactivating the store later is a pure un-archive.
    """
    configs = env["pos.config"].with_context(active_test=False).search([("warehouse_id", "=", wh.id)])
    original = {c.id: c.picking_type_id.id for c in configs}
    for config in configs:
        _archive(config)
    if configs and parking_type:
        configs.write({"picking_type_id": parking_type.id})
    try:
        _archive(wh)
    finally:
        for config in configs:
            config.write({"picking_type_id": original[config.id]})


# --------------------------------------------------------------------------
# 1. Head Office
# --------------------------------------------------------------------------
log.append("== Head Office ==")
ho = _wh(HO_CODE) or _wh(HO_NEW_CODE)
if not ho:
    sys.stderr.write("!! no Head-Office warehouse (%s/%s) found\n" % (HO_CODE, HO_NEW_CODE))
else:
    company = ho.company_id
    ho_analytic = company.l10n_ho_analytic_id
    old_ou = ho.l10n_ou_analytic_id
    if ho_analytic:
        _rename(ho_analytic, "name", HO_NAME)
        if old_ou != ho_analytic:
            # Point the HO warehouse at the company's Head-Office analytic and
            # retire the duplicate ("My Company") the warehouse loop created.
            ho.l10n_ou_analytic_id = ho_analytic.id
            log.append("  HO warehouse OU -> analytic %s" % ho_analytic.id)
            _archive(old_ou)
    else:
        # No company-level HO analytic: promote the warehouse's own.
        _rename(old_ou, "name", HO_NAME)

    _rename_store(ho, HO_NAME)
    # The HO warehouse holds no documents, so its code can be tidied too. This
    # renames its locations (WH/Stock -> EBR/Stock) and sequence prefixes.
    if ho.code != HO_NEW_CODE:
        ho.write({"code": HO_NEW_CODE})
        log.append("  HO warehouse code -> %s" % HO_NEW_CODE)
    _rename(ho.l10n_purchase_journal_id, "name", "Pembelian - %s" % HO_NAME)

# --------------------------------------------------------------------------
# 2. Stores — live and archived alike are fully renamed/configured
# --------------------------------------------------------------------------
log.append("== Stores ==")
missing = []
for code, name in list(STORES.items()) + list(ARCHIVED_STORES.items()):
    wh = _wh(code)
    if not wh:
        missing.append(code)
        continue
    _rename_store(wh, name)

# --------------------------------------------------------------------------
# 3. Archive what is not an active Operating Unit
# --------------------------------------------------------------------------
log.append("== Archive ==")
parking_type = ho.out_type_id if ho else env["stock.picking.type"]
for code in list(ARCHIVED_STORES) + STRAY_CODES:
    wh = _wh(code)
    if not wh:
        continue
    _archive(wh.l10n_purchase_journal_id)
    _archive(wh.l10n_ou_analytic_id)
    _archive_warehouse(wh, parking_type)

# Reactivate anything that should be live (makes the script re-runnable after a
# mistaken archive).
for code in STORES:
    wh = _wh(code)
    if not wh:
        continue
    # Warehouse first: core cascades the un-archive to its picking types,
    # locations, routes and rules, which pos.config's _check_active needs.
    for rec in (wh, wh.l10n_ou_analytic_id, wh.l10n_purchase_journal_id):
        if rec and not rec.active:
            rec.write({"active": True})
            log.append("  UNARCHIVE %s %s" % (rec._name, rec.id))
    for config in env["pos.config"].with_context(active_test=False).search(
        [("warehouse_id", "=", wh.id), ("active", "=", False)]
    ):
        config.write({"active": True})
        log.append("  UNARCHIVE %s %s" % (config._name, config.id))

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
plan = env["account.analytic.plan"].search([("name", "=", "Operating Unit")], limit=1)
Analytic = env["account.analytic.account"].with_context(active_test=False)
active = Analytic.search([("plan_id", "=", plan.id), ("active", "=", True)])
archived = Analytic.search([("plan_id", "=", plan.id), ("active", "=", False)])

out = sys.stderr
out.write("\n".join(log) + "\n\n")
out.write("Operating Units ACTIVE (%d):\n" % len(active))
for a in active.sorted("name"):
    out.write("  - %s\n" % a.name)
out.write("Operating Units ARCHIVED (%d):\n" % len(archived))
for a in archived.sorted("name"):
    out.write("  - %s\n" % a.name)
if missing:
    out.write("!! warehouse codes not found: %s\n" % ", ".join(missing))

if DRY:
    env.cr.rollback()
    out.write("\nDRY RUN — rolled back. Re-run with RUN_DRY=0 to apply.\n")
else:
    env.cr.commit()
    out.write("\nCOMMITTED.\n")
out.flush()
