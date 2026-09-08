# -*- coding: utf-8 -*-
{
    "name": "Payment Exchange Rate",
    "version": "19.0.1.1.0",
    "summary": "Type the dealt exchange rate on a payment, the way Odoo already lets you type it on a bill.",
    "description": """
Payment Exchange Rate
=====================
Odoo 19 lets a user type the rate on an invoice or bill -- ``invoice_currency_
rate`` sits in the document header with a button to reset it to the rate of the
day. A payment has no such field: its journal entry is always valued at whatever
``res.currency.rate`` holds for the payment date, and if no rate row exists for
that date the conversion silently falls back to the nearest one.

Treasury works the other way round. The bank advice carries the rate that was
actually dealt, and that is the number that has to hit the books.

What it adds
------------
An **Exchange Rate** field, quoted in the direction a user reads it::

    Amount          USD 10,000.00
    Exchange Rate      16,200.00   IDR per 1 USD

on both the payment form and the *Register Payment* wizard, defaulting to the
rate of the payment date so nothing changes unless somebody edits it.

It covers the two situations that matter:

* **Payment in a foreign currency** -- the rate values the payment's journal
  entry (liquidity and counterpart lines).
* **Company-currency payment settling a foreign document** (an IDR bank account
  paying a USD bill) -- the rate drives the amount the wizard proposes, so the
  user types the rate off the advice instead of back-computing the rupiah
  figure by hand.

How it works
------------
Every amount Odoo derives from a currency goes through
``res.currency._get_conversion_rate``. That method is overridden to honour a
``manual_fx_rate`` context payload, and the payment/wizard set it around the
calls that build the proposed amount and the journal entry. No balance is
recomputed by hand, so every native branch (write-offs, withholding, early
payment discount, grouped payments) keeps working.

Nothing is re-valued behind the user's back: the gap between the rate on the
bill and the rate on the payment still lands on the exchange-difference account
through the ordinary reconciliation, i.e. as a realised FX gain or loss.

Tenant-neutral: inert on any payment whose currency equals the company currency.
""",
    "author": "Platform",
    "website": "https://example.com/custom-platform",
    "category": "Accounting/Accounting",
    "depends": ["account"],
    "data": [
        "views/account_payment_views.xml",
        "views/account_payment_register_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
