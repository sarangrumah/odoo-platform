# -*- coding: utf-8 -*-
{
    "name": "Custom Operating Unit — Levi's Migration",
    "summary": "Turns the existing Levi's analytic Operating Units into operating.unit "
    "records — additively, without renaming a single warehouse, analytic or journal.",
    "description": """
Custom Operating Unit — Levi's Migration
========================================

Levi's already runs an Operating-Unit dimension: one
``account.analytic.account`` per store in a plan named *Operating Unit*, wired
to the warehouse and to a per-store purchase journal by
``custom_levis_localization``. This module lifts that into the platform's
``operating.unit`` master **without touching any of it**.

Strictly additive:

* ``stock.warehouse.code`` — the key the retail import joins on, which also
  drives the location names and picking sequences — is *copied* into
  ``operating.unit.code``, never modified.
* The analytic account, the purchase journal and the ``pos.config`` keep the
  names ``41_normalize_ou.py`` gave them.
* An archived store gets an archived unit, fully wired, so reactivating it
  stays the one-liner it is today.

Afterwards the Operating Unit is the master and the analytic account is one of
its links — but everything that reads ``l10n_ou_analytic_id`` keeps working, and
picking a unit on a journal item now fills that field so the ledger never stops
carrying the dimension the reports are built on.

The Head Office → store tree is two levels; adding an *area* layer afterwards is
pure data work (create the unit, re-parent the stores) with no code change.

Part of the Custom Platform — multi-tenant Odoo 19 for Indonesian SMB.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Localization",
    "version": "19.0.0.2.0",
    "license": "LGPL-3",
    "depends": ["custom_operating_unit_docs", "custom_levis_localization"],
    "capability_tags": ["operating-unit", "levis", "migration"],
    "data": [
        "views/operating_unit_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
    "post_init_hook": "post_init_hook",
}
