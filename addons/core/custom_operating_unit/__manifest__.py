# -*- coding: utf-8 -*-
{
    "name": "Custom Operating Unit",
    "summary": "Operating Unit master data with a Head Office / Area / Store hierarchy, "
    "and the user-to-unit assignment that data isolation is built on.",
    "description": """
Custom Operating Unit — Unit Operasional
========================================

Odoo has companies and warehouses, but nothing in between: no branch, no area,
no store dimension that documents, users and reports can all agree on. On this
platform an "Operating Unit" existed only as an ``account.analytic.account`` in
a plan named *Operating Unit*, created per store by a tenant localization. That
works as a reporting dimension, but it carries no hierarchy, no link to the
warehouse or the POS, and — crucially — cannot be used for access control.

This module supplies the master record:

* ``operating.unit`` — code, name, type (Head Office / Area / Store), a real
  parent-child hierarchy, and **links** to whatever the tenant already has: the
  analytic account here, the warehouse / journals / POS configs through the
  bridge modules. Nothing is renamed and nothing is replaced. A store's
  ``stock.warehouse.code`` in particular is a join key for the retail import and
  is never touched.
* ``res.users.operating_unit_ids`` — the assignment, and the derived
  ``ou_allowed_ids`` the record rules read. Assigning an *area* unit implicitly
  grants every store beneath it, so an area manager is one assignment, not
  twelve.
* ``operating.unit.mixin`` — the ``operating_unit_id`` field plus the write
  guard that stops a scoped user booking onto somebody else's unit, including
  by moving a document afterwards.

**Installing this module restricts nobody.** A user with no unit assigned sees
everything; scoping starts only when units are assigned. The isolation itself
(the stored columns and the record rules on accounting, stock, purchase, sales
and POS documents) lives in the bridge modules, which auto-install per app.

Part of the Custom Platform — multi-tenant Odoo 19 for Indonesian SMB.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Security",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "analytic"],
    "capability_tags": [
        "operating-unit",
        "multi-branch",
        "data-isolation",
        "organisation-hierarchy",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "views/operating_unit_views.xml",
        "views/res_users_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
