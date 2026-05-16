# -*- coding: utf-8 -*-
{
    "name": "Custom PDP Masking",
    "summary": "PII masking service & ORM read hook (UU 27/2022)",
    "description": "Strategy-based masking applied on read for PDP-classified fields.",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Compliance/PDP",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "custom_pdp_core", "custom_pdp_audit"],
    "data": [
        "security/pdp_security.xml",
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "wizards/pdp_unmask_wizard_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
