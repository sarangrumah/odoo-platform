# -*- coding: utf-8 -*-
{
    "name": "Custom Service Receipt",
    "summary": "Receive purchased services on a goods receipt, so billing is gated by an accepted quantity",
    "description": """
Goods receipt for service products.

Core Odoo never puts a service on a receipt: ``purchase_stock`` filters every
picking path on ``product_id.type == 'consu'``, so a purchased service can only
ever have its received quantity typed by hand on the purchase order line -- and
where the product bills on ordered quantities, not even that. A vendor bill for
a service is therefore backed by no acceptance document at all.

This module lets a *service* product be flagged to travel through the receipt
like a good, while staying a service everywhere else:

- ``product.template.receive_on_gr`` -- opt-in per product. Setting it also
  moves the product to *On received quantities* control, because a receipt that
  does not gate the bill is decoration.
- Flagged service lines are pushed onto the purchase order's receipt, are
  auto-available (a service is never reserved), and their validated quantity
  feeds ``qty_received`` through ``qty_received_method = 'stock_moves'``.
- An order made only of flagged services still gets its receipt, which core
  would have skipped.

No inventory and no accounting side effects: ``stock_account`` books a valuation
layer only for storable, real-time-valued products, so a service move creates no
quant, no SVL and no journal entry. The gain is control and traceability --
three-way match, receipt-date reporting, and an auditable acceptance per order.

Inert until a product is flagged, so it is safe to install anywhere.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Inventory/Purchase",
    "version": "19.0.0.2.0",
    "license": "LGPL-3",
    "depends": ["purchase_stock"],
    "capability_tags": ["purchase", "inventory", "three-way-match"],
    "data": [
        "views/product_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
