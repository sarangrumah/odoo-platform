"""Create the operating.unit records for an already-installed Levi's database.

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/tenants/levis/90_migrate_operating_unit.py

Dry-run by default (``RUN_DRY=1``): reports what it would create and rolls back.

The module's ``post_init_hook`` does this at install time; this script is for
databases where the module is already installed, or for re-running after new
stores were added by ``41_normalize_ou.py``.

Additive and idempotent. It never renames a warehouse, an analytic account, a
journal or a POS config — see the module README for what was verified on a clone.
"""

import logging
import os

from odoo.addons.custom_levis_operating_unit.models.setup import migrate_levis_operating_units

_logger = logging.getLogger("migrate_operating_unit")
logging.basicConfig(level=logging.INFO)

DRY = os.environ.get("RUN_DRY", "1") != "0"

created, existing = migrate_levis_operating_units(env)  # noqa: F821 — odoo shell

units = env["operating.unit"].with_context(active_test=False).search([])  # noqa: F821
_logger.info("%d unit(s) now on this database:", len(units))
for unit in units:
    _logger.info(
        "  %-10s %-40s %-8s analytic=%-5s warehouse=%-5s journal=%s%s",
        unit.code,
        unit.complete_name,
        unit.ou_type,
        unit.analytic_account_id.id or "-",
        unit.warehouse_id.id or "-",
        unit.purchase_journal_id.id or "-",
        "" if unit.active else "  [archived]",
    )

if DRY:
    env.cr.rollback()  # noqa: F821
    _logger.info("DRY run — rolled back (%d would be created). RUN_DRY=0 to apply.", created)
else:
    env.cr.commit()  # noqa: F821
    _logger.info("Committed: %d created, %d already present.", created, existing)
