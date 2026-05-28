/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class PdpMaskedField extends Component {
    static template = "custom_pdp_masking.PdpMaskedField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            revealed: false,
            clearValue: null,
            loading: false,
        });
    }

    get maskedValue() {
        const v = this.props.record.data[this.props.name];
        if (v === false || v === null || v === undefined) {
            return "";
        }
        return v;
    }

    get displayValue() {
        if (this.state.revealed && this.state.clearValue !== null) {
            return this.state.clearValue;
        }
        return this.maskedValue;
    }

    async onToggle() {
        if (this.state.loading) {
            return;
        }
        if (this.state.revealed) {
            this.state.revealed = false;
            this.state.clearValue = null;
            return;
        }
        const resId = this.props.record.resId;
        if (!resId) {
            this.notification.add("Save the record before revealing this field.", {
                type: "warning",
            });
            return;
        }
        const reason = window.prompt("Reason for revealing this field (audited):");
        if (!reason || !reason.trim()) {
            return;
        }
        this.state.loading = true;
        try {
            const clear = await this.orm.call(
                "pdp.masking",
                "_reveal_field",
                [this.props.record.resModel, resId, this.props.name, reason.trim()]
            );
            this.state.clearValue = clear === false || clear === null ? "" : clear;
            this.state.revealed = true;
        } catch (e) {
            const msg =
                (e && e.data && e.data.message) ||
                (e && e.message) ||
                "Reveal denied or failed.";
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

export const pdpMaskedField = {
    component: PdpMaskedField,
    displayName: "PDP Masked",
    supportedTypes: ["char", "text", "html"],
};

registry.category("fields").add("pdp_masked_field", pdpMaskedField);
