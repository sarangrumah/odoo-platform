# -*- coding: utf-8 -*-
{
    "name": "Custom Sign",
    "summary": "Drag-drop PDF signature with sequencing, reminders and audit trail",
    "description": """
Custom Sign is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/productivity/sign.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Drag-and-drop signature field placement on PDF templates
- Recipient sequencing (parallel or ordered signing)
- Automated email reminders for pending signatures
- Audit trail with cryptographic hash of signed document
- Integration with custom_documents (signed file storage)
""",
    "author": "Custom Platform",
    "category": "Productivity/Sign",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "mail", "portal"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
