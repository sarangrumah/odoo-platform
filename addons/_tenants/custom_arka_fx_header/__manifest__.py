# -*- coding: utf-8 -*-
{
    "name": "ARKA-AIM Foreign-Currency Invoice Header",
    "version": "19.0.1.0.0",
    "summary": "Show the foreign-currency total and the applied exchange rate in the "
    "invoice/bill header, for every accounting user.",
    "description": """
ARKA-AIM Foreign-Currency Invoice Header
========================================
On a customer invoice or vendor bill written in a currency other than the
company currency, the form header gains a summary block::

    Total  CN¥ 20,000.70        Rate  1 CNY = 2,672.29 IDR

Why this module exists
----------------------
Stock Odoo 19 does show ``invoice_currency_rate`` next to the currency in the
header, but:

* it is printed in the "1 <company currency> = N <foreign>" direction
  (``1 IDR = 0.00037421 CNY``), which is unreadable for IDR-based books - the
  number a user actually quotes is ``1 CNY = 2,672.30 IDR``;
* the document total in the foreign currency only appears at the bottom of the
  Invoice Lines tab, not in the header, so an approver has to scroll past all
  the lines to see the amount they are approving;
* the whole native block sits behind ``base.group_multi_currency``, so it
  disappears for any user whose role does not imply that group.

This module adds two non-stored computed helpers on ``account.move``:

``x_fx_is_foreign``
    True when the document currency differs from the company currency and the
    document is an invoice/bill/receipt (never on ``entry``).
``x_fx_rate_company_per_unit``
    The rate inverted into the readable direction: how many units of company
    currency one unit of the document currency is worth
    (``1 / invoice_currency_rate``).

Both are read-only display helpers - nothing about the posting, the amounts or
the rate actually used by the accounting engine is changed. The block carries no
``groups`` restriction, so it survives for users who lack
``base.group_multi_currency``.

TENANT-SCOPED: built for the arkaaim tenant DBs (prd_arkaaim, trn_arkaaim).
It is inert on any document whose currency equals the company currency, so it
is harmless anywhere, but it is deliberately kept out of the shared addon paths.
""",
    "author": "Platform",
    "website": "https://example.com/custom-platform",
    "category": "Tenants/ARKA-AIM",
    "depends": ["account"],
    "data": [
        "views/account_move_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
