"""Provision the Trade/Non-Trade + Operating-Unit feature on an EXISTING Levi's DB.

`custom_levis_localization`'s ``post_init_hook`` only runs on a fresh install, so
already-installed DBs (demo_levis / rnd_levis / prd_levis / demo_updated_levis)
are seeded with this script. Idempotent — safe to re-run.

    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_updated_levis \
        --no-http < scripts/tenants/levis/40_setup_trade_ou.py

Seeds, per company that has stores:
  * "Operating Unit" analytic plan + one analytic account per warehouse
    (warehouse.l10n_ou_analytic_id),
  * one purchase journal per warehouse (warehouse.l10n_purchase_journal_id),
  * levis.purchase.account.map rows (trade / non-trade) by account code.
"""

import sys

from odoo.addons.custom_levis_localization.models.setup import seed_trade_ou

res = seed_trade_ou(env)  # noqa: F821  (env is injected by `odoo shell`)
env.cr.commit()  # noqa: F821
sys.stderr.write("Trade/OU seeding done: %s\n" % (res,))
sys.stderr.flush()
