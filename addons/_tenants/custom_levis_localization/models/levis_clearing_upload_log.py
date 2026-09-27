# -*- coding: utf-8 -*-
"""``levis.clearing.upload.log`` — what was uploaded, by whom, and what it changed.

A reconciliation that leaves the system in a spreadsheet and comes back has to be
able to answer, months later, *which* file said so. The wizard is transient and
the manual mappings it writes carry only their final state, so the audit trail is
this: the file itself, its hash, the counts, and the rows that were refused with
the reason each was refused.

Borrowed wholesale from ``custom.bank.import.log`` (``custom_bank_import``), which
learned the shape the hard way: a failed import that raises and rolls back leaves
nothing to look at, so the log is written even when nothing is applied.
"""

from odoo import fields, models


class LevisClearingUploadLog(models.Model):
    _name = "levis.clearing.upload.log"
    _description = "POS Clearing Recon Upload"
    _order = "create_date desc, id desc"
    _rec_name = "file_name"

    company_id = fields.Many2one(
        "res.company", required=True, index=True, default=lambda self: self.env.company, ondelete="cascade"
    )
    run_id = fields.Many2one("levis.pos.clearing", string="Clearing Run", index=True, ondelete="set null")
    file_name = fields.Char(required=True)
    file_hash = fields.Char(string="SHA-256", index=True)
    state = fields.Selection(
        [("applied", "Applied"), ("partial", "Partly applied"), ("failed", "Nothing applied")],
        required=True,
        default="failed",
    )
    row_count = fields.Integer(string="Rows Read")
    applied_count = fields.Integer(string="Applied")
    unchanged_count = fields.Integer(string="Unchanged")
    rejected_count = fields.Integer(string="Rejected")
    rule_count = fields.Integer(string="MID Rules Created")
    recomputed = fields.Boolean(string="Run Recomputed")
    error_message = fields.Text(string="Rejections")
    manual_map_ids = fields.One2many("levis.clearing.manual.map", "upload_log_id", string="Mappings")
    user_id = fields.Many2one("res.users", string="Uploaded By", default=lambda self: self.env.user)

    def action_open_mappings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Manual mappings",
            "res_model": "levis.clearing.manual.map",
            "domain": [("upload_log_id", "=", self.id)],
            "view_mode": "list,form",
            "target": "current",
        }

    def action_open_attachments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Files",
            "res_model": "ir.attachment",
            "domain": [("res_model", "=", self._name), ("res_id", "=", self.id)],
            "view_mode": "list,form",
            "target": "current",
        }
