/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { api } from "../../services/api";

/**
 * Kanban-style pipeline of ``onboarding.journey`` records grouped by
 * ``stage``. Cards are draggable across columns; dropping a card writes
 * the new stage back via ORM.
 */
const DEFAULT_STAGES = [
    { key: "lead", label: "Lead" },
    { key: "brd", label: "BRD" },
    { key: "scoping", label: "Scoping" },
    { key: "provisioning", label: "Provisioning" },
    { key: "uat", label: "UAT" },
    { key: "live", label: "Live" },
];

export class OnboardingPipeline extends Component {
    static template = "custom_landing_admin.OnboardingPipeline";
    static props = {
        onOpenJourney: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            loading: true,
            search: "",
            filterBa: "",
            filterVertical: "",
            stages: DEFAULT_STAGES,
            journeysByStage: {},
            error: null,
        });
        onWillStart(() => this._reload());
    }

    async _reload() {
        this.state.loading = true;
        const domain = this._buildDomain();
        const rows = await api.searchRead(
            "onboarding.journey",
            domain,
            [
                "id", "name", "stage", "vertical", "ba_user_id",
                "tenant_name", "due_date", "priority",
            ],
            { limit: 500, order: "priority desc, id desc" }
        );
        const buckets = {};
        for (const s of this.state.stages) {
            buckets[s.key] = [];
        }
        (rows || []).forEach((r) => {
            const key = r.stage || "lead";
            if (!buckets[key]) {
                buckets[key] = [];
            }
            buckets[key].push(r);
        });
        this.state.journeysByStage = buckets;
        this.state.loading = false;
    }

    _buildDomain() {
        const d = [];
        if (this.state.search) {
            d.push("|");
            d.push(["name", "ilike", this.state.search]);
            d.push(["tenant_name", "ilike", this.state.search]);
        }
        if (this.state.filterBa) {
            d.push(["ba_user_id", "=", parseInt(this.state.filterBa, 10)]);
        }
        if (this.state.filterVertical) {
            d.push(["vertical", "=", this.state.filterVertical]);
        }
        return d;
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    onSearchSubmit(ev) {
        ev.preventDefault();
        this._reload();
    }

    onChangeBa(ev) {
        this.state.filterBa = ev.target.value;
        this._reload();
    }

    onChangeVertical(ev) {
        this.state.filterVertical = ev.target.value;
        this._reload();
    }

    onDragStart(ev, journeyId, fromStage) {
        ev.dataTransfer.setData("text/plain", JSON.stringify({
            id: journeyId, from: fromStage,
        }));
        ev.dataTransfer.effectAllowed = "move";
    }

    onDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
    }

    async onDrop(ev, toStage) {
        ev.preventDefault();
        let payload;
        try {
            payload = JSON.parse(ev.dataTransfer.getData("text/plain"));
        } catch (e) {
            return;
        }
        if (!payload || payload.from === toStage) {
            return;
        }
        const ok = await api.write(
            "onboarding.journey", [payload.id], { stage: toStage }
        );
        if (ok) {
            await this._reload();
        }
    }

    onClickCard(j) {
        if (this.props.onOpenJourney) {
            this.props.onOpenJourney(j.id);
        }
    }
}
