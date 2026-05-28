# -*- coding: utf-8 -*-
{
    "name": "Custom Intercompany Procurement",
    "summary": "Auto-mirror purchase.order + stock.picking antar sister company (Erajaya group pattern)",
    "description": """
Extends ``account.intercompany.rule`` from ``custom_accounting_full`` with
two new mirror toggles:

* ``mirror_purchase_order`` — when PO is confirmed in Company A against a
  partner that represents Company B, a draft sales order is created in
  Company B (and vice-versa).
* ``mirror_picking`` — when an outgoing picking is validated in the
  selling company, a matching incoming picking is created in the
  receiving company.

Useful for Erajaya-style group procurement where PT A buys drones from
PT B (sister company); previously only the GL invoice was mirrored.
""",
    "author": "Custom Platform",
    "category": "Inventory/Purchase",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": [
        "custom_core",
        "custom_pdp_audit",
        "custom_accounting_full",
        "purchase",
        "sale_management",
        "stock",
    ],
    "capability_tags": ["intercompany", "procurement", "audit-trail"],
    "data": [
        "views/account_intercompany_rule_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
