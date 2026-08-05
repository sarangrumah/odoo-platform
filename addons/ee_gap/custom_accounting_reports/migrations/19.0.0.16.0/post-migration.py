# -*- coding: utf-8 -*-
"""Hide ``Sales Detail (XStore X24DN)`` on tenants without POS.

prd_arkaaim carried the menu even though ``point_of_sale`` was never
installed there, so the report could only ever render empty. See
``hooks.sync_pos_only_menus``.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.custom_accounting_reports.hooks import sync_pos_only_menus


def migrate(cr, version):
    sync_pos_only_menus(api.Environment(cr, SUPERUSER_ID, {}))
