# -*- coding: utf-8 -*-
{
    "name": "Levi's Bank Reconciliation (POS Tender)",
    "version": "19.0.1.0.0",
    "summary": "Match bank settlements against POS tender receivables per store, "
    "net of MDR, with a cash suggestion capped at the statement amount.",
    "description": """
Levi's Bank Reconciliation — POS Tender
=======================================

The monthly ``levis.pos.clearing`` run settles a whole period in one go. This
module teaches the *line by line* bank matching wizard the same four facts, for
the days Finance wants to look a settlement in the eye:

1. **The Operating Unit is on the tender line.** Every candidate row shows the
   store its POS receivable belongs to, so a settlement is never matched against
   another outlet's sales by accident.

2. **A card settlement is matched at its gross.** The bank pays gross minus MDR,
   while the tender receivable is carried at gross — matching on the amount that
   landed would never find anything. The wizard reads gross and the fee out of
   the narrative, targets the gross, and offers the fee ready-booked to the MDR
   expense account with the store's Operating Unit on it.

3. **Cash deposits get a suggestion, capped at the deposit.** One transfer covers
   several days of cash sales, so the wizard fills the selection largest-first up
   to (never over) the statement amount and leaves the rest open.

4. **The statement line says which store it came from.** MID / TID / keyword
   resolution is stored on the line itself, so the reconciliation list can be
   filtered and grouped per Operating Unit.

Nothing here changes how a reconciliation is written: it is still
``custom_account_reconcile``'s ``_reconcile_with_amls`` on top of core
``reconcile()``. This module only decides what is *offered*.

TENANT-SCOPED, and installed by hand. ``auto_install`` is deliberately off: the
parents live on every Levi's database, so auto-installing would change the
reconciliation screen on four production databases the moment the module list is
refreshed. Install it per database, when that database's Finance team is ready.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Tenants/Levis",
    "license": "LGPL-3",
    "depends": [
        "custom_levis_localization",
        "custom_account_reconcile",
    ],
    "data": [
        "views/bank_reconcile_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
