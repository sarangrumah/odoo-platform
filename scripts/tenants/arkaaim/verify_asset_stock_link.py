"""Check the ARKA/AIM asset-to-stock link, read-only.

Run after ``materialize_assets_to_stock.py`` and any time the register and the
warehouse are suspected of having drifted::

    docker exec -i odoo19-platform-odoo sh -c 'odoo shell -d prd_arkaaim --no-http' \
        < scripts/tenants/arkaaim/verify_asset_stock_link.py

Prints, and never writes:

* per company/group: assets, serials, products, units on hand
* assets still without a serial
* serials with no stock anywhere, or sitting outside an internal location
* units whose cached physical location disagrees with their quant
* anything that would let stock valuation reach the ledger
"""

import logging

_logger = logging.getLogger(__name__)


def section(title):
    _logger.info("")
    _logger.info("== %s", title)


def coverage(env):
    section("coverage")
    env.cr.execute(
        """
        SELECT c.name, g.name, a.state,
               count(*), count(a.lot_id), count(a.product_id),
               count(*) FILTER (WHERE a.stock_state = 'in_stock')
          FROM custom_fixed_asset a
          LEFT JOIN res_company c ON c.id = a.company_id
          LEFT JOIN custom_fixed_asset_group g ON g.id = a.group_id
         GROUP BY 1, 2, 3 ORDER BY 4 DESC
        """
    )
    for company, group, state, assets, serials, products, in_stock in env.cr.fetchall():
        _logger.info(
            "  %-30s %-16s %-9s assets=%-6s serials=%-6s products=%-6s in_stock=%s",
            company,
            group,
            state,
            assets,
            serials,
            products,
            in_stock,
        )


def gaps(env):
    section("gaps")
    Asset = env["custom.fixed.asset"].with_context(active_test=False)

    no_serial = Asset.search([("lot_id", "=", False)])
    _logger.info("  assets without a serial: %s", len(no_serial))
    for asset in no_serial[:10]:
        _logger.info("    %s %s (%s)", asset.code, asset.name, asset.company_id.name)

    not_in_stock = Asset.search([("lot_id", "!=", False), ("stock_state", "!=", "in_stock")])
    _logger.info("  serialised assets not in stock: %s", len(not_in_stock))
    for asset in not_in_stock[:10]:
        _logger.info("    %s %s -> %s", asset.code, asset.name, asset.stock_state)

    env.cr.execute(
        """
        SELECT count(*) FROM custom_fixed_asset a
          JOIN stock_quant q ON q.lot_id = a.lot_id
          JOIN stock_location l ON l.id = q.location_id
         WHERE q.quantity > 0 AND l.usage NOT IN ('internal', 'transit')
        """
    )
    _logger.info("  asset serials outside an internal location: %s", env.cr.fetchone()[0])

    env.cr.execute(
        """
        SELECT count(*) FROM custom_fixed_asset a
          JOIN stock_quant q ON q.lot_id = a.lot_id AND q.quantity > 0
          JOIN stock_location l ON l.id = q.location_id AND l.usage IN ('internal', 'transit')
         WHERE a.stock_location_id IS DISTINCT FROM q.location_id
        """
    )
    stale = env.cr.fetchone()[0]
    _logger.info("  assets whose cached location is stale: %s", stale)
    if stale:
        _logger.info("    fix with: env['custom.fixed.asset']._cron_sync_stock_locations()")

    env.cr.execute(
        """
        SELECT count(*) FROM custom_fixed_asset a
         WHERE a.lot_id IS NOT NULL AND a.rental_asset_id IS NULL
        """
    )
    _logger.info("  serialised assets without a rental unit: %s", env.cr.fetchone()[0])


def valuation_exposure(env):
    section("valuation exposure -- all of these must be zero")
    Product = env["product.product"]
    products = Product.with_context(active_test=False).search(
        [("id", "in", env["custom.fixed.asset"].search([]).product_id.ids)]
    )
    perpetual = products.filtered(lambda p: p.valuation == "real_time")
    priced = products.filtered(lambda p: p.standard_price)
    lot_valued = products.filtered("lot_valuated")
    _logger.info("  asset products: %s", len(products))
    _logger.info("  ... valued perpetually: %s", len(perpetual))
    _logger.info("  ... with a non-zero cost: %s", len(priced))
    for product in priced[:10]:
        _logger.info("      %s = %s", product.display_name, product.standard_price)
    _logger.info("  ... with per-serial valuation: %s", len(lot_valued))

    for company in env["res.company"].search([]):
        _logger.info("  company %s valuation: %s", company.name, company.inventory_valuation)

    env.cr.execute("SELECT count(*) FROM stock_location WHERE valuation_account_id IS NOT NULL")
    _logger.info("  locations carrying a valuation account: %s", env.cr.fetchone()[0])


def rental_readiness(env):
    section("rental readiness")
    env.cr.execute(
        """
        SELECT coalesce(r.state, '(none)'), count(*)
          FROM custom_fixed_asset a
          LEFT JOIN rental_asset r ON r.id = a.rental_asset_id
         GROUP BY 1 ORDER BY 2 DESC
        """
    )
    for state, count in env.cr.fetchall():
        _logger.info("  %-12s %s", state, count)
    available = env["custom.fixed.asset"].search_count([("is_rentable", "=", True)])
    _logger.info("  units available to rent right now: %s", available)
    unpriced = env["rental.asset"].search_count([("daily_rate", "=", 0.0)])
    _logger.info("  rental units still without a daily rate: %s", unpriced)


def main(env):
    coverage(env)
    gaps(env)
    valuation_exposure(env)
    rental_readiness(env)
    env.cr.rollback()
    _logger.info("")
    _logger.info("verify_asset_stock_link: read-only, nothing written")
    return True


main(env)  # noqa: F821 -- `env` is provided by `odoo shell`
