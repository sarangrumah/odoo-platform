# -*- coding: utf-8 -*-
{
    "name": "Custom Operating Unit — Point of Sale",
    "summary": "Scopes points of sale, sessions and orders to their Operating Unit, and "
    "stamps the unit on every line of the session closing entry.",
    "description": """
Custom Operating Unit — Point of Sale
=====================================

A point of sale belongs to exactly one store, so the whole chain follows from
``pos.config.warehouse_id``: the config's Operating Unit, the sessions opened on
it, the orders rung up in them, and every line of the closing entry.

* ``pos.config`` / ``pos.session`` / ``pos.order`` carry ``operating_unit_id``,
  and record rules scope all three — a cashier stops seeing other stores'
  sessions and orders.
* The **closing entry is stamped line by line**. Core builds that move on the POS
  journal, which is normally company-wide and has no unit of its own, so there is
  nothing for the lines to inherit; each of core's vals hooks (sale, tax,
  receivable, invoice receivable, stock expense) is wrapped instead. Without it
  the entire POS revenue stream would sit outside per-unit reporting — the same
  reason ``custom_levis_localization`` stamps the analytic leg on those very
  lines. On a Levi's database both land, from the two modules, on the same line.

Auto-installs wherever Point of Sale and the Operating Unit documents module are
both present.

Part of the Custom Platform — multi-tenant Odoo 19 for Indonesian SMB.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Point of Sale",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_operating_unit_docs", "point_of_sale"],
    "capability_tags": ["operating-unit", "data-isolation", "point-of-sale"],
    "data": [
        "security/record_rules.xml",
        "views/pos_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
    "pre_init_hook": "pre_init_hook",
}
