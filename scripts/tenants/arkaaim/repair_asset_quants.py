"""Collapse the duplicate stock quants left behind by the old loan pickings.

Tenant: PT Aero Inovasi Media + PT Aero Reksa Kreasi Angkasa. DBs: a scratch
clone first, then ``prd_arkaaim``.

What is wrong
-------------

The register's 3,590 serials sit behind 11,929 quant rows. Two fossil patterns,
2,572 of each, both left by loan pickings that reserved from a location the units
were never in::

    ARKA/Stock             1.00 + -1.00   -> net 0   (an outbound leg never matched)
    WH/RUKO GUDANG PALEM   1.00 +  0.00   -> net 1   (a redundant row beside the unit)

**No unit is lost or duplicated**: all 3,590 net to exactly 1. This is bookkeeping
clutter, not a stock discrepancy, which is also why the repair is safe -- there is
nothing to decide about where a unit is, only rows to add up.

Why it still matters
--------------------

The ``0.00`` row beside the real one is what a reservation finds first, and drives
to ``-1.00`` while the ``1.00`` row sits untouched. So every move of one of those
2,572 units mints another offsetting pair. Measured on a clone with Odoo's own
reservation: a dispatch took negatives from 3 to 6 across three serials.

``reserved_quantity`` is broken in the same shape and is invisible in the quantity
column::

    negative rows  2,572   quantity -2,572   reserved_quantity -2,572
    zero rows      3,195   quantity      0   reserved_quantity      0
    positive rows  6,162   quantity +6,162   reserved_quantity +2,572

Collapsing quantity alone would leave 2,572 rows carrying ``reserved_quantity -1``
with nothing to match them -- Odoo would read those units as negatively reserved,
which is worse than today. Both columns are summed.

What it does
------------

Per (product, lot, location, package, owner) -- Odoo's own notion of a distinct
quant, not merely (lot, location): keep the lowest-id row, write it the **sum** of
both columns, delete the rest. Collapsing on (lot, location) alone would merge two
genuinely different holdings if one were in a package or under a different owner.
No such case exists on prd_arkaaim today, which is exactly when a shortcut like
that gets taken and survives until the data changes -- ``owner_id`` has already
bitten this platform once, on the Levi's consignment receipts. Then delete any row that ends at 0 on both columns -- leaving a
zero row simply recreates the thing that gets decremented next time. 11,929 rows
become 3,590: one per unit, where the unit actually is.

Written in SQL rather than through ``unlink``: the ORM's quant unlink adjusts
reserved quantities as a side effect and would fight the very columns being
repaired.

Refuses to run if any unit does not net to exactly 1, because then the data is not
merely cluttered and somebody has to look at it.

Run inside the Odoo container (stdin, so no file needs to exist in the image)::

    docker exec -i odoo19-platform-odoo sh -c 'odoo shell -d prd_arkaaim --no-http' \
        < scripts/tenants/arkaaim/repair_asset_quants.py

Environment:
    APPLY=1   actually write (default: dry run, rolled back)
"""

import logging
import os

_logger = logging.getLogger(__name__)

APPLY = os.environ.get("APPLY") == "1"


def section(title):
    _logger.info("")
    _logger.info("== %s", title)


def snapshot(env):
    env.cr.execute(
        """
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE q.quantity < 0) AS negative,
               count(*) FILTER (WHERE q.quantity = 0) AS zero,
               COALESCE(sum(q.quantity), 0) AS qty,
               COALESCE(sum(q.reserved_quantity), 0) AS reserved
        FROM stock_quant q
        JOIN stock_location l ON l.id = q.location_id
        WHERE l.usage = 'internal'
          AND q.lot_id IN (SELECT lot_id FROM custom_fixed_asset WHERE lot_id IS NOT NULL)
        """
    )
    return env.cr.dictfetchone()


def net_per_lot_ok(env):
    """Every asset must net to exactly 1 before anything is touched."""
    env.cr.execute(
        """
        SELECT count(*) FROM (
            SELECT q.lot_id
            FROM stock_quant q
            JOIN stock_location l ON l.id = q.location_id
            WHERE l.usage = 'internal'
              AND q.lot_id IN (SELECT lot_id FROM custom_fixed_asset WHERE lot_id IS NOT NULL)
            GROUP BY q.lot_id
            HAVING sum(q.quantity) <> 1
        ) t
        """
    )
    return env.cr.fetchone()[0]


def out_of_scope(env):
    """Asset serials with no internal quant at all.

    ``net_per_lot_ok`` groups internal rows, so a serial sitting entirely in a
    transit location produces no group and would never trip the net check. It
    would be silently skipped rather than corrupted -- but silently is the part
    worth fixing. None exist on prd_arkaaim; say so out loud anyway.
    """
    env.cr.execute(
        """
        SELECT count(*) FROM custom_fixed_asset a
        WHERE a.lot_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM stock_quant q
              JOIN stock_location l ON l.id = q.location_id
              WHERE q.lot_id = a.lot_id AND l.usage = 'internal'
          )
        """
    )
    return env.cr.fetchone()[0]


def repair(env):
    section("before")
    before = snapshot(env)
    _logger.info(
        "%s row(s): %s negative, %s zero, quantity %s, reserved %s",
        before["rows"],
        before["negative"],
        before["zero"],
        before["qty"],
        before["reserved"],
    )

    outside = out_of_scope(env)
    if outside:
        _logger.warning(
            "%s asset serial(s) have no quant in an internal location -- they are "
            "outside this repair and are left alone",
            outside,
        )

    off_net = net_per_lot_ok(env)
    if off_net:
        raise AssertionError(
            "%s asset serial(s) do not net to exactly 1. That is a real stock "
            "discrepancy, not clutter -- refusing to collapse rows over it." % off_net
        )
    _logger.info("every asset serial nets to exactly 1 -- safe to collapse")

    section("collapse")
    # Keep the lowest-id row per (lot, location); give it the sums; drop the rest.
    env.cr.execute(
        """
        WITH target AS (
            SELECT q.id, q.lot_id, q.location_id, q.quantity, q.reserved_quantity,
                   min(q.id) OVER w AS keep_id,
                   sum(q.quantity) OVER w AS net_qty,
                   sum(q.reserved_quantity) OVER w AS net_res
            FROM stock_quant q
            JOIN stock_location l ON l.id = q.location_id
            WHERE l.usage = 'internal'
              AND q.lot_id IN (SELECT lot_id FROM custom_fixed_asset WHERE lot_id IS NOT NULL)
            WINDOW w AS (
                PARTITION BY q.product_id, q.lot_id, q.location_id,
                             COALESCE(q.package_id, -1), COALESCE(q.owner_id, -1)
            )
        ),
        updated AS (
            UPDATE stock_quant q
            SET quantity = t.net_qty, reserved_quantity = t.net_res
            FROM (SELECT DISTINCT keep_id, net_qty, net_res FROM target) t
            WHERE q.id = t.keep_id
              AND (q.quantity, q.reserved_quantity) IS DISTINCT FROM (t.net_qty, t.net_res)
            RETURNING q.id
        ),
        deleted AS (
            DELETE FROM stock_quant q
            USING target t
            WHERE q.id = t.id AND t.id <> t.keep_id
            RETURNING q.id
        )
        SELECT (SELECT count(*) FROM updated), (SELECT count(*) FROM deleted)
        """
    )
    updated, deleted = env.cr.fetchone()
    _logger.info("%s row(s) rewritten to their net, %s duplicate row(s) removed", updated, deleted)

    # A row that nets to nothing is the seed of the next negative. Remove it.
    env.cr.execute(
        """
        DELETE FROM stock_quant q
        USING stock_location l
        WHERE l.id = q.location_id
          AND l.usage = 'internal'
          AND q.quantity = 0 AND q.reserved_quantity = 0
          AND q.lot_id IN (SELECT lot_id FROM custom_fixed_asset WHERE lot_id IS NOT NULL)
        """
    )
    _logger.info("%s empty row(s) removed", env.cr.rowcount)

    env.invalidate_all()

    section("after")
    after = snapshot(env)
    _logger.info(
        "%s row(s): %s negative, %s zero, quantity %s, reserved %s",
        after["rows"],
        after["negative"],
        after["zero"],
        after["qty"],
        after["reserved"],
    )

    section("guard")
    assets = env["custom.fixed.asset"].search_count([("lot_id", "!=", False)])
    problems = []
    if after["negative"]:
        problems.append("%s negative row(s) remain" % after["negative"])
    if after["zero"]:
        problems.append("%s zero row(s) remain" % after["zero"])
    if after["qty"] != before["qty"]:
        problems.append("total quantity moved from %s to %s" % (before["qty"], after["qty"]))
    if net_per_lot_ok(env):
        problems.append("some serial no longer nets to 1")
    expected = assets - outside
    if after["rows"] != expected:
        problems.append("%s row(s) for %s in-scope asset serial(s)" % (after["rows"], expected))
    if problems:
        raise AssertionError("; ".join(problems))
    _logger.info(
        "one row per unit (%s), no negatives, no empties, total quantity unchanged at %s",
        after["rows"],
        after["qty"],
    )


def main(env):
    moves_before = env["account.move"].search_count([])
    repair(env)
    if env["account.move"].search_count([]) != moves_before:
        raise AssertionError("repair_asset_quants posted a journal entry; it must post none")
    _logger.info("account.move delta: 0")

    if APPLY:
        env.cr.commit()
        _logger.info("repair_asset_quants: committed")
    else:
        env.cr.rollback()
        _logger.info("repair_asset_quants: dry run, rolled back. Set APPLY=1 to write.")


main(env)  # noqa: F821 -- `env` is injected by `odoo shell`
