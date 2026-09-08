# -*- coding: utf-8 -*-
{
    "name": "Custom Rental — BOM Explosion",
    "summary": "Bundling drone + perangkat via BOM kit, otomatis populate BAST lines saat pickup/return rental",
    "description": """
Extends ``custom_rental`` so that a rental product carrying an ``mrp.bom``
of type ``phantom`` (kit) is exploded into its components — on the stock
pickings AND on the BAST documents.

Use case: PT rental sewa drone bundle. The deal is priced and ordered as
ONE line ("Sewa Drone Show 1500 Unit", qty 1), but behind it sit 1500
serial-tracked drones plus batteries and controllers that physically leave
the shelf and must come back.

* ``_prepare_move_vals_list`` emits one stock.move per exploded component,
  so a qty-1 bundle really moves every unit it is made of. ``loan_qty``
  counts spare BUNDLES and is exploded the same way.
* ``_bast_lines_vals`` lists those components on the handover document.

Works in bulk mode (``product_id``) and serial mode (``asset_id``, where an
asset-level explicit ``bom_id`` still wins). Falls back to the plain
single-product behaviour when the rented product has no BOM, so non-bundle
rentals are untouched.
""",
    "author": "Custom Platform",
    "category": "Sales/Rental",
    "version": "19.0.0.2.0",
    "license": "LGPL-3",
    "depends": [
        "custom_rental",
        "custom_bast",
        "mrp",
    ],
    "capability_tags": ["rental", "bom", "audit-trail"],
    "data": [
        "views/rental_asset_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
