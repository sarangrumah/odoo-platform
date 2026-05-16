# -*- coding: utf-8 -*-
{
    "name": "Custom Marketing Automation",
    "summary": "Drip campaigns, lead scoring, A/B testing and triggered workflows",
    "description": """
Custom Marketing Automation is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/marketing/marketing_automation.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Drip email campaigns with delay / condition activities
- Lead scoring rules based on behavior and demographics
- A/B testing for email subject and content variants
- Triggered workflows on record events (server actions)
- Segmentation builder with saved audience filters
""",
    "author": "Custom Platform",
    "category": "Marketing",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "mass_mailing"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
