# -*- coding: utf-8 -*-
"""Retail import log — audit trail with SHA256 file-hash dedup.

Generalizes ``custom.bank.import.log``. Unlike the bank log, retail imports keep
the source file in ``ir.attachment`` (audit + reprocessing) and may run async via
queue_job, so we track ``job_uuid`` and per-stage record counters.

On top of the headline counters, each processed row is recorded as a
``retail.import.log.line`` (created/updated/archived/skipped/duplicate/error) so
errors and duplicates can be browsed as a table, filtered, and exported — instead
of the old capped ``raw_payload`` text blob (still written for backward compat).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Default cap on stored log lines per import; overridable via the
# ``retail_import.max_log_lines`` config parameter. The integer counters below
# stay exact even when lines are truncated.
DEFAULT_MAX_LOG_LINES = 500000


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
    records_updated = fields.Integer(default=0)
    records_archived = fields.Integer(default=0)
    records_matched = fields.Integer(
        default=0, help="Deprecated: variant matches. Superseded by records_updated."
    )
    records_skipped = fields.Integer(default=0)
    duplicate_count = fields.Integer(default=0, help="Rows whose key repeats within the file.")
    error_count = fields.Integer(default=0)

    line_ids = fields.One2many("retail.import.log.line", "log_id")
    lines_truncated = fields.Boolean(
        default=False, help="True when the per-row line cap was hit; counters remain exact."
    )

    # ---- progress -------------------------------------------------------
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    duration = fields.Float(
        string="Duration (h)", compute="_compute_duration", store=True, help="Elapsed processing time."
    )
    processed_count = fields.Integer(default=0, readonly=True, help="Rows processed so far.")
    progress = fields.Float(compute="_compute_progress", help="Percent of rows processed (0-100).")

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
    raw_payload = fields.Text(help="Row-level error summary (first N rows). Legacy; see line_ids.")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    def _compute_name(self):
        for rec in self:
            rec.name = f"RIL/{rec.id or '?'}/{rec.filename or (rec.profile_id.code or 'import')}"

    @api.depends("started_at", "finished_at")
    def _compute_duration(self):
        for rec in self:
            if rec.started_at and rec.finished_at:
                rec.duration = (rec.finished_at - rec.started_at).total_seconds() / 3600.0
            else:
                rec.duration = 0.0

    @api.depends("processed_count", "line_count", "state")
    def _compute_progress(self):
        for rec in self:
            if rec.state in ("imported", "partial", "failed"):
                rec.progress = 100.0
            elif rec.line_count:
                rec.progress = min(100.0, 100.0 * rec.processed_count / rec.line_count)
            else:
                rec.progress = 0.0

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

    # ------------------------------------------------------------------
    # Per-row line recording
    # ------------------------------------------------------------------
    def max_log_lines(self):
        """Configured cap on stored log lines per import."""
        val = self.env["ir.config_parameter"].sudo().get_param("retail_import.max_log_lines")
        try:
            return int(val) if val else DEFAULT_MAX_LOG_LINES
        except (TypeError, ValueError):
            return DEFAULT_MAX_LOG_LINES

    def _log_lines(self, vals_list):
        """Bulk-create per-row lines, honoring the configured cap.

        Called once per executor batch (never per row). Sets ``lines_truncated``
        and silently drops the overflow when the cap is reached — the integer
        counters on the log remain authoritative.
        """
        self.ensure_one()
        if not vals_list:
            return
        cap = self.max_log_lines()
        existing = self.env["retail.import.log.line"].search_count([("log_id", "=", self.id)])
        room = cap - existing
        if room <= 0:
            if not self.lines_truncated:
                self.lines_truncated = True
            return
        if len(vals_list) > room:
            vals_list = vals_list[:room]
            self.lines_truncated = True
        for v in vals_list:
            v.setdefault("log_id", self.id)
        self.env["retail.import.log.line"].create(vals_list)

    def set_errors(self, errors):
        """errors: list of (row, message). Creates error lines + a legacy text summary."""
        self.ensure_one()
        self.error_count = len(errors)
        if not errors:
            return
        self.raw_payload = "\n".join(f"row {n}: {m}" for n, m in errors[:200])
        self._log_lines(
            [
                {"row": n or 0, "status": "error", "message": str(m)}
                for n, m in errors
            ]
        )

    def source_b64(self):
        """Return the stored source file as base64 (for reprocessing / async jobs)."""
        self.ensure_one()
        if self.attachment_id and self.attachment_id.datas:
            return self.attachment_id.datas
        return False

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------
    @api.model
    def action_open_wizard(self):
        """Open the upload wizard as a dialog (from the Imports list header)."""
        return {
            "type": "ir.actions.act_window",
            "name": _("Upload File"),
            "res_model": "retail.import.wizard",
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def action_sync_feeds(self):
        """Poll every active FTP/SFTP feed once (one-click 'Sync from FTP')."""
        feeds = self.env["retail.import.feed"].search([("active", "=", True)])
        if not feeds:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No feeds"),
                    "message": _("No active feeds. Add one under Configuration → Feeds."),
                    "type": "warning",
                    "sticky": False,
                },
            }
        total = sum((feed._run_feed() or 0) for feed in feeds)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync complete"),
                "message": _("%(n)s new file(s) imported from %(m)s feed(s).")
                % {"n": total, "m": len(feeds)},
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "retail.import.log",
                    "view_mode": "list,form,pivot,graph",
                    "target": "current",
                    "name": _("Imports"),
                },
            },
        }

    def _action_view_lines(self, status, name):
        self.ensure_one()
        domain = [("log_id", "=", self.id)]
        if status:
            domain.append(("status", "=", status))
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "retail.import.log.line",
            "view_mode": "list,form",
            "domain": domain,
            "context": {"search_default_group_status": 1} if not status else {},
            "target": "current",
        }

    def action_view_errors(self):
        return self._action_view_lines("error", _("Errors"))

    def action_view_duplicates(self):
        return self._action_view_lines("duplicate", _("Duplicates"))

    def action_view_created(self):
        return self._action_view_lines("created", _("Created"))

    def action_view_updated(self):
        return self._action_view_lines("updated", _("Updated"))

    def action_view_lines_all(self):
        return self._action_view_lines(False, _("Row Results"))

    def action_refresh(self):
        """Reload the form so async progress/counters become visible."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_reprocess(self):
        """Re-run the executor from the stored source file (wipe prior results first)."""
        self.ensure_one()
        if self.state == "running":
            raise UserError(_("This import is currently running."))
        if not self.source_b64():
            raise UserError(_("No stored source file to reprocess."))
        self.line_ids.unlink()
        self.write(
            {
                "records_created": 0,
                "records_updated": 0,
                "records_archived": 0,
                "records_matched": 0,
                "records_skipped": 0,
                "duplicate_count": 0,
                "error_count": 0,
                "processed_count": 0,
                "lines_truncated": False,
                "error_message": False,
                "raw_payload": False,
                "started_at": False,
                "finished_at": False,
                "state": "queued",
            }
        )
        Executor = self.env["retail.import.executor"]
        # Lazy import to avoid a hard dependency cycle on the wizard module.
        async_types = {"x101", "x20", "x24", "x70d", "x32p"}
        channel = self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.queue_channel", "root.retail_import"
        )
        if self.file_type in async_types:
            try:
                job = Executor.with_delay(
                    channel=channel, description=f"Reprocess {self.name}"
                ).run(self)
                self.job_uuid = getattr(job, "uuid", False)
            except Exception:
                _logger.warning("queue_job unavailable; reprocessing synchronously")
                Executor.run(self)
        else:
            Executor.run(self)
        return self.action_refresh()

    def action_download_source(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("No stored source file."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}?download=true",
            "target": "self",
        }

    def action_download_errors(self):
        """Build a CSV of error/duplicate rows for the customer to fix and resend."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.status in ("error", "duplicate"))
        if not lines:
            raise UserError(_("No errors or duplicates to export."))
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["row", "status", "key", "message"])
        for l in lines.sorted(key=lambda r: (r.row or 0, r.id)):
            writer.writerow([l.row or "", l.status, l.ref_key or "", l.message or ""])
        data = base64.b64encode(buf.getvalue().encode("utf-8-sig"))
        att = self.env["ir.attachment"].create(
            {
                "name": f"errors_{self.name.replace('/', '_')}.csv",
                "datas": data,
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "text/csv",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=true",
            "target": "self",
        }

    def _notify_failure(self):
        """Best-effort failure alert hook. Never raises into the import path."""
        self.ensure_one()
        enabled = self.env["ir.config_parameter"].sudo().get_param("retail_import.alert_on_failure")
        if not enabled or enabled in ("0", "False", "false"):
            return
        try:
            # Seam for the platform orchestrator/WhatsApp alert (see backup-failure
            # alerting). Kept as a log statement until the alert API is wired so a
            # missing service never breaks an import.
            _logger.error(
                "Retail import FAILED: %s (profile %s): %s",
                self.name, self.profile_id.code, self.error_message,
            )
        except Exception:  # pragma: no cover - defensive
            _logger.exception("Failure alert hook errored (log %s)", self.id)
