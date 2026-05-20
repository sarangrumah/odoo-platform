# -*- coding: utf-8 -*-
{
    "name": "Custom Landing Admin (OWL)",
    "summary": "Modern OWL landing console for the odoo-mgmt instance",
    "description": """
Custom Landing Admin
====================

OWL-based custom apps shell for the internal admin landing experience.
Renders a top-nav + sidebar layout under ``/landing/*`` that replaces the
standard Odoo backend chrome with a modern, single-page console.

Components:

* Onboarding Pipeline (kanban / drag-drop across stages)
* Journey Workspace (BRD, Recommendations, VPS, Modules, Tasks, Activity)
* BRD Upload (drag-drop multi-file, status streaming)
* VPS Console (register, bootstrap, deploy stack, sync addons)
* Monitoring Dashboard (multi-tenant heatmap, drill-down)
* Module Deploy Console (catalog + canary deploy wizard)

**Only install on the ``odoo-mgmt`` instance.** This module assumes the
companion management-side models from the onboarding lifecycle tracks
are present (``onboarding.journey``, ``brd.document``, ``tenant.vps``,
``custom.hub.module.catalog`` …).
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Hub",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": [
        "web",
        "custom_onboarding_journey",
        "custom_tenant_infra",
        "custom_ops_monitor",
        "custom_hub_console",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_landing_admin/static/src/main.js",
            "custom_landing_admin/static/src/services/api.js",
            "custom_landing_admin/static/src/services/landing_router.js",
            "custom_landing_admin/static/src/components/onboarding_pipeline/onboarding_pipeline.js",
            "custom_landing_admin/static/src/components/onboarding_pipeline/onboarding_pipeline.xml",
            "custom_landing_admin/static/src/components/onboarding_pipeline/onboarding_pipeline.scss",
            "custom_landing_admin/static/src/components/journey_workspace/journey_workspace.js",
            "custom_landing_admin/static/src/components/journey_workspace/journey_workspace.xml",
            "custom_landing_admin/static/src/components/journey_workspace/journey_workspace.scss",
            "custom_landing_admin/static/src/components/brd_upload/brd_upload.js",
            "custom_landing_admin/static/src/components/brd_upload/brd_upload.xml",
            "custom_landing_admin/static/src/components/brd_upload/brd_upload.scss",
            "custom_landing_admin/static/src/components/vps_console/vps_console.js",
            "custom_landing_admin/static/src/components/vps_console/vps_console.xml",
            "custom_landing_admin/static/src/components/vps_console/vps_console.scss",
            "custom_landing_admin/static/src/components/monitoring_dashboard/monitoring_dashboard.js",
            "custom_landing_admin/static/src/components/monitoring_dashboard/monitoring_dashboard.xml",
            "custom_landing_admin/static/src/components/monitoring_dashboard/monitoring_dashboard.scss",
            "custom_landing_admin/static/src/components/module_deploy_console/module_deploy_console.js",
            "custom_landing_admin/static/src/components/module_deploy_console/module_deploy_console.xml",
            "custom_landing_admin/static/src/components/module_deploy_console/module_deploy_console.scss",
            "custom_landing_admin/static/src/scss/landing_theme.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
