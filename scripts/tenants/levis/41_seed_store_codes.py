"""Fill warehouse store codes on an EXISTING Levi's DB.

`custom_levis_localization`'s ``post_init_hook`` only runs on a fresh install, so
already-installed DBs are seeded with this script. Idempotent — safe to re-run.

    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d rnd_levis \
        --no-http < scripts/tenants/levis/41_seed_store_codes.py

Reads the ``posconfig_<CODE>`` xids the retail importer already wrote, walks them
back ``pos.config`` -> ``stock.warehouse``, and writes ``l10n_store_code``. Never
overwrites a code already on a warehouse, and never moves a code off the
warehouse that holds it — both cases are logged and left for a human.

Check the counters it prints: a large ``skipped`` or ``orphan`` means the feed's
store mapping disagrees with the warehouses, which is a finding, not a hiccup.
"""

import sys

from odoo.addons.custom_levis_localization.models.setup import seed_store_codes

res = seed_store_codes(env)  # noqa: F821  (env is injected by `odoo shell`)
env.cr.commit()  # noqa: F821
sys.stderr.write("Store-code seeding done: %s\n" % (res,))
sys.stderr.flush()
