# -*- coding: utf-8 -*-
# License: LGPL-3
{
    "name": "Custom HHT Bridge",
    "summary": "Handheld Terminal bridge: PWA shell + secure REST API + offline sync (Zebra/DataWedge)",
    "description": """
Handheld Terminal Integration Bridge
====================================
Brings physical handheld scanners (Zebra TC-series, Honeywell, generic Android
with DataWedge / keyboard wedge) into the Odoo platform.

Provides:
- ``hht.device``: enrolled device registry with HMAC api_key/secret + CIDR whitelist.
- ``hht.scan.log``: append-only audit log of every scan with GPS + signature.
- ``hht.sync.queue``: FIFO journal of events queued by the PWA while offline.
- PWA shell mounted at ``/hht/`` (manifest.webmanifest, Service Worker, OWL app).
- REST API ``/api/hht/*`` guarded by ``@secure_endpoint('hht')`` (HMAC-SHA256 +
  timestamp drift + nonce replay + CIDR allow-list).
- DataWedge ingest endpoint for thin scanners.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Inventory/Mobile",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": [
        "custom_core",
        "custom_pdp_audit",
        "custom_bast",
        "custom_barcode",
        "stock",
        "mail",
        "web",
    ],
    "capability_tags": ["hht", "barcode-scan", "wms", "audit-trail", "multi-tenant"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_config_parameter_data.xml",
        "data/cron.xml",
        "views/hht_device_views.xml",
        "views/hht_scan_log_views.xml",
        "views/hht_sync_queue_views.xml",
        "views/hht_shell_layout_views.xml",
        "wizards/regenerate_secret_wizard_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_hht_bridge/static/src/scss/hht_shell.scss",
        ],
        "custom_hht_bridge.pwa_assets": [
            ("include", "web._assets_helpers"),
            ("include", "web._assets_backend_helpers"),
            "web/static/lib/odoo_ui_icons/*",
            "web/static/src/scss/primary_variables.scss",
            "web/static/src/scss/bootstrap_overridden.scss",
            "web/static/src/libs/fontawesome/css/font-awesome.css",
            "custom_hht_bridge/static/src/scss/hht_shell.scss",
            "custom_hht_bridge/static/src/js/hht_shell/crypto.js",
            "custom_hht_bridge/static/src/js/hht_shell/sync_queue.js",
            "custom_hht_bridge/static/src/js/hht_shell/pages/ReceivePage.js",
            "custom_hht_bridge/static/src/js/hht_shell/pages/IssuePage.js",
            "custom_hht_bridge/static/src/js/hht_shell/pages/TransferPage.js",
            "custom_hht_bridge/static/src/js/hht_shell/pages/CountPage.js",
            "custom_hht_bridge/static/src/js/hht_shell/pages/HandoverPage.js",
            "custom_hht_bridge/static/src/js/hht_shell/pages/pages.xml",
            "custom_hht_bridge/static/src/js/hht_shell/hht_shell.js",
            "custom_hht_bridge/static/src/js/hht_shell/hht_shell.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
