/** @odoo-module **/
/*
 * Studio systray — paintbrush button in the top bar that opens the
 * visual view editor scoped to whichever view is currently visible.
 *
 * Phase 4a deliverable. We don't (yet) do true inline drag-drop on the
 * live view like Enterprise Studio; instead this is a one-click route
 * from any record/list/kanban/form straight into our existing OWL
 * editor, with the current view + model pre-selected. The user edits,
 * saves, navigates back via breadcrumb — the original page reloads
 * picking up the new inheritance.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class StudioSystrayItem extends Component {
    static template = "custom_studio_lite.StudioSystrayItem";
    static props = {};

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.user = useService("user");
    }

    /**
     * Look up the currently active controller and return the bits the
     * editor needs to preselect (model + view id). Falls back to a
     * generic editor if no view is identifiable.
     */
    _currentViewContext() {
        const ctrl = this.action.currentController;
        if (!ctrl || !ctrl.props) {
            return {};
        }
        const props = ctrl.props;
        // resModel + viewType are reliable on every view controller.
        // viewId is set when the controller picked a specific view
        // (otherwise Odoo resolved it from defaults — we'd need an
        // extra RPC to discover it, deferred to Phase 4b).
        const ctx = {};
        if (props.resModel) {
            ctx.default_model = props.resModel;
        }
        if (props.viewId) {
            ctx.default_view_id = props.viewId;
        }
        return ctx;
    }

    onClick() {
        const ctx = this._currentViewContext();
        if (!ctx.default_model) {
            this.notification.add(
                _t("Open a record/list/form first, then click the Studio button."),
                { type: "info" },
            );
        }
        this.action.doAction(
            {
                type: "ir.actions.client",
                tag: "custom_studio_lite.studio_view_editor",
                name: _t("Studio — Visual View Editor"),
                target: "main",
            },
            { additionalContext: ctx },
        );
    }
}

// Add to the systray. ``sequence: 1`` puts us near the right side of
// the navbar (lower sequence = righter — same convention Odoo uses).
registry.category("systray").add(
    "custom_studio_lite.systray_studio_button",
    {
        Component: StudioSystrayItem,
    },
    { sequence: 1 },
);
