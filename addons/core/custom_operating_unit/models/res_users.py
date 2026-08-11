# -*- coding: utf-8 -*-
"""Which Operating Units a user may see.

The posture is deliberately **open by default**: a user with no unit assigned
is unrestricted. Installing this module on a live tenant therefore changes
nothing until somebody is actually assigned — no user wakes up to an empty
Accounting app because a module landed overnight.

``ou_allowed_ids`` is computed, not stored, so there is no column to create and
no mass recompute at upgrade. The record rules in the bridge modules read it.
"""

from odoo import api, fields, models

ALL_UNITS_GROUP = "custom_operating_unit.group_operating_unit_all"
INCLUDE_UNTAGGED_PARAM = "custom_operating_unit.include_untagged"


class ResUsers(models.Model):
    _inherit = "res.users"

    operating_unit_ids = fields.Many2many(
        "operating.unit",
        "res_users_operating_unit_rel",
        "user_id",
        "operating_unit_id",
        string="Operating Units",
        help="Leave empty — or grant 'All Operating Units' — to see every unit. "
        "Assigning an area unit implicitly grants every store beneath it.",
    )
    default_operating_unit_id = fields.Many2one(
        "operating.unit",
        string="Default Operating Unit",
        help="Pre-filled on documents this user creates.",
    )
    ou_all_access = fields.Boolean(
        string="All Operating Units",
        compute="_compute_ou_all_access",
        inverse="_inverse_ou_all_access",
        help="Head-office profile: sees every unit regardless of the assignment below.",
    )

    # --- what the record rules read -----------------------------------
    ou_is_scoped = fields.Boolean(compute="_compute_ou_scope", compute_sudo=True)
    ou_allowed_ids = fields.Many2many(
        "operating.unit",
        compute="_compute_ou_scope",
        compute_sudo=True,
        string="Allowed Operating Units",
    )
    ou_include_untagged = fields.Boolean(compute="_compute_ou_scope", compute_sudo=True)

    @api.depends("operating_unit_ids", "all_group_ids")
    def _compute_ou_scope(self):
        OU = self.env["operating.unit"].sudo()
        every_unit = OU.search([])
        group_all = self.env.ref(ALL_UNITS_GROUP, raise_if_not_found=False)
        include_untagged = self.env["ir.config_parameter"].sudo().get_param(INCLUDE_UNTAGGED_PARAM, "1") != "0"
        root_id = self.env.ref("base.user_root").id
        for user in self:
            unrestricted = (
                not user.operating_unit_ids or user.id == root_id or (group_all and group_all in user.all_group_ids)
            )
            user.ou_is_scoped = not unrestricted
            user.ou_allowed_ids = (
                every_unit
                if unrestricted
                # child_of over parent_path: an area manager gets the whole
                # subtree for free, with no denormalised table to maintain.
                else OU.search([("id", "child_of", user.operating_unit_ids.ids)])
            )
            user.ou_include_untagged = include_untagged

    @api.depends("all_group_ids")
    def _compute_ou_all_access(self):
        group_all = self.env.ref(ALL_UNITS_GROUP, raise_if_not_found=False)
        for user in self:
            user.ou_all_access = bool(group_all) and group_all in user.all_group_ids

    def _inverse_ou_all_access(self):
        group_all = self.env.ref(ALL_UNITS_GROUP, raise_if_not_found=False)
        if not group_all:
            return
        for user in self:
            if user.ou_all_access:
                user.sudo().write({"group_ids": [fields.Command.link(group_all.id)]})
            elif group_all in user.group_ids:
                user.sudo().write({"group_ids": [fields.Command.unlink(group_all.id)]})
