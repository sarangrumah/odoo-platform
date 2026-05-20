/** @odoo-module **/

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { api } from "../../services/api";

/**
 * VPS console — list ``tenant.vps`` records, expose lifecycle actions
 * (register / bootstrap / deploy stack / sync addons), and stream the
 * bootstrap log of the selected VPS via 2s polling.
 */
const LOG_POLL_MS = 2000;

export class VpsConsole extends Component {
    static template = "custom_landing_admin.VpsConsole";
    static props = {};

    setup() {
        this.state = useState({
            loading: true,
            vpsList: [],
            selectedId: null,
            detail: null,
            envs: [],
            logTail: "",
            grafanaUrl: "",
            actionBusy: false,
            actionError: null,
        });
        this._logHandle = null;
        onWillStart(() => this._loadList());
        onWillUnmount(() => this._stopLog());
    }

    async _loadList() {
        this.state.loading = true;
        const rows = await api.searchRead(
            "tenant.vps", [],
            [
                "id", "name", "state", "ip_address",
                "region", "provider", "journey_id",
            ],
            { limit: 200, order: "id desc" }
        );
        this.state.vpsList = rows || [];
        this.state.loading = false;
    }

    async openDetail(vps) {
        this.state.selectedId = vps.id;
        const rows = await api.read(
            "tenant.vps", [vps.id],
            [
                "id", "name", "state", "ip_address",
                "region", "provider", "bootstrap_log",
                "grafana_dashboard_url",
            ]
        );
        this.state.detail = (rows && rows[0]) || null;
        this.state.grafanaUrl = (this.state.detail
            && this.state.detail.grafana_dashboard_url) || "";
        this.state.envs = (await api.searchRead(
            "tenant.environment",
            [["vps_id", "=", vps.id]],
            ["id", "name", "key", "value", "is_secret"],
            { limit: 200 }
        )) || [];
        this.state.logTail = (this.state.detail
            && this.state.detail.bootstrap_log) || "";
        this._startLog();
    }

    closeDetail() {
        this._stopLog();
        this.state.selectedId = null;
        this.state.detail = null;
    }

    _startLog() {
        this._stopLog();
        if (!this.state.detail) return;
        this._logHandle = window.setInterval(
            () => this._refreshLog(), LOG_POLL_MS
        );
    }

    _stopLog() {
        if (this._logHandle) {
            window.clearInterval(this._logHandle);
            this._logHandle = null;
        }
    }

    async _refreshLog() {
        if (!this.state.detail) return;
        const rows = await api.read(
            "tenant.vps",
            [this.state.detail.id],
            ["state", "bootstrap_log"]
        );
        if (rows && rows[0]) {
            this.state.detail.state = rows[0].state;
            this.state.logTail = rows[0].bootstrap_log || "";
        }
    }

    async _runAction(method, kwargs = {}) {
        this.state.actionBusy = true;
        this.state.actionError = null;
        try {
            const target = this.state.detail
                ? [this.state.detail.id]
                : [];
            const res = await api.action(
                "tenant.vps", target, method, kwargs
            );
            if (res === null) {
                this.state.actionError = `${method} failed`;
            }
        } finally {
            this.state.actionBusy = false;
        }
        await this._loadList();
        if (this.state.detail) {
            await this.openDetail({ id: this.state.detail.id });
        }
    }

    onRegister() {
        // Register typically opens a wizard; for MVP we just call a
        // server method that creates a draft VPS.
        this._runAction("action_register_vps");
    }
    onBootstrap() { this._runAction("action_bootstrap"); }
    onDeployStack() { this._runAction("action_deploy_stack"); }
    onSyncAddons() { this._runAction("action_sync_addons"); }
}
