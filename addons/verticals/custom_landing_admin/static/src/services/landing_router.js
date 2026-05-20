/** @odoo-module **/

import { reactive } from "@odoo/owl";

/**
 * Hash-based client-side router.
 *
 * Routes are declared as patterns with ``:param`` segments. The router
 * maintains a reactive ``current`` object containing the matched route
 * key plus any URL params.
 *
 *   #/pipeline                 → { name: "pipeline", params: {} }
 *   #/journey/42               → { name: "journey", params: { id: "42" } }
 *   #/vps                      → { name: "vps", params: {} }
 *   #/monitoring               → { name: "monitoring", params: {} }
 *   #/modules                  → { name: "modules", params: {} }
 */
const ROUTES = [
    { pattern: /^#?\/?$/, name: "pipeline", keys: [] },
    { pattern: /^#?\/?pipeline\/?$/, name: "pipeline", keys: [] },
    {
        pattern: /^#?\/?journey\/([^/]+)\/?$/,
        name: "journey",
        keys: ["id"],
    },
    { pattern: /^#?\/?vps\/?$/, name: "vps", keys: [] },
    { pattern: /^#?\/?monitoring\/?$/, name: "monitoring", keys: [] },
    { pattern: /^#?\/?modules\/?$/, name: "modules", keys: [] },
];

function _match(hash) {
    const h = hash || "#/";
    for (const r of ROUTES) {
        const m = h.match(r.pattern);
        if (m) {
            const params = {};
            r.keys.forEach((k, i) => (params[k] = m[i + 1]));
            return { name: r.name, params };
        }
    }
    return { name: "notfound", params: {} };
}

export function createLandingRouter() {
    const state = reactive({
        current: _match(window.location.hash),
    });

    window.addEventListener("hashchange", () => {
        state.current = _match(window.location.hash);
    });

    return {
        state,
        navigate(path) {
            // ``path`` should look like ``/pipeline`` or ``/journey/12``
            const clean = path.startsWith("#") ? path : "#" + path;
            if (window.location.hash !== clean) {
                window.location.hash = clean;
            } else {
                // Force re-match (no-op hashchange).
                state.current = _match(clean);
            }
        },
        get current() {
            return state.current;
        },
    };
}
