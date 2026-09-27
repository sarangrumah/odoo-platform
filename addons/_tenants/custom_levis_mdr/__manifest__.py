# -*- coding: utf-8 -*-
{
    "name": "Levi's Card MDR (per tender type)",
    "version": "19.0.1.0.0",
    "summary": "Merchant discount rate per X70D PAYMENT label, and the expected fee "
    "and net settlement for every card transaction.",
    "description": """
Levi's Card MDR — per tender type
=================================

What the bank pays a store is the gross takings minus a merchant discount rate,
and the rate depends on the acquirer *and* the card product: 0% on a BCA QRIS,
0,15% on an on-us debit, 1,2% on an off-us credit card.

The nightly X70D cannot tell those apart. It carries ``TENDER TYPE``, and one
``OFFLINE_OTHER_CREDITCARD`` bucket holds all three. The pair that identifies a
rate — acquirer and product — appears only in the ``PAYMENT`` column of the
X70D a store exports itself ("BCA - QRIS", "BRI - DEBIT OTHER"), which
``custom_retail_import`` stages as ``x70d_store``.

This module holds the two halves of that arithmetic:

1. ``levis.mdr.rate`` — the rate table, keyed on the PAYMENT label exactly as
   the file writes it, effective-dated so a renegotiated rate does not rewrite
   history.

2. ``levis.mdr.txn`` — a read-only view: every nightly X70D transaction, with
   the acquirer label attached from the store export where one has been
   received, the rate resolved as of the trading day, and the fee and the net
   settlement computed. Transactions whose store has not sent its export show
   no label and no rate rather than a guessed one.

Kept out of ``custom_levis_localization`` on purpose: this is new, self-contained
configuration, and a tenant module that installs and uninstalls on its own is
easier to roll out store by store than a new version of the module every Levi's
database already loads.

TENANT-SCOPED. ``auto_install`` is off: install it per database, once that
database's stores actually send their weekly export.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Tenants/Levis",
    "license": "LGPL-3",
    "depends": [
        "custom_retail_import",
        "custom_levis_localization",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/mdr_rates.xml",
        "views/levis_mdr_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
