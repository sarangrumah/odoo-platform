# -*- coding: utf-8 -*-
{
    "name": "Custom HR Payroll (Indonesia)",
    "summary": "Indonesian payroll: PPh 21, BPJS, THR",
    "description": """
Custom HR Payroll (Indonesia) — Phase 2E MVP:
- PPh 21 progressive bracket calculator (5%/15%/25%/30%/35%)
- BPJS Kesehatan + Ketenagakerjaan (JHT/JKK/JKM/JP) with ceilings
- PTKP tabel (TK/0..3, K/0..3, K/I/0..3)
- THR (Tunjangan Hari Raya) calculation
- Monthly payslip with line-item breakdown
- res.partner / res.users / hr.employee field extensions tagged with PDP
  classification 'sensitive_pii' for NIK/NPWP via pre_init hook
""",
    "author": "Custom Platform",
    "category": "Human Resources/Payroll",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "custom_pdp_audit", "custom_pdp_core", "hr"],
    "data": [
        "security/custom_hr_payroll_id_security.xml",
        "security/ir.model.access.csv",
        "data/hr_payroll_config_data.xml",
        "views/hr_payroll_config_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_payslip_views.xml",
        "views/menu_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
