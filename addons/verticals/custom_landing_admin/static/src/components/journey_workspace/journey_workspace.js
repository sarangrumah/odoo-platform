/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { api } from "../../services/api";
import { BrdUpload } from "../brd_upload/brd_upload";

const TABS = [
    { key: "brd", label: "BRD AI Analysis" },
    { key: "recommendations", label: "Recommendations" },
    { key: "vps", label: "VPS" },
    { key: "modules", label: "Modules" },
    { key: "devcycles", label: "Dev Cycles" },
    { key: "tasks", label: "Project Tasks" },
    { key: "activity", label: "Activity" },
];

/**
 * Workspace for a single ``onboarding.journey`` record.
 *
 * Sidebar shows journey info + smart links; tabs render lazily on
 * activation. All data fetches are best-effort — a missing related
 * model only blanks the tab instead of failing the whole workspace.
 */
export class JourneyWorkspace extends Component {
    static template = "custom_landing_admin.JourneyWorkspace";
    static components = { BrdUpload };
    static props = {
        journeyId: { type: [String, Number] },
        onBack: { type: Function, optional: true },
    };

    setup() {
        this.tabs = TABS;
        this.state = useState({
            loading: true,
            journey: null,
            activeTab: "brd",
            brds: [],
            recommendations: [],
            vpsList: [],
            modules: [],
            devCycles: [],
            tasks: [],
            activity: [],
        });
        onWillStart(() => this._loadJourney());
        onWillUpdateProps((next) => {
            if (next.journeyId !== this.props.journeyId) {
                this._loadJourney(next.journeyId);
            }
        });
    }

    async _loadJourney(id) {
        const jid = parseInt(id ?? this.props.journeyId, 10);
        this.state.loading = true;
        const rows = await api.read(
            "onboarding.journey",
            [jid],
            [
                "id", "name", "stage", "vertical", "tenant_name",
                "ba_user_id", "due_date", "priority", "notes",
            ]
        );
        this.state.journey = (rows && rows[0]) || null;
        this.state.loading = false;
        this._loadTab(this.state.activeTab);
    }

    async _loadTab(key) {
        if (!this.state.journey) return;
        const jid = this.state.journey.id;
        const domain = [["journey_id", "=", jid]];
        if (key === "brd") {
            this.state.brds = (await api.searchRead(
                "brd.document", domain,
                ["id", "name", "state", "uploaded_on"],
                { limit: 50, order: "id desc" }
            )) || [];
        } else if (key === "recommendations") {
            this.state.recommendations = (await api.searchRead(
                "onboarding.recommendation", domain,
                ["id", "title", "module_id", "score", "rationale"],
                { limit: 100 }
            )) || [];
        } else if (key === "vps") {
            this.state.vpsList = (await api.searchRead(
                "tenant.vps",
                [["journey_id", "=", jid]],
                ["id", "name", "state", "ip_address", "region"],
                { limit: 20 }
            )) || [];
        } else if (key === "modules") {
            this.state.modules = (await api.searchRead(
                "custom.hub.module.deployment",
                [["journey_id", "=", jid]],
                ["id", "module_id", "state", "canary", "deployed_on"],
                { limit: 200 }
            )) || [];
        } else if (key === "devcycles") {
            this.state.devCycles = (await api.searchRead(
                "onboarding.dev.cycle", domain,
                ["id", "name", "state", "start_date", "end_date"],
                { limit: 50 }
            )) || [];
        } else if (key === "tasks") {
            this.state.tasks = (await api.searchRead(
                "project.task",
                [["onboarding_journey_id", "=", jid]],
                ["id", "name", "stage_id", "user_ids", "date_deadline"],
                { limit: 200 }
            )) || [];
        } else if (key === "activity") {
            this.state.activity = (await api.searchRead(
                "mail.message",
                [["model", "=", "onboarding.journey"], ["res_id", "=", jid]],
                ["id", "subject", "body", "date", "author_id"],
                { limit: 50, order: "date desc" }
            )) || [];
        }
    }

    selectTab(key) {
        this.state.activeTab = key;
        this._loadTab(key);
    }

    onBack() {
        if (this.props.onBack) this.props.onBack();
    }

    onBrdUploaded() {
        this._loadTab("brd");
    }
}
