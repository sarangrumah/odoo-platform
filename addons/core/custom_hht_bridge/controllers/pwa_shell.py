# -*- coding: utf-8 -*-
# License: LGPL-3
"""PWA shell endpoints: HTML, web manifest, service worker."""
from __future__ import annotations

import json

from odoo import http
from odoo.http import request


_MANIFEST = {
    "name": "Hub HHT",
    "short_name": "HHT",
    "start_url": "/hht/",
    "display": "standalone",
    "theme_color": "#1f2937",
    "background_color": "#111827",
    "icons": [
        {
            "src": "/custom_hht_bridge/static/src/pwa/icon-192.png",
            "sizes": "192x192",
            "type": "image/png",
        },
        {
            "src": "/custom_hht_bridge/static/src/pwa/icon-512.png",
            "sizes": "512x512",
            "type": "image/png",
        },
    ],
}


_SW_SOURCE = r"""
// Hub HHT Service Worker — precache + SWR + offline POST queue.
const CACHE_NAME = 'hht-shell-v1';
const PRECACHE = ['/hht/', '/hht/manifest.webmanifest'];
const DB_NAME = 'hht-offline';
const STORE = 'pending';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

function openDb() {
    return new Promise((resolve, reject) => {
        const r = indexedDB.open(DB_NAME, 1);
        r.onupgradeneeded = () => {
            r.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        };
        r.onsuccess = () => resolve(r.result);
        r.onerror = () => reject(r.error);
    });
}

async function enqueue(req) {
    const body = await req.clone().text();
    const db = await openDb();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).add({
            url: req.url,
            method: req.method,
            headers: [...req.headers],
            body: body,
            ts: Date.now(),
        });
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

async function flushQueue() {
    const db = await openDb();
    const items = await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, 'readonly');
        const req = tx.objectStore(STORE).getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
    for (const item of items) {
        try {
            const resp = await fetch(item.url, {
                method: item.method,
                headers: new Headers(item.headers),
                body: item.body,
            });
            if (resp.ok) {
                await new Promise((resolve, reject) => {
                    const tx = db.transaction(STORE, 'readwrite');
                    tx.objectStore(STORE).delete(item.id);
                    tx.oncomplete = () => resolve();
                    tx.onerror = () => reject(tx.error);
                });
            }
        } catch (e) {
            // network still down; retry later
            break;
        }
    }
}

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method === 'POST' && url.pathname.startsWith('/api/hht/')) {
        event.respondWith(
            fetch(event.request.clone()).catch(async () => {
                await enqueue(event.request);
                return new Response(
                    JSON.stringify({ ok: true, queued: true }),
                    { status: 202, headers: { 'Content-Type': 'application/json' } }
                );
            })
        );
        return;
    }
    if (event.request.method === 'GET' && url.pathname.startsWith('/api/hht/')) {
        // Stale-while-revalidate.
        event.respondWith(
            caches.open(CACHE_NAME).then(async (cache) => {
                const cached = await cache.match(event.request);
                const networkPromise = fetch(event.request).then((resp) => {
                    if (resp.ok) cache.put(event.request, resp.clone());
                    return resp;
                }).catch(() => cached);
                return cached || networkPromise;
            })
        );
        return;
    }
    if (event.request.method === 'GET') {
        event.respondWith(
            caches.match(event.request).then((cached) => cached || fetch(event.request))
        );
    }
});

self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'flush') {
        event.waitUntil(flushQueue());
    }
});

self.addEventListener('sync', (event) => {
    if (event.tag === 'hht-flush') {
        event.waitUntil(flushQueue());
    }
});
"""


class HhtPwaShell(http.Controller):

    @http.route("/hht", type="http", auth="user", methods=["GET"], csrf=False)
    def hht_root(self, **_kw):
        return request.redirect("/hht/", code=301)

    @http.route("/hht/", type="http", auth="user", methods=["GET"], csrf=False)
    def hht_shell(self, **_kw):
        return request.render("custom_hht_bridge.hht_shell_layout", {})

    @http.route(
        "/hht/manifest.webmanifest",
        type="http", auth="public", methods=["GET"], csrf=False,
    )
    def hht_manifest(self, **_kw):
        body = json.dumps(_MANIFEST, separators=(",", ":"))
        return request.make_response(
            body,
            headers=[
                ("Content-Type", "application/manifest+json"),
                ("Cache-Control", "public, max-age=3600"),
            ],
        )

    @http.route("/hht/sw.js", type="http", auth="public", methods=["GET"], csrf=False)
    def hht_service_worker(self, **_kw):
        return request.make_response(
            _SW_SOURCE,
            headers=[
                ("Content-Type", "application/javascript; charset=utf-8"),
                ("Cache-Control", "no-cache"),
                ("Service-Worker-Allowed", "/"),
            ],
        )
