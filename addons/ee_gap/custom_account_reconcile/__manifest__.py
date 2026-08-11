# -*- coding: utf-8 -*-
{
    "name": "Custom Account Reconciliation",
    "summary": "Enterprise-style manual reconciliation menu and wizard for Odoo CE (EE-gap closure).",
    "description": """
Custom Account Reconciliation
=============================

Closes the EE-gap on Odoo CE ``account_accountant`` manual
reconciliation:

* **Accounting → Accounting → Reconciliation → Reconcile** — overview of
  every reconcilable account that still carries open (unreconciled)
  journal items, with counts and residual balance. Click through to the
  open items of one account.
* **Reconcile** action on Journal Items (list-view action menu) — select
  matching debit/credit lines and reconcile them in one click, with an
  optional write-off entry when the selection does not net to zero.

The heavy lifting is core CE ``account.move.line.reconcile()`` (partial
reconciliation, matching numbers, exchange differences) — this module
only supplies the missing UI.

It also keeps a reconciliation from being lost without anyone noticing:

* **Reset to draft unreconciles first.** Odoo 19's ``button_draft`` stopped
  calling ``remove_move_reconcile()``, so a payment pulled back to draft kept
  its matches — the bill went on reading "Paid" against an entry that was no
  longer in the trial balance, and the aged report simply dropped it.
* **Structural edits on a matched line are refused.** The account or partner of
  a line that still carries partials can no longer be swapped, in any state.
* **Duplicate payments are stopped at posting**, with an explicit override for
  the genuine second payment.
* **Accounting → Entries → Unapplied Payments** lists posted payments that
  settle nothing, so they surface continuously rather than at month-end.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Accounting/Accounting",
    "version": "19.0.3.1.0",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "views/reconcile_views.xml",
        "views/bank_reconcile_views.xml",
        "views/unapplied_payment_views.xml",
    ],
    "installable": True,
    "application": False,
}
