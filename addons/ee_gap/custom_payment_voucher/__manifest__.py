# -*- coding: utf-8 -*-
{
    "name": "Payment Voucher / Payment Receipt",
    "version": "19.0.1.0.0",
    "summary": "Printable payment voucher and receipt on account.payment, with terbilang.",
    "description": """
Payment Voucher / Payment Receipt
=================================
Two PDF documents on ``account.payment``, reachable from the Print menu:

* **Payment Voucher** — vendor / outbound payments
* **Payment Receipt** — customer / inbound payments

Both render the payment's own journal entry as a COA / DEBIT / CREDIT table,
one row per journal item, showing the reconciled AP/AR document and the vendor
invoice reference behind each line. Below it: the amount in Indonesian words
(*terbilang*), the counterparty bank block, and a four-column signature strip.

Three informational/override fields are added to the payment form:

* **Note** and **Remark** — free text, printed on the voucher
* **Override Outstanding Account** — replaces the liquidity account coming from
  the payment method line on this one payment. This changes the POSTED GL; it
  exists for the odd payment that must clear through a different bank/clearing
  account without re-configuring the journal for everybody.

Tenant-neutral extraction of the Levi's payment voucher
(``custom_levis_localization``). The Levi's copy stays where it is — it carries
Operating-Unit stamping that only makes sense there — so the two modules are
independent and must not be installed on the same database.
""",
    "author": "Platform",
    "website": "https://example.com/custom-platform",
    "category": "Accounting/Accounting",
    "depends": ["account"],
    "data": [
        "reports/paperformat.xml",
        "reports/payment_voucher_templates.xml",
        "reports/payment_receipt_templates.xml",
        "reports/payment_report_actions.xml",
        "views/account_payment_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
