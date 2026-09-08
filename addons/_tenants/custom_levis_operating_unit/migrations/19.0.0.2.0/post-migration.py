# -*- coding: utf-8 -*-
"""Link the store cash journals on databases that already have the module.

The first release linked only the purchase journal, so every POS cash entry on
an installed tenant is still without an Operating Unit. Re-running the migration
is safe — it creates nothing that exists and never overwrites a link.
"""

from odoo.addons.custom_levis_operating_unit.models.setup import migrate_levis_operating_units


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_levis_operating_units(env)
