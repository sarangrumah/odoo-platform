# -*- coding: utf-8 -*-
{
    "name": "Custom Quality (Full)",
    "summary": "Quality control points, SPC charts, NCR and root-cause analysis",
    "description": """
Custom Quality (Full) is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/quality.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Control points anchored on manufacturing / receipt operations
- Quality alerts with workflow stages
- SPC (Statistical Process Control) charts for measurement trends
- Non-conformance management (NCR lifecycle)
- Root-cause analysis with AI hints via custom_ai_bridge
""",
    "author": "Custom Platform",
    "category": "Manufacturing/Quality",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "mrp", "stock"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
