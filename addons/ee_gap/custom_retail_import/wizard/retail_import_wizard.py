# -*- coding: utf-8 -*-
"""Retail import wizard — upload a file, preview (dry-run), then import.

Mirrors ``custom.bank.import.csv.wizard`` (Binary upload + SHA256 dedup) and adds:
- ``action_preview``: parse the first rows, show counts + samples, NO commit.
- ``action_import``: persist the file to ir.attachment, create a log, then run the
  executor — asynchronously via queue_job for large files (X101 ~30 min) so the web
  worker does not hit the reverse-proxy timeout (ERR_EMPTY_RESPONSE).
"""

from __future__ import annotations

import base64
import json
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# File types whose volume warrants async processing.
ASYNC_TYPES = {"x101", "x20", "x24", "x70d", "x32p"}


class RetailImportWizard(models.TransientModel):
    _name = "retail.import.wizard"
    _description = "Retail Import Wizard"

    profile_id = fields.Many2one("retail.import.profile", required=True)
    file_type = fields.Selection(related="profile_id.file_type")
    file = fields.Binary(string="Source File", required=True)
    filename = fields.Char()
    force = fields.Boolean(
        string="Force re-import",
        help="Bypass the file-hash duplicate guard (use with care).",
    )
    preview_text = fields.Text(readonly=True)

    # ------------------------------------------------------------------
    def _decoded(self):
        if not self.file:
            raise UserError(_("Please upload a file."))
        return base64.b64decode(self.file)

    def action_preview(self):
        """Dry-run: parse a sample and report, without writing anything."""
        self.ensure_one()
        self._decoded()
        sample = self.profile_id.read_records(self.file, limit=20)
        lines = [
            f"Profile: {self.profile_id.code} ({self.profile_id.file_type})",
            f"Parsed sample rows: {len(sample['records'])} (blank skipped: {sample['blank_rows']})",
            "",
            "First rows (logical fields):",
        ]
        for rec in sample["records"][:8]:
            shown = {k: v for k, v in rec.items() if k != "_row"}
            lines.append(f"  row {rec.get('_row')}: {json.dumps(shown, default=str, ensure_ascii=False)}")
        self.preview_text = "\n".join(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_import(self):
        self.ensure_one()
        raw = self._decoded()
        Log = self.env["retail.import.log"].sudo()
        file_hash = Log.compute_hash(raw)
        if not self.force:
            dup = Log.find_duplicate(file_hash)
            if dup:
                raise UserError(
                    _("This exact file was already imported/queued (log #%s). Tick 'Force re-import' to override.")
                    % dup.id
                )
        log = Log.create(
            {
                "profile_id": self.profile_id.id,
                "filename": self.filename,
                "file_hash": file_hash,
                "state": "queued",
            }
        )
        log.store_source(self.file, self.filename)
        Executor = self.env["retail.import.executor"]
        if self.profile_id.file_type in ASYNC_TYPES:
            channel = (
                self.env["ir.config_parameter"].sudo().get_param("retail_import.queue_channel", "root.retail_import")
            )
            try:
                job = Executor.with_delay(
                    channel=channel,
                    description=f"Retail import {self.profile_id.code} ({self.filename})",
                ).run(log)
                log.job_uuid = getattr(job, "uuid", False)
            except Exception:
                # queue_job unavailable -> fall back to synchronous run.
                _logger.warning("queue_job unavailable; running retail import synchronously")
                Executor.run(log)
        else:
            Executor.run(log)
        return {
            "type": "ir.actions.act_window",
            "res_model": "retail.import.log",
            "res_id": log.id,
            "view_mode": "form",
            "target": "current",
        }
