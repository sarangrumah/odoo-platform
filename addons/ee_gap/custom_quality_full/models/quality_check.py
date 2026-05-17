# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


CHECK_STATES = [("waiting", "Waiting"), ("pass", "Pass"), ("fail", "Fail")]


class QualityCheck(models.Model):
    _name = "quality.check"
    _description = "Quality Check Execution"
    _inherit = ["mail.thread", "pdp.audited.mixin"]
    _order = "create_date desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    point_id = fields.Many2one("quality.point", required=True, index=True)
    product_id = fields.Many2one(related="point_id.product_id", store=True)
    check_kind = fields.Selection(related="point_id.check_kind", store=True)
    user_id = fields.Many2one("res.users", default=lambda s: s.env.user)
    state = fields.Selection(CHECK_STATES, default="waiting", required=True, tracking=True, index=True)

    measure_value = fields.Float()
    measure_uom_id = fields.Many2one("uom.uom", related="point_id.measure_uom_id", readonly=True)
    note = fields.Text()
    performed_at = fields.Datetime(readonly=True)
    alert_id = fields.Many2one("quality.alert", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    def _pdp_audit_classification(self):
        return "internal"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("quality.check") or "QC-???"
        return super().create(vals_list)

    def action_pass(self):
        for rec in self:
            if rec.check_kind == "measure":
                pt = rec.point_id
                if (pt.measure_min and rec.measure_value < pt.measure_min) or \
                   (pt.measure_max and rec.measure_value > pt.measure_max):
                    raise UserError(_(
                        "Measurement %(val)s outside [%(min)s, %(max)s] — use 'Fail' instead.",
                        val=rec.measure_value, min=pt.measure_min, max=pt.measure_max,
                    ))
            rec.write({"state": "pass", "performed_at": fields.Datetime.now()})
            rec._pdp_audit_write("quality_check_pass", rec.id, None)

    def action_fail(self):
        for rec in self:
            rec.write({"state": "fail", "performed_at": fields.Datetime.now()})
            # Auto-raise an alert
            alert = self.env["quality.alert"].sudo().create({
                "name": f"NCR from check {rec.name}",
                "check_id": rec.id,
                "product_id": rec.product_id.id,
                "severity": "major",
                "description": rec.note or "",
            })
            rec.write({"alert_id": alert.id})
            rec._pdp_audit_write("quality_check_fail", rec.id, {"alert_id": alert.id})
