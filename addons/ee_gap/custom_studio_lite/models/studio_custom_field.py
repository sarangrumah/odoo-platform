# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


SUPPORTED_TYPES = [
    ("char", "Text (single line)"),
    ("text", "Text (multi-line)"),
    ("integer", "Integer"),
    ("float", "Float"),
    ("boolean", "Boolean"),
    ("date", "Date"),
    ("datetime", "Datetime"),
    ("selection", "Selection"),
]

FIELD_NAME_RE = re.compile(r"^x_studio_[a-z0-9_]{1,60}$")


class StudioCustomField(models.Model):
    _name = "studio.custom.field"
    _description = "Studio Custom Field (declarative)"
    _inherit = ["pdp.audited.mixin"]
    _order = "model_id, technical_name"

    name = fields.Char(string="Label", required=True, translate=True)
    technical_name = fields.Char(
        required=True,
        help="Must start with x_studio_ — enforced at create time.",
    )
    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    model_name = fields.Char(related="model_id.model", store=True, readonly=True)
    field_type = fields.Selection(SUPPORTED_TYPES, required=True, default="char")
    selection_values = fields.Text(
        help="One key|label pair per line. Only used when field_type=selection.",
    )
    help_text = fields.Char()
    required = fields.Boolean()
    readonly = fields.Boolean()

    ir_model_fields_id = fields.Many2one("ir.model.fields", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("applied", "Applied"), ("error", "Error")],
        default="draft",
        required=True,
    )
    last_error = fields.Text(readonly=True)

    _uniq_model_field = models.Constraint(
        "unique(model_id, technical_name)",
        "Field name already exists on this model.",
    )

    def _pdp_audit_classification(self):
        return "internal"

    @api.constrains("technical_name")
    def _check_technical_name(self):
        for rec in self:
            if not FIELD_NAME_RE.match(rec.technical_name or ""):
                raise ValidationError(_("Technical name must match %s") % FIELD_NAME_RE.pattern)

    def action_apply(self):
        """Materialise the declared field on the target model via ir.model.fields."""
        IrField = self.env["ir.model.fields"].sudo()
        for rec in self:
            try:
                if rec.ir_model_fields_id:
                    rec.ir_model_fields_id.write(
                        {
                            "field_description": rec.name,
                            "help": rec.help_text,
                            "required": rec.required,
                            "readonly": rec.readonly,
                        }
                    )
                else:
                    vals = {
                        "name": rec.technical_name,
                        "field_description": rec.name,
                        "model_id": rec.model_id.id,
                        "ttype": rec.field_type,
                        "help": rec.help_text,
                        "required": rec.required,
                        "readonly": rec.readonly,
                    }
                    if rec.field_type == "selection" and rec.selection_values:
                        # Odoo stores selection as a string repr of list of tuples
                        pairs = []
                        for line in (rec.selection_values or "").splitlines():
                            if "|" in line:
                                k, v = line.split("|", 1)
                                pairs.append((k.strip(), v.strip()))
                        if not pairs:
                            raise UserError(_("Selection needs at least one key|label line."))
                        vals["selection"] = str(pairs)
                    rec.ir_model_fields_id = IrField.create(vals).id
                rec.write({"state": "applied", "last_error": False})
                rec._pdp_audit_write(
                    "studio_field_applied", rec.id, {"model": rec.model_name, "field": rec.technical_name}
                )
            except Exception as e:
                rec.write({"state": "error", "last_error": str(e)})
                rec._pdp_audit_write("studio_field_apply_failed", rec.id, {"error": str(e)})
