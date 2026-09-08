# -*- coding: utf-8 -*-
"""Bulk role assignment from the Users list."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class CustomSecurityRoleAssign(models.TransientModel):
    _name = "custom.security.role.assign"
    _description = "Assign Security Roles"

    user_ids = fields.Many2many("res.users", string="Users", required=True)
    role_ids = fields.Many2many("custom.security.role", string="Roles", required=True)
    mode = fields.Selection(
        [
            ("add", "Add these roles"),
            ("replace", "Replace with these roles"),
        ],
        default="add",
        required=True,
        help="Replace also revokes the groups the removed roles had granted — "
        "but never groups the user held before roles were introduced.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("active_model") == "res.users":
            active_ids = self.env.context.get("active_ids") or []
            if active_ids:
                res["user_ids"] = [Command.set(active_ids)]
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.user_ids:
            raise UserError(_("Select at least one user."))
        command = Command.set(self.role_ids.ids) if self.mode == "replace" else None
        for user in self.user_ids:
            if command is not None:
                user.write({"role_ids": [command]})
            else:
                user.write({"role_ids": [Command.link(r.id) for r in self.role_ids]})
        return {"type": "ir.actions.act_window_close"}
