# -*- coding: utf-8 -*-
{
    "name": "ARKA Show Date",
    "version": "19.0.1.3.0",
    "summary": "Show-date, event and DP fields on quotation/SO/customer invoice, "
    "with payment terms anchored to the show date. PT ARKA only.",
    "description": """
ARKA Show Date
==============
Adds a 'Show Date' (``x_custom_show_date``) Date field captured on the
Quotation (``sale.order``), carried to the Sales Order, and propagated to the
Customer Invoice (``account.move``, ``out_invoice``). For companies that opt in
via ``res.company.x_custom_show_date_enabled``, the customer-invoice
payment-term due dates (``date_maturity``) are anchored to the Show Date instead
of the invoice date (i.e. "X days after show date").

Event description block
-----------------------
The same opt-in also captures ``x_custom_event_name``,
``x_custom_event_location`` and ``x_custom_dp_note`` on the order, and appends
them (with the show date, ``dd.mm.yy``) as a second line under every product
line's description::

    Jasa Drone Show 250 unit
    Event Danone, Lokasi Taman Bhagawan Bali, 07.08.26, DP 50%

The description is a stored compute with ``readonly=False``, so the block is
rebuilt whenever the event data changes but manual edits survive in between. It
travels to the customer invoice through the standard
``_prepare_invoice_line``. Down-payment lines are left alone.

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
