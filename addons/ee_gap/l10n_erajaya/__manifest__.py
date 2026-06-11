# -*- coding: utf-8 -*-
{
    "name": "Indonesia - Erajaya Chart of Accounts",
    "summary": "Erajaya 10-digit Indonesian CoA + PPN/PPh taxes, journals, fiscal positions",
    "description": """
Erajaya localization (selectable chart template, code ``erajaya``).

Provides a ready-to-use Indonesian accounting package for any new Erajaya
company: the generic 10-digit chart of accounts (bank/cash and entity-named
accounts excluded — Odoo auto-creates generic bank/cash accounts from the code
prefixes), the full PPN/PPh tax set with tax groups, sale/purchase/general
journals, fiscal positions, and company accounting defaults.

Data is generated from the master COA (imports/arka_aim_coa.csv) and the live
ArkaAim tax configuration via tools/gen_l10n_erajaya.py.
""",
    "author": "Custom Platform",
    "category": "Accounting/Localizations/Account Charts",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["account"],
    "countries": ["id"],
    "data": [],
    "installable": True,
    "auto_install": False,
}
