"""Backfill the Operating Unit onto POS revenue that was posted without one.

``custom_levis_localization`` now stamps the store's OU analytic on every POS
session closing entry (``pos.session._get_sale_vals``), but entries posted before
that — the whole retail-import backlog — carry no analytic distribution at all,
so a per-OU P&L reports nothing for the sales stream.

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/tenants/levis/42_backfill_ou_analytic.py

Dry-run by default (``RUN_DRY=1``).

Scope: the P&L (``display_type='product'``) lines of each ``pos.session.move_id``.
Tax, receivable and bank lines are balance sheet and are left alone. The OU comes
from ``session.config_id.warehouse_id.l10n_ou_analytic_id``, so run
``41_normalize_ou.py`` first.

Written through the ORM on purpose: ``analytic_distribution`` is a plain jsonb
column, but writing it is what makes Odoo generate the ``account.analytic.line``
ledger rows the analytic reports read. A raw SQL UPDATE would leave those empty.

Posted moves can take this: ``analytic_distribution`` is neither a lock-date
protected field (``account.move.line._get_lock_date_protected_fields``) nor part
of the integrity hash, so the company's ``fiscalyear_lock_date`` does not block
it. A ``hard_lock_date`` would, and is reported rather than worked around.
"""

import os
import sys

DRY = os.environ.get("RUN_DRY", "1") not in ("0", "false", "False")

env = env  # noqa: F821  injected by `odoo shell`
out = sys.stderr

hard_locked = env["res.company"].search([("hard_lock_date", "!=", False)])
if hard_locked:
    out.write(
        "!! hard_lock_date set on %s — journal items are immutable, aborting.\n" % ", ".join(hard_locked.mapped("name"))
    )
    raise SystemExit(1)

Merge = env["purchase.order.line"]._levis_merge_ou_distribution
sessions = env["pos.session"].with_context(active_test=False).search([("move_id", "!=", False)])

stamped = skipped_no_ou = already = 0
no_ou = set()

for session in sessions:
    ou = session.config_id.warehouse_id.l10n_ou_analytic_id
    lines = session.move_id.line_ids.filtered(lambda l: l.display_type == "product")
    if not ou:
        no_ou.add(session.config_id.display_name)
        skipped_no_ou += len(lines)
        continue
    for line in lines:
        target = Merge(line.analytic_distribution, ou.id)
        if line.analytic_distribution == target and line.l10n_ou_analytic_id == ou:
            already += 1
            continue
        line.write({"l10n_ou_analytic_id": ou.id, "analytic_distribution": target})
        stamped += 1

out.write("sessions with a closing entry : %d\n" % len(sessions))
out.write("P&L lines stamped             : %d\n" % stamped)
out.write("P&L lines already correct     : %d\n" % already)
out.write("P&L lines skipped (no OU)     : %d\n" % skipped_no_ou)
if no_ou:
    out.write("!! POS configs without an OU analytic: %s\n" % ", ".join(sorted(no_ou)))

# The analytic ledger is what the per-OU P&L reads; prove it was written.
# account.analytic.line stores one m2o column per analytic plan (account_id for
# the root plan, x_plan<N>_id for the others); ``auto_account_id`` is a
# non-stored helper and cannot be grouped on.
plan = env["account.analytic.plan"].search([("name", "=", "Operating Unit")], limit=1)
column = plan._column_name()
rows = env["account.analytic.line"]._read_group([(column, "!=", False)], [column], ["amount:sum"])
out.write("\nAnalytic ledger by Operating Unit (%d):\n" % len(rows))
for account, amount in sorted(rows, key=lambda r: r[0].name):
    out.write("  %-40s %15.2f\n" % (account.name, amount))

if DRY:
    env.cr.rollback()
    out.write("\nDRY RUN — rolled back. Re-run with RUN_DRY=0 to apply.\n")
else:
    env.cr.commit()
    out.write("\nCOMMITTED.\n")
out.flush()
