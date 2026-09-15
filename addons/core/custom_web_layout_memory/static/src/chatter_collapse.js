/**
 * Let the user fold the chatter away, and remember that per model.
 *
 * `FormRenderer.mailLayout()` picks the chatter's position from the window
 * width alone: wide screens get it on the side, narrow ones get it below.
 * There is no way to say "not on this screen, I need the room" -- which is
 * exactly what someone reading a wide journal-entry table wants.
 *
 * The chatter stays mounted when collapsed and is reduced to a rail by CSS,
 * instead of being removed from the layout. That keeps this patch out of the
 * form compiler (which builds the chatter container at template-compile time)
 * and, more importantly, keeps the toggle itself on screen: a chatter that
 * unmounted would leave nothing to click to get it back.
 */
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { onWillStart, useState } from "@odoo/owl";

import { LAYOUT_PREFS_SERVICE } from "./layout_prefs_service";

const SECTION = "chatterCollapsed";

patch(Chatter.prototype, {
    setup() {
        super.setup();
        this.layoutPrefs = useService(LAYOUT_PREFS_SERVICE);
        this.layoutMemoryState = useState({ collapsed: false });
        onWillStart(async () => {
            await this.layoutPrefs.ready();
            if (this.canCollapseChatter) {
                this.layoutMemoryState.collapsed = Boolean(
                    this.layoutPrefs.get(SECTION, this.props.threadModel)
                );
            }
        });
    },

    /**
     * Only the form-view chatter is foldable. The same component also backs
     * Discuss and the portal, where it is the whole point of the page and
     * collapsing it would leave an empty screen.
     */
    get canCollapseChatter() {
        return Boolean(this.props.record);
    },

    toggleChatterCollapsed() {
        const collapsed = !this.layoutMemoryState.collapsed;
        this.layoutMemoryState.collapsed = collapsed;
        // Stored per model, so "hide it on journal entries" does not also hide
        // it on the contact form, where the same user may live in the chatter.
        this.layoutPrefs.set(SECTION, this.props.threadModel, collapsed || null);
    },
});
