# -*- coding: utf-8 -*-
{
    "name": "Custom Rental",
    "summary": "Product rental: pricing tiers, pickup/return scheduling, late fees",
    "description": """
Custom Rental is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/sales/rental.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Rental product configuration (rentable flag, availability windows)
- Period-based pricing (hour / day / week / month tiers)
- Pickup and return scheduling with calendar
- Late-fee automation on overdue returns
- Integration with delivery (stock pickings for handover)
""",
    "author": "Custom Platform",
    "category": "Sales/Rental",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "sale_management", "stock"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
