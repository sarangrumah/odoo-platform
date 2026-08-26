/**
 * Session-wide cache for the user's backend layout preferences.
 *
 * The whole blob is fetched once per session and then served synchronously to
 * every list view and chatter that asks for it -- those components render on
 * the critical path, so they cannot each afford a round trip. Writes go the
 * other way: they are coalesced and flushed on a timer, because a column drag
 * produces one write but a user rearranging a table produces a dozen.
 *
 * Every failure here is swallowed. A preference store is a convenience; if the
 * server refuses to talk (portal user, database without the model upgraded,
 * offline tab) the client must still render the view with default widths.
 */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

export const LAYOUT_PREFS_SERVICE = "custom_web_layout_memory.prefs";

const SECTIONS = ["columnWidths", "chatterCollapsed"];
const FLUSH_DELAY = 800;

function emptyPrefs() {
    return Object.fromEntries(SECTIONS.map((section) => [section, {}]));
}

export const layoutPrefsService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        let cache = emptyPrefs();
        let pending = emptyPrefs();
        let hasPending = false;
        let loadProm = null;
        let flushTimeout = null;

        async function flush() {
            browser.clearTimeout(flushTimeout);
            flushTimeout = null;
            if (!hasPending) {
                return;
            }
            const changes = pending;
            pending = emptyPrefs();
            hasPending = false;
            try {
                await orm.silent.call("res.users.settings", "set_layout_prefs", [changes]);
            } catch {
                // The in-memory cache already reflects the change, so the tab
                // the user is in stays consistent; only persistence is lost.
            }
        }

        function schedule() {
            if (flushTimeout === null) {
                flushTimeout = browser.setTimeout(flush, FLUSH_DELAY);
            }
        }

        // A user who drags a column and immediately switches tabs or closes
        // the browser would otherwise lose the write still sitting in the
        // debounce window.
        browser.addEventListener("visibilitychange", () => {
            if (browser.document.visibilityState === "hidden") {
                flush();
            }
        });

        return {
            /**
             * Resolve once the preferences are in memory. Safe to await from
             * `onWillStart` of any number of components: the fetch happens
             * once and every later call returns the settled promise.
             */
            ready() {
                if (!loadProm) {
                    loadProm = orm.silent
                        .call("res.users.settings", "get_layout_prefs", [])
                        .then((prefs) => {
                            for (const section of SECTIONS) {
                                if (prefs && typeof prefs[section] === "object") {
                                    cache[section] = prefs[section] || {};
                                }
                            }
                        })
                        .catch(() => {
                            cache = emptyPrefs();
                        });
                }
                return loadProm;
            },
            /** Synchronous read; returns undefined before `ready()` settles. */
            get(section, key) {
                return cache[section]?.[key];
            },
            /** Write through to the cache now, to the server shortly after. */
            set(section, key, value) {
                if (!SECTIONS.includes(section) || !key) {
                    return;
                }
                if (value === null || value === undefined) {
                    delete cache[section][key];
                    pending[section][key] = null;
                } else {
                    cache[section][key] = value;
                    pending[section][key] = value;
                }
                hasPending = true;
                schedule();
            },
        };
    },
};

registry.category("services").add(LAYOUT_PREFS_SERVICE, layoutPrefsService);
