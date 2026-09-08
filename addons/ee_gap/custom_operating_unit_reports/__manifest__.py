# -*- coding: utf-8 -*-
{
    "name": "Custom Operating Unit — Reports",
    "summary": "Makes the custom accounting reports respect the reader's Operating Units. "
    "Without it the list views are filtered but the Trial Balance is not.",
    "description": """
Custom Operating Unit — Reports
===============================

``custom_accounting_reports`` builds its own SQL over ``account_move_line`` for
speed — and **``ir.rule`` does not apply to raw SQL**. So on a tenant with
Operating-Unit isolation, a store-scoped user would see their own store in every
list view and *every* store in a Trial Balance, a General Ledger or a P&L. That
is the quietest kind of data leak: nothing looks broken.

This bridge implements the engine's ``_ou_sql_filter`` hook, which the report
queries splice into their WHERE clause, and restricts the branch columns of the
P&L-by-branch to the units the reader may see. It also exposes the unit on the
GL Analysis cube so it can be pivoted and filtered like any other dimension.

Auto-installs wherever the reports and the Operating Unit documents module are
both present. On a tenant without Operating Units nothing changes: the hook
returns a no-op for any reader who is not scoped.

**Install this before assigning Operating Units to anybody on a production
database**, or the reports keep leaking until it lands.

Part of the Custom Platform — multi-tenant Odoo 19 for Indonesian SMB.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Accounting",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_operating_unit_docs", "custom_accounting_reports"],
    "capability_tags": ["operating-unit", "data-isolation", "accounting-reports"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": True,
}
