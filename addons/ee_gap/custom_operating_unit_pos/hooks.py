# -*- coding: utf-8 -*-
"""Create the POS operating_unit_id columns before the ORM looks for them.

Same reason as in ``custom_operating_unit_docs``: a stored computed field whose
column is missing makes Odoo flag the whole table for recompute in a single
transaction at the end of the registry load. ``pos_order`` is the big one — a
Levi's tenant accumulates hundreds of thousands of rows.
"""

import logging

from odoo.tools import SQL

_logger = logging.getLogger(__name__)

OU_TABLES = ("pos_config", "pos_session", "pos_order")


def create_operating_unit_columns(cr):
    for table in OU_TABLES:
        cr.execute("SELECT to_regclass(%s)", (table,))
        if not cr.fetchone()[0]:
            continue
        # Identifiers cannot be bound parameters; SQL.identifier() quotes
        # them. The names come from OU_TABLES above, never from input.
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
    _logger.info("Operating Unit columns ensured on the POS tables")


def pre_init_hook(env):
    create_operating_unit_columns(env.cr)
