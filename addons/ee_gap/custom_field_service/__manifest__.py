# -*- coding: utf-8 -*-
{
    "name": "Custom Field Service",
    "summary": "Technician dispatch, on-site tasks, materials, signature and routing",
    "description": """
Custom Field Service is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/services/field_service.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Technician dispatch board (calendar / map view)
- On-site task checklists per service type
- Material consumption logging tied to stock moves
- Signature capture on completion
- Time tracking with billable / non-billable distinction
- Route optimization between scheduled stops
""",
    "author": "Custom Platform",
    "category": "Services/Field Service",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "project", "hr", "stock"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
