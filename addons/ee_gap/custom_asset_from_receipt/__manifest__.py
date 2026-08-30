# -*- coding: utf-8 -*-
{
    "name": "Custom Asset From Receipt",
    "summary": "Convert received goods into Fixed Assets from the receipt — one asset per serial number, or one pooled asset for the received quantity",
    "description": """
Bridges ``custom_accounting_asset`` and ``custom_rental`` so a single
goods receipt (e.g. 200 drones with 200 serial numbers) can spawn one
``custom.fixed.asset`` per SN — and optionally one ``rental.asset`` per
SN — through a wizard with per-row select checkboxes and a Select All
shortcut. Idempotent: previously-converted serial numbers are detected
and disabled in the wizard.

Products can also be capitalised as a **pooled** asset instead: flag the product
with *Create Fixed Asset on Receipt* and set *Asset Tracking* to the pooled mode,
and the whole received quantity (e.g. 5 waste bins on one non-trade PO line)
becomes a single asset number carrying quantity 5 and the total value. Broken
units are taken out later with *Retire Units* on the asset. Untracked products
are fine in this mode — no serial numbers required.
""",
    "author": "Custom Platform",
    "category": "Inventory/Inventory",
    "version": "19.0.0.2.0",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "purchase",
        "account",
        "custom_accounting_asset",
        "custom_rental",
    ],
    "capability_tags": ["fixed-assets", "rental", "inventory"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_template_views.xml",
        "views/stock_picking_views.xml",
        "views/purchase_order_views.xml",
        "wizard/asset_conversion_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
