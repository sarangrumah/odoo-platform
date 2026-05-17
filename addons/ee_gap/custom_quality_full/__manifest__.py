# -*- coding: utf-8 -*-
{
    "name": "Custom Quality (Full)",
    "summary": "Quality control points + check execution + non-conformance reports (NCR)",
    "description": """
Define quality.point per (product, operation, frequency); operators
execute quality.check inline on manufacturing/inbound flows. Failed
checks raise quality.alert (NCR) with root-cause + corrective action.
""",
    "author": "Custom Platform",
    "category": "Manufacturing/Quality",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "custom_pdp_audit", "mrp", "stock", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/quality_point_views.xml",
        "views/quality_check_views.xml",
        "views/quality_alert_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
