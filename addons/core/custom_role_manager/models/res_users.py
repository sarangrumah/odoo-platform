# -*- coding: utf-8 -*-
"""Role assignment on ``res.users`` and the reconciliation engine.

Group membership in Odoo is a computed closure over ``res.groups.implied_ids``;
``res.users.group_ids`` holds only the *direct* groups and ``all_group_ids`` the
closure. Every write here therefore goes through the ORM on ``group_ids`` —
writing ``res_groups_users_rel`` directly leaves the closure stale, which is how
a tenant ends up with users who "have" a group that grants them nothing.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    role_ids = fields.Many2many(
        "custom.security.role",
        "res_users_security_role_rel",
        "user_id",
        "role_id",
        string="Roles",
        help="Named position(s) held by this user. The groups below are kept in "
        "sync with the roles automatically.",
    )
    role_granted_group_ids = fields.Many2many(
        "res.groups",
        "res_users_role_granted_group_rel",
        "user_id",
        "group_id",
        string="Groups Granted by Roles",
        readonly=True,
        copy=False,
        help="Ledger of what the role engine granted last time. Only these may "
        "ever be revoked by it.",
    )
    role_baseline_group_ids = fields.Many2many(
        "res.groups",
        "res_users_role_baseline_group_rel",
        "user_id",
        "group_id",
        string="Groups Held Before Roles",
        readonly=True,
        copy=False,
        help="Snapshot taken the first time a role was applied to this user. "
        "Groups in here are never revoked by the role engine.",
    )

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        with_roles = users.filtered("role_ids")
        if with_roles and not self.env.context.get("role_apply"):
            with_roles._apply_security_roles()
        return users

    def write(self, vals):
        res = super().write(vals)
        if "role_ids" in vals and not self.env.context.get("role_apply"):
            self._apply_security_roles()
        return res

    # ------------------------------------------------------------------
    # The engine
    # ------------------------------------------------------------------
    def _apply_security_roles(self):
        """Reconcile ``group_ids`` with ``role_ids``.

        Revokes **only** groups this engine granted and that the user did not
        already hold before roles were introduced. Anything granted by hand, or
        by another module (the Keycloak SSO mapping writes additively, for
        example), is therefore untouched by a role change.
        """
        for user in self:
            sudo_user = user.sudo()
            if not sudo_user.role_baseline_group_ids and not sudo_user.role_granted_group_ids:
                # First application: whatever the user holds now is "manual".
                sudo_user.with_context(role_apply=True).write(
                    {"role_baseline_group_ids": [Command.set(sudo_user.group_ids.ids)]}
                )

            target = sudo_user.role_ids._all_group_ids()
            to_grant = target - sudo_user.group_ids
            to_revoke = (
                sudo_user.role_granted_group_ids - target - sudo_user.role_baseline_group_ids
            ) & sudo_user.group_ids

            user._check_role_lockout(to_revoke)

            commands = [Command.link(g.id) for g in to_grant]
            commands += [Command.unlink(g.id) for g in to_revoke]
            if commands:
                sudo_user.with_context(role_apply=True).write({"group_ids": commands})
            sudo_user.with_context(role_apply=True).write(
                {"role_granted_group_ids": [Command.set(target.ids)]}
            )
            if to_grant or to_revoke:
                _logger.info(
                    "Roles applied to %s: granted %s, revoked %s",
                    user.login,
                    to_grant.mapped("name") or "-",
                    to_revoke.mapped("name") or "-",
                )

    def _check_role_lockout(self, to_revoke):
        """Refuse the two revocations that would leave nobody able to fix this."""
        self.ensure_one()
        if not to_revoke:
            return
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        system = self.env.ref("base.group_system", raise_if_not_found=False)
        if not system or system not in to_revoke:
            return
        if self == self.env.user:
            raise UserError(
                _("Applying this role would remove your own Settings access. "
                  "Ask another administrator to change your roles.")
            )
        if admin and self == admin and not self.env.su:
            raise UserError(
                _("The %s user must keep Settings access. Change its roles as a "
                  "superuser if this is really intended.", admin.name)
            )

    def action_reapply_security_roles(self):
        self._apply_security_roles()
        return True
