# -*- coding: utf-8 -*-
"""Retail import feed — recurring SFTP pull of source files into the importer.

Phase 6 of the Levi's onboarding plan: answers "can Odoo read directly from the
customer FTP?". A feed binds an SFTP location + glob to a ``retail.import.profile``.
An ``ir.cron`` polls active feeds; each new file (deduplicated by SHA256 against
``retail.import.log``) is stored in ir.attachment and handed to the same
``retail.import.executor`` used by the manual wizard.

Credentials: the SFTP secret lives in ``ir.config_parameter`` under the key named
in ``password_param`` (or a private-key file path). NOTE: the platform does not yet
expose an at-rest decryptor for config params, so the value is stored raw — restrict
read access to the parameter and prefer key-based auth where possible.

Networking: SFTP egress goes out from the Odoo container on ``odoo-net``; no new
docker volume is needed (downloads land in the shared filestore via ir.attachment).
"""

from __future__ import annotations

import base64
import fnmatch
import io
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RetailImportFeed(models.Model):
    _name = "retail.import.feed"
    _description = "Retail Import SFTP Feed"
    _order = "name"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    profile_id = fields.Many2one("retail.import.profile", required=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    host = fields.Char(required=True)
    port = fields.Integer(default=22, required=True)
    username = fields.Char(required=True)
    auth_type = fields.Selection(
        [("password", "Password"), ("key", "Private key file")], default="password", required=True
    )
    password_param = fields.Char(
        string="Password ir.config_parameter Key",
        help="Key in ir.config_parameter that holds the SFTP password.",
    )
    private_key_path = fields.Char(help="Path (inside the container) to the SFTP private key file.")

    remote_dir = fields.Char(default="/", required=True)
    file_glob = fields.Char(default="*", required=True, help="e.g. 'X20_*.csv' or 'X24DN_*.xlsx'.")
    run_async = fields.Boolean(
        string="Process asynchronously", default=True, help="Hand each file to queue_job."
    )

    last_run = fields.Datetime(readonly=True)
    last_status = fields.Selection(
        [("ok", "OK"), ("error", "Error"), ("idle", "Idle")], default="idle", readonly=True
    )
    last_message = fields.Text(readonly=True)
    files_imported = fields.Integer(default=0, readonly=True)

    # ------------------------------------------------------------------
    def _secret(self):
        self.ensure_one()
        if not self.password_param:
            return ""
        return self.env["ir.config_parameter"].sudo().get_param(self.password_param, "") or ""

    def _open_sftp(self):
        self.ensure_one()
        try:
            import paramiko  # noqa: PLC0415 - optional, image-provided
        except ImportError as e:  # pragma: no cover - depends on image
            raise UserError(
                _("paramiko is not installed in this Odoo image. Add it to odoo/requirements.txt and rebuild.")
            ) from e
        transport = paramiko.Transport((self.host, self.port))
        try:
            if self.auth_type == "key":
                if not self.private_key_path:
                    raise UserError(_("Feed %s: private key path is required for key auth.") % self.name)
                pkey = paramiko.RSAKey.from_private_key_file(self.private_key_path)
                transport.connect(username=self.username, pkey=pkey)
            else:
                transport.connect(username=self.username, password=self._secret())
        except Exception:
            transport.close()
            raise
        return paramiko.SFTPClient.from_transport(transport), transport

    def action_test_connection(self):
        self.ensure_one()
        sftp, transport = self._open_sftp()
        try:
            names = sftp.listdir(self.remote_dir)
        finally:
            sftp.close()
            transport.close()
        matched = [n for n in names if fnmatch.fnmatch(n, self.file_glob)]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Connection OK"),
                "message": _("%s file(s) match %s in %s.") % (len(matched), self.file_glob, self.remote_dir),
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    def _poll_one(self):
        """Download new matching files and feed them to the executor. Returns count."""
        self.ensure_one()
        Log = self.env["retail.import.log"].sudo()
        Executor = self.env["retail.import.executor"]
        sftp, transport = self._open_sftp()
        imported = 0
        try:
            names = [n for n in sftp.listdir(self.remote_dir) if fnmatch.fnmatch(n, self.file_glob)]
            for name in sorted(names):
                remote_path = self.remote_dir.rstrip("/") + "/" + name
                buf = io.BytesIO()
                sftp.getfo(remote_path, buf)
                raw = buf.getvalue()
                if not raw:
                    continue
                file_hash = Log.compute_hash(raw)
                if Log.find_duplicate(file_hash):
                    continue  # already seen this exact file
                file_b64 = base64.b64encode(raw).decode("ascii")
                log = Log.create(
                    {
                        "profile_id": self.profile_id.id,
                        "filename": name,
                        "file_hash": file_hash,
                        "state": "queued",
                    }
                )
                log.store_source(file_b64, name)
                if self.run_async:
                    try:
                        job = Executor.with_delay(
                            channel="root.retail_import",
                            description=f"Feed {self.name}: {name}",
                        ).run(log)
                        log.job_uuid = getattr(job, "uuid", False)
                    except Exception:
                        Executor.run(log)
                else:
                    Executor.run(log)
                imported += 1
        finally:
            sftp.close()
            transport.close()
        return imported

    def action_poll_now(self):
        for feed in self:
            feed._run_feed()
        return True

    def _run_feed(self):
        self.ensure_one()
        try:
            n = self._poll_one()
            self.write(
                {
                    "last_run": fields.Datetime.now(),
                    "last_status": "ok",
                    "last_message": _("Imported %s new file(s).") % n,
                    "files_imported": self.files_imported + n,
                }
            )
        except Exception as e:
            _logger.exception("Feed %s poll failed", self.name)
            self.write(
                {
                    "last_run": fields.Datetime.now(),
                    "last_status": "error",
                    "last_message": str(e),
                }
            )

    def _cron_poll_feeds(self):
        """ir.cron entry point: poll every active feed."""
        for feed in self.search([("active", "=", True)]):
            feed._run_feed()
        return True
