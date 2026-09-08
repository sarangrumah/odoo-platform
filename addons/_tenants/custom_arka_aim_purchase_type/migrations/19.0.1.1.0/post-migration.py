# -*- coding: utf-8 -*-
"""Seed the Trade stream's GR/IR account on an existing installation.

``post_init_hook`` runs on INSTALL only (``odoo/modules/loading.py``), so a
tenant that already has the module keeps whatever mapping it was installed
with -- and every ARKA-AIM database was installed when Trade deliberately had
no GR/IR account. 19.0.1.1.0 gives Trade its own clearing account
(``2103109199``), which the goods-receipt journal needs in order to post at all.

``seed_account_map`` only fills a field that is still empty, so a wiring an
accountant has corrected by hand survives untouched. Idempotent.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.custom_arka_aim_purchase_type.hooks import seed_account_map


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_account_map(env)
