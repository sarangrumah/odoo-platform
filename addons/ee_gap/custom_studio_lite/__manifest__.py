# -*- coding: utf-8 -*-
{
    "name": "Custom Studio Lite",
    "summary": "Declarative custom-field + view-extension manager (lightweight Studio replacement)",
    "description": """
Lightweight 'Studio': admins declare custom fields + view inserts via
DB records (rather than editing source). The manager pre-creates
``ir.model.fields`` rows (prefixed ``x_studio_``) and ``ir.ui.view``
inheritances on save. Useful for vertical-specific quick tweaks
without forking a module.
""",
    "author": "Custom Platform",
    "category": "Productivity/Studio",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "custom_pdp_audit", "base"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/studio_custom_field_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
