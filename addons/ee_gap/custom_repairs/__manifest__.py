# -*- coding: utf-8 -*-
{
    "name": "Custom Repairs",
    "summary": "Repair extensions: warranty tracking, WhatsApp status updates, turnaround SLA",
    "description": """
Custom Repairs extends the CE `repair` module for Indonesian SMB tenants with:

- Warranty tracking (in/out/extended) and warranty-until date.
- Promised vs actual completion-date tracking.
- Turnaround SLA computation (on_track / at_risk / breached / done).
- Customer status updates via custom_whatsapp (stub queue creation).
- Customer complaint capture in Bahasa Indonesia.

Convention notes:
- Uses <list>, no <tree>; flat search filters (no <group string="Group By">).
- Booleans in XML use eval="True"/"False".
- Inherits mail.thread for tracking=True fields.
""",
    "author": "Custom Platform",
    "category": "Manufacturing/Repair",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": [
        "custom_core",
        "custom_pdp_audit",
        "custom_quality_full",
        "repair",
        "custom_whatsapp",
        "mail",
    ],
    "capability_tags": ["helpdesk", "whatsapp", "quality", "manufacturing"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/repair_order_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
