# -*- coding: utf-8 -*-
{
    "name": "Custom VoIP",
    "summary": "SIP softphone (WebRTC), click-to-call, call logging and transcription",
    "description": """
Custom VoIP is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/productivity/voip.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- SIP softphone via WebRTC in the Odoo web client
- Click-to-call from contact / lead / ticket records
- Call log linking back to source record with mail.thread
- Transcription of recorded calls via custom_ai_bridge
""",
    "author": "Custom Platform",
    "category": "Productivity/Telephony",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "crm", "mail"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
