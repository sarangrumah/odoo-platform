# -*- coding: utf-8 -*-
"""Retail import feed — recurring SFTP/FTP/FTPS pull of source files into the importer.

Phase 6 of the Levi's onboarding plan: answers "can Odoo read directly from the
customer file server?". A feed binds a remote location + glob to a
``retail.import.profile``. An ``ir.cron`` polls active feeds; each new file
(deduplicated by SHA256 against ``retail.import.log``) is stored in ir.attachment
and handed to the same ``retail.import.executor`` used by the manual wizard.

Protocols: ``sftp`` (paramiko, password or private key), ``ftp`` (stdlib ftplib),
``ftps`` (ftplib FTP_TLS, encrypted data channel). FTP/FTPS need no extra Python
dependency; SFTP needs paramiko (already an image dep).

Credentials: the secret can be typed directly into ``password`` (masked,
manager-only) or, for shared secrets, kept in ``ir.config_parameter`` under the key
named in ``password_param``. NOTE: the platform does not yet expose an at-rest
decryptor, so a typed password is stored raw in the DB — restrict access and prefer
key-based auth for SFTP where possible.

Networking: egress goes out from the Odoo container on ``odoo-net``; no new docker
volume is needed (downloads land in the shared filestore via ir.attachment).
"""

from __future__ import annotations

import base64
import fnmatch
import ftplib
import io
import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RetailImportFeed(models.Model):
    _name = "retail.import.feed"
    _description = "Retail Import Feed"
    _order = "name"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    profile_id = fields.Many2one("retail.import.profile", required=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    protocol = fields.Selection(
        [("sftp", "SFTP"), ("ftp", "FTP"), ("ftps", "FTP over TLS")],
        default="sftp",
        required=True,
    )
    host = fields.Char(required=True)
    port = fields.Integer(default=22, required=True)
    username = fields.Char(required=True)
    auth_type = fields.Selection(
        [("password", "Password"), ("key", "Private key file")],
        default="password",
        required=True,
        help="Private-key auth applies to SFTP only.",
    )
    password = fields.Char(
        groups="custom_retail_import.group_retail_import_manager",
        help="Connection password. Stored unencrypted in the DB — restrict access.",
    )
    password_param = fields.Char(
        string="Password ir.config_parameter Key",
        help="Fallback: key in ir.config_parameter that holds the password (used when "
             "the Password field is empty).",
    )
    private_key_path = fields.Char(help="SFTP only: path (inside the container) to the private key file.")
    passive = fields.Boolean(
        default=True, help="FTP/FTPS passive mode (recommended behind NAT/firewalls)."
    )

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

    @api.onchange("protocol")
    def _onchange_protocol(self):
        for feed in self:
            feed.port = 22 if feed.protocol == "sftp" else 21
            if feed.protocol != "sftp":
                feed.auth_type = "password"

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------
    def _secret(self):
        self.ensure_one()
        if self.password:
            return self.password
        if self.password_param:
            return self.env["ir.config_parameter"].sudo().get_param(self.password_param, "") or ""
        return ""

    def _queue_channel(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.queue_channel", "root.retail_import"
        )

    # ------------------------------------------------------------------
    # SFTP backend
    # ------------------------------------------------------------------
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

    def _sftp_list(self):
        sftp, transport = self._open_sftp()
        try:
            names = sftp.listdir(self.remote_dir)
        finally:
            sftp.close()
            transport.close()
        return [os.path.basename(n) for n in names if fnmatch.fnmatch(os.path.basename(n), self.file_glob)]

    def _sftp_download(self, name):
        sftp, transport = self._open_sftp()
        try:
            remote_path = self.remote_dir.rstrip("/") + "/" + name
            buf = io.BytesIO()
            sftp.getfo(remote_path, buf)
            return buf.getvalue()
        finally:
            sftp.close()
            transport.close()

    # ------------------------------------------------------------------
    # FTP / FTPS backend
    # ------------------------------------------------------------------
    def _open_ftp(self):
        self.ensure_one()
        cls = ftplib.FTP_TLS if self.protocol == "ftps" else ftplib.FTP
        ftp = cls()
        ftp.connect(self.host, self.port or 21, timeout=30)
        ftp.login(self.username or "", self._secret())
        if self.protocol == "ftps":
            ftp.prot_p()  # encrypt the data channel
        ftp.set_pasv(bool(self.passive))
        return ftp

    def _ftp_list(self):
        ftp = self._open_ftp()
        try:
            try:
                names = ftp.nlst(self.remote_dir)
            except ftplib.error_perm as e:
                # "550 No files found" / empty directory -> treat as empty, not error.
                if str(e).startswith("550"):
                    return []
                raise
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()
        return [os.path.basename(n) for n in names if fnmatch.fnmatch(os.path.basename(n), self.file_glob)]

    def _ftp_download(self, name):
        ftp = self._open_ftp()
        try:
            remote_path = self.remote_dir.rstrip("/") + "/" + name
            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {remote_path}", buf.write)
            return buf.getvalue()
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()

    # ------------------------------------------------------------------
    # Protocol-neutral interface
    # ------------------------------------------------------------------
    def _list_remote(self):
        self.ensure_one()
        if self.protocol == "sftp":
            return sorted(self._sftp_list())
        return sorted(self._ftp_list())

    def _download_remote(self, name):
        self.ensure_one()
        if self.protocol == "sftp":
            return self._sftp_download(name)
        return self._ftp_download(name)

    def action_test_connection(self):
        self.ensure_one()
        matched = self._list_remote()
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
        channel = self._queue_channel()
        imported = 0
        for name in self._list_remote():
            raw = self._download_remote(name)
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
                        channel=channel,
                        description=f"Feed {self.name}: {name}",
                    ).run(log)
                    log.job_uuid = getattr(job, "uuid", False)
                except Exception:
                    Executor.run(log)
            else:
                Executor.run(log)
            imported += 1
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
