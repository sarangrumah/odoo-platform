# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BankH2HConnection(models.Model):
    _name = "custom.bank.h2h.connection"
    _description = "Bank Host-to-Host Connection"
    _order = "name"
    _inherit = ["mail.thread", "custom.bank.import.dedup"]

    name = fields.Char(required=True, tracking=True)
    bank_code = fields.Selection(
        [
            ("BCA", "BCA"),
            ("Mandiri", "Mandiri"),
            ("BNI", "BNI"),
            ("BRI", "BRI"),
            ("CIMB", "CIMB Niaga"),
            ("Permata", "Permata"),
            ("Danamon", "Danamon"),
            ("Other", "Other / Generic"),
        ],
        required=True,
        tracking=True,
    )
    adapter_config_id = fields.Many2one(
        "custom.adapter.config",
        required=True,
        ondelete="restrict",
        tracking=True,
        help="Holds base_url, auth method, secret ref, circuit breaker config.",
    )
    account_number = fields.Char(required=True, tracking=True)
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        ondelete="restrict",
        domain=[("type", "=", "bank")],
        tracking=True,
    )
    sync_interval_minutes = fields.Integer(default=60, required=True)
    last_sync_at = fields.Datetime(readonly=True)
    status = fields.Selection(
        [("active", "Active"), ("paused", "Paused"), ("error", "Error")],
        default="active",
        required=True,
        tracking=True,
    )
    last_error = fields.Text(readonly=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    _acct_bank_uniq = models.Constraint(
        "unique(bank_code, account_number, company_id)",
        "Account number must be unique per bank per company.",
    )

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def action_sync_now(self):
        for rec in self:
            rec._do_sync()
        return True

    def _do_sync(self) -> None:
        self.ensure_one()
        if self.status == "paused":
            return
        adapter = self.adapter_config_id.get_adapter()
        # Pull range: last_sync_at or last 24h
        end = fields.Datetime.now()
        start = self.last_sync_at or (end - timedelta(days=1))
        try:
            statement = adapter.inquiry_statement(
                account_number=self.account_number,
                date_from=start.date() if isinstance(start, datetime) else start,
                date_to=end.date(),
            )
        except Exception as e:
            _logger.exception("H2H sync failed for %s", self.name)
            self.write({"status": "error", "last_error": str(e)[:1000]})
            return
        if not statement or not getattr(statement, "ok", False):
            err = (statement.error if statement else "no response") or "unknown"
            self.write({"status": "error", "last_error": err[:1000]})
            return
        lines = (statement.data or {}).get("lines", [])
        self._persist_lines(lines, raw_payload=statement.data)
        self.write(
            {
                "last_sync_at": end,
                "status": "active",
                "last_error": False,
            }
        )

    def _persist_lines(self, lines: list[dict], raw_payload: dict | None) -> None:
        """Write down what the bank sent, minus what this journal already holds.

        A fetch window is not a fresh set of transactions: ``_sync_one`` asks for
        a span that deliberately overlaps the last one, so the same transaction
        arrives again on every run by design. Without the guard the H2H feed
        would repeat exactly what the CSV uploads did — and worse, because a cron
        does it unattended.
        """
        Log = self.env["custom.bank.import.log"].sudo()
        StatementLine = self.env["account.bank.statement.line"]
        Statement = self.env["account.bank.statement"]
        vals = [
            {
                "journal_id": self.journal_id.id,
                "date": ln.get("date") or fields.Date.today(),
                "payment_ref": (ln.get("description") or ln.get("ref") or "/")[:255],
                "ref": (ln.get("ref") or "")[:64] or False,
                "amount": float(ln.get("amount") or 0.0),
            }
            for ln in lines
        ]
        line_vals, duplicates = self._split_already_imported(
            [(self._dedup_key(row["date"], row["payment_ref"], row["amount"]), row) for row in vals]
        )
        if not line_vals:
            # Nothing new — an empty window and an entirely repeated one are the
            # same event here, and neither may create a statement: an empty
            # statement reads as a delivery that happened.
            Log.create(
                {
                    "template_id": self._h2h_pseudo_template().id,
                    "journal_id": self.journal_id.id,
                    "filename": f"h2h-{self.bank_code}-{fields.Datetime.now()}",
                    "line_count": 0,
                    "duplicate_count": len(duplicates),
                    "state": "imported",
                    "raw_payload": str(raw_payload)[:8000] if raw_payload else None,
                }
            )
            return
        statement = Statement.create(
            {
                "name": f"H2H {self.bank_code} {fields.Date.today()}",
                "date": fields.Date.today(),
                "journal_id": self.journal_id.id,
            }
        )
        for row in line_vals:
            row["statement_id"] = statement.id
        StatementLine.create(line_vals)
        Log.create(
            {
                "template_id": self._h2h_pseudo_template().id,
                "journal_id": self.journal_id.id,
                "statement_id": statement.id,
                "filename": f"h2h-{self.bank_code}-{fields.Datetime.now()}",
                "line_count": len(line_vals),
                "duplicate_count": len(duplicates),
                "state": "imported",
                "raw_payload": str(raw_payload)[:8000] if raw_payload else None,
            }
        )

    def _h2h_pseudo_template(self):
        """Get or create a per-bank placeholder template for log linkage."""
        Template = self.env["custom.bank.import.template"].sudo()
        code = f"h2h_{self.bank_code.lower()}"
        tpl = Template.search([("code", "=", code)], limit=1)
        if tpl:
            return tpl
        return Template.create(
            {
                "name": f"H2H Pseudo — {self.bank_code}",
                "code": code,
                "bank_id": False,
                "date_format": "%Y-%m-%d",
            }
        )

    # ------------------------------------------------------------------
    # Cron entry point
    # ------------------------------------------------------------------

    @api.model
    def _cron_sync_due(self) -> None:
        now = fields.Datetime.now()
        active = self.search([("status", "=", "active")])
        for conn in active:
            last = conn.last_sync_at
            interval = max(1, conn.sync_interval_minutes or 60)
            if last and (now - last).total_seconds() < interval * 60:
                continue
            try:
                conn._do_sync()
            except Exception:  # noqa: BLE001
                _logger.exception("h2h cron sync error for %s", conn.name)
