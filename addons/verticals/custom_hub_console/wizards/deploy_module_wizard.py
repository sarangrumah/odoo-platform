# -*- coding: utf-8 -*-
"""Deploy a catalog module to one or more tenants.

The wizard creates ``custom.hub.module.deployment`` rows and, when
``confirmed`` is checked, immediately fires ``action_deploy()`` on each.
Orchestrator errors are caught inside the deployment model so the wizard
always commits — failures surface on the deployment rows themselves.
"""

from __future__ import annotations

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CustomHubDeployModuleWizard(models.TransientModel):
    _name = "custom.hub.deploy.module.wizard"
    _description = "Deploy Module to Tenant(s) Wizard"

    catalog_id = fields.Many2one(
        "custom.hub.module.catalog", required=True, string="Module",
    )
    tenant_ids = fields.Many2many(
        "tenant.registry",
        relation="custom_hub_deploy_wizard_tenant_rel",
        column1="wizard_id", column2="tenant_id",
        string="Tenants", required=True,
    )
    deploy_mode = fields.Selection(
        [
            ("install", "Install"),
            ("upgrade", "Upgrade"),
            ("uninstall", "Uninstall"),
        ],
        required=True, default="install",
    )
    schedule_at = fields.Datetime(
        help="If set, deployments are recorded but not executed now; an "
             "external scheduler / ops process is expected to pick them up."
    )
    confirmed = fields.Boolean(
        string="I confirm",
        help="Required to actually create deployment rows.",
    )
    note = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        if not self.confirmed:
            raise UserError(_(
                "Please tick the confirmation box before proceeding."
            ))
        if not self.tenant_ids:
            raise UserError(_("Select at least one tenant."))

        Deployment = self.env["custom.hub.module.deployment"].sudo()
        rows = Deployment
        for tenant in self.tenant_ids:
            row = Deployment.create({
                "catalog_id": self.catalog_id.id,
                "tenant_id": tenant.id,
                "deploy_mode": self.deploy_mode,
                "state": "pending",
            })
            rows |= row

        # Fire immediately unless scheduled for later.
        if not self.schedule_at:
            rows.action_deploy()

        return {
            "type": "ir.actions.act_window",
            "name": "Deployments",
            "res_model": "custom.hub.module.deployment",
            "view_mode": "list,form",
            "domain": [("id", "in", rows.ids)],
            "target": "current",
        }
