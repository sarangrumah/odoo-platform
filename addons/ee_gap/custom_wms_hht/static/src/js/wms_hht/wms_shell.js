/** @odoo-module **/
// License: LGPL-3
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";

import { call } from "./rpc";
import { ReceivePage } from "./pages/ReceivePage";
import { PutawayPage } from "./pages/PutawayPage";
import { PickPage } from "./pages/PickPage";
import { PackagePage } from "./pages/PackagePage";
import { CountPage } from "./pages/CountPage";
import { BinToBinPage } from "./pages/BinToBinPage";
import { StockPage } from "./pages/StockPage";

// A handheld belongs to one warehouse at a time; remembering the choice keeps
// an operator who reboots the device out of the wrong building's queue.
const WAREHOUSE_KEY = "wms_hht_warehouse_id";

// `badge` names the key returned by /hht/wms/queue. A page with no badge key
// (Package) is a lookup tool, not a work queue, so it shows no count.
const MENU = [
    { id: "receive", label: "Receive", icon: "fa-truck", badge: "receive", Comp: ReceivePage },
    { id: "putaway", label: "Put-away", icon: "fa-sitemap", badge: "putaway", Comp: PutawayPage },
    { id: "pick", label: "Pick & Pack", icon: "fa-shopping-basket", badge: "pick", Comp: PickPage },
    { id: "package", label: "Package", icon: "fa-cube", badge: null, Comp: PackagePage },
    { id: "count", label: "Stock Count", icon: "fa-list-ol", badge: "count", Comp: CountPage },
    { id: "bin2bin", label: "Bin to Bin", icon: "fa-exchange", badge: "bin2bin", Comp: BinToBinPage },
    { id: "stock", label: "Stock Check", icon: "fa-search", badge: null, Comp: StockPage },
];

export class WmsHhtShell extends Component {
    static template = "custom_wms_hht.WmsHhtShell";
    static components = {
        ReceivePage, PutawayPage, PickPage, PackagePage, CountPage, BinToBinPage, StockPage,
    };
    static props = {};

    setup() {
        this.state = useState({
            active: "receive",
            sidebarOpen: false,
            online: typeof navigator !== "undefined" ? navigator.onLine : true,
            queue: {},
            warehouse: "",
            warehouses: [],
            warehouseId: Number(localStorage.getItem(WAREHOUSE_KEY)) || null,
            user: "",
            banner: null, // {kind: 'ok'|'error', text}
            // The prompt lives in reactive state: kept on the plain
            // scanTarget object it went stale, so the box still read "Scan
            // transfer" after the operator had moved to another screen.
            scanPrompt: "Scan barcode",
        });
        this.scanRef = useRef("scanInput");
        // The active page registers a handler here, so the single scan box at
        // the top of the shell always drives whatever screen is open — the
        // operator never has to find the right input on a 4" display.
        this.scanTarget = { handler: null };

        this._onOnline = () => (this.state.online = true);
        this._onOffline = () => (this.state.online = false);

        onMounted(async () => {
            window.addEventListener("online", this._onOnline);
            window.addEventListener("offline", this._onOffline);
            await this.loadWarehouses();
            await this.refreshQueue();
            this._queueTimer = setInterval(() => this.refreshQueue(), 60000);
            this.focusScan();
        });
        onWillUnmount(() => {
            window.removeEventListener("online", this._onOnline);
            window.removeEventListener("offline", this._onOffline);
            clearInterval(this._queueTimer);
        });
    }

    get menu() {
        return MENU;
    }

    get current() {
        return MENU.find((m) => m.id === this.state.active) || MENU[0];
    }

    async loadWarehouses() {
        const res = await call("/hht/wms/warehouses");
        if (!res.ok) return;
        this.state.warehouses = res.warehouses;
        const known = res.warehouses.some((w) => w.id === this.state.warehouseId);
        if (!known) {
            this.state.warehouseId = res.default_id || null;
            if (this.state.warehouseId) {
                localStorage.setItem(WAREHOUSE_KEY, String(this.state.warehouseId));
            }
        }
    }

    async onWarehouseChange(ev) {
        this.state.warehouseId = Number(ev.target.value) || null;
        localStorage.setItem(WAREHOUSE_KEY, String(this.state.warehouseId));
        await this.refreshQueue();
        // Re-enter the page so its list reloads against the new warehouse.
        this.select(this.state.active);
    }

    async refreshQueue() {
        const res = await call("/hht/wms/queue", { warehouse_id: this.state.warehouseId });
        if (res.ok) {
            this.state.queue = res.queue;
            this.state.warehouse = res.warehouse;
            this.state.user = res.user;
        }
    }

    badge(item) {
        if (!item.badge) return 0;
        return this.state.queue[item.badge] || 0;
    }

    select(id) {
        this.state.active = id;
        this.state.sidebarOpen = false;
        this.state.banner = null;
        this.scanTarget = { handler: null };
        this.state.scanPrompt = "Scan barcode";
        this.focusScan();
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
    }

    focusScan() {
        setTimeout(() => this.scanRef.el && this.scanRef.el.focus(), 50);
    }

    /** Pages call this in setup/onMounted to own the shell's scan box. */
    setScanTarget(handler, prompt) {
        this.scanTarget = { handler };
        this.state.scanPrompt = prompt || "Scan barcode";
        this.focusScan();
    }

    notify(kind, text) {
        this.state.banner = { kind, text };
        if (kind === "ok") {
            setTimeout(() => {
                if (this.state.banner && this.state.banner.text === text) this.state.banner = null;
            }, 4000);
        }
    }

    async onScanKeydown(ev) {
        if (ev.key !== "Enter") return;
        ev.preventDefault();
        const input = ev.target;
        const code = (input.value || "").trim();
        input.value = "";
        if (!code) return;
        if (!this.scanTarget.handler) {
            this.notify("error", "This screen is not waiting for a scan.");
            return;
        }
        try {
            await this.scanTarget.handler(code);
        } catch (e) {
            this.notify("error", String(e));
        } finally {
            this.focusScan();
        }
    }

    get pageProps() {
        return {
            warehouseId: this.state.warehouseId,
            setScanTarget: this.setScanTarget.bind(this),
            notify: this.notify.bind(this),
            refreshQueue: this.refreshQueue.bind(this),
            focusScan: this.focusScan.bind(this),
        };
    }
}
