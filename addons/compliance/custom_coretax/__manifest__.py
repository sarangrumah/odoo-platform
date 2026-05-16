# -*- coding: utf-8 -*-
{
    "name": "Custom Coretax (Indonesia DJP)",
    "summary": "Indonesian Coretax DJP compliance: NSFP, e-Faktur XML export/import, Bukti Potong, Sertel storage",
    "description": """
Custom Coretax — Indonesia DJP Compliance Module
=============================================

Implements the Coretax DJP (Direktorat Jenderal Pajak) compliance surface
for the Custom Odoo 19 Platform, aligned with PER-11/PJ/2025 (effective
22 May 2025).

Features
--------
- NSFP (Nomor Seri Faktur Pajak) lifecycle on `account.move` (17-digit
  format: 2 transaction-code + 2 status-code + 13 serial). NSFP is
  assigned by DJP *after* approval on the Coretax portal; the field is
  empty on draft and filled after submission.
- XML export/import wizards covering the 7 main document types:
  e-Faktur Keluaran, Faktur Masukan, Bupot PPh 21 (Tetap & Bukan Tetap),
  Bupot PPh 23, Bupot PPh 26, Bupot Unifikasi.
- Sertifikat Elektronik (.p12) storage via env-keyed Fernet encryption
  using `custom.ir.config` from `custom_core`.
- Adapter pattern (`custom.coretax.adapter.base`) with a default manual
  upload implementation. Future host-to-host (ASPP) adapters plug in by
  inheriting and switching the `adapter_type` on `custom.coretax.config`.
- Every export / import / sertel access is audit-logged to
  `pdp.audit_log` (append-only, hash-chained — UU 27/2022).

Notes
-----
A public REST API for DJP Coretax B2B integration is not confirmed as of
May 2026. The default workflow is XML upload via the official portal.
XSD files are not bundled — operators must place official XSDs from
`https://www.pajak.go.id/reformdjp/coretax/template-xml-dan-converter-excel-ke-xml`
under `data/xsd/` post-install.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Compliance/Coretax",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core", "account"],
    "data": [
        "security/coretax_security.xml",
        "security/ir.model.access.csv",
        "data/coretax_data.xml",
        # wizard actions first — referenced by config form + menu items
        "wizards/coretax_export_wizard_views.xml",
        "wizards/coretax_import_wizard_views.xml",
        "wizards/coretax_sertel_upload_views.xml",
        "views/coretax_config_views.xml",
        "views/coretax_bukti_potong_views.xml",
        "views/account_move_views.xml",
        "views/menu_views.xml",
    ],
    "external_dependencies": {
        "python": ["lxml", "xmlschema", "cryptography"],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
