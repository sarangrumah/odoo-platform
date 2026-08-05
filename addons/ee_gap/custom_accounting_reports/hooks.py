# -*- coding: utf-8 -*-
"""Keep tenant-specific report menus out of tenants that cannot use them.

``Sales Detail (XStore X24DN)`` reads ``pos.order.line`` and the
``ri_src_*`` columns that ``custom_retail_import_pos`` adds. This module
ships to every tenant, so on a tenant with no POS — ARKA-AIM runs the
importer without ``point_of_sale`` on purpose — the menu was visible and
led to a report that can only ever come back empty.

The menu cannot be gated declaratively: a ``groups="point_of_sale...."``
on the menuitem would need a dependency on ``point_of_sale``, which is
exactly the dependency the split between ``custom_retail_import`` and
``custom_retail_import_pos`` exists to avoid. So the visibility is
resolved at install/upgrade time instead, and ``custom_retail_import_pos``
re-runs the same sync from its own install hook for the case where POS
arrives after this module.
"""

POS_ONLY_MENUS = ("menu_custom_reports_sales_detail",)


def sync_pos_only_menus(env):
    """Archive the POS-only report menus unless this tenant has POS. Idempotent."""
    has_pos = "pos.order.line" in env
    for xmlid in POS_ONLY_MENUS:
        menu = env.ref("custom_accounting_reports.%s" % xmlid, raise_if_not_found=False)
        if menu and menu.active != has_pos:
            menu.active = has_pos


def post_init_hook(env):
    sync_pos_only_menus(env)
