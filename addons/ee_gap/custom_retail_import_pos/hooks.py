# -*- coding: utf-8 -*-
"""Re-show the POS-only report menus once this bridge is installed.

``custom_accounting_reports`` archives ``Sales Detail (XStore X24DN)`` on
tenants where ``pos.order.line`` does not exist. When POS and the retail
importer arrive afterwards, nothing would upgrade that module again, so
the menu would stay hidden. This module cannot simply depend on
``custom_accounting_reports`` — it is ``auto_install``, and an extra
dependency would stop it auto-installing on tenants that have the
importer and POS but no reports module — hence the soft lookup.
"""


def post_init_hook(env):
    if "custom.report.engine" not in env:
        return
    menu = env.ref(
        "custom_accounting_reports.menu_custom_reports_sales_detail",
        raise_if_not_found=False,
    )
    if menu and not menu.active:
        menu.active = True
