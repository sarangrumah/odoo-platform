# -*- coding: utf-8 -*-
{
    "name": "Custom Cash Advance & Petty Cash",
    "summary": "Employee cash advances / petty cash: typed request, Finance approval, "
    "Bank-Out disbursement, realization (third-party vendor bill or plain expense), "
    "return/top-up settlement, advance ceilings, and Kartu Uang Muka / outstanding / "
    "aging monitoring — multi-currency throughout.",
    "description": """
Custom Cash Advance & Petty Cash — Uang Muka Karyawan
======================================================

Odoo (Community *and* Enterprise) ships no cash-advance concept at all: the
Expenses app only knows "paid by employee, reimburse me" — money always moves
*after* the spend. This module supplies the advance cycle for Finance and
employees on Odoo 19 Community:

0. **Jenis uang muka** — each ``petty.cash.type`` maps a kind of advance
   (Cash Advance, Petty Cash, Travel…) to its own advance account, journals
   and ceilings, per company.
0b. **Saldo petty cash per toko** — every Operating Unit holds a revolving
   float (``petty.cash.float``), granted by a **Petty Cash Awal** request up
   to a plafon Finance sets (1.000.000 by default). Each spend goes through a
   **Realisasi** request, which reserves against that balance from the moment
   it is drafted and is refused once the store runs dry; realizing it restores
   exactly what was realized. A **Claim** is the escape hatch for a spend the
   float cannot cover and bypasses the check.
1. **Pengajuan** — an employee requests an advance for an Operating Unit
   (``petty.cash.request``), optionally broken down into estimate lines.
2. **Review & Approval** — Finance reviews; approval routes through the
   generic ``custom_approval_engine`` matrix (multi-tier, delegation, SLA).
3. **Pencairan (Bank Out)** — Finance disburses the approved amount, booking
   *Dr Uang Muka Petty Cash (employee) / Cr Bank* through the Bank-Out journal.
4. **Realisasi** — the employee accounts for the spend
   (``petty.cash.realization``):

     * *Pihak ketiga* lines create a full vendor bill (billing → PPN/PPh via
       ``custom_tax_id`` → invoicing → payment against the advance → COA),
       and require the supplier invoice attachment.
     * *Expense* lines post a direct entry *Dr Expense / Cr Uang Muka*.
5. **Pengembalian / Top-up** — leftover cash is returned to the bank, or a
   shortfall is topped up, until the employee advance nets to zero and the
   request is settled (advance lines auto-reconciled).
5b. **Review Finance** — a review queue with inline approve / send-back and a
   batch wizard that records the refusal reason, per-store float monitoring,
   and an outstanding pivot broken down by Operating Unit. Plus a dashboard
   over list / kanban / pivot / graph with search, filters and native export.
6. **Monitoring** — kanban/list dashboards by state, plus three reports on the
   ``custom_accounting_reports`` engine (PDF / XLSX / on-screen table): the
   **Kartu Uang Muka** movement card, the per-employee **Outstanding** ledger
   and an **Aging** report.
7. **Kontrol** — per-employee / per-position / per-type ceilings, a cap on
   simultaneous open advances, and a block on borrowing again while an
   advance is past its realization deadline. Off by default; Finance opts in
   per type.

Multi-currency throughout: every generated journal item carries
``currency_id`` + ``amount_currency``, so a foreign-currency advance books its
correct counter-value and settles through the exchange-difference journal.

Operating-Unit aware: when the Levi's localization is installed the OU

analytic is stamped onto every generated journal item; otherwise the module
runs unchanged.

Part of the Custom Platform — multi-tenant Odoo 19 for Indonesian SMB.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Accounting/Accounting",
    "version": "19.0.0.6.0",
    "license": "LGPL-3",
    "depends": [
        "custom_core",
        "custom_pdp_core",
        "custom_pdp_audit",
        "account",
        "hr",
        "mail",
        "custom_approval_engine",
        "custom_tax_id",
        "custom_accounting_reports",
    ],
    "capability_tags": [
        "cash-advance",
        "petty-cash",
        "store-float",
        "finance-review",
        "dashboard",
        "employee-advance",
        "multi-currency",
        "approval-workflow",
        "audit-trail",
        "accounting",
    ],
    "data": [
        "security/security.xml",
        "security/record_rules.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_template_data.xml",
        "data/ir_cron_data.xml",
        "views/petty_cash_type_views.xml",
        "views/petty_cash_float_views.xml",
        "views/petty_cash_request_views.xml",
        "views/petty_cash_realization_views.xml",
        "views/petty_cash_review_views.xml",
        "views/report_views.xml",
        "views/res_config_settings_views.xml",
        "reports/petty_cash_templates.xml",
        "reports/petty_cash_vouchers.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
