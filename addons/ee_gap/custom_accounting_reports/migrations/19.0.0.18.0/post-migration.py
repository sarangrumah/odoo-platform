# -*- coding: utf-8 -*-
"""Re-archive the XStore menu, and pin it so the next -u cannot undo that.

The 19.0.0.16.0 migration archived ``Sales Detail (XStore X24DN)`` on
tenants without POS, but the menuitem was a plain (updatable) record: the
very next ``-u custom_accounting_reports`` reloaded ``menu_views.xml`` and
brought it back, which is exactly what happened on prd_arkaaim and
trn_arkaaim when they went to 19.0.0.17.0. The menuitem now carries
``noupdate="1"``; this pass repairs the databases that already drifted.

Runs after the data load, so it wins over whatever the XML just wrote.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.custom_accounting_reports.hooks import sync_pos_only_menus


def migrate(cr, version):
    sync_pos_only_menus(api.Environment(cr, SUPERUSER_ID, {}))
