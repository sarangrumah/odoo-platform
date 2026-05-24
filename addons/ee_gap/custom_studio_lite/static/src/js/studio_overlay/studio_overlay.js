/** @odoo-module **/
/*
 * Studio overlay — Phase 4b.
 *
 * When the systray flips studio mode on, this component:
 *   1. Reads the currently active view via the action service
 *      (resModel + viewId from action.currentController.props).
 *   2. Slides a sidebar in from the right listing all fields on the
 *      model that are not already on the current view (drag sources).
 *   3. Installs a document-level drag-over/drop delegator that
 *      paints drop indicators on existing rendered fields
 *      (``.o_field_widget[name]``) and queues an add_field op
 *      anchored after whichever field receives the drop.
 *   4. Persists each drop as a studio.view.customization operation
 *      via the same backend used by Phase 2 — then reloads the
 *      action so the form re-renders with the new arch.
 *
 * Caveats vs. Enterprise Studio:
 *   - We don't (yet) detect group / notebook ancestry; the op anchor
 *     is just the field name and we rely on the server-side
 *     ``<xpath expr="//field[@name='anchor']" position="after">``.
 *     For Phase 4b that's good enough; Phase 4c can add nested
 *     group/page resolution.
 *   - No properties panel / no inline label editing — drop-only.
 *   - Click-to-hide still goes through the click handler on
 *     decorated fields.
 */
import { Component, useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const FIELD_SELECTOR = ".o_field_widget[name]";

export class StudioOverlay extends Component {
    static template = "custom_studio_lite.StudioOverlay";
    static props = {};

    setup() {
        this.overlayService = useService("studio_overlay");
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");

        // OWL reactivity rule: a component only re-renders when it
        // accesses the reactive via its OWN useState wrapper. Without
        // this line, toggling overlayService.state.active would mutate
        // the value but never trigger a re-render here.
        this.overlayState = useState(this.overlayService.state);

        this.state = useState({
            currentModel: null,
            currentViewId: null,
            currentViewName: "",
            availableFields: [],
            inViewFields: [],
            filter: "",
            saving: false,
            selectedField: null,
        });

        // React to studio-mode toggle: initialise + install listeners
        // when active, tear them down when not.
        useEffect(
            () => {
                if (this.isActive) {
                    document.body.classList.add("o_studio_active");
                    this._initialize();
                    const cleanup = this._installDelegatedListeners();
                    return () => {
                        document.body.classList.remove("o_studio_active");
                        cleanup();
                    };
                }
                return () => {};
            },
            () => [this.isActive],
        );
    }

    get isActive() {
        return this.overlayState.active;
    }

    /** Snapshot the current view + field lists when studio mode is enabled. */
    async _initialize() {
        const ctrl = this.action.currentController;
        if (!ctrl || !ctrl.props || !ctrl.props.resModel) {
            this.notification.add(
                _t("Open a form / list / kanban first, then activate Studio."),
                { type: "warning" },
            );
            this.overlayService.deactivate();
            return;
        }
        this.state.currentModel = ctrl.props.resModel;
        this.state.currentViewId = await this._resolveViewId(ctrl);
        this.state.currentViewName =
            (ctrl.props.viewType ? `[${ctrl.props.viewType}] ` : "") +
            (ctrl.title || ctrl.displayName || "");

        // Fields displayed on the rendered view, harvested directly
        // from the DOM. Falls back to empty if the view isn't fully
        // mounted yet (rare race).
        const renderedFieldNames = this._readRenderedFieldNames();
        this.state.inViewFields = renderedFieldNames;

        // All fields on the model, sourced from ir.model.fields.
        const all = await this.orm.searchRead(
            "ir.model.fields",
            [["model", "=", this.state.currentModel]],
            ["id", "name", "field_description", "ttype"],
            { order: "field_description", limit: 500 },
        );
        const displayedSet = new Set(renderedFieldNames);
        this.state.availableFields = all.filter((f) => !displayedSet.has(f.name));
    }

    /** Resolve the view id of the currently-rendered view via three
     *  fallbacks. Many actions don't set props.viewId directly (it's
     *  derived from the action's ``views`` tuple list). When the action
     *  itself is opaque (search/global filter results), fall back to
     *  an ir.ui.view RPC matching model + type. */
    async _resolveViewId(ctrl) {
        if (ctrl.props.viewId) return ctrl.props.viewId;
        const viewType = ctrl.props.viewType;
        // ctrl.props.views shape: [[id, type], [id|false, type], ...]
        const fromProps = (ctrl.props.views || []).find(
            ([, type]) => type === viewType,
        );
        if (fromProps && fromProps[0]) return fromProps[0];
        // ctrl.action.views same shape — fallback when ctrl.props lacks it
        const fromAction =
            ctrl.action && (ctrl.action.views || []).find(([, type]) => type === viewType);
        if (fromAction && fromAction[0]) return fromAction[0];
        // Last resort: RPC for the primary view of (model, type).
        try {
            const rows = await this.orm.searchRead(
                "ir.ui.view",
                [
                    ["model", "=", ctrl.props.resModel],
                    ["type", "=", viewType],
                    ["inherit_id", "=", false],
                ],
                ["id"],
                { limit: 1, order: "priority, id" },
            );
            return rows.length ? rows[0].id : null;
        } catch (e) {
            return null;
        }
    }

    _readRenderedFieldNames() {
        const names = [];
        for (const el of document.querySelectorAll(FIELD_SELECTOR)) {
            const n = el.getAttribute("name");
            if (n && !names.includes(n)) names.push(n);
        }
        return names;
    }

    // ----- Sidebar drag source -----

    onDragStart(fieldName, ev) {
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("application/x-studio-field", fieldName);
        ev.dataTransfer.setData("text/plain", fieldName);
    }

    // ----- Document-level drag delegate -----

    _installDelegatedListeners() {
        const onOver = (ev) => {
            if (!ev.dataTransfer.types.includes("application/x-studio-field")) return;
            const target = ev.target.closest(FIELD_SELECTOR);
            if (!target) return;
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "copy";
            document
                .querySelectorAll(".o_studio_drag_over")
                .forEach((el) => el.classList.remove("o_studio_drag_over"));
            target.classList.add("o_studio_drag_over");
        };

        const onLeave = (ev) => {
            const target = ev.target.closest(FIELD_SELECTOR);
            if (target) target.classList.remove("o_studio_drag_over");
        };

        const onDrop = async (ev) => {
            if (!ev.dataTransfer.types.includes("application/x-studio-field")) return;
            const target = ev.target.closest(FIELD_SELECTOR);
            if (!target) return;
            ev.preventDefault();
            ev.stopPropagation();
            target.classList.remove("o_studio_drag_over");
            const newField =
                ev.dataTransfer.getData("application/x-studio-field") ||
                ev.dataTransfer.getData("text/plain");
            const anchor = target.getAttribute("name");
            if (newField && anchor) {
                await this._queueAddField(newField, anchor);
            }
        };

        // Field click → mark as selected (visual feedback only for now).
        const onFieldClick = (ev) => {
            const target = ev.target.closest(FIELD_SELECTOR);
            if (!target) return;
            document
                .querySelectorAll(".o_studio_selected")
                .forEach((el) => el.classList.remove("o_studio_selected"));
            target.classList.add("o_studio_selected");
            this.state.selectedField = target.getAttribute("name");
        };

        document.body.addEventListener("dragover", onOver);
        document.body.addEventListener("dragleave", onLeave);
        document.body.addEventListener("drop", onDrop);
        document.body.addEventListener("click", onFieldClick, true);

        return () => {
            document.body.removeEventListener("dragover", onOver);
            document.body.removeEventListener("dragleave", onLeave);
            document.body.removeEventListener("drop", onDrop);
            document.body.removeEventListener("click", onFieldClick, true);
            document
                .querySelectorAll(".o_studio_drag_over, .o_studio_selected")
                .forEach((el) =>
                    el.classList.remove("o_studio_drag_over", "o_studio_selected"),
                );
        };
    }

    // ----- Persist + apply -----

    async _queueAddField(fieldName, anchorName) {
        // Re-resolve at drop-time in case the user dragged before
        // _initialize() finished, OR the active controller changed
        // (e.g. they navigated while studio was open).
        if (!this.state.currentViewId) {
            const ctrl = this.action.currentController;
            if (ctrl && ctrl.props && ctrl.props.resModel) {
                this.state.currentViewId = await this._resolveViewId(ctrl);
            }
        }
        if (!this.state.currentViewId) {
            this.notification.add(
                _t(
                    "Cannot detect the current view id. Model=%s, type=%s — please report.",
                    this.state.currentModel || "?",
                    (this.action.currentController &&
                        this.action.currentController.props &&
                        this.action.currentController.props.viewType) || "?",
                ),
                { type: "danger", sticky: true },
            );
            return;
        }
        this.state.saving = true;
        try {
            // Re-use any existing customization for this view so multiple
            // drops accumulate into one inheritance instead of fanning out.
            const existing = await this.orm.searchRead(
                "studio.view.customization",
                [["target_view_id", "=", this.state.currentViewId]],
                ["id"],
                { limit: 1, order: "id desc" },
            );

            const op = {
                op_type: "add_field",
                field_name: fieldName,
                anchor_field: anchorName,
                position: "after",
            };

            let custId;
            if (existing.length) {
                custId = existing[0].id;
                await this.orm.write("studio.view.customization", [custId], {
                    operation_ids: [[0, 0, op]],
                });
            } else {
                custId = await this.orm.create("studio.view.customization", [
                    {
                        name: `Studio overlay edits — view ${this.state.currentViewId}`,
                        target_view_id: this.state.currentViewId,
                        operation_ids: [[0, 0, op]],
                    },
                ]);
                custId = Array.isArray(custId) ? custId[0] : custId;
            }

            await this.orm.call("studio.view.customization", "action_apply", [
                [custId],
            ]);

            const [persisted] = await this.orm.read(
                "studio.view.customization",
                [custId],
                ["state", "last_error"],
            );

            if (persisted.state === "applied") {
                this.notification.add(
                    _t("Added %s after %s — reloading view…", fieldName, anchorName),
                    { type: "success" },
                );
                // Reload the action so the form picks up the new arch.
                // softReload would be ideal; restore() + the form's own
                // load cycle is the cleanest cross-version option.
                await this.action.doAction(
                    this.action.currentController.action,
                    { clearBreadcrumbs: false },
                );
                await this._initialize();
            } else {
                this.notification.add(
                    _t("Apply failed: %s", persisted.last_error || "unknown"),
                    { type: "danger", sticky: true },
                );
            }
        } catch (e) {
            this.notification.add(
                _t("Drop failed: %s", e.message || String(e)),
                { type: "danger", sticky: true },
            );
        } finally {
            this.state.saving = false;
        }
    }

    async hideSelectedField() {
        if (!this.state.selectedField) return;
        if (!this.state.currentViewId) return;
        this.state.saving = true;
        try {
            const existing = await this.orm.searchRead(
                "studio.view.customization",
                [["target_view_id", "=", this.state.currentViewId]],
                ["id"],
                { limit: 1, order: "id desc" },
            );
            const op = {
                op_type: "hide_field",
                field_name: this.state.selectedField,
                anchor_field: "",
                position: "after",
            };
            let custId;
            if (existing.length) {
                custId = existing[0].id;
                await this.orm.write("studio.view.customization", [custId], {
                    operation_ids: [[0, 0, op]],
                });
            } else {
                custId = await this.orm.create("studio.view.customization", [
                    {
                        name: `Studio overlay edits — view ${this.state.currentViewId}`,
                        target_view_id: this.state.currentViewId,
                        operation_ids: [[0, 0, op]],
                    },
                ]);
                custId = Array.isArray(custId) ? custId[0] : custId;
            }
            await this.orm.call("studio.view.customization", "action_apply", [
                [custId],
            ]);
            this.notification.add(
                _t("Hid %s — reloading view…", this.state.selectedField),
                { type: "success" },
            );
            await this.action.doAction(
                this.action.currentController.action,
                { clearBreadcrumbs: false },
            );
            this.state.selectedField = null;
            await this._initialize();
        } catch (e) {
            this.notification.add(_t("Hide failed: %s", e.message || String(e)), {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.saving = false;
        }
    }

    close() {
        this.overlayService.deactivate();
    }

    /** Filtered subset of availableFields shown in the sidebar. */
    get filteredFields() {
        const q = (this.state.filter || "").toLowerCase().trim();
        if (!q) return this.state.availableFields;
        return this.state.availableFields.filter(
            (f) =>
                f.name.toLowerCase().includes(q) ||
                (f.field_description || "").toLowerCase().includes(q),
        );
    }
}

registry.category("main_components").add("custom_studio_lite.studio_overlay", {
    Component: StudioOverlay,
});
