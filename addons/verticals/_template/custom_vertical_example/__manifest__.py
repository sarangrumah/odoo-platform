# -*- coding: utf-8 -*-
{
    "name": "Custom Vertical (Example)",
    "summary": "Reference vertical template used as a starting point",
    "description": """
Custom Vertical (Example)
======================

Reference implementation that demonstrates how to:

* Inherit core models with an `x_custom_vertical_example_` field prefix
* Attach a top-level menu under `custom_core.menu_custom_root`
* Declare a security group under the Custom Platform category
* Ship form-view extensions using Odoo 19 syntax (`<list>` not `<tree>`)

Copy this folder under `addons/verticals/<slug>` and follow
`addons/verticals/_template/README.md`.
""",
    "author": "Custom Platform Team",
    "website": "https://custom.local",
    "category": "Vertical/Example",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": [
        "custom_core",
    ],
    "data": [
        "security/example_security.xml",
        "security/ir.model.access.csv",
        "views/menu_views.xml",
        "views/res_partner_views.xml",
    ],
    "demo": [],
    "application": True,
    "installable": True,
    "auto_install": False,
}
