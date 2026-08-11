# -*- coding: utf-8 -*-
"""``custom.security.role`` — a named bundle of ``res.groups``.

A role is *only* a bundle. It never becomes a ``res.groups`` itself and never
becomes a ``res.groups.privilege``: groups that share a privilege are rendered
as a single pick-one dropdown on the user form, so modelling roles that way
would silently drop every other module's group when a user is saved (this is
exactly the incident that emptied the custom menus on a production tenant).
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CustomSecurityRole(models.Model):
    _name = "custom.security.role"
    _description = "Security Role"
    _order = "role_domain, sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        index=True,
        help="Stable technical key. Used by the SSO role mapping and by the "
        "provisioning scripts — renaming it breaks them.",
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    role_domain = fields.Selection(
        [
            ("accounting", "Accounting"),
            ("inventory", "Inventory & Warehouse"),
            ("purchase", "Purchasing"),
            ("sales", "Sales"),
            ("pos", "Point of Sale"),
            ("hr", "HR"),
            ("it", "IT / System"),
            ("audit", "Audit / Read-only"),
            ("other", "Other"),
        ],
        string="Functional Domain",
        default="other",
        required=True,
        index=True,
    )
    level = fields.Selection(
        [
            ("manager", "Manager"),
            ("supervisor", "Supervisor"),
            ("staff", "Staff"),
            ("operator", "Operator"),
            ("readonly", "Read-only"),
        ],
        default="staff",
        required=True,
    )
    scope = fields.Selection(
        [
            ("head_office", "Head Office"),
            ("retail", "Retail / Store"),
            ("both", "Both"),
        ],
        default="both",
        required=True,
        help="Where this position exists in the organisation. Informational — "
        "it drives grouping in the role list, not the rights themselves.",
    )
    description = fields.Text()

    group_ids = fields.Many2many(
        "res.groups",
        "custom_security_role_group_rel",
        "role_id",
        "group_id",
        string="Granted Groups",
    )
    implied_role_ids = fields.Many2many(
        "custom.security.role",
        "custom_security_role_implied_rel",
        "role_id",
        "implied_id",
        string="Inherits Roles",
        help="This role also grants everything these roles grant.",
    )
    company_ids = fields.Many2many(
        "res.company",
        string="Restricted to Companies",
        help="Empty means the role is offered to every company.",
    )
    user_ids = fields.Many2many(
        "res.users",
        "res_users_security_role_rel",
        "role_id",
        "user_id",
        string="Users",
    )
    user_count = fields.Integer(compute="_compute_user_count")

    is_seed = fields.Boolean(
        string="Shipped by Platform",
        readonly=True,
        copy=False,
        help="Created from the platform's seed catalogue.",
    )
    customized = fields.Boolean(
        readonly=True,
        copy=False,
        help="A shipped role that an administrator has edited. Platform upgrades "
        "no longer re-sync its group list, so local changes are never lost.",
    )

    # Odoo 19 ignores the legacy ``_sql_constraints`` list — table objects only.
    _code_uniq = models.Constraint("UNIQUE (code)", "Role code must be unique.")

    # ------------------------------------------------------------------
    # Compute / constraints
    # ------------------------------------------------------------------
    @api.depends("user_ids")
    def _compute_user_count(self):
        for role in self:
            role.user_count = len(role.user_ids)

    @api.constrains("implied_role_ids")
    def _check_implied_recursion(self):
        for role in self:
            if role._has_cycle("implied_role_ids"):
                raise ValidationError(
                    _("A role cannot inherit itself, directly or through another role.")
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def _all_group_ids(self):
        """Every group this role grants, following ``implied_role_ids``.

        Cycle-safe on purpose: ``_check_implied_recursion`` should prevent
        cycles, but this method also runs during data loading (before the
        constraint fires on the last write of a mutual pair).
        """
        seen = set()
        todo = list(self)
        groups = self.env["res.groups"]
        while todo:
            role = todo.pop()
            if role.id in seen:
                continue
            seen.add(role.id)
            groups |= role.group_ids
            todo.extend(role.implied_role_ids)
        return groups

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    def write(self, vals):
        # An administrator editing a shipped role opts that role out of future
        # platform refreshes — better a stale template than lost local intent.
        if not self.env.context.get("role_seed_sync") and (
            "group_ids" in vals or "implied_role_ids" in vals
        ):
            seeds = self.filtered(lambda r: r.is_seed and not r.customized)
            if seeds:
                super(CustomSecurityRole, seeds).write({"customized": True})
        res = super().write(vals)
        if "group_ids" in vals or "implied_role_ids" in vals or "active" in vals:
            # The composition changed: push it to everyone holding the role,
            # including holders of roles that inherit this one.
            self._reapply_to_holders()
        return res

    def _reapply_to_holders(self):
        """Re-run the role engine for every user affected by these roles."""
        affected = self._holder_roles()
        users = affected.mapped("user_ids")
        if users:
            users._apply_security_roles()

    def _holder_roles(self):
        """These roles plus every role that (transitively) inherits them."""
        result = self
        frontier = self
        while frontier:
            parents = self.search([("implied_role_ids", "in", frontier.ids)]) - result
            result |= parents
            frontier = parents
        return result

    @api.model
    def _sync_seed_roles(self):
        """Entry point for ``data/seed_roles_load.xml`` (install and every update)."""
        from ..data.seed_roles import sync_seed_roles

        return sync_seed_roles(self.env)

    def action_sync_seed_roles(self):
        self._sync_seed_roles()
        return True

    def action_reapply(self):
        self.ensure_one()
        self.user_ids._apply_security_roles()
        return True
