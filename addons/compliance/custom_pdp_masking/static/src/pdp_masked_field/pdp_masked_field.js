/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, useEffect } from "@odoo/owl";
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
            clearValue: null, // audited clear value once revealed
            loading: false,
            dirty: false, // user has typed since load/reveal
            editBuffer: "", // live value the user is editing (only used while dirty)
        });

        // Reset widget state when we navigate to another record, or when the
        // record transitions dirty -> clean (a save/discard happened). The
        // record object is mutated in place, so we compare against previously
        // seen primitive values rather than against this.props.
        this._prevResId = this.props.record.resId;
        this._prevDirty = this.props.record.dirty;
        useEffect(
            () => {
                const id = this.props.record.resId;
                const d = this.props.record.dirty;
                const switched = id !== this._prevResId;
                const savedOrDiscarded = this._prevDirty && !d;
                if (switched || savedOrDiscarded) {
                    this.state.revealed = false;
                    this.state.clearValue = null;
                    this.state.dirty = false;
                    this.state.editBuffer = "";
                }
                this._prevResId = id;
                this._prevDirty = d;
            },
            () => [this.props.record.resId, this.props.record.dirty]
        );
    }

    // ---- helpers -----------------------------------------------------

    get isCreate() {
        return !this.props.record.resId;
    }

    get rawValue() {
        // In edit mode this is the MASKED value; in create mode it is the
        // real (unmasked) value the user typed. Used only for display in
        // readonly mode, as a placeholder in edit mode, or as the live value
        // in create mode.
        const v = this.props.record.data[this.props.name];
        if (v === false || v === null || v === undefined) {
            return "";
        }
        return v;
    }

    get isTextarea() {
        const field = this.props.record.fields[this.props.name];
        return field && field.type !== "char";
    }

    // ---- display getters --------------------------------------------

    // Readonly span text: revealed clear value if revealed, else masked.
    get displayValue() {
        if (this.state.revealed && this.state.clearValue !== null) {
            return this.state.clearValue;
        }
        return this.rawValue;
    }

    // Value bound to the editable input/textarea. NEVER the masked record
    // value in edit mode -- only user-typed or revealed-clear text. This is
    // what guarantees an untouched existing record is never overwritten with
    // its own mask.
    get inputValue() {
        if (this.state.revealed && this.state.clearValue !== null && !this.state.dirty) {
            return this.state.clearValue;
        }
        if (this.state.dirty) {
            return this.state.editBuffer;
        }
        if (this.isCreate) {
            return this.rawValue; // real value; reflects onchange-populated data
        }
        return ""; // edit mode, untouched -> empty; mask shown as placeholder
    }

    // Placeholder shows the current masked value in edit mode so the user can
    // see the existing (masked) content without it being editable text.
    get inputPlaceholder() {
        if (this.isCreate || this.state.dirty || this.state.revealed) {
            return "";
        }
        return this.rawValue; // the masked string, e.g. "08••••1234"
    }

    // ---- editing -----------------------------------------------------

    onInput(ev) {
        // Local only: never write to the record on every keystroke.
        this.state.editBuffer = ev.target.value;
        this.state.dirty = true;
    }

    onChange(ev) {
        // Commit on blur / Enter, mirroring useInputField.
        if (!this.state.dirty) {
            // Never touched -> do NOT write, so the real stored value (hidden
            // behind the mask) is preserved.
            return;
        }
        const value = ev.target.value;
        this.state.editBuffer = value;
        this.props.record.update({ [this.props.name]: value === "" ? false : value });
    }

    // ---- reveal ------------------------------------------------------

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
                "reveal_field",
                [this.props.record.resModel, resId, this.props.name, reason.trim()]
            );
            const clearStr = clear === false || clear === null ? "" : clear;
            this.state.clearValue = clearStr;
            this.state.revealed = true;
            // Seed the editable buffer so the input now shows/edits the real
            // value. Revealing is not itself an edit, so keep dirty=false until
            // the user actually types.
            this.state.editBuffer = clearStr;
            this.state.dirty = false;
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
