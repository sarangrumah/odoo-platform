# -*- coding: utf-8 -*-
{
    "name": "Custom Accounting Full",
    "summary": "Indonesian COA + intercompany automation + consolidation reports (CE multi-company gap)",
    "description": """
Custom Accounting Full
======================

Closes the multi-company gap between Odoo CE's base ``account`` module
and the EE ``account_consolidation`` + ``account_inter_company_rules``
modules. Scoped to what an Indonesian SMB-mid group needs:

Features
--------
- **Indonesian Chart of Accounts (PSAK-aligned)** — minimum-viable
  set of ~70 accounts covering Aset / Kewajiban / Ekuitas / Pendapatan
  / HPP / Beban / Pajak. Installable from ``data/account_chart_id.xml``.
- **Intercompany automation** — rule table maps a partner (linked to
  ``res.company.partner_id`` of another company) to an auto-mirror
  policy. When Company A posts a sales invoice to a partner that
  represents Company B's commercial entity, Company B automatically
  receives a draft vendor bill mirroring the same lines, with mapped
  accounts and the inter-company journal.
- **Consolidation engine** — declare a parent + N subsidiaries +
  elimination accounts. Wizards produce consolidated Trial Balance,
  P&L, and Balance Sheet across all subsidiaries with a dedicated
  "Eliminations" column.
- **Branch dimension** — ``account.analytic.account`` extended with
  ``branch_code`` + ``is_branch_root`` for cost-centre reporting by
  legal branch / kantor cabang.

The reports honour the active Odoo user's allowed_company_ids — a
consolidator user must have access to *all* subsidiaries for figures
to be complete; otherwise the report renders only the visible slice
and flags the gap in its header.

Audit
-----
Every consolidation report run, intercompany mirror creation, and
elimination journal entry is written to ``pdp.audit_log`` via the
``pdp.audited.mixin`` chain.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Accounting/Accounting",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": [
        "custom_core",
        "custom_pdp_core",
        "custom_pdp_audit",
        "account",
        "analytic",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/account_chart_id.xml",
        "data/account_account_id_data.xml",
        "data/account_tax_id_data.xml",
        "data/fiscal_position_id_data.xml",
        "views/intercompany_rule_views.xml",
        "views/consolidation_config_views.xml",
        "views/account_analytic_views.xml",
        "views/res_company_views.xml",
        "wizards/consolidation_report_wizard_views.xml",
        "reports/consolidation_report_templates.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
