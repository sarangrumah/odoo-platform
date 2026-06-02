# -*- coding: utf-8 -*-
{
    "name": "Custom Stock Delivery Report Fix",
    "summary": "Patch upstream delivery-slip template that references stock.move.line.packaging_uom_id (which only exists on stock.move)",
    "author": "Custom Platform",
    "category": "Inventory/Reports",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [
        "views/report_deliveryslip_inherit.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
