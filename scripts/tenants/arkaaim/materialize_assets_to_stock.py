"""Bring the ARKA/AIM fixed-asset register into inventory as serial numbers.

Tenant: PT Aero Inovasi Media (company 1) + PT Aero Reksa Kreasi Angkasa
(company 2). DBs: ``trn_arkaaim_begbal`` (test) then ``prd_arkaaim`` (prod).

The 3,590 drones and support items in ``custom.fixed.asset`` exist only in
accounting -- ``lot_id`` and ``product_id`` are null on every one of them, so
nobody can say which warehouse a unit is in or which drone is free to rent out.
This script gives each unit a serial-tracked product, a ``stock.lot`` named
after its asset code, one unit of stock in a real location, and (optionally) a
``rental.asset``.

**No accounting entry is posted.** These units are already capitalised in the
AIM opening balance (1205104000 cost / 1205203000 accumulated), so materialising
them into stock must not touch the ledger. The wizard this script drives refuses
to run unless the company, the product category, every product and every
destination location are all outside perpetual valuation -- and it books the
opening stock through an inventory adjustment at zero cost, which also keeps the
periodic year-end valuation entry at nil. The run asserts a zero
``account.move`` delta at the end regardless.

All the rules live in ``custom_asset_stock_link`` so a manual wizard run and this
script cannot drift apart. What only this script does is create the tenant's
locations and drive the whole register through in batches.

Run inside the Odoo container (stdin, so no file needs to exist in the image)::

    docker exec -i odoo19-platform-odoo sh -c 'odoo shell -d prd_arkaaim --no-http' \
        < scripts/tenants/arkaaim/materialize_assets_to_stock.py

Environment:
    MATERIALIZE=1        actually write (default: dry run, rolled back)
    RENTAL_UNITS=0       skip rental.asset creation (default: create them)
    ASSET_GROUPS=a,b     limit to these asset group codes (default: every group)
    BATCH=250            assets per commit
    AIM_WAREHOUSE=WH     warehouse whose tree gets the RUKO GUDANG PALEM location
    ARKA_WAREHOUSE=WH-01 warehouse holding the ARKA support items
"""

import logging
import os

_logger = logging.getLogger(__name__)

APPLY = os.environ.get("MATERIALIZE") == "1"
CREATE_RENTAL = os.environ.get("RENTAL_UNITS", "1") == "1"
GROUP_CODES = [c.strip() for c in os.environ.get("ASSET_GROUPS", "").split(",") if c.strip()]
BATCH = int(os.environ.get("BATCH", "250"))

AIM_COMPANY = "PT Aero Inovasi Media"
ARKA_COMPANY = "PT Aero Reksa Kreasi Angkasa"
# The register's single asset location. Mirrored into stock as a named location
# under the AIM warehouse rather than a fourth warehouse: AIM already runs WH,
# ARKA and DMG, and a warehouse would drag a whole picking-type set with it.
ASSET_LOCATION_NAME = "RUKO GUDANG PALEM"
AIM_WAREHOUSE_CODE = os.environ.get("AIM_WAREHOUSE", "WH")
ARKA_WAREHOUSE_CODE = os.environ.get("ARKA_WAREHOUSE", "WH-01")


def resolve_company(env, name):
    company = env["res.company"].search([("name", "=", name)], limit=1)
    if not company:
        raise ValueError("company %r not found in this database" % name)
    return company


def resolve_warehouse(env, company, code):
    """Warehouse by code, with the alternatives spelled out when it is missing.

    ARKA's WH-01 was created by hand on 13-Aug-2026 and is younger than most
    backups, so a restored copy will not have it.
    """
    warehouse = env["stock.warehouse"].search([("code", "=", code), ("company_id", "=", company.id)], limit=1)
    if warehouse:
        return warehouse
    available = env["stock.warehouse"].search([("company_id", "=", company.id)])
    raise ValueError(
        "warehouse %r not found for %s. Warehouses in that company: %s"
        % (
            code,
            company.name,
            ", ".join("%s (%s)" % (w.name, w.code) for w in available) or "none",
        )
    )


def ensure_stock_location(env, company, warehouse_code, name):
    """Named internal location under ``warehouse_code``, created if missing."""
    parent = resolve_warehouse(env, company, warehouse_code).view_location_id
    location = env["stock.location"].search([("name", "=", name), ("location_id", "=", parent.id)], limit=1)
    if not location:
        location = env["stock.location"].create(
            {
                "name": name,
                "usage": "internal",
                "location_id": parent.id,
                "company_id": company.id,
            }
        )
        _logger.info("materialize: created stock location %s", location.complete_name)
    return location


def map_asset_locations(env, stock_location):
    """Point every asset location at its stock counterpart.

    Only the ones still unmapped are touched, so a hand-made mapping survives a
    re-run.
    """
    locations = env["custom.fixed.asset.location"].search([("stock_location_id", "=", False)])
    if locations:
        locations.write({"stock_location_id": stock_location.id})
        _logger.info(
            "materialize: mapped %s asset location(s) to %s",
            len(locations),
            stock_location.complete_name,
        )
    return locations


def pending_assets(env, company):
    domain = [("company_id", "=", company.id), ("lot_id", "=", False)]
    if GROUP_CODES:
        domain.append(("group_id.code", "in", GROUP_CODES))
    return env["custom.fixed.asset"].with_context(active_test=False).search(domain)


def materialize(env, assets, location, categ):
    """Drive the register through the wizard, one committed batch at a time."""
    Wizard = env["custom.asset.stock.materialize.wizard"]
    done = 0
    for start in range(0, len(assets), BATCH):
        chunk = assets[start : start + BATCH]
        wizard = Wizard.create(
            {
                "asset_ids": [(6, 0, chunk.ids)],
                "location_id": location.id,
                "categ_id": categ.id,
                "create_rental_asset": CREATE_RENTAL,
            }
        )
        wizard.action_confirm()
        done += len(chunk)
        if APPLY:
            env.cr.commit()
        _logger.info("materialize: %s/%s units into %s", done, len(assets), location.complete_name)
    return done


def report(env):
    env.cr.execute(
        """
        SELECT c.name AS company,
               g.name AS asset_group,
               count(*) AS assets,
               count(a.lot_id) AS serials,
               count(a.product_id) AS products
          FROM custom_fixed_asset a
          LEFT JOIN res_company c ON c.id = a.company_id
          LEFT JOIN custom_fixed_asset_group g ON g.id = a.group_id
         GROUP BY 1, 2
         ORDER BY 3 DESC
        """
    )
    _logger.info("materialize: register vs stock")
    for company, group, assets, serials, products in env.cr.fetchall():
        _logger.info(
            "  %-32s %-18s assets=%-6s serials=%-6s products=%s",
            company,
            group,
            assets,
            serials,
            products,
        )
    env.cr.execute(
        """
        SELECT count(*) FROM stock_quant q
          JOIN custom_fixed_asset a ON a.lot_id = q.lot_id
         WHERE q.quantity = 1
        """
    )
    _logger.info("materialize: quants holding exactly one asset serial: %s", env.cr.fetchone()[0])
    env.cr.execute("SELECT count(*) FROM rental_asset")
    _logger.info("materialize: rental units: %s", env.cr.fetchone()[0])


def main(env):
    categ = env.ref("custom_asset_stock_link.product_category_fixed_asset_non_valued")
    aim = resolve_company(env, AIM_COMPANY)
    arka = resolve_company(env, ARKA_COMPANY)

    moves_before = env["account.move"].search_count([])

    aim_location = ensure_stock_location(env, aim, AIM_WAREHOUSE_CODE, ASSET_LOCATION_NAME)
    # ARKA gets its own location of the same name rather than WH-01/Stock:
    # WH-01 was created by hand on 13-Aug-2026 and its operational purpose is
    # not ours to assume, so the register's units stay in a location that says
    # plainly what they are.
    arka_location = ensure_stock_location(env, arka, ARKA_WAREHOUSE_CODE, ASSET_LOCATION_NAME)
    map_asset_locations(env, aim_location)

    total = 0
    for company, location in ((aim, aim_location), (arka, arka_location)):
        assets = pending_assets(env, company)
        _logger.info("materialize: %s has %s unit(s) waiting for a serial", company.name, len(assets))
        if assets:
            total += materialize(env, assets, location, categ)

    report(env)

    moves_after = env["account.move"].search_count([])
    if moves_after != moves_before:
        raise AssertionError(
            "materialize: %s journal entries appeared -- the fleet is already "
            "capitalised and must not be valued in stock" % (moves_after - moves_before)
        )
    _logger.info("materialize: journal entry count unchanged at %s", moves_after)

    if not APPLY:
        env.cr.rollback()
        _logger.info(
            "materialize: dry run over %s unit(s), rolled back. Set MATERIALIZE=1 to apply.",
            total,
        )
        return True

    env.cr.commit()
    _logger.info("materialize: %s unit(s) materialised into stock; committed", total)
    return True


main(env)  # noqa: F821 -- `env` is provided by `odoo shell`
