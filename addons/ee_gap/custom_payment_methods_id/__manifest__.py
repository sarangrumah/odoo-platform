# -*- coding: utf-8 -*-
{
    "name": "Indonesian Payment Methods (Giro / Bank Transfer)",
    "version": "19.0.1.0.0",
    "summary": "Adds GIRO and BANK TRANSFER as selectable payment methods on bank journals.",
    "description": """
Indonesian Payment Methods
==========================
Out of the box a bank journal in Odoo offers only *Manual Payment* and, with
``account_check_printing``, *Checks*. Indonesian finance teams settle vendor
bills by **giro** (post-dated bank draft) and **bank transfer**, and expect to
say so on the payment itself — the method ends up on the payment voucher, on
the bill-payment report and in the bank-reconciliation search.

This module registers both as manual-style methods (``mode='multi'``,
``type=('bank',)``), i.e. they behave exactly like Manual Payment and post to
whatever outstanding account the journal's method line carries. No electronic
file is generated; the method is a label plus a reporting dimension.

Tenant-neutral extraction of the same four methods in
``custom_levis_localization`` (Finance-AP feedback #7).

WHY A HOOK AND NOT A DATA FILE
------------------------------
``account.payment.method`` is unique on ``(code, payment_type)``. Levi's
databases already carry these four records, owned by
``custom_levis_localization``. A ``<record>`` in this module's data file would
hit that unique constraint the moment anyone installs it on a Levi's DB, so the
records are created from ``post_init_hook`` which simply skips whatever already
exists. Both modules can then coexist.

AFTER INSTALLING
----------------
The methods are available but not yet attached to any journal. Add them per
journal under Accounting -> Configuration -> Journals -> Incoming/Outgoing
Payments, or run ``scripts/tenants/arkaaim/setup_payment_journals.py``, which
adds the lines and points them at the journal's bank account.
""",
    "author": "Platform",
    "website": "https://example.com/custom-platform",
    "category": "Accounting/Accounting",
    "depends": ["account"],
    "data": [],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
