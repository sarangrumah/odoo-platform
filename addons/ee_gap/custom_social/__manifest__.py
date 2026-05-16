# -*- coding: utf-8 -*-
{
    "name": "Custom Social",
    "summary": "Multi-account social posting, scheduling and engagement metrics",
    "description": """
Custom Social is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/marketing/social_marketing.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Multi-account posting (Facebook / Instagram / X placeholders)
- Scheduling calendar with timezone handling
- Content library (reusable assets, captions, hashtags)
- Basic engagement metrics (likes, comments, shares, reach)
""",
    "author": "Custom Platform",
    "category": "Marketing/Social Marketing",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "mail"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
