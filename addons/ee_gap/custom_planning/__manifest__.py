# -*- coding: utf-8 -*-
{
    "name": "Custom Planning",
    "summary": "Shift planning with role templates, rotations and capacity views",
    "description": """
Custom Planning is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/human_resources/planning.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Shift management (create, assign, swap, publish)
- Role templates with required skill / certification matching
- Auto-fill rotations (weekly / fortnightly recurrences)
- Employee preference handling (preferred / unavailable slots)
- Capacity vs demand view (under / over staffing alerts)
""",
    "author": "Custom Platform",
    "category": "Human Resources/Planning",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "hr"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
