"""Point ARKA-AIM's deployment bridge at the right warehouse locations.

Tenant: PT Aero Inovasi Media (company 1) + PT Aero Reksa Kreasi Angkasa
(company 2). DBs: a scratch clone first, then ``prd_arkaaim``.

Two locations per company, and getting the second one right is the whole point:

* **On-Deployment** -- where units sit while they are out at an event. Created
  here as an internal location under the company's own warehouse, because
  internal is what keeps stock valuation away from the ledger: the units never
  leave the company, so nothing is delivered and nothing is sold.
* **Source** -- where dispatched units are picked *from*. ``custom_rental``
  defaults this to the first internal picking type's source, which is the Input
  dock in a multi-step warehouse. ARKA-AIM's fleet does not live there: 3,324 AIM
  units sit in ``WH/RUKO GUDANG PALEM`` and 266 ARKA units in
  ``WH-01/RUKO GUDANG PALEM``. Reserving from the wrong location does not fail --
  it books a negative quant at the source, a positive one at the destination, and
  leaves the units where they were. So the source is resolved from where the
  fleet actually is, counted from the register rather than assumed.

Everything is per company. Warehouse codes are not unique across companies, and
a location belonging to another company cannot receive a transfer at all.

**The feature stays off.** ``deployment_auto_create`` is not switched on here:
that is what changes behaviour when a salesperson confirms an order, and it
should be a deliberate act once Ops is ready. Pass ``ENABLE=1`` to turn it on.

Run inside the Odoo container (stdin, so no file needs to exist in the image)::

    docker exec -i odoo19-platform-odoo sh -c 'odoo shell -d prd_arkaaim --no-http' \
        < scripts/tenants/arkaaim/setup_deployment.py

Environment:
    APPLY=1              actually write (default: dry run, rolled back)
    ENABLE=1             also switch deployment_auto_create on (default: leave off)
    DEPLOY_LOC=...       name of the on-deployment location (default: On Deployment)
"""

import logging
import os

_logger = logging.getLogger(__name__)

APPLY = os.environ.get("APPLY") == "1"
ENABLE = os.environ.get("ENABLE") == "1"
DEPLOY_LOC_NAME = os.environ.get("DEPLOY_LOC", "On Deployment")


def section(title):
    _logger.info("")
    _logger.info("== %s", title)


def fleet_location(env, company):
    """Where this company's fleet actually sits, by unit count.

    Read from the register rather than guessed: the answer differs per company
    and is not the warehouse's default stock location in either of them.
    """
    groups = env["custom.fixed.asset"]._read_group(
        domain=[
            ("company_id", "=", company.id),
            ("stock_location_id", "!=", False),
        ],
        groupby=["stock_location_id"],
        aggregates=["__count"],
    )
    if not groups:
        return env["stock.location"], 0
    groups = sorted(groups, key=lambda pair: pair[1], reverse=True)
    return groups[0]


def ensure_deployment_location(env, company):
    """Create it beside the fleet, not in whichever warehouse sorts first.

    PT Aero Inovasi Media has four warehouses, all on sequence 10, two of them the
    damage and lost warehouses -- so an unordered ``search(limit=1)`` could file
    the on-deployment location inside the damage warehouse. The fleet location we
    just resolved already knows the right warehouse.
    """
    source, _count = fleet_location(env, company)
    warehouse = source.warehouse_id if source else False
    if not warehouse:
        warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1, order="sequence, id")
    if not warehouse:
        _logger.warning("%s has no warehouse -- cannot place the on-deployment location", company.name)
        return env["stock.location"]
    parent = warehouse.view_location_id
    existing = env["stock.location"].search([("name", "=", DEPLOY_LOC_NAME), ("location_id", "=", parent.id)], limit=1)
    if existing:
        return existing
    _logger.info("%s: creating %s/%s", company.name, parent.complete_name, DEPLOY_LOC_NAME)
    return env["stock.location"].create(
        {
            "name": DEPLOY_LOC_NAME,
            "usage": "internal",
            "location_id": parent.id,
            "company_id": company.id,
        }
    )


def configure(env):
    section("deployment configuration")
    companies = env["custom.fixed.asset"].search([]).company_id
    for company in companies:
        on_deployment = ensure_deployment_location(env, company)
        source, count = fleet_location(env, company)
        if not source:
            _logger.warning(
                "%s: no unit in the register has a physical location -- cannot "
                "tell where dispatches should be picked from",
                company.name,
            )
        else:
            _logger.info("%s: fleet sits in %s (%s unit(s))", company.name, source.complete_name, count)
            if source.company_id and source.company_id != company:
                _logger.error(
                    "%s: fleet location %s belongs to %s -- refusing to configure it",
                    company.name,
                    source.complete_name,
                    source.company_id.name,
                )
                source = env["stock.location"]

        vals = {}
        if on_deployment and company.deployment_location_id != on_deployment:
            vals["deployment_location_id"] = on_deployment.id
        if source and company.deployment_source_location_id != source:
            vals["deployment_source_location_id"] = source.id
        if ENABLE and not company.deployment_auto_create:
            vals["deployment_auto_create"] = True
        if vals:
            company.write(vals)

        _logger.info(
            "%s: on-deployment=%s source=%s auto-create=%s",
            company.name,
            company.deployment_location_id.complete_name or "-",
            company.deployment_source_location_id.complete_name or "-",
            company.deployment_auto_create,
        )
        if not company.deployment_auto_create:
            _logger.info(
                "%s: automatic creation is OFF -- sales orders behave exactly as "
                "before, and Ops can still raise a dispatch with Create Deployment. "
                "Re-run with ENABLE=1 when ready.",
                company.name,
            )


def main(env):
    moves_before = env["account.move"].search_count([])
    quants_before = env["stock.quant"].search_count([])

    configure(env)

    section("guard")
    if env["account.move"].search_count([]) != moves_before:
        raise AssertionError("setup_deployment posted a journal entry; it must post none")
    if env["stock.quant"].search_count([]) != quants_before:
        raise AssertionError("setup_deployment moved stock; it must move none")
    _logger.info("account.move and stock.quant deltas: 0 -- configuration only")

    if APPLY:
        env.cr.commit()
        _logger.info("setup_deployment: committed")
    else:
        env.cr.rollback()
        _logger.info("setup_deployment: dry run, rolled back. Set APPLY=1 to write.")


main(env)  # noqa: F821 -- `env` is injected by `odoo shell`
