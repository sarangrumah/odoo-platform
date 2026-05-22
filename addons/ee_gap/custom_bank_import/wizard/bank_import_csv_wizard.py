# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BankImportCsvWizard(models.TransientModel):
    _name = "custom.bank.import.csv.wizard"
    _description = "Bank Statement CSV Import Wizard"

    journal_id = fields.Many2one("account.journal", required=True, domain=[("type", "=", "bank")])
    template_id = fields.Many2one("custom.bank.import.template", required=True)
    file = fields.Binary(string="CSV File", required=True)
    filename = fields.Char()
    statement_name = fields.Char(default="Imported")

    def action_import(self):
        self.ensure_one()
        Log = self.env["custom.bank.import.log"].sudo()
        if not self.file:
            raise UserError(_("Please upload a file."))
        raw = base64.b64decode(self.file)
        file_hash = hashlib.sha256(raw).hexdigest()
        existing = Log.search(
            [
                ("file_hash", "=", file_hash),
                ("state", "in", ("imported", "partial")),
            ],
            limit=1,
        )
        if existing:
            raise UserError(
                _(
                    "This exact file was already imported (log #%s). "
                    "Archive the previous import first if you really want to redo.",
                )
                % existing.id
            )

        try:
            parsed = self.template_id.parse_csv(self.file)
        except Exception as e:  # pragma: no cover - defensive
            _logger.exception("CSV parse failed")
            log = Log.create(
                {
                    "template_id": self.template_id.id,
                    "journal_id": self.journal_id.id,
                    "filename": self.filename,
                    "file_hash": file_hash,
                    "state": "failed",
                    "error_message": str(e),
                }
            )
            raise UserError(_("Parsing failed: %s") % e) from e

        lines = parsed["lines"]
        errors = parsed["errors"]
        if not lines:
            log = Log.create(
                {
                    "template_id": self.template_id.id,
                    "journal_id": self.journal_id.id,
                    "filename": self.filename,
                    "file_hash": file_hash,
                    "state": "failed",
                    "line_count": 0,
                    "error_count": len(errors),
                    "error_message": "; ".join(f"row {n}: {e}" for n, e in errors[:50]) or "No parseable lines.",
                }
            )
            raise UserError(
                _(
                    "No transaction lines parsed. %s parse errors. See log #%s.",
                )
                % (len(errors), log.id)
            )

        Statement = self.env["account.bank.statement"]
        StatementLine = self.env["account.bank.statement.line"]
        statement = Statement.create(
            {
                "name": self.statement_name or self.filename or "Bank Import",
                "date": lines[0]["date"],
                "journal_id": self.journal_id.id,
            }
        )
        line_vals = []
        for ln in lines:
            line_vals.append(
                {
                    "statement_id": statement.id,
                    "journal_id": self.journal_id.id,
                    "date": ln["date"],
                    "payment_ref": (ln["ref"] or ln.get("partner_hint") or "/")[:255],
                    "ref": (ln["ref"] or "")[:64] or False,
                    "amount": float(ln["amount"]),
                }
            )
        StatementLine.create(line_vals)

        state = "partial" if errors else "imported"
        log = Log.create(
            {
                "template_id": self.template_id.id,
                "journal_id": self.journal_id.id,
                "statement_id": statement.id,
                "filename": self.filename,
                "file_hash": file_hash,
                "line_count": len(line_vals),
                "error_count": len(errors),
                "state": state,
                "raw_payload": "; ".join(f"row {n}: {e}" for n, e in errors[:200]) if errors else False,
            }
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": "custom.bank.import.log",
            "res_id": log.id,
            "view_mode": "form",
            "target": "current",
        }
