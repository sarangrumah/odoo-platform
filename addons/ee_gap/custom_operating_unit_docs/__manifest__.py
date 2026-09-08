# -*- coding: utf-8 -*-
{
    "name": "Custom Operating Unit — Documents",
    "summary": "Stamps the Operating Unit on accounting, stock, purchase and sales "
    "documents and isolates them per unit: a store user sees and books only their own.",
    "description": """
Custom Operating Unit — Documents
=================================

Turns the Operating Unit from master data into actual data isolation.

* An indexed, stored ``operating_unit_id`` on ``account.move`` /
  ``account.move.line`` / ``account.payment`` / ``account.bank.statement.line``,
  ``stock.picking`` / ``stock.move`` / ``stock.quant``, ``purchase.order`` and
  ``sale.order``, derived from the journal, the warehouse or (for a journal
  item) the analytic distribution — and never overwriting a value someone set
  by hand.
* Record rules scoping every one of those models to the user's units, written
  so that a user with no unit assigned is unrestricted. **Installing this
  restricts nobody**; scoping starts when units are assigned.
* A server-side constraint (from ``operating.unit.mixin``) that stops a scoped
  user booking onto another unit — including by moving a document afterwards,
  which a create-time check would miss. ``env.su`` remains free, so crons, the
  retail-import executor and queue_job workers are unaffected.

The columns are created by a ``pre_init_hook`` rather than by the ORM: a stored
computed field whose column is missing makes Odoo flag the whole table for
recompute in a single transaction, which on a large ``account_move_line`` is an
outage. History is filled out of band by
``scripts/ops/backfill_operating_unit.py``.

Auto-installs wherever Accounting and Inventory are present.

Part of the Custom Platform — multi-tenant Odoo 19 for Indonesian SMB.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Security",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    # sale_stock, not sale: sale.order.warehouse_id (the unit's source) comes
    # from there. It auto-installs wherever Sales and Inventory coexist.
    "depends": ["custom_operating_unit", "account", "stock", "purchase", "sale_stock"],
    "capability_tags": [
        "operating-unit",
        "data-isolation",
        "record-rules",
        "multi-branch",
    ],
    "data": [
        "security/record_rules.xml",
        "views/operating_unit_views.xml",
        "views/document_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
    "pre_init_hook": "pre_init_hook",
}
