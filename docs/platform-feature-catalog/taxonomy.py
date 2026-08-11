# -*- coding: utf-8 -*-
"""Hand-curated classification of every module in ``addons/``.

This file is the one place where a human decides what a module *is* to the
business. ``build_catalog_json.py`` refuses to run when a module on disk has no
entry in ``DOMAIN_BY_MODULE`` (and when an entry names a module that no longer
exists), so adding an addon forces someone to classify it. There is
deliberately no "lain-lain" bucket — a catch-all is how a feature catalog rots
without anyone noticing.

The initial mapping was seeded from each manifest's ``capability_tags`` +
``category``, then corrected by hand. The seeding code is not kept: a heuristic
left in the build path would silently reclassify modules on the next run.
"""

from __future__ import annotations

import os

# --- domains ----------------------------------------------------------------

DOMAINS = [
    {
        "id": "keuangan-akuntansi",
        "order": 1,
        "title_id": "Keuangan & Akuntansi",
        "title_en": "Finance & Accounting",
        "blurb_id": "Buku besar, laporan keuangan, aset tetap, kas & bank, dan portal keuangan "
                    "yang menutup selisih antara Odoo Community dan Enterprise.",
    },
    {
        "id": "perpajakan-indonesia",
        "order": 2,
        "title_id": "Perpajakan Indonesia",
        "title_en": "Indonesian Taxation",
        "blurb_id": "Coretax DJP, e-Faktur, Bukti Potong Unifikasi, dan mesin pemotongan PPh — "
                    "mengikuti PER-11/PJ/2025 dan PMK 131/2024.",
    },
    {
        "id": "sdm-payroll",
        "order": 3,
        "title_id": "SDM & Payroll",
        "title_en": "HR & Payroll",
        "blurb_id": "Payroll PPh 21 TER dan BPJS, absensi geofence, cuti UU Cipta Kerja, "
                    "rekrutmen, penilaian kinerja, dan reimbursement.",
    },
    {
        "id": "gudang-inventori",
        "order": 4,
        "title_id": "Gudang & Inventori",
        "title_en": "Warehouse & Inventory",
        "blurb_id": "Putaway, cycle count, QC inbound, transfer order, handheld terminal, "
                    "barcode, dan retur pembelian.",
    },
    {
        "id": "penjualan-retail-pos",
        "order": 5,
        "title_id": "Penjualan, Retail & POS",
        "title_en": "Sales, Retail & POS",
        "blurb_id": "CRM, POS Indonesia, eCommerce dan storefront headless, langganan, "
                    "serta jalur impor data retail dari XStore.",
    },
    {
        "id": "layanan-proyek",
        "order": 6,
        "title_id": "Layanan, Proyek & Sewa",
        "title_en": "Services, Projects & Rental",
        "blurb_id": "Manajemen proyek dan change request, helpdesk ber-SLA, field service, "
                    "timesheet, dan siklus penyewaan aset dengan BAST.",
    },
    {
        "id": "manufaktur-kualitas",
        "order": 7,
        "title_id": "Manufaktur, Kualitas & Pemeliharaan",
        "title_en": "Manufacturing, Quality & Maintenance",
        "blurb_id": "Quality point dan CAPA, PLM/ECO, pemeliharaan prediktif dengan MTBF/MTTR, "
                    "perbaikan aset, dan ingest sensor IoT.",
    },
    {
        "id": "produktivitas-ai",
        "order": 8,
        "title_id": "Produktivitas & AI",
        "title_en": "Productivity & AI",
        "blurb_id": "Jembatan AI ke Claude/OpenAI/Ollama, dokumen, knowledge base, spreadsheet, "
                    "dashboard, tanda tangan elektronik, dan Studio Lite.",
    },
    {
        "id": "pemasaran-komunikasi",
        "order": 9,
        "title_id": "Pemasaran & Komunikasi",
        "title_en": "Marketing & Communications",
        "blurb_id": "WhatsApp Cloud API, SMS Indonesia, email marketing, marketing automation, "
                    "event, survei, dan kanal komunikasi pelanggan.",
    },
    {
        "id": "kepatuhan-data-pdp",
        "order": 10,
        "title_id": "Kepatuhan Data (UU PDP) & Audit",
        "title_en": "Data Compliance (UU PDP) & Audit",
        "blurb_id": "Klasifikasi data pribadi, audit log berantai-hash, consent, DSAR, "
                    "masking PII, dan kebijakan retensi — UU 27/2022.",
    },
    {
        "id": "integrasi-platform",
        "order": 11,
        "title_id": "Integrasi & Fondasi Platform",
        "title_en": "Integration & Platform Foundation",
        "blurb_id": "Fondasi bersama: HMAC endpoint, adapter framework, mesin persetujuan, "
                    "SSO Keycloak, konektor ESB, dan komponen OCA.",
    },
    {
        "id": "vertikal-industri",
        "order": 12,
        "title_id": "Vertikal Industri",
        "title_en": "Industry Verticals",
        "blurb_id": "Paket khusus industri: PPOB/VAS (dompet mitra, provider, switching H2H) "
                    "dan operasi stok F&B di atas ESB Core.",
    },
    {
        "id": "admin-saas",
        "order": 13,
        "title_id": "Administrasi Platform & Odoo-as-a-Service",
        "title_en": "Platform Admin & Odoo-as-a-Service",
        "blurb_id": "Lapisan kendali multi-tenant: registry tenant, provisioning, deploy modul, "
                    "monitoring kapasitas, onboarding journey, dan pelacakan siklus dev.",
    },
]

DOMAIN_IDS = {d["id"] for d in DOMAINS}


# --- brands / tenants -------------------------------------------------------

TENANTS = [
    {"id": "arkaaim", "brand": "ARKA-AIM", "legal": "PT Arka Mandiri Nusantara / PT AIM",
     "erajaya": True, "dbs": ["prd_arkaaim", "trn_arkaaim"], "status": "live",
     "industry": "Sewa & pertunjukan drone"},
    {"id": "levis", "brand": "Levi's", "legal": "PT Era Busana Retailindo (EBR)",
     "erajaya": True, "dbs": ["prd_levis_begbal", "rnd_levis"], "status": "live",
     "industry": "Retail fashion"},
    {"id": "ppob", "brand": "Eraspace / PPOB-VAS", "legal": "PT Erajaya Swasembada Tbk",
     "erajaya": True, "dbs": ["rnd_ppob"], "status": "development",
     "industry": "Value-added services / bill payment"},
    {"id": "efn", "brand": "EFN (Erajaya F&B)", "legal": "Erajaya Food & Nourishment",
     "erajaya": True, "dbs": ["rnd_esb"], "status": "pre-pilot",
     "industry": "Food & beverage"},
    {"id": "finportal", "brand": "Finance Portal", "legal": "Erajaya Group Shared Services",
     "erajaya": True, "dbs": [], "status": "development",
     "industry": "Corporate finance over SAP"},
    {"id": "vaspmo", "brand": "VAS PMO", "legal": "Erajaya Value-Added Services",
     "erajaya": True, "dbs": ["rnd_vas_pmo"], "status": "live",
     "industry": "Delivery management"},
    {"id": "gentlewoman", "brand": "GentleWoman", "legal": "GentleWoman AP",
     "erajaya": False, "dbs": [], "status": "pre-implementation",
     "industry": "Retail fashion / eCommerce"},
    {"id": "jds", "brand": "JDS Warehouse", "legal": "JDS",
     "erajaya": False, "dbs": ["rnd_wms"], "status": "poc",
     "industry": "Warehouse management"},
]

TENANT_IDS = {t["id"] for t in TENANTS}


# --- primary domain, one entry per module on disk ---------------------------

DOMAIN_BY_MODULE = {
    # -- _tenants ------------------------------------------------------------
    "custom_arka_aim_asset_register": "keuangan-akuntansi",
    "custom_arka_aim_numbering": "integrasi-platform",
    "custom_arka_aim_opening_balance": "keuangan-akuntansi",
    "custom_arka_aim_seed": "keuangan-akuntansi",
    "custom_arka_fx_header": "keuangan-akuntansi",
    "custom_arka_show_date": "layanan-proyek",
    "custom_levis_asset_accounts": "keuangan-akuntansi",
    "custom_levis_bank_reconcile": "keuangan-akuntansi",
    "custom_levis_categ_approval": "keuangan-akuntansi",
    "custom_levis_localization": "penjualan-retail-pos",
    "custom_levis_operating_unit": "keuangan-akuntansi",

    # -- _vendor -------------------------------------------------------------
    "auth_jwt": "integrasi-platform",
    "base_rest": "integrasi-platform",
    "partner_firstname": "integrasi-platform",
    "queue_job": "integrasi-platform",

    # -- compliance ----------------------------------------------------------
    "custom_coretax": "perpajakan-indonesia",
    "custom_coretax_bupot": "perpajakan-indonesia",
    "custom_pph_witholding": "perpajakan-indonesia",
    "custom_pdp_audit": "kepatuhan-data-pdp",
    "custom_pdp_consent": "kepatuhan-data-pdp",
    "custom_pdp_core": "kepatuhan-data-pdp",
    "custom_pdp_dsar": "kepatuhan-data-pdp",
    "custom_pdp_masking": "kepatuhan-data-pdp",
    "custom_pdp_retention": "kepatuhan-data-pdp",

    # -- control_plane -------------------------------------------------------
    "custom_hub_console": "admin-saas",
    "custom_onboarding_journey": "admin-saas",
    "custom_super_admin": "admin-saas",
    "custom_tenant_infra": "admin-saas",

    # -- core ----------------------------------------------------------------
    "custom_adapter_framework": "integrasi-platform",
    "custom_ai_bridge": "produktivitas-ai",
    "custom_bast": "layanan-proyek",
    "custom_core": "integrasi-platform",
    "custom_operating_unit": "integrasi-platform",
    "custom_role_manager": "integrasi-platform",
    "custom_currency_nbsp": "integrasi-platform",
    "custom_hht_bridge": "gudang-inventori",
    "custom_home_console": "integrasi-platform",
    "custom_product_barcode": "gudang-inventori",
    "custom_sale_bast": "layanan-proyek",

    # -- ee_gap: keuangan ----------------------------------------------------
    "custom_account_batch_payment": "keuangan-akuntansi",
    "custom_account_deferred": "keuangan-akuntansi",
    "custom_account_reconcile": "keuangan-akuntansi",
    "custom_accounting_asset": "keuangan-akuntansi",
    "custom_accounting_full": "keuangan-akuntansi",
    "custom_accounting_recurring": "keuangan-akuntansi",
    "custom_accounting_reports": "keuangan-akuntansi",
    "custom_operating_unit_reports": "keuangan-akuntansi",
    "custom_asset_from_receipt": "keuangan-akuntansi",
    "custom_bank_import": "keuangan-akuntansi",
    "custom_esg": "keuangan-akuntansi",
    "custom_finance_budget": "keuangan-akuntansi",
    "custom_finance_portal": "keuangan-akuntansi",
    "custom_finance_portal_sap": "keuangan-akuntansi",
    "custom_finance_portal_sso": "keuangan-akuntansi",
    "custom_payment_admin_fee": "keuangan-akuntansi",
    "custom_payment_id": "keuangan-akuntansi",
    "custom_payment_methods_id": "keuangan-akuntansi",
    "custom_payment_voucher": "keuangan-akuntansi",
    "custom_petty_cash": "keuangan-akuntansi",
    "l10n_erajaya": "keuangan-akuntansi",
    "l10n_id_psak_custom": "keuangan-akuntansi",

    # -- ee_gap: perpajakan --------------------------------------------------
    "custom_coretax_export": "perpajakan-indonesia",
    "custom_coretax_pajakku": "perpajakan-indonesia",
    "custom_tax_id": "perpajakan-indonesia",

    # -- ee_gap: SDM ---------------------------------------------------------
    "custom_attendance": "sdm-payroll",
    "custom_elearning": "sdm-payroll",
    "custom_expenses": "sdm-payroll",
    "custom_fleet_id": "sdm-payroll",
    "custom_frontdesk": "sdm-payroll",
    "custom_hr_appraisal": "sdm-payroll",
    "custom_hr_leave_id": "sdm-payroll",
    "custom_hr_payroll_id": "sdm-payroll",
    "custom_hr_referral": "sdm-payroll",
    "custom_hr_sso_keycloak": "sdm-payroll",
    "custom_lunch": "sdm-payroll",
    "custom_planning": "sdm-payroll",
    "custom_recruitment_id": "sdm-payroll",

    # -- ee_gap: gudang ------------------------------------------------------
    "custom_barcode": "gudang-inventori",
    "custom_intercompany_procurement": "gudang-inventori",
    "custom_po_return": "gudang-inventori",
    "custom_receipt_async": "gudang-inventori",
    "custom_stock_delivery_report_fix": "gudang-inventori",
    "custom_wms_cycle_count": "gudang-inventori",
    "custom_wms_docs": "gudang-inventori",
    "custom_wms_hht": "gudang-inventori",
    "custom_wms_inbound_qc": "gudang-inventori",
    "custom_wms_integration": "gudang-inventori",
    "custom_wms_putaway": "gudang-inventori",
    "custom_wms_receiving_ext": "gudang-inventori",
    "custom_wms_reports": "gudang-inventori",
    "custom_wms_sap_slotting": "gudang-inventori",
    "custom_wms_to_engine": "gudang-inventori",

    # -- ee_gap: penjualan / retail -----------------------------------------
    "custom_crm": "penjualan-retail-pos",
    "custom_ecommerce": "penjualan-retail-pos",
    "custom_pos_id": "penjualan-retail-pos",
    "custom_retail_import": "penjualan-retail-pos",
    "custom_operating_unit_pos": "penjualan-retail-pos",
    "custom_retail_import_api": "penjualan-retail-pos",
    "custom_retail_import_pos": "penjualan-retail-pos",
    "custom_retail_import_recon": "penjualan-retail-pos",
    "custom_storefront_api": "penjualan-retail-pos",
    "custom_subscription": "penjualan-retail-pos",

    # -- ee_gap: layanan & proyek -------------------------------------------
    "custom_field_service": "layanan-proyek",
    "custom_helpdesk": "layanan-proyek",
    "custom_ops_reports": "layanan-proyek",
    "custom_project_api": "layanan-proyek",
    "custom_project_cr": "layanan-proyek",
    "custom_project_notify": "layanan-proyek",
    "custom_project_portfolio": "layanan-proyek",
    "custom_rental": "layanan-proyek",
    "custom_rental_bom_explosion": "layanan-proyek",
    "custom_rental_invoicing": "layanan-proyek",
    "custom_rental_quality_hook": "layanan-proyek",
    "custom_timesheet": "layanan-proyek",

    # -- ee_gap: manufaktur --------------------------------------------------
    "custom_iot_bridge": "manufaktur-kualitas",
    "custom_maintenance": "manufaktur-kualitas",
    "custom_mrp_plm": "manufaktur-kualitas",
    "custom_quality_full": "manufaktur-kualitas",
    "custom_repairs": "manufaktur-kualitas",

    # -- ee_gap: produktivitas & AI -----------------------------------------
    "custom_ai_features": "produktivitas-ai",
    "custom_dashboards": "produktivitas-ai",
    "custom_data_cleaning": "produktivitas-ai",
    "custom_documents": "produktivitas-ai",
    "custom_knowledge": "produktivitas-ai",
    "custom_sign": "produktivitas-ai",
    "custom_spreadsheet": "produktivitas-ai",
    "custom_studio_lite": "produktivitas-ai",
    "custom_todo": "produktivitas-ai",

    # -- ee_gap: pemasaran ---------------------------------------------------
    "custom_affiliate": "pemasaran-komunikasi",
    "custom_appointments": "pemasaran-komunikasi",
    "custom_email_marketing": "pemasaran-komunikasi",
    "custom_events": "pemasaran-komunikasi",
    "custom_forum": "pemasaran-komunikasi",
    "custom_livechat": "pemasaran-komunikasi",
    "custom_marketing_automation": "pemasaran-komunikasi",
    "custom_sms_id": "pemasaran-komunikasi",
    "custom_social": "pemasaran-komunikasi",
    "custom_survey": "pemasaran-komunikasi",
    "custom_voip": "pemasaran-komunikasi",
    "custom_whatsapp": "pemasaran-komunikasi",

    # -- ee_gap: fondasi -----------------------------------------------------
    "custom_operating_unit_docs": "integrasi-platform",
    "authenticate_keycloak": "integrasi-platform",
    "custom_approval_engine": "integrasi-platform",
    "custom_esb_connector": "integrasi-platform",
    "custom_report_templates": "integrasi-platform",

    # -- operations ----------------------------------------------------------
    "custom_brd_analyzer": "admin-saas",
    "custom_dev_cycle": "admin-saas",
    "custom_ops_monitor": "admin-saas",

    # -- verticals -----------------------------------------------------------
    "custom_fnb_stock_ops": "vertikal-industri",
    "custom_ppob_biller_digiflazz": "vertikal-industri",
    "custom_ppob_commission": "vertikal-industri",
    "custom_ppob_core": "vertikal-industri",
    "custom_ppob_eraspace_bridge": "vertikal-industri",
    "custom_ppob_oracle_bridge": "vertikal-industri",
    "custom_ppob_pps_gateway": "vertikal-industri",
    "custom_ppob_provider": "vertikal-industri",
    "custom_ppob_rollup": "vertikal-industri",
    "custom_ppob_sale": "vertikal-industri",
    "custom_ppob_sla": "vertikal-industri",
    "custom_ppob_va": "vertikal-industri",
    "custom_ppob_wallet": "vertikal-industri",
    "custom_vertical_example": "vertikal-industri",
}


# Secondary domains — a module shows up in these chapters as a cross-reference,
# never in their counts. Sparse on purpose: everything is cross-cutting if you
# squint, and a catalog where every module appears in four chapters is noise.
DOMAIN_SECONDARY = {
    "custom_arka_show_date": ["keuangan-akuntansi"],
    "custom_asset_from_receipt": ["gudang-inventori"],
    "custom_bast": ["gudang-inventori"],
    "custom_esb_connector": ["vertikal-industri", "gudang-inventori"],
    "custom_finance_portal_sap": ["integrasi-platform"],
    "custom_finance_portal_sso": ["integrasi-platform"],
    "custom_operating_unit": ["admin-saas"],
    "custom_operating_unit_docs": ["keuangan-akuntansi", "gudang-inventori"],
    "custom_operating_unit_pos": ["integrasi-platform"],
    "custom_operating_unit_reports": ["integrasi-platform"],
    "custom_role_manager": ["admin-saas", "kepatuhan-data-pdp"],
    "custom_hr_sso_keycloak": ["integrasi-platform"],
    "custom_hht_bridge": ["integrasi-platform"],
    "custom_intercompany_procurement": ["keuangan-akuntansi"],
    "custom_levis_categ_approval": ["penjualan-retail-pos"],
    "custom_levis_localization": ["keuangan-akuntansi", "gudang-inventori"],
    "custom_levis_operating_unit": ["penjualan-retail-pos", "integrasi-platform"],
    "custom_livechat": ["layanan-proyek"],
    "custom_ops_reports": ["manufaktur-kualitas", "keuangan-akuntansi"],
    "custom_payment_id": ["penjualan-retail-pos"],
    "custom_petty_cash": ["sdm-payroll"],
    "custom_pos_id": ["perpajakan-indonesia"],
    "custom_ppob_commission": ["perpajakan-indonesia"],
    "custom_ppob_rollup": ["perpajakan-indonesia"],
    "custom_retail_import_pos": ["keuangan-akuntansi"],
    "custom_timesheet": ["sdm-payroll"],
    "custom_wms_hht": ["integrasi-platform"],
    "l10n_erajaya": ["perpajakan-indonesia"],
    "l10n_id_psak_custom": ["perpajakan-indonesia"],
}


# --- scope ------------------------------------------------------------------

# Default scope comes from the addons group. These are the exceptions.
# Nothing here yet: the group rule has held so far. Keep the hook — the moment
# a `_tenants/` module is promoted to `ee_gap/` mid-release, this is where the
# override lands before the move happens.
SCOPE_OVERRIDE: dict[str, str] = {}

_SCOPE_BY_GROUP = {
    "_tenants": "tenant",
    "_vendor": "vendor",
    "control_plane": "platform",
    "operations": "platform",
}


def scope_for(name: str, group: str) -> str:
    if name in SCOPE_OVERRIDE:
        return SCOPE_OVERRIDE[name]
    return _SCOPE_BY_GROUP.get(group, "general")


# Brands a module currently carries data or configuration for. For a `general`
# module this is what turns "umum" into "umum, dikonfigurasi untuk brand X" —
# the distinction `docs/architecture.md` insists on when it says a shared engine
# stays in ee_gap even though its seed data belongs to one customer.
TENANTS_BY_MODULE = {
    # ARKA-AIM
    "custom_arka_aim_asset_register": ["arkaaim"],
    "custom_arka_aim_numbering": ["arkaaim"],
    "custom_arka_aim_opening_balance": ["arkaaim"],
    "custom_arka_aim_seed": ["arkaaim"],
    "custom_arka_fx_header": ["arkaaim"],
    "custom_arka_show_date": ["arkaaim"],
    "custom_ops_reports": ["arkaaim"],
    "custom_rental_bom_explosion": ["arkaaim"],
    "custom_rental_invoicing": ["arkaaim"],
    "custom_rental_quality_hook": ["arkaaim"],
    "custom_asset_from_receipt": ["arkaaim"],
    "custom_rental": ["arkaaim"],

    # Levi's / EBR
    "custom_levis_asset_accounts": ["levis"],
    "custom_levis_bank_reconcile": ["levis"],
    "custom_levis_categ_approval": ["levis"],
    "custom_levis_localization": ["levis"],
    "custom_levis_operating_unit": ["levis"],
    "custom_retail_import": ["levis"],
    "custom_retail_import_api": ["levis"],
    "custom_retail_import_pos": ["levis"],
    "custom_retail_import_recon": ["levis"],
    "custom_po_return": ["levis"],
    "custom_payment_admin_fee": ["levis"],
    "custom_payment_voucher": ["levis"],
    "custom_payment_methods_id": ["levis"],

    # shared across both live Erajaya tenants
    "l10n_erajaya": ["arkaaim", "levis"],
    "custom_petty_cash": ["arkaaim", "levis"],
    "custom_coretax_export": ["arkaaim", "levis"],
    "custom_tax_id": ["arkaaim", "levis"],
    "custom_accounting_reports": ["arkaaim", "levis"],
    "custom_accounting_asset": ["arkaaim", "levis"],
    "custom_bank_import": ["levis", "arkaaim"],

    # PPOB / Eraspace
    "custom_ppob_biller_digiflazz": ["ppob"],
    "custom_ppob_commission": ["ppob"],
    "custom_ppob_core": ["ppob"],
    "custom_ppob_eraspace_bridge": ["ppob"],
    "custom_ppob_oracle_bridge": ["ppob"],
    "custom_ppob_pps_gateway": ["ppob"],
    "custom_ppob_provider": ["ppob"],
    "custom_ppob_rollup": ["ppob"],
    "custom_ppob_sale": ["ppob"],
    "custom_ppob_sla": ["ppob"],
    "custom_ppob_va": ["ppob"],
    "custom_ppob_wallet": ["ppob"],

    # EFN F&B x ESB
    "custom_esb_connector": ["efn"],
    "custom_fnb_stock_ops": ["efn"],

    # Finance Portal
    "custom_finance_budget": ["finportal"],
    "custom_finance_portal": ["finportal"],
    "custom_finance_portal_sap": ["finportal"],
    "custom_finance_portal_sso": ["finportal"],

    # VAS PMO
    "custom_project_api": ["vaspmo"],
    "custom_project_cr": ["vaspmo"],
    "custom_project_notify": ["vaspmo"],
    "custom_project_portfolio": ["vaspmo"],

    # GentleWoman
    "custom_storefront_api": ["gentlewoman"],
    "custom_ecommerce": ["gentlewoman"],

    # JDS warehouse POC
    "custom_wms_cycle_count": ["jds"],
    "custom_wms_docs": ["jds"],
    "custom_wms_hht": ["jds"],
    "custom_wms_inbound_qc": ["jds"],
    "custom_wms_putaway": ["jds"],
    "custom_wms_receiving_ext": ["jds"],
    "custom_wms_reports": ["jds", "levis"],
    "custom_wms_sap_slotting": ["jds"],
    "custom_wms_to_engine": ["jds"],
}


# ``infer_maturity`` reads tests + content, which misjudges a few modules.
MATURITY_OVERRIDE = {
    # Data-only modules: no models, no tests, but shipped and posted against.
    "custom_arka_aim_opening_balance": "production",
    "custom_arka_aim_seed": "production",
    # UI/controller-only module driving live handheld operations.
    "custom_wms_hht": "production",
    # Live on prd_levis_begbal and prd_arkaaim despite carrying no test suite.
    "custom_accounting_reports": "production",
    "custom_levis_localization": "production",
    "custom_retail_import": "production",
    "custom_tax_id": "production",
    "custom_coretax_export": "production",
    "custom_petty_cash": "production",
    # Reference template — never installed anywhere.
    "custom_vertical_example": "scaffold",
}


# --- Indonesian labels ------------------------------------------------------
# Business-facing name and one-line summary. The English manifest text is the
# fallback, marked "[EN]" so an untranslated row is visible rather than a silent
# language mix.

ID_LABELS = {
    # ---- _tenants ----------------------------------------------------------
    "custom_arka_aim_asset_register": ("Register Aset Drone ARKA-AIM",
        "Subledger aset tetap per unit drone, direkonsiliasi ke saldo awal GL 31 Mei 2026."),
    "custom_arka_aim_numbering": ("Penomoran Dokumen ARKA-AIM",
        "Nomor SQ/SO/PO/INV/DO/BAST per perusahaan dengan reset bulanan."),
    "custom_arka_aim_opening_balance": ("Saldo Awal ARKA-AIM",
        "Saldo awal perusahaan AIM dan ARKA per 31 Mei 2026."),
    "custom_arka_aim_seed": ("Seed CoA ARKA-AIM",
        "Bagan akun, pajak, dan posisi fiskal awal untuk basis data pengembangan ARKA-AIM."),
    "custom_arka_fx_header": ("Header Valuta Asing ARKA-AIM",
        "Menampilkan total mata uang asing dan kurs yang dipakai di header faktur serta popup pembayaran."),
    "custom_arka_show_date": ("Tanggal Pertunjukan ARKA",
        "Field tanggal show, event, dan uang muka di penawaran/SO/faktur, dengan termin pembayaran berpatokan tanggal show."),
    "custom_levis_asset_accounts": ("Akun Revaluasi Aset Levi's",
        "Enam kategori aset tetap EBR beserta akun revaluasi IAS 16, resolusi kode akun per perusahaan."),
    "custom_levis_bank_reconcile": ("Rekonsiliasi Bank POS Levi's",
        "Mencocokkan settlement bank dengan piutang tender POS per toko, bersih dari MDR."),
    "custom_levis_categ_approval": ("Persetujuan Perubahan Kategori Produk",
        "Perubahan kategori produk tidak lagi diam-diam — harus lewat persetujuan Finance, dengan koreksi GL."),
    "custom_levis_operating_unit": ("Migrasi Unit Operasional Levi's",
        "Mengangkat dimensi Operating Unit Levi's yang sudah ada menjadi master unit "
        "platform — tanpa mengubah kode gudang, nama akun analitik, jurnal, maupun POS."),
    "custom_levis_localization": ("Lokalisasi Levi's",
        "Kustomisasi tenant Levi's: HS Code, batas qty terima, jurnal billing, voucher pembayaran, kliring POS."),

    # ---- _vendor -----------------------------------------------------------
    "auth_jwt": ("Autentikasi JWT (OCA)",
        "Autentikasi bearer token JWT untuk API keluar-masuk."),
    "base_rest": ("Base REST (OCA)",
        "Kerangka membangun REST API tingkat tinggi di Odoo. Tidak dipasang."),
    "partner_firstname": ("Nama Depan/Belakang Partner (OCA)",
        "Memisahkan nama depan dan nama belakang untuk partner perorangan."),
    "queue_job": ("Antrean Pekerjaan (OCA)",
        "Eksekusi pekerjaan latar belakang berbasis basis data — dipakai 6 modul."),

    # ---- compliance --------------------------------------------------------
    "custom_coretax": ("Coretax DJP",
        "NSFP, ekspor/impor XML e-Faktur, Bukti Potong, dan penyimpanan Sertifikat Elektronik terenkripsi."),
    "custom_coretax_bupot": ("Bukti Potong Unifikasi",
        "Bupot PPh 22/23/4(2)/15/26 dengan ekspor XML dan pembaruan nomor DJP."),
    "custom_pph_witholding": ("Mesin Pemotongan PPh",
        "Registry tarif, perhitungan, dan log penerapan pemotongan PPh."),
    "custom_pdp_audit": ("Audit Log UU PDP",
        "Log audit append-only berantai-hash, dilindungi trigger Postgres."),
    "custom_pdp_consent": ("Manajemen Consent",
        "Pencatatan pemberian dan penarikan persetujuan subjek data, teraudit."),
    "custom_pdp_core": ("Klasifikasi Data Pribadi",
        "Taksonomi klasifikasi data pribadi sesuai UU 27/2022."),
    "custom_pdp_dsar": ("Permintaan Subjek Data (DSAR)",
        "Alur permintaan akses/koreksi/penghapusan data pribadi."),
    "custom_pdp_masking": ("Masking PII",
        "Layanan penyamaran data pribadi dengan hook pada pembacaan ORM."),
    "custom_pdp_retention": ("Kebijakan Retensi Data",
        "Kebijakan retensi dan otomasi siklus hidup data pribadi."),

    # ---- control_plane -----------------------------------------------------
    "custom_hub_console": ("Konsol Hub Terpadu",
        "Satu pintu: tenant, katalog & deploy modul, monitoring, BRD, HHT, AI, audit."),
    "custom_onboarding_journey": ("Perjalanan Onboarding Tenant",
        "Orkestrasi intake → BRD → Go/No-Go → provisioning → handover, sinkron dua arah dengan Project."),
    "custom_super_admin": ("Super Admin Platform",
        "Kendali multi-tenant khusus ops: provision, suspend, backup, restore."),
    "custom_tenant_infra": ("Infrastruktur Tenant (VPS)",
        "Siklus hidup VPS dan auto-deploy: bootstrap SSH, Docker, Caddy, stack Odoo."),

    # ---- core --------------------------------------------------------------
    "custom_adapter_framework": ("Kerangka Adapter Integrasi",
        "Registry adapter, klien HTTP dengan retry dan circuit breaker, serta log panggilan append-only."),
    "custom_ai_bridge": ("Jembatan AI",
        "Menghubungkan Odoo ke gateway AI platform (Claude / OpenAI / Ollama)."),
    "custom_bast": ("Berita Acara Serah Terima",
        "Dokumen serah terima generik dengan tanda tangan ganda dan jejak audit."),
    "custom_operating_unit": ("Manajemen Unit Operasional",
        "Master unit operasional berjenjang Kantor Pusat → Area → Toko, dan pemetaan "
        "pengguna ke unit yang menjadi dasar pembatasan data."),
    "custom_role_manager": ("Manajemen Peran Pengguna",
        "Pilih peran jabatan alih-alih mencentang puluhan grup akses; 18 peran standar "
        "Kantor Pusat dan retail, dengan pencabutan yang hanya menyentuh pemberian peran."),
    "custom_core": ("Fondasi Platform",
        "Utilitas bersama, mixin, helper kebijakan, dan endpoint ber-HMAC."),
    "custom_currency_nbsp": ("Perbaikan Format Mata Uang & CSV",
        "Menghapus non-breaking space pada nominal dan menambahkan BOM UTF-8 pada ekspor CSV."),
    "custom_hht_bridge": ("Jembatan Handheld Terminal",
        "Shell PWA, REST API ber-HMAC per perangkat, dan sinkronisasi offline idempoten."),
    "custom_home_console": ("Konsol Beranda",
        "Halaman depan bergaya spotlight: kartu aplikasi terkelompok, pencarian, branding."),
    "custom_product_barcode": ("Barcode Produk Ganda",
        "Beberapa barcode alternatif per varian produk — satu varian, satu stok, semua terpindai."),
    "custom_sale_bast": ("BAST dari Sales Order",
        "Membuat dan mengakses dokumen BAST langsung dari Sales Order."),

    # ---- ee_gap: keuangan --------------------------------------------------
    "custom_account_batch_payment": ("Pembayaran Batch",
        "Pembayaran massal dengan ekspor file transfer bank Indonesia."),
    "custom_account_deferred": ("Pendapatan & Beban Ditangguhkan",
        "Menyebar baris faktur/tagihan ke rentang periode lewat akun tangguhan."),
    "custom_account_reconcile": ("Rekonsiliasi Akun",
        "Menu dan wizard rekonsiliasi manual bergaya Enterprise untuk Odoo Community."),
    "custom_accounting_asset": ("Aset Tetap & Penyusutan",
        "Register aset, jadwal penyusutan, cron posting bulanan, dan alur pelepasan aset."),
    "custom_accounting_full": ("Akuntansi Lengkap & Konsolidasi",
        "Otomasi antar-perusahaan, eliminasi, konsolidasi, batas kredit, tahun fiskal, dan follow-up."),
    "custom_accounting_recurring": ("Jurnal & Pembayaran Berulang",
        "Template jurnal dan pembayaran berulang dengan penjadwalan otomatis."),
    "custom_operating_unit_reports": ("Laporan per Unit Operasional",
        "Membatasi laporan keuangan pada unit yang boleh dibaca pengguna — laporan "
        "menyusun SQL sendiri sehingga aturan akses Odoo tidak berlaku di sana."),
    "custom_accounting_reports": ("Mesin Laporan Keuangan",
        "P&L, Neraca, Buku Besar, Neraca Saldo, Arus Kas, Aging, Buku Kas/Bank, dan laporan pajak."),
    "custom_asset_from_receipt": ("Aset dari Penerimaan Barang",
        "Mengubah massal produk ber-serial yang diterima menjadi Aset Tetap dan Aset Sewa."),
    "custom_bank_import": ("Impor Rekening Koran",
        "Impor mutasi bank berbasis template CSV dan kerangka adapter API H2H bank."),
    "custom_esg": ("Pelaporan ESG",
        "Metrik lingkungan, sosial, dan tata kelola untuk POJK 51/2017."),
    "custom_finance_budget": ("Anggaran Biaya Divisi",
        "Anggaran biaya per divisi/periode yang disinkronkan dari SAP."),
    "custom_finance_portal": ("Finance Portal",
        "Uang muka, reimbursement, tagihan vendor, dan perjalanan dinas di atas SAP — tanpa posting GL sendiri."),
    "custom_finance_portal_sap": ("Integrasi Finance Portal ↔ SAP",
        "Adapter jembatan, push asinkron, sinkronisasi master data, webhook status, dan log sinkronisasi."),
    "custom_finance_portal_sso": ("SSO Finance Portal",
        "Login Keycloak dan pemetaan peran ke grup, memisahkan karyawan dari vendor."),
    "custom_payment_admin_fee": ("Biaya Admin Pembayaran",
        "Baris biaya admin/bank multi-COA pada wizard Register Payment."),
    "custom_payment_id": ("Payment Gateway Indonesia",
        "Adapter Midtrans, Xendit, dan DOKU untuk payment.provider."),
    "custom_payment_methods_id": ("Metode Pembayaran GIRO & Transfer",
        "Menambahkan GIRO dan BANK TRANSFER sebagai metode pembayaran pada jurnal bank."),
    "custom_payment_voucher": ("Voucher & Kuitansi Pembayaran",
        "Cetak bukti kas keluar dan kuitansi pada pembayaran, lengkap dengan terbilang."),
    "custom_petty_cash": ("Uang Muka & Kas Kecil",
        "Permintaan bertipe, persetujuan Finance, pencairan bank, realisasi, dan Kartu Uang Muka."),
    "l10n_erajaya": ("Bagan Akun Erajaya",
        "CoA Indonesia 10 digit khas Erajaya beserta pajak PPN/PPh, jurnal, dan posisi fiskal."),
    "l10n_id_psak_custom": ("Bagan Akun PSAK",
        "CoA 5 digit selaras PSAK dengan pajak PPN dan posisi fiskal Indonesia."),

    # ---- ee_gap: perpajakan ------------------------------------------------
    "custom_coretax_export": ("Ekspor Template Coretax",
        "Workbook sesuai format DJP: e-Faktur FK/OF, Retur Masukan, Bupot Unifikasi dan PPh 21."),
    "custom_coretax_pajakku": ("Adapter Pajakku (ASPP)",
        "Adapter host-to-host ke Pajakku sebagai Penyedia Jasa Aplikasi Perpajakan."),
    "custom_tax_id": ("Pajak Indonesia (PPh & DPP Nilai Lain)",
        "Pemotongan PPh 23/4(2)/26, PPN DPP Nilai Lain (PMK 131/2024), dan Faktur Pengganti."),

    # ---- ee_gap: SDM -------------------------------------------------------
    "custom_attendance": ("Absensi & Lembur",
        "Check-in geofence, portal kiosk, alur persetujuan, dan lembur yang mengalir ke payroll."),
    "custom_elearning": ("Pembelajaran Daring",
        "Sertifikat berbahasa Indonesia, kohort peserta, dan integrasi penilaian kinerja."),
    "custom_expenses": ("Klaim Biaya Karyawan",
        "Ekstraksi struk dengan OCR AI, persetujuan, kartu korporat, dan klaim kilometer."),
    "custom_fleet_id": ("Armada Kendaraan",
        "Pengingat STNK dan KIR, pencatatan BBM, dan penugasan pengemudi."),
    "custom_frontdesk": ("Front Desk & Tamu",
        "Manajemen kunjungan tamu dengan notifikasi ke host dan jejak audit PDP."),
    "custom_hr_appraisal": ("Penilaian Kinerja",
        "Review berbasis template, umpan balik 360 derajat, dan penilaian kompetensi."),
    "custom_hr_leave_id": ("Cuti Indonesia",
        "Cuti sesuai UU Cipta Kerja, cuti haid, hari libur nasional, dan carry-over saldo."),
    "custom_hr_payroll_id": ("Payroll Indonesia",
        "PPh 21 TER dan progresif tahunan, BPJS Kesehatan/Ketenagakerjaan, PTKP, THR, SPT 1721 A1."),
    "custom_hr_referral": ("Program Referral Karyawan",
        "Pelacakan kandidat rujukan beserta buku besar imbalannya."),
    "custom_hr_sso_keycloak": ("SSO Karyawan (Keycloak)",
        "SSO Keycloak yang menautkan dan menyinkronkan data karyawan dari klaim token dan HC API."),
    "custom_lunch": ("Katering & Makan Siang",
        "Tautan GoFood/GrabFood/ShopeeFood, potongan payroll nyata, dan penanda halal."),
    "custom_planning": ("Perencanaan Shift",
        "Perencanaan sumber daya dan penjadwalan shift tim."),
    "custom_recruitment_id": ("Rekrutmen Indonesia",
        "Ingest lowongan dari job board via webhook dan retensi data pelamar sadar-PDP."),

    # ---- ee_gap: gudang ----------------------------------------------------
    "custom_barcode": ("Pemindaian Barcode Gudang",
        "Scan-in dan scan-out mobile untuk pengiriman dan penerimaan, setara Enterprise."),
    "custom_intercompany_procurement": ("Pengadaan Antar-Perusahaan",
        "Cerminan otomatis purchase order dan pengiriman antar perusahaan sekelompok."),
    "custom_po_return": ("Retur Pembelian",
        "Retur ke vendor berbasis kuantitas dengan alokasi FIFO lintas PO dan nota kredit otomatis."),
    "custom_receipt_async": ("Validasi Penerimaan Asinkron",
        "Validasi penerimaan barang berukuran besar di latar belakang lewat antrean pekerjaan."),
    "custom_stock_delivery_report_fix": ("Perbaikan Surat Jalan",
        "Tambalan template surat jalan bawaan. Sengaja dinonaktifkan."),
    "custom_wms_cycle_count": ("Stock Opname Berkala",
        "Cycle count berbasis rencana dengan alur persetujuan selisih."),
    "custom_wms_docs": ("Dokumen & Label Gudang",
        "Picking list, packing list, lembar scan barcode, dan label harga produk."),
    "custom_wms_hht": ("Aplikasi Handheld Gudang",
        "Antarmuka handheld berbasis tugas: terima, putaway, pick, pack, count, bin-to-bin."),
    "custom_wms_inbound_qc": ("QC Penerimaan Barang",
        "Karantina inbound, gerbang QC, stok belum bisa direservasi, dan registrasi item tak dikenal."),
    "custom_wms_integration": ("Integrasi WMS Eksternal",
        "REST masuk, adapter keluar, dan outbox event untuk host WMS/SAP."),
    "custom_wms_putaway": ("Mesin Putaway",
        "Mesin penempatan bertingkat yang dapat dikonfigurasi, bergaya ZWME001."),
    "custom_wms_receiving_ext": ("Kelengkapan Penerimaan Barang",
        "Kedaluwarsa GS1, nomor batch pemasok pada lot, dan impor penerimaan dari CSV/XLSX."),
    "custom_wms_reports": ("Paket Laporan Gudang",
        "Retur pembelian, ringkasan stok (qty dan nilai), stock take, spot check, dan transfer."),
    "custom_wms_sap_slotting": ("Slotting Bergaya SAP",
        "Pencarian lokasi dua dimensi ala SAP (Lagertyp × Lagerbereich)."),
    "custom_wms_to_engine": ("Mesin Transfer Order",
        "Transfer internal berbasis aturan: batas stok minimum, kedaluwarsa, dan konsolidasi."),

    # ---- ee_gap: penjualan -------------------------------------------------
    "custom_crm": ("CRM & Prospek",
        "Penambangan prospek, skoring prediktif, pengayaan data, formulir web, dan otomasi."),
    "custom_ecommerce": ("eCommerce Indonesia",
        "Registry kurir (JNE, JNT, SiCepat, AnterAja, Pos) dan checkout Midtrans/Xendit."),
    "custom_pos_id": ("POS Indonesia",
        "QRIS, pembulatan rupiah, dan struk elektronik via WhatsApp/SMS."),
    "custom_operating_unit_pos": ("Unit Operasional di Kasir",
        "Membatasi POS, sesi, dan pesanan per toko, serta membubuhkan unit pada setiap "
        "baris jurnal penutupan sesi."),
    "custom_retail_import": ("Impor Data Retail",
        "Ingest Excel/CSV dan SFTP untuk master serta transaksi retail dari XStore."),
    "custom_retail_import_api": ("API Master Produk (MDM)",
        "REST masuk untuk feed master produk mendekati real-time dari MDM HUB."),
    "custom_retail_import_pos": ("Jembatan POS Impor Retail",
        "Membukukan penjualan dan retur POS hasil impor dengan akun pajak, diskon, dan retur dari sumbernya."),
    "custom_retail_import_recon": ("Rekonsiliasi X-Store vs Odoo",
        "Pencocokan per transaksi antara berkas penjualan X24DN dan yang benar-benar terbukukan."),
    "custom_storefront_api": ("API Storefront Headless",
        "REST JSON untuk storefront Next.js: katalog, keranjang, autentikasi JWT, checkout."),
    "custom_subscription": ("Langganan Berulang",
        "Penagihan berulang, analitik MRR/LTV, dan prediksi churn berbasis AI."),

    # ---- ee_gap: layanan ---------------------------------------------------
    "custom_field_service": ("Layanan Lapangan",
        "Penugasan teknisi, work order di lokasi, pemakaian material, dan tanda tangan pelanggan."),
    "custom_helpdesk": ("Helpdesk & SLA",
        "Alur tiket dengan SLA, eskalasi, dan portal pelanggan."),
    "custom_ops_reports": ("Laporan Operasional Armada",
        "Opname aset, pergerakan per event, suku cadang, kesehatan pemeliharaan, dan riwayat perbaikan."),
    "custom_project_api": ("API PMO",
        "Permukaan REST ber-JWT dan HMAC untuk aplikasi VAS PMO."),
    "custom_project_cr": ("Change Request Proyek",
        "Change Request sebagai record tersendiri: triase, analisis dampak, persetujuan berjenjang."),
    "custom_project_notify": ("Notifikasi Proyek",
        "Notifikasi berbasis aturan untuk proyek, CR, task, dan progres mingguan."),
    "custom_project_portfolio": ("Portofolio Proyek & SLA",
        "Vertikal brand, portofolio, sprint mingguan, dan tahap Hold/WUV dengan jam SLA."),
    "custom_rental": ("Penyewaan Aset",
        "Siklus sewa: tarif bertingkat, jadwal, BAST, denda keterlambatan, portal, dan pengiriman stok."),
    "custom_rental_bom_explosion": ("Paket Sewa via BOM",
        "Membundel drone dan perangkat lewat BOM kit, mengisi baris BAST otomatis."),
    "custom_rental_invoicing": ("Penagihan Sewa",
        "Membuat faktur saat barang sewa kembali: biaya sewa, denda, dan kerusakan."),
    "custom_rental_quality_hook": ("Pemeriksaan Kualitas Sewa",
        "Quality check otomatis saat pengembalian, menautkan aset sewa ke equipment pemeliharaan."),
    "custom_timesheet": ("Timesheet & Penagihan Jasa",
        "Timesheet billable dengan integrasi lembur ke payroll."),

    # ---- ee_gap: manufaktur ------------------------------------------------
    "custom_iot_bridge": ("Jembatan IoT",
        "Menerima pembacaan sensor via webhook, menampilkannya di dashboard dengan alert ambang batas."),
    "custom_maintenance": ("Pemeliharaan Prediktif",
        "Alert IoT, MTBF/MTTR, penjadwalan prediktif, SLA, suku cadang, dan biaya."),
    "custom_mrp_plm": ("Manajemen Siklus Produk (PLM)",
        "Alur ECO, versi BoM, dan perubahan yang dikunci persetujuan."),
    "custom_quality_full": ("Manajemen Kualitas",
        "Quality point, pemeriksaan, alert NCR, tanda tangan, CAPA, dan template uji."),
    "custom_repairs": ("Perbaikan Aset",
        "Perbaikan aset internal yang terhubung ke equipment dan permintaan pemeliharaan."),

    # ---- ee_gap: produktivitas --------------------------------------------
    "custom_ai_features": ("Fitur AI Terpadu",
        "Ask AI di mana saja, inbox anomali, chat bahasa alami ke data, dan klasifikasi dokumen otomatis."),
    "custom_dashboards": ("Dashboard KPI",
        "Dashboard berbasis ubin dengan kueri bahasa alami."),
    "custom_data_cleaning": ("Pembersihan Data",
        "Aturan deduplikasi dan normalisasi format Indonesia (nomor telepon, NIK)."),
    "custom_documents": ("Manajemen Dokumen",
        "Workspace, penandaan, versi, dan akses yang sadar klasifikasi PDP."),
    "custom_knowledge": ("Basis Pengetahuan",
        "Wiki internal ringan dengan template dan versi artikel."),
    "custom_sign": ("Tanda Tangan Elektronik",
        "Alur tanda tangan multi-penandatangan dengan portal bertoken."),
    "custom_spreadsheet": ("Spreadsheet Terintegrasi",
        "Lapisan workbook dengan impor/ekspor CSV, bantuan AI, versi, dan berbagi."),
    "custom_studio_lite": ("Studio Lite",
        "Pengelola field kustom dan ekstensi tampilan secara deklaratif."),
    "custom_todo": ("Daftar Tugas Pribadi",
        "Timer pomodoro, pemecahan tugas oleh AI, dan template berulang."),

    # ---- ee_gap: pemasaran -------------------------------------------------
    "custom_affiliate": ("Program Afiliasi",
        "Tautan terlacak, penangkapan klik, atribusi pesanan, komisi, dan pembayaran."),
    "custom_appointments": ("Reservasi Janji Temu",
        "Pemesanan publik dan kalender internal dengan ketersediaan sumber daya."),
    "custom_email_marketing": ("Email Marketing",
        "Galeri template, uji A/B, dan berhenti berlangganan yang patuh UU PDP."),
    "custom_events": ("Manajemen Event",
        "Tiket WhatsApp ber-QR, check-in QR, sponsor, track, survei pasca-acara, dan waiting list."),
    "custom_forum": ("Forum Komunitas",
        "Moderasi AI, gamifikasi, dan penyamaran identitas penulis sesuai PDP."),
    "custom_livechat": ("Live Chat",
        "Eskalasi ke helpdesk, jawaban siap pakai, chatbot, routing keahlian, dan saran balasan AI."),
    "custom_marketing_automation": ("Marketing Automation",
        "Kampanye multi-langkah, rangkaian drip, dan segmentasi audiens."),
    "custom_sms_id": ("SMS Indonesia",
        "Adapter Zenziva dan Twilio dengan gerbang persetujuan PDP untuk pesan pemasaran."),
    "custom_social": ("Media Sosial",
        "Pengelolaan akun dan penjadwalan unggahan media sosial."),
    "custom_survey": ("Survei & NPS",
        "Pulse karyawan, NPS pelanggan, sertifikasi, dan survei terkait penilaian kinerja."),
    "custom_voip": ("Telepon & VoIP",
        "Click-to-call dan pencatatan panggilan dengan beberapa adapter SIP/PBX."),
    "custom_whatsapp": ("WhatsApp Bisnis",
        "Adapter Meta WhatsApp Cloud API dengan manajemen template dan antrean keluar bergerbang PDP."),

    # ---- ee_gap: fondasi ---------------------------------------------------
    "authenticate_keycloak": ("Autentikasi Keycloak",
        "Alur OAuth2 authorization code (confidential client) di atas auth_oauth Odoo."),
    "custom_operating_unit_docs": ("Pembatasan Data per Unit Operasional",
        "Menempelkan unit operasional pada dokumen akuntansi, gudang, pembelian dan "
        "penjualan, lalu membatasi baca maupun tulisnya per unit."),
    "custom_approval_engine": ("Mesin Persetujuan",
        "Persetujuan berjenjang generik dengan delegasi, mode cuti, dan eskalasi SLA."),
    "custom_esb_connector": ("Konektor ESB Core",
        "Adapter REST bersesi ke ESB Core/OMS, mirror master data, snapshot stok, dan outbox dokumen."),
    "custom_report_templates": ("Template Laporan Berbranding",
        "Tata letak PDF faktur, penawaran, dan PO dengan branding per tenant."),

    # ---- operations --------------------------------------------------------
    "custom_brd_analyzer": ("Analisis Kesenjangan BRD",
        "Analisis dokumen kebutuhan bisnis berbantuan AI terhadap katalog kapabilitas modul."),
    "custom_dev_cycle": ("Pelacakan Siklus Pengembangan",
        "Pelacakan siklus dev penuh dengan webhook pull request dan CI dari GitHub/GitLab."),
    "custom_ops_monitor": ("Monitor Operasi & Kapasitas",
        "Kesehatan server dan prakiraan kapasitas untuk operasi multi-tenant."),

    # ---- verticals ---------------------------------------------------------
    "custom_fnb_stock_ops": ("Operasi Stok F&B",
        "Stock opname, prakiraan permintaan, dan replenishment otomatis untuk outlet F&B di atas ESB Core."),
    "custom_ppob_biller_digiflazz": ("Biller Digiflazz",
        "Adapter H2H Digiflazz untuk topup prabayar dan pembayaran tagihan, idempoten lewat ref_id."),
    "custom_ppob_commission": ("Komisi PPOB",
        "Komisi dua arah: pendapatan dari provider dan rebate ke mitra, dengan pemotongan PPh 23."),
    "custom_ppob_core": ("Fondasi PPOB",
        "Partner mitra dan provider, katalog produk, tingkatan harga, dan kerangka pemetaan CoA."),
    "custom_ppob_eraspace_bridge": ("Jembatan ERASPACE",
        "Mencerminkan feed POS dan H2H ERASPACE ke Odoo Finance lewat dua kanal ingest ber-HMAC."),
    "custom_ppob_oracle_bridge": ("Jembatan Oracle EVShop",
        "Menghubungkan suite PPOB ke pipeline Oracle EVShop lama lewat stored procedure dan polling status."),
    "custom_ppob_pps_gateway": ("Gateway PPS (H2H Masuk)",
        "Mengekspos API H2H PPS/EVShop sehingga POS ERASPACE bertransaksi ke Odoo sebagai switcher."),
    "custom_ppob_provider": ("Provider & Stok Denom",
        "Master provider, inventori bucket atomik, pemetaan SKU, dan topup deposit DP 100%."),
    "custom_ppob_rollup": ("Rollup Harian PPOB",
        "Agregasi transaksi sukses menjadi satu sales order dan faktur ringkas per mitra untuk e-Faktur."),
    "custom_ppob_sale": ("Transaksi PPOB",
        "State machine transaksi, penarikan dompet dan bucket secara atomik, dispatch provider, PPN margin PMK-63."),
    "custom_ppob_sla": ("SLA & Throughput PPOB",
        "Target throughput dan latensi per provider, dengan pengambilan sampel tiap jam."),
    "custom_ppob_va": ("Virtual Account Mitra",
        "Virtual account mitra dan topup dompet lewat callback H2H bank serta rekonsiliasi CSV."),
    "custom_ppob_wallet": ("Dompet Prabayar Mitra",
        "Dompet mitra dengan primitif debit/kredit atomik terkunci baris dan buku besar GL berpasangan."),
    "custom_vertical_example": ("Template Vertikal",
        "Modul rujukan sebagai titik awal membangun vertikal baru."),
}


def id_labels(name: str, manifest: dict) -> dict:
    """Indonesian display name and summary, falling back to the manifest.

    The fallback is marked so an untranslated entry is visible in the rendered
    document instead of quietly mixing languages.
    """
    entry = ID_LABELS.get(name)
    if entry:
        return {"nama": entry[0], "ringkasan": entry[1], "translated": True}
    return {
        "nama": f"[EN] {manifest.get('name') or name}",
        "ringkasan": f"[EN] {manifest.get('summary') or ''}".strip(),
        "translated": False,
    }


# --- gap register -----------------------------------------------------------


def load_gaps(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    gaps = data.get("gaps") or []
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(gaps, key=lambda g: (order.get(g.get("severity"), 9), g.get("id", "")))
