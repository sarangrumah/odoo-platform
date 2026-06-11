# -*- coding: utf-8 -*-
"""Retail import log — audit trail with SHA256 file-hash dedup.

Generalizes ``custom.bank.import.log``. Unlike the bank log, retail imports keep
the source file in ``ir.attachment`` (audit + reprocessing) and may run async via
queue_job, so we track ``job_uuid`` and per-stage record counters.
"""

from __future__ import annotations

import base64
import hashlib

from odoo import fields, models


class RetailImportLog(models.Model):
    _name = "retail.import.log"
    _description = "Retail Import Log"
    _order = "imported_at desc, id desc"
    _inherit = ["mail.thread"]

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one("retail.import.profile", required=True, ondelete="restrict")
    file_type = fields.Selection(related="profile_id.file_type", store=True, index=True)
    filename = fields.Char()
    file_hash = fields.Char(index=True, help="sha256 of raw bytes, for dedup.")
    attachment_id = fields.Many2one(
        "ir.attachment", ondelete="set null", help="Stored source file for audit / reprocessing."
    )
    job_uuid = fields.Char(index=True, help="queue_job UUID when processed asynchronously.")

    line_count = fields.Integer(default=0, help="Data rows read from the source.")
    records_created = fields.Integer(default=0)
    records_matched = fields.Integer(default=0)
    records_skipped = fields.Integer(default=0)
    error_count = fields.Integer(default=0)

    imported_at = fields.Datetime(default=fields.Datetime.now)
    imported_by_id = fields.Many2one("res.users", default=lambda s: s.env.user, readonly=True)
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("imported", "Imported"),
            ("partial", "Partial"),
            ("failed", "Failed"),
        ],
        default="queued",
        required=True,
        index=True,
        tracking=True,
    )
    error_message = fields.Text()
    raw_payload = fields.Text(help="Row-level error summary (first N rows).")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    def _compute_name(self):
        for rec in self:
            rec.name = f"RIL/{rec.id or '?'}/{rec.filename or (rec.profile_id.code or 'import')}"

    @staticmethod
    def compute_hash(raw_bytes: bytes) -> str:
        return hashlib.sha256(raw_bytes).hexdigest()

    def find_duplicate(self, file_hash):
        """Return an existing successful log for this hash, if any (dedup guard)."""
        return self.search(
            [("file_hash", "=", file_hash), ("state", "in", ("imported", "partial", "running"))],
            limit=1,
        )

    def store_source(self, file_b64, filename):
        """Persist the uploaded file as an ir.attachment for audit."""
        self.ensure_one()
        att = self.env["ir.attachment"].create(
            {
                "name": filename or self.name,
                "datas": file_b64,
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/octet-stream",
            }
        )
        self.attachment_id = att.id
        return att

    def set_errors(self, errors):
        """errors: list of (row, message). Stores a capped summary."""
        self.ensure_one()
        self.error_count = len(errors)
        if errors:
            self.raw_payload = "\n".join(f"row {n}: {m}" for n, m in errors[:200])

    def source_b64(self):
        """Return the stored source file as base64 (for reprocessing / async jobs)."""
        self.ensure_one()
        if self.attachment_id and self.attachment_id.datas:
            return self.attachment_id.datas
        return False
