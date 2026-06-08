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
        # Obsolete: Odoo 19's stock.stock_report_delivery_has_serial_move_line
        # already reads move_line.move_id.packaging_uom_id, so this patch's
        # xpath no longer matches and breaks any fresh DB install. Retired
        # (installable/auto_install = False); re-enable only if upstream
        # regresses. See views/report_deliveryslip_inherit.xml.
        # "views/report_deliveryslip_inherit.xml",
    ],
    "installable": False,
    "application": False,
    "auto_install": False,
}
