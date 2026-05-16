# -*- coding: utf-8 -*-
{
    "name": "Custom Documents",
    "summary": "Tagged document workspaces, versioning, sharing and OCR",
    "description": """
Custom Documents is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/productivity/documents.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Tagged document workspaces with ACL
- Version control with revision history
- Sharing links with expiry and password protection
- OCR placeholder integration for indexing scanned files
- Request-info workflow (request a document from a contact)
""",
    "author": "Custom Platform",
    "category": "Productivity/Documents",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "mail", "portal"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
