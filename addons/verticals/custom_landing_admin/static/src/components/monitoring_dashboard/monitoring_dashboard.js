/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { api } from "../../services/api";

/**
 * Multi-tenant monitoring heatmap.
 *
 * Renders one tile per ``tenant.health`` record (color coded by
 * ``status``) and drills down on click to a placeholder time-series
 * panel (or a Grafana iframe when ``grafana_dashboard_url`` is set on
 * the underlying tenant).
 */
const STATUS_CLASS = {
    healthy: "ok",
    degraded: "warn",
    down: "bad",
    unknown: "unknown",
};

export class MonitoringDashboard extends Component {
    static template = "custom_landing_admin.MonitoringDashboard";
    static props = {};

    setup() {
        this.state = useState({
            loading: true,
            tiles: [],
            drillId: null,
            drill: null,
        });
        onWillStart(() => this._load());
    }

    async _load() {
        this.state.loading = true;
        const rows = await api.searchRead(
            "tenant.health", [],
            [
                "id", "tenant_id", "status",
                "cpu_pct", "mem_pct", "disk_pct",
                "last_check",
            ],
            { limit: 200, order: "status desc, id asc" }
        );
        this.state.tiles = (rows || []).map((r) => ({
            ...r,
            tenantName: r.tenant_id ? r.tenant_id[1] : "—",
            klass: STATUS_CLASS[r.status] || "unknown",
        }));
        this.state.loading = false;
    }

    async openDrill(tile) {
        this.state.drillId = tile.id;
        const tenantId = tile.tenant_id && tile.tenant_id[0];
        if (!tenantId) {
            this.state.drill = { ...tile, grafanaUrl: "" };
            return;
        }
        const trows = await api.read(
            "tenant.registry", [tenantId],
            ["id", "name", "grafana_dashboard_url"]
        );
        const t = (trows && trows[0]) || {};
        this.state.drill = {
            ...tile,
            grafanaUrl: t.grafana_dashboard_url || "",
            tenantName: t.name || tile.tenantName,
        };
    }

    closeDrill() {
        this.state.drillId = null;
        this.state.drill = null;
    }
}
