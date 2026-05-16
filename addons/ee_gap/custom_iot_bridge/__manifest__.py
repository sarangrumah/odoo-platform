# -*- coding: utf-8 -*-
{
    "name": "Custom IoT Bridge",
    "summary": "Abstract IoT device registry with MQTT routing and certificate auth",
    "description": """
Custom IoT Bridge is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/general/iot.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Abstract IoT device registry (model-agnostic device profiles)
- MQTT bridge configuration (broker URL, topics, QoS)
- Certificate-based mutual TLS authentication
- Message routing from topics to Odoo server actions
- Status dashboard (last seen, error rate, throughput)
""",
    "author": "Custom Platform",
    "category": "Productivity/IoT",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
