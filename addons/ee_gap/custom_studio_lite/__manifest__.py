# -*- coding: utf-8 -*-
{
    "name": "Custom Studio Lite",
    "summary": "Low-code customization: field builder, view editor, report designer",
    "description": """
Custom Studio Lite is a CE-targeted reimplementation of a subset of Odoo Studio (EE),
documented at https://www.odoo.com/documentation/19.0/applications/studio.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Low-code custom field builder UI (ir.model.fields wrapper)
- View inheritance editor with visual XPath assistance
- Custom report designer (QWeb template authoring)
- App creation wizard (model + menu + security boilerplate)
""",
    "author": "Custom Platform",
    "category": "Tools/Customization",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "web"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
