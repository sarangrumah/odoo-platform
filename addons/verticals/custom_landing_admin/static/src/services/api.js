/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

/**
 * Tiny wrapper over the ORM JSON-RPC surface.
 *
 * Every helper returns ``null`` on error rather than throwing, so a
 * missing model on this odoo-mgmt instance only blanks the panel
 * instead of crashing the whole console.
 */
async function _call(model, method, args = [], kwargs = {}) {
    try {
        return await rpc("/web/dataset/call_kw", {
            model,
            method,
            args,
            kwargs,
        });
    } catch (e) {
        // eslint-disable-next-line no-console
        console.warn(`[landing_admin] ${model}.${method} failed`, e);
        return null;
    }
}

export const api = {
    callKw: _call,

    searchRead(model, domain = [], fields = [], opts = {}) {
        return _call(model, "search_read", [domain, fields], opts);
    },

    read(model, ids, fields = []) {
        return _call(model, "read", [ids, fields], {});
    },

    write(model, ids, values) {
        return _call(model, "write", [ids, values], {});
    },

    create(model, values) {
        return _call(model, "create", [values], {});
    },

    searchCount(model, domain = []) {
        return _call(model, "search_count", [domain], {});
    },

    action(model, ids, method, kwargs = {}) {
        return _call(model, method, [ids], kwargs);
    },
};
