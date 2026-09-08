"""Turn on the asset damage / missing / repair lifecycle for ARKA-AIM.

Tenant: PT Aero Inovasi Media (company 1) + PT Aero Reksa Kreasi Angkasa
(company 2). DBs: a scratch clone first, then ``prd_arkaaim``.

Three jobs, all idempotent:

1. **Point the company at its lifecycle locations and accounts.** The client
   already created the warehouses -- ``WH/Damage`` (DMG) and ``WH/Lost-Missing``
   (WH/LM) -- so this only wires ``asset_damage_location_id`` /
   ``asset_missing_location_id`` to their stock locations.

   The two GL accounts are passed in by code, never guessed: which account
   carries an asset loss and which carries compensation income is Finance's
   call. For ARKA-AIM those are ``7701000000`` *Loss on sale of Fixed Assets*
   (the CoA's only fixed-asset derecognition loss account -- PSAK 16.68 treats
   derecognition as one item whatever the cause) and ``7609000000``
   *Reimbursement Income* (IAS 16.65: third-party compensation for a lost asset
   goes to profit or loss when it becomes receivable). Deliberately **not**
   ``7706000000`` *Loss on impairment of Fixed Assets*: impairment writes down
   an asset that stays on the books, a lost drone is derecognised. Anything left
   unset is reported loudly at the end of the run.

2. **Resync every unit's physical position.** ``custom_asset_stock_link``
   19.0.1.2.0 fixed a position read that ignored offsetting negative quants;
   before it, 2,572 of the 3,590 units showed as sitting in ``ARKA/Stock`` when
   they were really in ``WH/RUKO GUDANG PALEM``. The nightly cron would get
   there in its own time, in batches of 2,000; this does the whole register at
   once so the first damage report moves stock from the right shelf.

3. **Provision maintenance equipment cards.** The register had 3,590 units and
   zero ``maintenance.equipment`` records, which is the broken link that stopped
   any repair history from accumulating against a serial. One card per running
   unit, skipping any that already has one.

Nothing here posts to the ledger, and nothing changes an asset's ``state`` or
its depreciation schedule.

Run inside the Odoo container (stdin, so no file needs to exist in the image)::

    docker exec -i odoo19-platform-odoo sh -c 'odoo shell -d prd_arkaaim --no-http' \
        < scripts/tenants/arkaaim/setup_asset_lifecycle.py

Environment:
    APPLY=1              actually write (default: dry run, rolled back)
    EQUIPMENT=0          skip equipment-card creation (default: create them)
    RESYNC=0             skip the position resync (default: resync)
    BATCH=500            units per commit
    DAMAGE_WH=DMG        warehouse code holding the damage location
    MISSING_WH=WH/LM     warehouse code holding the lost/missing location
    DAMAGE_FALLBACK=...  location name created for a company with no damage warehouse
    MISSING_FALLBACK=... location name created for a company with no lost warehouse
    LOSS_ACCOUNT=...     account code debited for the NBV of a written-off unit
    INCOME_ACCOUNT=...   account code credited at fair value for a replacement
    REPLACEMENT_JOURNAL=MISC,JM  journal codes to try, first match per company
"""

import logging
import os

_logger = logging.getLogger(__name__)

APPLY = os.environ.get("APPLY") == "1"
DO_EQUIPMENT = os.environ.get("EQUIPMENT", "1") == "1"
DO_RESYNC = os.environ.get("RESYNC", "1") == "1"
BATCH = int(os.environ.get("BATCH", "500"))
DAMAGE_WH = os.environ.get("DAMAGE_WH", "DMG")
MISSING_WH = os.environ.get("MISSING_WH", "WH/LM")
DAMAGE_FALLBACK = os.environ.get("DAMAGE_FALLBACK", "Damaged Assets")
MISSING_FALLBACK = os.environ.get("MISSING_FALLBACK", "Lost Assets")
LOSS_ACCOUNT = os.environ.get("LOSS_ACCOUNT", "7701000000")
INCOME_ACCOUNT = os.environ.get("INCOME_ACCOUNT", "7609000000")
REPLACEMENT_JOURNALS = [
    code.strip() for code in os.environ.get("REPLACEMENT_JOURNAL", "MISC,JM").split(",") if code.strip()
]

EQUIPMENT_CATEGORY = "Drone Fleet"


def section(title):
    _logger.info("")
    _logger.info("== %s", title)


def account_by_code(env, company, code):
    """Look the account up *in the company's own context*.

    ``account.account.code`` is company-dependent in Odoo 19 -- read it without
    ``with_company`` and it comes back blank, so a plain search on ``code``
    silently finds nothing.
    """
    if not code:
        return env["account.account"]
    return (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
    )


def journal_for(env, company):
    for code in REPLACEMENT_JOURNALS:
        journal = env["account.journal"].search(
            [("code", "=", code), ("type", "=", "general"), ("company_id", "=", company.id)],
            limit=1,
        )
        if journal:
            return journal
    return env["account.journal"]


def warehouse_stock_location(env, code, company):
    """Resolve a warehouse code **within one company**.

    Warehouse codes are not unique across companies, so resolving ``DMG`` without
    a company filter hands PT Aero Inovasi Media's damage warehouse to PT Aero
    Reksa Kreasi Angkasa -- and a stock transfer between two companies' locations
    is refused at validation time, in front of an operator reporting a broken
    drone. That is not hypothetical: this script did exactly that on its first
    production run.
    """
    warehouse = env["stock.warehouse"].search([("code", "=", code), ("company_id", "=", company.id)], limit=1)
    if warehouse:
        return warehouse.lot_stock_id
    return env["stock.location"]


def ensure_child_location(env, company, name):
    """A company without its own damage/lost warehouse gets a location instead.

    Cheaper than a warehouse -- no sequences, picking types or rules -- and all
    these units need is somewhere of their own company to sit.
    """
    warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
    if not warehouse:
        _logger.warning("%s has no warehouse -- cannot place %r", company.name, name)
        return env["stock.location"]
    parent = warehouse.view_location_id
    existing = env["stock.location"].search([("name", "=", name), ("location_id", "=", parent.id)], limit=1)
    if existing:
        return existing
    _logger.info("%s: creating location %s/%s", company.name, parent.complete_name, name)
    return env["stock.location"].create(
        {
            "name": name,
            "usage": "internal",
            "location_id": parent.id,
            "company_id": company.id,
        }
    )


def lifecycle_location(env, company, code, fallback_name):
    """The company's own warehouse for this purpose, or a location we make."""
    location = warehouse_stock_location(env, code, company)
    if location:
        return location
    return ensure_child_location(env, company, fallback_name)


def configure_companies(env):
    section("company configuration")
    category = env["maintenance.equipment.category"].search([("name", "=", EQUIPMENT_CATEGORY)], limit=1)
    if not category:
        category = env["maintenance.equipment.category"].create({"name": EQUIPMENT_CATEGORY})
        _logger.info("created maintenance category %r", EQUIPMENT_CATEGORY)

    companies = env["custom.fixed.asset"].search([]).company_id
    for company in companies:
        damage = lifecycle_location(env, company, DAMAGE_WH, DAMAGE_FALLBACK)
        missing = lifecycle_location(env, company, MISSING_WH, MISSING_FALLBACK)

        vals = {}
        # Repoint anything that currently sits in another company's warehouse --
        # that configuration cannot complete a transfer, so leaving it in place
        # is not "already configured", it is broken.
        current_damage = company.asset_damage_location_id
        current_missing = company.asset_missing_location_id
        if damage and (not current_damage or (current_damage.company_id and current_damage.company_id != company)):
            if current_damage and current_damage.company_id != company:
                _logger.warning(
                    "%s: damage location %s belongs to %s -- repointing to %s",
                    company.name,
                    current_damage.complete_name,
                    current_damage.company_id.name,
                    damage.complete_name,
                )
            vals["asset_damage_location_id"] = damage.id
        if missing and (not current_missing or (current_missing.company_id and current_missing.company_id != company)):
            if current_missing and current_missing.company_id != company:
                _logger.warning(
                    "%s: lost/missing location %s belongs to %s -- repointing to %s",
                    company.name,
                    current_missing.complete_name,
                    current_missing.company_id.name,
                    missing.complete_name,
                )
            vals["asset_missing_location_id"] = missing.id
        if not company.asset_equipment_category_id:
            vals["asset_equipment_category_id"] = category.id

        loss = account_by_code(env, company, LOSS_ACCOUNT)
        income = account_by_code(env, company, INCOME_ACCOUNT)
        journal = journal_for(env, company)
        if LOSS_ACCOUNT and not loss:
            _logger.warning("%s: no account %s in this company's chart", company.name, LOSS_ACCOUNT)
        if INCOME_ACCOUNT and not income:
            _logger.warning("%s: no account %s in this company's chart", company.name, INCOME_ACCOUNT)
        if loss and not company.asset_loss_account_id:
            vals["asset_loss_account_id"] = loss.id
        if income and not company.asset_compensation_income_account_id:
            vals["asset_compensation_income_account_id"] = income.id
        if journal and not company.asset_replacement_journal_id:
            vals["asset_replacement_journal_id"] = journal.id
        if vals:
            company.write(vals)
        _logger.info(
            "%s: damage=%s missing=%s category=%s",
            company.name,
            company.asset_damage_location_id.complete_name or "-",
            company.asset_missing_location_id.complete_name or "-",
            company.asset_equipment_category_id.name or "-",
        )
        _logger.info(
            "%s: loss=%s income=%s journal=%s",
            company.name,
            company.asset_loss_account_id.with_company(company).code or "-",
            company.asset_compensation_income_account_id.with_company(company).code or "-",
            company.asset_replacement_journal_id.code or "-",
        )
        # Finance owns these two. Say so loudly rather than guessing an account.
        for field, label in (
            ("asset_loss_account_id", "Asset Loss Account"),
            ("asset_compensation_income_account_id", "Asset Compensation Income Account"),
            ("asset_replacement_journal_id", "Asset Replacement Journal"),
        ):
            if not company[field]:
                _logger.warning(
                    "%s: %s IS NOT SET -- write-offs and replacements will refuse to "
                    "post until Finance picks one (Accounting Settings > Asset Lifecycle)",
                    company.name,
                    label,
                )


def resync_positions(env):
    section("physical position resync")
    Asset = env["custom.fixed.asset"]
    assets = Asset.with_context(active_test=False).search([("lot_id", "!=", False)])
    _logger.info("%s unit(s) carry a serial", len(assets))

    before = {asset.id: asset.stock_location_id for asset in assets}
    for index in range(0, len(assets), BATCH):
        chunk = assets[index : index + BATCH]
        Asset._sync_stock_from_lots(chunk.lot_id.ids)
        _logger.info("  resynced %s/%s", min(index + BATCH, len(assets)), len(assets))

    moved = 0
    for asset in assets:
        if before[asset.id] != asset.stock_location_id:
            moved += 1
    _logger.info("%s unit(s) had the wrong location cached and were corrected", moved)
    by_location = {}
    for asset in assets:
        key = asset.stock_location_id.complete_name or "(nowhere)"
        by_location[key] = by_location.get(key, 0) + 1
    for location, count in sorted(by_location.items(), key=lambda pair: -pair[1]):
        _logger.info("  %-40s %s", location, count)


def provision_equipment(env):
    section("maintenance equipment cards")
    Asset = env["custom.fixed.asset"]
    pending = Asset.search([("state", "=", "running"), ("equipment_id", "=", False)])
    _logger.info("%s running unit(s) without an equipment card", len(pending))
    created = 0
    for index in range(0, len(pending), BATCH):
        chunk = pending[index : index + BATCH]
        created += len(chunk._ensure_equipment())
        _logger.info("  created %s/%s", min(index + BATCH, len(pending)), len(pending))
    _logger.info("%s equipment card(s) created", created)
    linked = env["rental.asset"].search_count([("equipment_id", "!=", False)])
    _logger.info("%s rental unit(s) now point at an equipment card", linked)


def main(env):
    moves_before = env["account.move"].search_count([])

    configure_companies(env)
    if DO_RESYNC:
        resync_positions(env)
    if DO_EQUIPMENT:
        provision_equipment(env)

    section("guard")
    moves_after = env["account.move"].search_count([])
    if moves_after != moves_before:
        raise AssertionError(
            "setup_asset_lifecycle posted %s journal entr(ies); it must post none" % (moves_after - moves_before)
        )
    _logger.info("account.move delta: 0 -- nothing reached the ledger")

    if APPLY:
        env.cr.commit()
        _logger.info("setup_asset_lifecycle: committed")
    else:
        env.cr.rollback()
        _logger.info("setup_asset_lifecycle: dry run, rolled back. Set APPLY=1 to write.")


main(env)  # noqa: F821 -- `env` is injected by `odoo shell`
