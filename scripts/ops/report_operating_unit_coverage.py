"""How much of a tenant's data carries an Operating Unit yet.

    docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/ops/report_operating_unit_coverage.py

Read-only. This is the go/no-go for flipping
``custom_operating_unit.include_untagged`` to ``"0"``: while it is ``"1"`` (the
shipped default) a scoped user still sees documents that carry no unit, which is
what keeps history visible on day one. Turning it off before coverage is
complete makes legacy documents disappear for store users — technically correct,
operationally alarming.
"""

import logging

_logger = logging.getLogger("ou_coverage")
logging.basicConfig(level=logging.INFO)

cr = env.cr  # noqa: F821 — provided by odoo shell

TABLES = (
    "account_move",
    "account_move_line",
    "account_payment",
    "account_bank_statement_line",
    "stock_picking",
    "stock_move",
    "stock_quant",
    "purchase_order",
    "sale_order",
    "pos_order",
    "pos_session",
)

cr.execute("SELECT count(*) FROM operating_unit WHERE active")
_logger.info("Active operating units: %s", cr.fetchone()[0])

ConfigParameter = env["ir.config_parameter"].sudo()  # noqa: F821 — odoo shell global
param = ConfigParameter.get_param("custom_operating_unit.include_untagged", "1")
_logger.info("include_untagged = %r (%s)", param, "untagged visible" if param != "0" else "hidden")

_logger.info("%-34s %10s %10s %7s", "table", "rows", "no unit", "cover")
total_missing = 0
for table in TABLES:
    cr.execute("SELECT to_regclass(%s)", (table,))
    if not cr.fetchone()[0]:
        continue
    cr.execute("SELECT count(*), count(*) FILTER (WHERE operating_unit_id IS NULL) FROM %s" % table)
    rows, missing = cr.fetchone()
    total_missing += missing
    coverage = 100.0 if not rows else 100.0 * (rows - missing) / rows
    _logger.info("%-34s %10d %10d %6.1f%%", table, rows, missing, coverage)

_logger.info(
    "%s",
    "Coverage complete — safe to set include_untagged = 0."
    if not total_missing
    else "%d row(s) still have no unit. Run backfill_operating_unit.py, and keep "
    "include_untagged = 1 until this is zero." % total_missing,
)
