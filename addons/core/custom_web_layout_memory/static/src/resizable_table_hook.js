/**
 * Column resizing with memory, for tables that are not Odoo list views.
 *
 * `ListRenderer` gets this for free: core already draws the resize grips and
 * runs the width algebra, and `list_column_width.js` only has to remember the
 * result. A hand-written OWL table -- the accounting reports table, say --
 * has none of that machinery, so this hook supplies the whole thing: the drag,
 * the freeze, and the per-user persistence through the same service.
 *
 * The consumer is responsible for two things in its template:
 *   1. a `data-name` on every `<th>` (the key widths are stored under), and
 *   2. a grip element calling `onStartResize`, e.g.
 *      <span class="o-ux-resizeGrip" t-on-pointerdown.stop.prevent="..."/>
 * and for adding `o-ux-resizableTable` to the table so the grip positions.
 */
import { useComponent, useEffect, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { LAYOUT_PREFS_SERVICE } from "./layout_prefs_service";

const SECTION = "columnWidths";
const MIN_WIDTH = 40;

/** djb2, base36 — keeps a long column signature short in the stored blob. */
function shortHash(str) {
    let hash = 5381;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0;
    }
    return (hash >>> 0).toString(36);
}

/**
 * @param {Object} tableRef  a t-ref pointing at the <table>
 * @param {Object} options
 * @param {() => string} options.getKey     stable identity of this table
 * @param {() => string[]} options.getColumns  current column names, in order
 */
export function useResizableColumnWidths(tableRef, { getKey, getColumns }) {
    const component = useComponent();
    const prefs = useService(LAYOUT_PREFS_SERVICE);
    let resizing = false;
    // A drag ends on pointerup, but the browser then fires a `click` on the
    // header the grip lives in -- so a plain "am I dragging?" flag is already
    // false by the time the header's own handler runs, and every resize would
    // also sort the column. Core's list view has the same problem and solves
    // it the same way: raise a one-shot flag the click handler consumes.
    let suppressNextClick = false;
    let suppressTimer = null;

    onWillStart(() => prefs.ready());

    function storageKey() {
        // Fold the column set into the key: widths measured against one set of
        // columns mean nothing against another (a report run with different
        // options can return a different column list entirely).
        return `${getKey()}|${shortHash(getColumns().join(","))}`;
    }

    /** Push the stored widths into the DOM. Runs after every patch, because
     *  sorting or filtering re-renders the rows and the browser would
     *  otherwise recompute widths from the new content. */
    function applyStoredWidths() {
        const table = tableRef.el;
        if (!table || resizing) {
            return;
        }
        const stored = prefs.get(SECTION, storageKey());
        if (!stored) {
            table.style.tableLayout = "";
            table.style.width = "";
            return;
        }
        let any = false;
        for (const th of table.querySelectorAll("thead th[data-name]")) {
            const width = stored[th.dataset.name];
            if (width) {
                th.style.width = `${width}px`;
                any = true;
            }
        }
        // Fixed layout is what makes the browser honour the widths instead of
        // treating them as a suggestion it may overrule to fit the content.
        table.style.tableLayout = any ? "fixed" : "";
    }

    function save() {
        const table = tableRef.el;
        if (!table) {
            return;
        }
        const widths = {};
        for (const th of table.querySelectorAll("thead th[data-name]")) {
            const width = th.getBoundingClientRect().width;
            if (width > 0) {
                widths[th.dataset.name] = Math.round(width);
            }
        }
        if (Object.keys(widths).length) {
            prefs.set(SECTION, storageKey(), widths);
        }
    }

    function onStartResize(ev) {
        const table = tableRef.el;
        const th = ev.target.closest("th");
        if (!table || !th) {
            return;
        }
        resizing = true;
        // Freeze the table at its current size first: without this, shrinking
        // one column would let the others silently re-flow to fill the gap.
        table.style.tableLayout = "fixed";
        table.style.width = `${Math.round(table.getBoundingClientRect().width)}px`;
        for (const other of table.querySelectorAll("thead th")) {
            other.style.width = `${Math.round(other.getBoundingClientRect().width)}px`;
        }
        const startX = ev.clientX;
        const startWidth = th.getBoundingClientRect().width;
        const startTableWidth = table.getBoundingClientRect().width;
        th.classList.add("o-ux-resizing");

        const onMove = (moveEv) => {
            const delta = moveEv.clientX - startX;
            const newWidth = Math.max(MIN_WIDTH, startWidth + delta);
            th.style.width = `${Math.round(newWidth)}px`;
            table.style.width = `${Math.round(startTableWidth + (newWidth - startWidth))}px`;
        };
        const onStop = () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onStop);
            window.removeEventListener("keydown", onStop);
            th.classList.remove("o-ux-resizing");
            save();
            resizing = false;
            suppressNextClick = true;
            // A drag stopped by a keypress produces no click at all, and a
            // flag left standing would eat the user's next real one.
            clearTimeout(suppressTimer);
            suppressTimer = setTimeout(() => {
                suppressNextClick = false;
            }, 400);
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onStop);
        window.addEventListener("keydown", onStop);
    }

    /** Forget this table's widths and let the browser lay it out again. */
    function resetWidths() {
        const table = tableRef.el;
        prefs.set(SECTION, storageKey(), null);
        if (table) {
            for (const th of table.querySelectorAll("thead th")) {
                th.style.width = "";
            }
            table.style.tableLayout = "";
            table.style.width = "";
        }
        component.render();
    }

    useEffect(applyStoredWidths);

    return {
        onStartResize,
        resetWidths,
        get resizing() {
            return resizing;
        },
        /**
         * True if this click is the tail of a resize and the header's own
         * handler (sorting, usually) should stand down. Self-clearing: ask
         * once per click.
         */
        shouldSuppressClick() {
            if (suppressNextClick) {
                suppressNextClick = false;
                clearTimeout(suppressTimer);
                return true;
            }
            return resizing;
        },
    };
}
