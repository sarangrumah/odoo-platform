# -*- coding: utf-8 -*-
"""Create the POS operating_unit_id columns before the ORM looks for them.

Same reason as in ``custom_operating_unit_docs``: a stored computed field whose
column is missing makes Odoo flag the whole table for recompute in a single
transaction at the end of the registry load. ``pos_order`` is the big one — a
Levi's tenant accumulates hundreds of thousands of rows.
"""

import logging

_logger = logging.getLogger(__name__)

OU_TABLES = ("pos_config", "pos_session", "pos_order")


def create_operating_unit_columns(cr):
    for table in OU_TABLES:
        cr.execute("SELECT to_regclass(%s)", (table,))
        if not cr.fetchone()[0]:
            continue
        cr.execute(
            "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS operating_unit_id integer;"
            "CREATE INDEX IF NOT EXISTS {t}_operating_unit_id_index "
            "  ON {t} (operating_unit_id) WHERE operating_unit_id IS NOT NULL;".format(t=table)
        )
    _logger.info("Operating Unit columns ensured on the POS tables")


def pre_init_hook(env):
    create_operating_unit_columns(env.cr)
