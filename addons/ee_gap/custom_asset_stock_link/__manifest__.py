# -*- coding: utf-8 -*-
{
    "name": "Custom Asset Stock Link",
    "summary": "Materialise existing fixed assets into inventory as serial numbers "
    "so each unit can be located, moved and rented -- without any stock valuation GL impact",
    "description": """
Custom Asset Stock Link
=======================

``custom_asset_from_receipt`` walks one direction: a goods receipt becomes fixed
assets. This module walks the other one -- a fixed asset that already exists
(loaded from an opening-balance sheet, say) becomes a serial number sitting in a
warehouse, so the physical unit can be tracked and rented.

What it adds
------------

* ``custom.fixed.asset.location.stock_location_id`` -- maps the accounting-side
  asset location tree onto real ``stock.location`` records.
* ``custom.fixed.asset.stock_location_id`` / ``on_hand_qty`` -- where the unit
  physically is right now, read from the ``stock.quant`` of its serial. Computed,
  searchable, and **never** written back to ``location_id``: the accounting
  location and the asset opname report keep working untouched.
* ``custom.fixed.asset.rental_state`` -- available / on rent / maintenance, read
  from the linked ``rental.asset``.
* ``custom.asset.stock.materialize.wizard`` -- bulk-creates, per selected asset,
  a serial-tracked product (one per asset name), a ``stock.lot`` named after the
  asset code, an inventory adjustment putting 1 unit in the target location, and
  optionally a ``rental.asset``. Idempotent: assets that already carry a
  ``lot_id`` are skipped.

Zero valuation impact
---------------------

Assets materialised this way are already capitalised in the GL. Putting them
into stock must therefore post **nothing**. In Odoo 19 stock only reaches the
ledger through ``stock_account.stock_move._should_create_account_move()``, which
needs a storable valued product *and* a location with a valuation account *and*
``product.valuation == 'real_time'``. The wizard files its products in a
dedicated *Fixed Assets (Non-Valuated)* category pinned to ``periodic``
valuation with a zero cost -- zero cost also keeps the periodic year-end
valuation entry at nil -- and refuses to run if any of the company, category,
product or destination location would value the stock.
""",
    "author": "Custom Platform",
    "category": "Inventory/Inventory",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": [
        "stock",
        # for product.valuation / lot_valuated / stock.location.valuation_account_id --
        # the fields the zero-GL guard reads
        "stock_account",
        "custom_accounting_asset",
        "custom_asset_from_receipt",
        "custom_rental",
    ],
    "capability_tags": ["fixed-assets", "inventory", "rental", "serial-tracking"],
    "data": [
        "security/ir.model.access.csv",
        "data/product_category_data.xml",
        "data/ir_cron_data.xml",
        "views/fixed_asset_location_views.xml",
        "views/fixed_asset_views.xml",
        "views/rental_asset_views.xml",
        "views/stock_lot_views.xml",
        "wizard/asset_stock_materialize_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
