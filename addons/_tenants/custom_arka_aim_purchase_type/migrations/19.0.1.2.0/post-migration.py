# -*- coding: utf-8 -*-
"""Re-seed the account mapping now that the codes are chart-independent.

19.0.1.1.0 seeded the mapping from the Erajaya chart's codes only, which left
`trn_arkaaim` -- running the plain Indonesian chart -- with four empty mapping
rows and therefore no goods-receipt journal at all. 19.0.1.2.0 turns each entry
into an ordered list of candidate codes, so the seeding has to run once more to
pick up the codes that database does have.

Only empty fields are filled, so `prd_arkaaim`'s wiring passes through untouched.
Idempotent.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.custom_arka_aim_purchase_type.hooks import seed_account_map


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_account_map(env)
