# -*- coding: utf-8 -*-
"""``operating.unit`` — the organisational unit data is scoped by.

Before this model, an Operating Unit on this platform was *only* an
``account.analytic.account`` in a plan named "Operating Unit", created per store
by the Levi's localization. That works as a reporting dimension but cannot carry
a hierarchy, cannot be linked to a warehouse or a POS config, and — most
importantly — cannot be used for access control.

This model becomes the master record and **links** to whatever already exists:
the analytic account, and (through the bridge modules) the warehouse, the
journals and the POS configs. Nothing is renamed and nothing is replaced; the
store's ``stock.warehouse.code`` in particular is the join key the retail import
relies on and is never touched.
"""

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError


class OperatingUnit(models.Model):
    _name = "operating.unit"
    _description = "Operating Unit"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "complete_name"
    _rec_names_search = ["code", "name", "complete_name"]

    name = fields.Char(required=True, index=True)
    code = fields.Char(
        required=True,
        index=True,
        help="Stable business key. For a store this is normally the "
        "stock.warehouse code — the retail import joins on it, so never change it.",
    )
    complete_name = fields.Char(compute="_compute_complete_name", store=True, recursive=True)
    ou_type = fields.Selection(
        [
            ("company", "Head Office"),
            ("area", "Area / Region"),
            ("store", "Store / Branch"),
            ("other", "Other"),
        ],
        string="Type",
        default="store",
        required=True,
        index=True,
    )
    parent_id = fields.Many2one(
        "operating.unit", string="Parent", ondelete="restrict", index=True
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("operating.unit", "parent_id", string="Children")
    company_id = fields.Many2one(
        "res.company", required=True, index=True, default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    manager_user_id = fields.Many2one("res.users", string="Manager")
    partner_id = fields.Many2one("res.partner", string="Address")
    note = fields.Text()

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        ondelete="restrict",
        index=True,
        help="Analytic account representing this unit on journal items. Links to "
        "the dimension a tenant may already have — it is not created here.",
    )
    user_ids = fields.Many2many(
        "res.users",
        "res_users_operating_unit_rel",
        "operating_unit_id",
        "user_id",
        string="Assigned Users",
    )
    user_count = fields.Integer(compute="_compute_user_count")

    _code_company_uniq = models.Constraint(
        "UNIQUE (code, company_id)", "Operating Unit code must be unique per company."
    )
    _analytic_uniq = models.Constraint(
        "UNIQUE (analytic_account_id)",
        "That analytic account already belongs to another Operating Unit.",
    )

    # ------------------------------------------------------------------
    # Compute / constraints
    # ------------------------------------------------------------------
    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for ou in self:
            ou.complete_name = (
                "%s / %s" % (ou.parent_id.complete_name, ou.name) if ou.parent_id else ou.name
            )

    @api.depends("user_ids")
    def _compute_user_count(self):
        for ou in self:
            ou.user_count = len(ou.user_ids)

    @api.constrains("parent_id")
    def _check_parent_recursion(self):
        for ou in self:
            if ou._has_cycle():
                raise ValidationError(_("An Operating Unit cannot be its own ancestor."))
            if ou.parent_id and ou.parent_id.company_id != ou.company_id:
                raise ValidationError(
                    _("An Operating Unit must belong to the same company as its parent.")
                )

    @api.constrains("ou_type", "parent_id", "company_id")
    def _check_head_office(self):
        for ou in self:
            if ou.ou_type != "company":
                continue
            if ou.parent_id:
                raise ValidationError(_("The Head Office unit cannot have a parent."))
            other = self.with_context(active_test=False).search(
                [
                    ("ou_type", "=", "company"),
                    ("company_id", "=", ou.company_id.id),
                    ("id", "!=", ou.id),
                ],
                limit=1,
            )
            if other:
                raise ValidationError(
                    _("%(company)s already has a Head Office unit (%(existing)s).",
                      company=ou.company_id.display_name, existing=other.display_name)
                )

    # ------------------------------------------------------------------
    # Public API — used by the bridges, the migration and the scripts
    # ------------------------------------------------------------------
    @api.model
    def _ensure(self, code, name, company, ou_type="store", parent=None, **links):
        """Idempotent get-or-create keyed on (company, code).

        Never renames an existing unit and never overwrites a link that is
        already set — re-running a provisioning script must be a no-op.
        """
        company_id = company.id if hasattr(company, "id") else company
        existing = self.with_context(active_test=False).search(
            [("code", "=", code), ("company_id", "=", company_id)], limit=1
        )
        links = {k: v for k, v in links.items() if v}
        if existing:
            fill = {
                field: value
                for field, value in links.items()
                if field in self._fields and not existing[field]
            }
            if parent and not existing.parent_id and parent != existing:
                fill["parent_id"] = parent.id
            if fill:
                existing.write(fill)
            return existing
        vals = {
            "code": code,
            "name": name,
            "company_id": company_id,
            "ou_type": ou_type,
            "parent_id": parent.id if parent else False,
        }
        vals.update({k: v for k, v in links.items() if k in self._fields})
        return self.create(vals)

    @api.model
    @tools.ormcache()
    def _analytic_index(self):
        """``{analytic_account_id: operating_unit_id}``.

        One query, cached for the registry: the stored-OU computes run over
        whole journals, and a per-line search would turn a 500-line bill into
        500 queries.
        """
        rows = self.with_context(active_test=False).sudo().search_read(
            [("analytic_account_id", "!=", False)], ["analytic_account_id"]
        )
        return {row["analytic_account_id"][0]: row["id"] for row in rows}

    def _descendant_ids(self):
        """These units plus every unit below them."""
        if not self:
            return []
        return self.with_context(active_test=False).search([("id", "child_of", self.ids)]).ids

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        units = super().create(vals_list)
        self.env.registry.clear_cache()
        return units

    def write(self, vals):
        res = super().write(vals)
        # ``ou_allowed_ids`` is not stored, so re-parenting or archiving a unit
        # needs no recompute — but the analytic index is cached, and the users'
        # in-memory field cache must be dropped so the new tree is seen at once.
        if {"analytic_account_id", "active", "parent_id"} & set(vals):
            self.env.registry.clear_cache()
            self.env.invalidate_all()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res
