# -*- coding: utf-8 -*-
{
    "name": "ARKA Show Date",
    "version": "19.0.1.2.0",
    "summary": "Show-date field on quotation/SO/customer invoice with payment "
    "terms anchored to the show date. PT ARKA only.",
    "description": """
ARKA Show Date
==============
Adds a 'Show Date' (``x_custom_show_date``) Date field captured on the
Quotation (``sale.order``), carried to the Sales Order, and propagated to the
Customer Invoice (``account.move``, ``out_invoice``). For companies that opt in
via ``res.company.x_custom_show_date_enabled``, the customer-invoice
payment-term due dates (``date_maturity``) are anchored to the Show Date instead
of the invoice date (i.e. "X days after show date").

TENANT-SCOPED: built for the PT ARKA company on the aimarka tenant DBs
(uat_aimarka, rnd_aimarka, prd_EAL_ArkaAim). The behaviour is gated by the
``res.company`` boolean flag, NOT by company name and NOT merely by install, so
the module is safe to install on a multi-company DB (e.g. AIM + ARKA): only the
company with the flag ticked (PT ARKA) is affected. Until the flag is ticked the
module is inert.
""",
    "author": "Platform",
    "website": "https://example.com/custom-platform",
    "category": "Tenants/ARKA-AIM",
    "depends": ["sale_management", "account", "custom_core", "custom_accounting_reports"],
    "data": [
        "views/res_company_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/profit_loss_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
