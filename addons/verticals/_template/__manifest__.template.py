# -*- coding: utf-8 -*-
#
# Manifest TEMPLATE for Custom verticals.
#
# Replace placeholders:
#   {vertical_slug}  -> lowercase underscore name, e.g. "custom_logistics"
#   {vertical_name}  -> human-readable name, e.g. "Custom Logistics"
#   {vertical_cat}   -> sub-category, e.g. "Logistics"
#
# Keep `custom_core` first in `depends`. Append EE-gap modules
# (e.g. `custom_pdp_audit`, `custom_coretax_ext`) as needed.
#
# Copy this file to `__manifest__.py` inside the new vertical folder, then
# strip the placeholder comments and rename.
{
    "name": "{vertical_name}",
    "summary": "Short one-liner about {vertical_name}",
    "description": """
{vertical_name}
===============

Longer description of business scope. List integration points with
custom_core and other verticals.
""",
    "author": "Custom Platform Team",
    "website": "https://custom.local",
    "category": "Vertical/{vertical_cat}",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    # ---------------------------------------------------------------
    # Dependencies
    # ---------------------------------------------------------------
    # `custom_core` is mandatory. Append any EE-gap modules this vertical
    # consumes, e.g. `custom_pdp_audit` for tamper-evident logs,
    # `custom_coretax_ext` for Coretax exports.
    "depends": [
        "custom_core",
        # "custom_pdp_audit",   # uncomment if vertical writes audit events
        # "custom_coretax_ext", # uncomment if vertical issues invoices
    ],
    # ---------------------------------------------------------------
    # Data files (loaded on install/update)
    # ---------------------------------------------------------------
    "data": [
        "security/{vertical_slug}_security.xml",
        "security/ir.model.access.csv",
        "views/menu_views.xml",
        "views/res_partner_views.xml",
    ],
    # ---------------------------------------------------------------
    # Demo files (loaded only when demo mode is on)
    # ---------------------------------------------------------------
    "demo": [
        # "demo/{vertical_slug}_demo.xml",
    ],
    "application": True,
    "installable": True,
    "auto_install": False,
}
