# -*- coding: utf-8 -*-
{
    "name": "Custom Appointments",
    "summary": "Public booking pages with availability rules and group appointments",
    "description": """
Custom Appointments is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/services/calendar/appointments.html.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Public booking pages bound to staff calendars
- Availability rules (working hours, blackouts, holidays)
- Buffer time before / after each appointment
- Group appointments with capacity caps
- Payment placeholder for paid bookings
""",
    "author": "Custom Platform",
    "category": "Services/Appointments",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "website", "calendar"],
    "data": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
