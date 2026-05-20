/** @odoo-module **/

import { Component, useState, useRef, onWillUnmount } from "@odoo/owl";
import { api } from "../../services/api";

/**
 * Drag-drop multi-file uploader for BRD documents.
 *
 * Uses Odoo's standard ``/web/binary/upload_attachment`` endpoint to
 * stage the file as an ``ir.attachment`` linked to the parent
 * ``brd.document`` model, then triggers the ``analyze`` action server
 * side. Status is refreshed every 2s via polling until all documents
 * settle (state ∈ {analyzed, failed}).
 */
const POLL_MS = 2000;
const TERMINAL_STATES = new Set(["analyzed", "failed", "approved", "rejected"]);

export class BrdUpload extends Component {
    static template = "custom_landing_admin.BrdUpload";
    static props = {
        journeyId: { type: [String, Number] },
        onUploaded: { type: Function, optional: true },
    };

    setup() {
        this.fileInput = useRef("fileInput");
        this.state = useState({
            dragging: false,
            uploading: false,
            uploads: [],   // [{ id, name, state, progress }]
            error: null,
        });
        this._pollHandle = null;
        onWillUnmount(() => this._stopPolling());
    }

    onDragEnter(ev) {
        ev.preventDefault();
        this.state.dragging = true;
    }

    onDragLeave(ev) {
        ev.preventDefault();
        this.state.dragging = false;
    }

    onDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "copy";
    }

    async onDrop(ev) {
        ev.preventDefault();
        this.state.dragging = false;
        const files = Array.from(ev.dataTransfer.files || []);
        await this._uploadAll(files);
    }

    onPick() {
        this.fileInput.el && this.fileInput.el.click();
    }

    async onFileChange(ev) {
        const files = Array.from(ev.target.files || []);
        await this._uploadAll(files);
        ev.target.value = "";
    }

    async _uploadAll(files) {
        if (!files.length) return;
        this.state.uploading = true;
        this.state.error = null;
        for (const f of files) {
            try {
                const doc = await this._uploadOne(f);
                if (doc) {
                    this.state.uploads.push({
                        id: doc.id,
                        name: doc.name || f.name,
                        state: doc.state || "uploading",
                    });
                }
            } catch (err) {
                this.state.error = String(err);
            }
        }
        this.state.uploading = false;
        if (this.props.onUploaded) this.props.onUploaded();
        this._startPolling();
    }

    async _uploadOne(file) {
        // Stage the file as an attachment first.
        const form = new FormData();
            form.append("ufile", file);
            form.append("model", "brd.document");
            form.append("id", "0");
            form.append("csrf_token", odoo.csrf_token || "");
        const resp = await fetch("/web/binary/upload_attachment", {
            method: "POST",
            body: form,
        });
        const txt = await resp.text();
        // The endpoint returns a script block; we just need the
        // attachment id, which we can grab via JSON-shaped substring.
        let attachmentId = null;
        const m = txt.match(/"id"\s*:\s*(\d+)/);
        if (m) attachmentId = parseInt(m[1], 10);

        // Now create the brd.document record and link the attachment.
        const docId = await api.create("brd.document", {
            name: file.name,
            journey_id: parseInt(this.props.journeyId, 10),
            attachment_id: attachmentId,
        });
        if (!docId) return null;
        const rows = await api.read(
            "brd.document", [docId], ["id", "name", "state"]
        );
        return (rows && rows[0]) || { id: docId, name: file.name };
    }

    _startPolling() {
        this._stopPolling();
        if (!this.state.uploads.length) return;
        this._pollHandle = window.setInterval(
            () => this._pollOnce(), POLL_MS
        );
    }

    _stopPolling() {
        if (this._pollHandle) {
            window.clearInterval(this._pollHandle);
            this._pollHandle = null;
        }
    }

    async _pollOnce() {
        const ids = this.state.uploads
            .filter((u) => !TERMINAL_STATES.has(u.state))
            .map((u) => u.id);
        if (!ids.length) {
            this._stopPolling();
            return;
        }
        const rows = await api.read("brd.document", ids, ["id", "state"]);
        const byId = {};
        (rows || []).forEach((r) => (byId[r.id] = r.state));
        this.state.uploads = this.state.uploads.map((u) => ({
            ...u,
            state: byId[u.id] || u.state,
        }));
    }
}
