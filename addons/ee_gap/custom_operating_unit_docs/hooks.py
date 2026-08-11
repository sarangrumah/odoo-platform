# -*- coding: utf-8 -*-
"""Create the ``operating_unit_id`` columns before the ORM ever looks for them.

This is the whole reason the module is safe to install on a live tenant.

When the ORM finds a stored computed field whose column does not exist yet, it
creates the column and then flags **every row of the table** for recompute at
the end of the registry load — one unbounded transaction. On a large
``account_move_line`` that is minutes of held locks during ``-u``, which is
precisely the shape of the outage that took thirteen databases down here once.

Creating the columns in a ``pre_init_hook`` (and, for later version bumps, a
``pre-migration.py``) means ``_init_column`` finds them already present and
queues nothing. The columns stay NULL; history is filled out of band by
``scripts/ops/backfill_operating_unit.py``, which bypasses the ORM entirely.
"""

import logging

from odoo.tools import SQL

_logger = logging.getLogger(__name__)

# Tables that get an operating_unit_id column. Each one exists only if its app
# is installed, hence the to_regclass guard.
OU_TABLES = (
    "account_move",
    "account_move_line",
    "account_payment",
    "account_bank_statement_line",
    "stock_picking",
    "stock_move",
    "stock_quant",
    "purchase_order",
    "sale_order",
)


def create_operating_unit_columns(cr):
    """Idempotent. Safe to call from a pre-init hook and from a pre-migration."""
    created = []
    for table in OU_TABLES:
        cr.execute("SELECT to_regclass(%s)", (table,))
        if not cr.fetchone()[0]:
            continue
        # DDL cannot take a bound parameter for an identifier, so the table
        # name goes through SQL.identifier() (which quotes it) rather than a
        # bare format. The names come from OU_TABLES above, never from input.
        table_sql = SQL.identifier(table)
        cr.execute(
            SQL(
                "ALTER TABLE %s ADD COLUMN IF NOT EXISTS operating_unit_id integer",
                table_sql,
            )
        )
        cr.execute(
            SQL(
                "CREATE INDEX IF NOT EXISTS %s ON %s (operating_unit_id) WHERE operating_unit_id IS NOT NULL",
                SQL.identifier("%s_operating_unit_id_index" % table),
                table_sql,
            )
        )
        created.append(table)
    # Partial index: the column is entirely NULL until the backfill runs, so the
    # index costs nothing to build now and grows with the data.
    _logger.info("Operating Unit columns ensured on: %s", ", ".join(created) or "-")
    return created


def pre_init_hook(env):
    create_operating_unit_columns(env.cr)
