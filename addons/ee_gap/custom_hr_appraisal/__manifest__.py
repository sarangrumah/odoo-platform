# -*- coding: utf-8 -*-
{
    "name": "Custom HR Appraisal",
    "summary": "Employee appraisal cycles, 360 reviews, and goal tracking",
    "description": """
Custom HR Appraisal is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/human_resources/appraisals.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- 360 review templates (self / peer / manager / subordinate)
- Quarterly appraisal cycle scheduling with reminders
- Goal tracking with progress milestones and KPI links
- Employee self-assessment forms with structured questionnaires
- Manager review workflow with approval gating
- AI-assisted summary generation via custom_ai_bridge
""",
    "author": "Custom Platform",
    "category": "Human Resources",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "hr"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
