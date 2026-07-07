# -*- coding: utf-8 -*-
"""Retail import log line — per-row outcome of one import.

Each source row of an imported file gets one line here, classified by ``status``
(created / updated / archived / skipped / duplicate / error). This turns the old
capped ``raw_payload`` text blob on ``retail.import.log`` into a queryable table:
the operator can filter by status, group by ``ref_key`` to surface in-file
duplicates, and download an error report.

High volume: X101 can be ~160k rows, so this model is intentionally lean (no
mail.thread, short ``message`` Char, ``raw_json`` only kept for error/duplicate
lines). The executor bulk-``create()``s lines at its existing batch-commit
boundaries — never per row. A configurable cap
(``retail_import.max_log_lines``) caps how many lines a single import may store;
the integer counters on the log stay exact even when lines are truncated.
"""

from __future__ import annotations

from odoo import api, fields, models

MESSAGE_CAP = 500


class RetailImportLogLine(models.Model):
    _name = "retail.import.log.line"
    _description = "Retail Import Log Line"
    _order = "log_id, row, id"

    log_id = fields.Many2one("retail.import.log", required=True, ondelete="cascade", index=True)
    row = fields.Integer(string="Source Row", index=True, help="1-based row number in the source file.")
    status = fields.Selection(
        [
            ("created", "Created"),
            ("updated", "Updated"),
            ("archived", "Archived"),
            ("skipped", "Skipped"),
            ("duplicate", "Duplicate"),
            ("error", "Error"),
        ],
        index=True,
        required=True,
    )
    ref_key = fields.Char(string="Key", index=True, help="Natural key of the row (SKU / code / store).")
    model_name = fields.Char(string="Model", help="Target Odoo model, e.g. product.template.")
    res_id = fields.Integer(string="Record ID", help="Created/updated record id, when applicable.")
    message = fields.Char()
    raw_json = fields.Text(help="Cleaned source values; kept only for error/duplicate rows.")
    company_id = fields.Many2one(related="log_id.company_id", store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            msg = vals.get("message")
            if msg and len(msg) > MESSAGE_CAP:
                vals["message"] = msg[:MESSAGE_CAP]
        return super().create(vals_list)

    @api.depends("ref_key", "row", "status")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"row {rec.row}: {rec.ref_key or rec.status or ''}"
