# -*- coding: utf-8 -*-
"""Mixin carrying the Operating Unit on a document, plus the write guard.

Record rules keep a scoped user from *seeing* other units' documents. They do
not reliably keep one from *booking* onto another unit: a rule is bypassed by
every ``sudo()`` path, and a create-time check misses a document that is moved
to another unit afterwards. The constraint below closes both.

``env.su`` is the intentional escape hatch — crons, post-init hooks, queue_job
workers, the retail-import executor and the POS closing entry all run elevated
and legitimately touch every unit.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class OperatingUnitMixin(models.AbstractModel):
    _name = "operating.unit.mixin"
    _description = "Operating Unit scoping mixin"

    operating_unit_id = fields.Many2one(
        "operating.unit",
        string="Operating Unit",
        index=True,
        ondelete="restrict",
        copy=True,
    )

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------
    # The check runs from create/write, not only from @api.constrains, because
    # a constraint is validated at *flush* time and flushing may happen through
    # a different environment than the one that made the change — an elevated
    # one, in which the guard would short-circuit and let a foreign unit
    # through. Checking in create/write pins the check to the environment that
    # actually performed the write. The constraint stays as a second line of
    # defence for values that reach the field by other routes.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_operating_unit_allowed()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "operating_unit_id" in vals:
            self._check_operating_unit_allowed()
        return res

    @api.constrains("operating_unit_id")
    def _check_operating_unit_allowed(self):
        if self.env.su or self.env.context.get("ou_skip_check"):
            return
        user = self.env.user
        if not user.ou_is_scoped:
            return
        allowed = set(user.ou_allowed_ids.ids)
        for record in self:
            unit = record.operating_unit_id
            if unit and unit.id not in allowed:
                raise AccessError(
                    _(
                        "You are not allowed to book %(document)s on Operating Unit "
                        "%(unit)s.",
                        document=record.display_name or record._description,
                        unit=unit.display_name,
                    )
                )

    @api.model
    def _ou_default(self):
        """Default unit for a new document: the user's own, when they have one."""
        return self.env.user.default_operating_unit_id
