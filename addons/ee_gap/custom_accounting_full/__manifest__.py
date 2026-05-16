# -*- coding: utf-8 -*-
{
    "name": "Custom Accounting Full",
    "summary": "Advanced accounting features (reports, budgets, assets, follow-ups) for Odoo CE",
    "description": """
Custom Accounting Full is a CE-targeted reimplementation of capabilities documented at
https://www.odoo.com/documentation/19.0/applications/finance/accounting.html.

It fills the gap between Odoo CE's base ``account`` module and the Enterprise
``account_reports`` / ``account_accountant`` apps by providing comparable
reporting, budgeting, asset, and dunning workflows.

IMPLEMENTATION STATUS: SCAFFOLD - manifest only, no models/views yet.
Reference spec:
- Advanced P&L vs Balance Sheet comparative reports (multi-period, multi-company)
- Budget management with per-account and per-analytic-plan tracking
- Full asset depreciation lifecycle (linear, degressive, disposal, re-evaluation)
- Customer follow-ups (dunning levels, automated reminder schedules)
- Multi-company consolidation
- Analytic plans and multi-dimensional analytic accounting
""",
    "author": "Custom Platform",
    "category": "Accounting/Accounting",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "account"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
