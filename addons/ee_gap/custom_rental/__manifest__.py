# -*- coding: utf-8 -*-
{
    "name": "Custom Rental",
    "summary": "Asset/equipment rental lifecycle: pickup → return with availability check",
    "description": """
Track rental of assets. Each rental.order has pickup_dt and return_dt;
overlap rejected on the same asset. Daily fee + late penalty computed.
""",
    "author": "Custom Platform",
    "category": "Sales/Rental",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "custom_pdp_audit", "mail", "product", "account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/rental_asset_views.xml",
        "views/rental_order_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
