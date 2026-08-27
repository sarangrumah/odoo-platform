/**
 * Remember list column widths per user, per view.
 *
 * Odoo's own `useMagicColumnWidths` computes ideal widths on every mount and
 * lets the user drag them, but it stores the result in a closure variable that
 * dies with the component -- and it deliberately throws the widths away on a
 * window resize or a column toggle. So a user who narrows "Account" to see
 * "Label" does it again on every visit.
 *
 * Rather than fight that hook, we feed it: a saved width is injected into the
 * column as `attrs.width`, which is exactly how a developer pins a width in the
 * arch (`<field name="x" width="80px"/>`). `getWidthSpecs` then treats the
 * column as fixed, and the hook's own layout maths does the rest -- including
 * showing a horizontal scrollbar when the saved layout is wider than the
 * window, which is the behaviour you want when the same user opens the view on
 * a narrower screen.
 */
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ListRenderer } from "@web/views/list/list_renderer";
import { onWillStart } from "@odoo/owl";

import { LAYOUT_PREFS_SERVICE } from "./layout_prefs_service";

const SECTION = "columnWidths";

/**
 * Widgets that read `attrs.width` themselves to size their own content (an
 * image, a signature pad). Pinning a column width there would resize the
 * picture, not the column, so those columns are left alone.
 */
const WIDTH_CONSUMING_WIDGETS = new Set([
    "image",
    "image_url",
    "signature",
    "binary",
    "many2many_binary",
    "pdf_viewer",
]);

/** djb2, base36. The full view key is long and we store hundreds of them. */
function shortHash(str) {
    let hash = 5381;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0;
    }
    return (hash >>> 0).toString(36);
}

/** Sum of a cell's left and right padding, which sits outside the stored width. */
function horizontalPadding(el) {
    const { paddingLeft, paddingRight } = getComputedStyle(el);
    return parseFloat(paddingLeft) + parseFloat(paddingRight);
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        this.layoutPrefs = useService(LAYOUT_PREFS_SERVICE);
        // `createViewKey` already distinguishes a nested x2many list from the
        // top-level one, and changes when the arch's field set changes -- the
        // same identity Odoo uses to remember optional columns.
        const viewKey = this.createViewKey();
        this.layoutMemoryKey = `${this.props.list.resModel}|${
            this.env.config?.viewId || 0
        }|${shortHash(viewKey)}`;
        onWillStart(() => this.layoutPrefs.ready());

        if (!this.constructor.useMagicColumnWidths || !this.columnWidths) {
            return;
        }
        const magic = this.columnWidths;
        const superOnStartResize = magic.onStartResize;
        magic.onStartResize = (ev) => {
            superOnStartResize(ev);
            // Odoo stops a resize on any of these three, and its own handlers
            // are registered first -- so by the time ours runs, the header
            // cells already hold the widths the user let go of.
            const stopEvents = ["pointerup", "pointerdown", "keydown"];
            const onStop = () => {
                for (const type of stopEvents) {
                    window.removeEventListener(type, onStop);
                }
                this.saveColumnWidths();
            };
            for (const type of stopEvents) {
                window.addEventListener(type, onStop);
            }
        };
        const superResetWidths = magic.resetWidths;
        magic.resetWidths = (...args) => {
            // Double-clicking the resize handle means "give me the defaults
            // back", and that has to outlive the page.
            this.layoutPrefs.set(SECTION, this.layoutMemoryKey, null);
            return superResetWidths(...args);
        };
    },

    /**
     * Snapshot every named column, not just the one that was dragged: what the
     * user is really adjusting is the balance between columns, and restoring
     * one width without its neighbours would not reproduce what they saw.
     */
    saveColumnWidths() {
        const table = this.tableRef.el;
        if (!table) {
            return;
        }
        const widths = {};
        for (const th of table.querySelectorAll("thead th[data-name]")) {
            const width = th.getBoundingClientRect().width - horizontalPadding(th);
            if (width > 0) {
                // Stored without padding, matching what the hook itself keeps,
                // so a stored value can be handed straight back as attrs.width.
                widths[th.dataset.name] = Math.round(width);
            }
        }
        if (Object.keys(widths).length) {
            this.layoutPrefs.set(SECTION, this.layoutMemoryKey, widths);
        }
    },

    processAllColumn(allColumns, list) {
        const columns = super.processAllColumn(allColumns, list);
        const saved = this.layoutPrefs?.get(SECTION, this.layoutMemoryKey);
        if (!saved) {
            return columns;
        }
        return columns.map((column) => {
            const width = saved[column.name];
            if (
                !width ||
                column.type !== "field" ||
                column.attrs?.width || // an explicit arch width outranks a user drag
                WIDTH_CONSUMING_WIDGETS.has(column.widget)
            ) {
                return column;
            }
            // Copy rather than mutate: these column objects come from the
            // parsed arch, which is cached and shared across every instance of
            // the view (and across users, in the same worker).
            return { ...column, attrs: { ...(column.attrs || {}), width: `${width}px` } };
        });
    },
});
