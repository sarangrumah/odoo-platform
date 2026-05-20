/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { api } from "../../services/api";

/**
 * Module catalog + deploy wizard.
 *
 * Reads ``custom.hub.module.catalog`` for the table view, and on
 * "Deploy" opens a modal that lets the operator pick a target tenant
 * and toggle canary mode before creating a ``custom.hub.module.deployment``
 * record.
 */
export class ModuleDeployConsole extends Component {
    static template = "custom_landing_admin.ModuleDeployConsole";
    static props = {};

    setup() {
        this.state = useState({
            loading: true,
            modules: [],
            wizardOpen: false,
            wizardModule: null,
            tenants: [],
            targetTenantId: "",
            canary: false,
            wizardBusy: false,
            wizardError: null,
            wizardOk: null,
        });
        onWillStart(() => this._loadCatalog());
    }

    async _loadCatalog() {
        this.state.loading = true;
        const rows = await api.searchRead(
            "custom.hub.module.catalog", [],
            [
                "id", "technical_name", "display_name", "version",
                "maturity", "category",
            ],
            { limit: 500, order: "display_name asc" }
        );
        this.state.modules = rows || [];
        this.state.loading = false;
    }

    async openWizard(mod) {
        this.state.wizardModule = mod;
        this.state.wizardOpen = true;
        this.state.wizardError = null;
        this.state.wizardOk = null;
        this.state.targetTenantId = "";
        this.state.canary = false;
        const tenants = await api.searchRead(
            "tenant.registry", [["state", "=", "active"]],
            ["id", "name"], { limit: 500, order: "name asc" }
        );
        this.state.tenants = tenants || [];
    }

    closeWizard() {
        this.state.wizardOpen = false;
        this.state.wizardModule = null;
    }

    onChangeTenant(ev) {
        this.state.targetTenantId = ev.target.value;
    }

    onToggleCanary(ev) {
        this.state.canary = ev.target.checked;
    }

    async submitDeploy() {
        if (!this.state.wizardModule || !this.state.targetTenantId) {
            this.state.wizardError = "Pick a target tenant.";
            return;
        }
        this.state.wizardBusy = true;
        this.state.wizardError = null;
        const id = await api.create("custom.hub.module.deployment", {
            module_id: this.state.wizardModule.id,
            tenant_id: parseInt(this.state.targetTenantId, 10),
            canary: this.state.canary,
            state: "queued",
        });
        this.state.wizardBusy = false;
        if (id) {
            this.state.wizardOk =
                `Deployment #${id} queued.`;
        } else {
            this.state.wizardError = "Failed to queue deployment.";
        }
    }
}
