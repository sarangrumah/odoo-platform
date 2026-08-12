"""How much of a tenant's data carries an Operating Unit yet.

    docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/ops/report_operating_unit_coverage.py

Read-only. This is the go/no-go for flipping
``custom_operating_unit.include_untagged`` to ``"0"``: while it is ``"1"`` (the
shipped default) a scoped user still sees documents that carry no unit, which is
what keeps history visible on day one.

**The question is not whether coverage reached 100%** — on a tenant with a
central bank journal it never will, and waiting for it is waiting forever. It is
whether every row that is still untagged is one that *genuinely* has no
Operating Unit. So the report also breaks the untagged entries down by journal:
central bank and head-office payments are fine to hide, a store's own entries in
a journal nobody linked to a unit are not. That second kind is what the
cash-journal gap looked like on rnd_levis — 378 entries that read as acceptable
residue and were a missing link.
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

if total_missing:
    _logger.info("")
    _logger.info("--- untagged journal entries, by journal ---")
    cr.execute(
        """
        SELECT j.type, coalesce(j.name ->> 'en_US', '?'), count(*)
          FROM account_move m
          JOIN account_journal j ON j.id = m.journal_id
         WHERE m.operating_unit_id IS NULL
         GROUP BY 1, 2
         ORDER BY 3 DESC
         LIMIT 15
        """
    )
    for jtype, jname, count in cr.fetchall():
        _logger.info("%-10s %-44s %8d", jtype, jname[:44], count)
    _logger.info("")
    _logger.info(
        "%d row(s) have no unit. Before setting include_untagged = 0, check the list "
        "above: a central bank or head-office journal belongs there, a store's own "
        "journal does not — that one needs its Operating Unit link fixed and the "
        "backfill re-run first.",
        total_missing,
    )
else:
    _logger.info("Nothing is untagged — include_untagged = 0 changes nothing.")
