"""Fill ``operating_unit_id`` on the historical documents of a tenant.

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/ops/backfill_operating_unit.py

Dry-run by default (``RUN_DRY=1``): reports what it would fill and rolls back.

**Run this outside the ``-u`` window.** ``custom_operating_unit_docs`` creates
the columns empty in its ``pre_init_hook`` precisely so that installing the
module is O(1); this script does the data, in batches, committing as it goes, so
a slow table can never hold locks through a container start.

The work, in order:

1. journal items, from the analytic distribution — the dimension most tenants
   already have. The key of ``analytic_distribution`` is a comma-joined list of
   analytic ids across plans ("12,45"), which is why this needs a LATERAL
   unnest and why the same shape is hopeless as a record-rule domain;
2. journal items with no distribution (tax and payment-term lines), from their
   move;
3. moves themselves, from the majority unit of their lines;
4. the small document tables, straight from the warehouse — including the POS
   chain (config from its warehouse, session from its config, order from its
   session), which the module's own computes never fill on history because the
   columns are created ready-made by the pre-init hook.

Everything is plain SQL: going through the ORM would trigger the recompute this
whole design exists to avoid, and ``operating_unit_id`` is ``readonly=False`` so
no later compute will overwrite what is written here.

Idempotent — every statement only touches rows where ``operating_unit_id IS
NULL``, so an interrupted run is resumed by running it again.
"""

import logging
import os

_logger = logging.getLogger("backfill_operating_unit")
logging.basicConfig(level=logging.INFO)

DRY = os.environ.get("RUN_DRY", "1") != "0"
BATCH = int(os.environ.get("OU_BATCH", "50000"))

cr = env.cr  # noqa: F821 — provided by odoo shell


def _table_exists(table):
    cr.execute("SELECT to_regclass(%s)", (table,))
    return bool(cr.fetchone()[0])


def _count_null(table):
    if not _table_exists(table):
        return None
    cr.execute("SELECT count(*) FROM %s WHERE operating_unit_id IS NULL" % table)
    return cr.fetchone()[0]


def _id_range(table):
    cr.execute("SELECT coalesce(min(id), 0), coalesce(max(id), 0) FROM %s" % table)
    return cr.fetchone()


def _batched(table, sql, label):
    """Run ``sql`` (parameterised on %(lo)s/%(hi)s) over the table's id space."""
    if not _table_exists(table):
        _logger.info("%s: table absent, skipped", label)
        return 0
    lo, hi = _id_range(table)
    total = 0
    while lo <= hi:
        cr.execute(sql, {"lo": lo, "hi": lo + BATCH - 1})
        total += cr.rowcount
        lo += BATCH
        if not DRY:
            cr.commit()
    _logger.info("%s: %d row(s) filled", label, total)
    return total


AML_FROM_DISTRIBUTION = """
    WITH ou AS (
        SELECT id, analytic_account_id
          FROM operating_unit
         WHERE analytic_account_id IS NOT NULL
    )
    UPDATE account_move_line aml
       SET operating_unit_id = sub.ou_id
      FROM (
        SELECT l.id AS line_id,
               (SELECT ou.id
                  FROM jsonb_object_keys(l.analytic_distribution) AS k(key)
                  CROSS JOIN LATERAL unnest(string_to_array(k.key, ',')) AS part(aid)
                  JOIN ou ON ou.analytic_account_id = trim(part.aid)::int
                 LIMIT 1) AS ou_id
          FROM account_move_line l
         WHERE l.id BETWEEN %(lo)s AND %(hi)s
           AND l.operating_unit_id IS NULL
           AND l.analytic_distribution IS NOT NULL
      ) sub
     WHERE aml.id = sub.line_id AND sub.ou_id IS NOT NULL
"""

AML_FROM_MOVE = """
    UPDATE account_move_line l
       SET operating_unit_id = m.operating_unit_id
      FROM account_move m
     WHERE l.move_id = m.id
       AND l.id BETWEEN %(lo)s AND %(hi)s
       AND l.operating_unit_id IS NULL
       AND m.operating_unit_id IS NOT NULL
"""

MOVE_FROM_LINES = """
    UPDATE account_move m
       SET operating_unit_id = sub.ou_id
      FROM (
        SELECT l.move_id, l.operating_unit_id AS ou_id, count(*) AS n,
               row_number() OVER (PARTITION BY l.move_id ORDER BY count(*) DESC,
                                                                 l.operating_unit_id) AS rn
          FROM account_move_line l
         WHERE l.move_id BETWEEN %(lo)s AND %(hi)s
           AND l.operating_unit_id IS NOT NULL
         GROUP BY l.move_id, l.operating_unit_id
      ) sub
     WHERE m.id = sub.move_id AND sub.rn = 1 AND m.operating_unit_id IS NULL
"""

MOVE_FROM_JOURNAL = """
    UPDATE account_move m
       SET operating_unit_id = ou.id
      FROM operating_unit ou
     WHERE m.id BETWEEN %(lo)s AND %(hi)s
       AND m.operating_unit_id IS NULL
       AND (m.journal_id = ou.journal_id OR m.journal_id = ou.purchase_journal_id)
"""

# Small tables: one statement each, no batching needed.
SIMPLE_PASSES = [
    (
        "stock_picking",
        """
        UPDATE stock_picking p SET operating_unit_id = ou.id
          FROM stock_picking_type t
          JOIN operating_unit ou ON ou.warehouse_id = t.warehouse_id
         WHERE p.picking_type_id = t.id AND p.operating_unit_id IS NULL
        """,
    ),
    (
        "stock_move",
        """
        UPDATE stock_move sm SET operating_unit_id = p.operating_unit_id
          FROM stock_picking p
         WHERE sm.picking_id = p.id AND sm.operating_unit_id IS NULL
           AND p.operating_unit_id IS NOT NULL
        """,
    ),
    (
        "stock_quant",
        """
        UPDATE stock_quant q SET operating_unit_id = ou.id
          FROM stock_location l
          JOIN operating_unit ou ON ou.warehouse_id = l.warehouse_id
         WHERE q.location_id = l.id AND q.operating_unit_id IS NULL
        """,
    ),
    (
        "purchase_order",
        """
        UPDATE purchase_order po SET operating_unit_id = ou.id
          FROM stock_picking_type t
          JOIN operating_unit ou ON ou.warehouse_id = t.warehouse_id
         WHERE po.picking_type_id = t.id AND po.operating_unit_id IS NULL
        """,
    ),
    (
        "sale_order",
        """
        UPDATE sale_order so SET operating_unit_id = ou.id
          FROM operating_unit ou
         WHERE so.warehouse_id = ou.warehouse_id AND so.operating_unit_id IS NULL
        """,
    ),
    (
        "pos_config",
        """
        UPDATE pos_config c SET operating_unit_id = ou.id
          FROM operating_unit ou
         WHERE c.warehouse_id = ou.warehouse_id AND c.operating_unit_id IS NULL
        """,
    ),
    (
        "pos_session",
        """
        UPDATE pos_session s SET operating_unit_id = c.operating_unit_id
          FROM pos_config c
         WHERE s.config_id = c.id AND s.operating_unit_id IS NULL
           AND c.operating_unit_id IS NOT NULL
        """,
    ),
    (
        "pos_order",
        """
        UPDATE pos_order o SET operating_unit_id = s.operating_unit_id
          FROM pos_session s
         WHERE o.session_id = s.id AND o.operating_unit_id IS NULL
           AND s.operating_unit_id IS NOT NULL
        """,
    ),
    (
        "account_payment",
        """
        UPDATE account_payment p SET operating_unit_id = m.operating_unit_id
          FROM account_move m
         WHERE p.move_id = m.id AND p.operating_unit_id IS NULL
           AND m.operating_unit_id IS NOT NULL
        """,
    ),
    (
        "account_bank_statement_line",
        """
        UPDATE account_bank_statement_line s SET operating_unit_id = m.operating_unit_id
          FROM account_move m
         WHERE s.move_id = m.id AND s.operating_unit_id IS NULL
           AND m.operating_unit_id IS NOT NULL
        """,
    ),
]


def main():
    cr.execute("SELECT count(*) FROM operating_unit")
    units = cr.fetchone()[0]
    if not units:
        _logger.warning("No operating.unit records — run the provisioning first. Nothing to do.")
        return

    _logger.info("%s run, %d unit(s), batch %d", "DRY" if DRY else "LIVE", units, BATCH)

    _batched("account_move", MOVE_FROM_JOURNAL, "account_move (from journal)")
    _batched("account_move_line", AML_FROM_DISTRIBUTION, "account_move_line (from analytic)")
    _batched("account_move", MOVE_FROM_LINES, "account_move (from its lines)")
    _batched("account_move_line", AML_FROM_MOVE, "account_move_line (from its move)")

    for table, sql in SIMPLE_PASSES:
        if not _table_exists(table):
            _logger.info("%s: table absent, skipped", table)
            continue
        cr.execute(sql)
        _logger.info("%s: %d row(s) filled", table, cr.rowcount)
        if not DRY:
            cr.commit()

    _logger.info("--- remaining NULL after backfill ---")
    for table in (
        "account_move",
        "account_move_line",
        "account_payment",
        "account_bank_statement_line",
        "stock_picking",
        "stock_move",
        "stock_quant",
        "purchase_order",
        "sale_order",
        "pos_config",
        "pos_session",
        "pos_order",
    ):
        remaining = _count_null(table)
        if remaining is not None:
            _logger.info("%-32s %d", table, remaining)

    if DRY:
        cr.rollback()
        _logger.info("DRY run — rolled back. Re-run with RUN_DRY=0 to apply.")
    else:
        cr.commit()
        _logger.info("Committed. Now run: VACUUM (ANALYZE) account_move_line;")


main()
