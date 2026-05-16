# -*- coding: utf-8 -*-
"""Odoo-side read-only model mapped onto pdp.audit_log_v view."""

from odoo import fields, models, tools


class PdpAuditLog(models.Model):
    _name = "pdp.audit.log"
    _description = "PDP Audit Log (read-only view)"
    _auto = False
    _order = "ts desc"
    _rec_name = "id"

    ts = fields.Datetime(string="Timestamp", readonly=True)
    actor_user_id = fields.Integer(string="Actor User ID", readonly=True)
    actor_login = fields.Char(readonly=True)
    tenant_db = fields.Char(readonly=True)
    model_name = fields.Char(readonly=True, index=True)
    res_id = fields.Integer(readonly=True)
    action = fields.Selection(
        [
            ("create", "Create"),
            ("read", "Read"),
            ("write", "Write"),
            ("unlink", "Unlink"),
            ("export", "Export"),
            ("login", "Login"),
            ("logout", "Logout"),
            ("dsar", "DSAR"),
            ("unmask", "Unmask"),
            ("consent_grant", "Consent Grant"),
            ("consent_withdraw", "Consent Withdraw"),
            ("sertel_access", "Sertel Access"),
            ("xml_export", "XML Export"),
            ("xml_import", "XML Import"),
            ("custom", "Custom"),
        ],
        readonly=True,
    )
    field_changes = fields.Json(readonly=True)
    classification = fields.Char(readonly=True, index=True)
    ip_address = fields.Char(readonly=True)
    user_agent = fields.Text(readonly=True)
    request_id = fields.Char(readonly=True)
    reason = fields.Text(readonly=True)
    prev_hash_hex = fields.Char(string="Prev Hash", readonly=True)
    hash_hex = fields.Char(string="Hash", readonly=True)

    def init(self):
        # Map onto the existing pdp.audit_log_v view created in 02-pdp-schema.sql
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE OR REPLACE VIEW {self._table} AS
            SELECT
                id,
                ts,
                actor_user_id,
                actor_login,
                tenant_db,
                model_name,
                res_id,
                action,
                field_changes,
                classification,
                ip_address,
                user_agent,
                request_id,
                reason,
                prev_hash_hex,
                hash_hex
            FROM pdp.audit_log_v
            """
        )

    def action_verify_chain(self):
        """Run pdp.verify_audit_chain() and display the result."""
        self.env.cr.execute("SELECT broken_id, expected_hash, actual_hash FROM pdp.verify_audit_chain(NULL)")
        rows = self.env.cr.fetchall()
        if not rows:
            msg = "Audit chain VERIFIED — all rows consistent."
            kind = "success"
        else:
            broken = ", ".join(str(r[0]) for r in rows[:10])
            msg = "Audit chain BROKEN at row(s): %s%s" % (
                broken, " ..." if len(rows) > 10 else "",
            )
            kind = "danger"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "PDP Audit Chain",
                "message": msg,
                "type": kind,
                "sticky": True,
            },
        }
