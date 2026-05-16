# -*- coding: utf-8 -*-
{
    "name": "Custom MRP PLM",
    "summary": "Product lifecycle management: ECO workflow and BoM versioning",
    "description": """
Custom MRP PLM is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/plm.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- ECO (Engineering Change Order) workflow with stages
- BoM versioning with archival of previous revisions
- Document attachment per BoM version
- Approval workflow (multi-step, role-based)
- Diff viewer between BoM versions (components, quantities, routings)
""",
    "author": "Custom Platform",
    "category": "Manufacturing/PLM",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "mrp"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
