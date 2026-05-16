# -*- coding: utf-8 -*-
{
    "name": "Custom HR Referral",
    "summary": "Employee referral program with points, leaderboard and rewards",
    "description": """
Custom HR Referral is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/human_resources/referrals.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Referral campaigns linked to recruitment jobs
- Point reward accounting per referral stage (applied / hired / retained)
- Employee leaderboard with gamification
- Share-to-social plumbing (LinkedIn / WhatsApp / email)
- Redemption catalog with reward fulfillment workflow
""",
    "author": "Custom Platform",
    "category": "Human Resources",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "hr", "hr_recruitment"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
