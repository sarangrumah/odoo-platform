# -*- coding: utf-8 -*-
"""Stage configuration -- the per-stage SLA clock.

The development plan named a ``custom.project.stage.config`` model. It is realised
here as an extension of ``project.task.type`` on purpose: Odoo already owns the stage
engine and the kanban that renders it. A parallel stage model would have meant two
kanban implementations, two orderings, and two places to ask "what stage is this in".

What the plan actually needed was *behaviour attached to a stage*, and that is what
these fields carry.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProjectTaskType(models.Model):
    _name = "project.task.type"
    _inherit = ["project.task.type", "pdp.audited.mixin"]

    custom_code = fields.Char(
        string="Stage Code",
        help="Stable key used by the REST API and the Jira status map, so renaming a "
        "stage for humans does not break integrations.",
    )
    custom_applies_to = fields.Selection(
        [
            ("task", "Tasks only"),
            ("cr", "Change requests only"),
            ("both", "Tasks and change requests"),
        ],
        string="Applies To",
        default="both",
        required=True,
    )
    custom_sla_clock = fields.Selection(
        [
            ("running", "Running — time counts against the team"),
            ("paused", "Paused — time is deducted from cycle time"),
            ("user_side", "User side — time counts, but is booked to the user"),
            ("stopped", "Stopped — work is closed"),
        ],
        string="SLA Clock",
        default="running",
        required=True,
        help="How elapsed time in this stage is treated. This single field is what makes team metrics honest.",
    )
    custom_is_hold = fields.Boolean(
        string="Is Hold",
        help="A side stage, not a step in the flow. Entering it pauses the SLA clock.",
    )
    custom_is_waiting_user = fields.Boolean(
        string="Is Waiting User Verification",
        help="Work is done on our side; the brand still has to verify it.",
    )
    custom_is_closed_stage = fields.Boolean(
        string="Is Closing Stage",
        help="Reaching this stage stops the clock and stamps the closing date.",
    )
    custom_auto_close_days = fields.Integer(
        string="Auto-close After (working days)",
        default=0,
        help="Only meaningful on a Waiting-User-Verification stage: silence for this many "
        "working days closes the item automatically, with a notification.",
    )
    custom_require_reason = fields.Boolean(
        string="Reason Required",
        help="Moving into this stage demands a written reason (used by Hold).",
    )
    custom_next_stage_ids = fields.Many2many(
        "project.task.type",
        "custom_stage_next_rel",
        "stage_id",
        "next_stage_id",
        string="Allowed Next Stages",
        help="Leave empty to allow any transition. Filled in, it stops work from skipping stages.",
    )

    _custom_code_uniq = models.Constraint(
        "unique(custom_code)",
        "Another stage already uses this stage code.",
    )

    @api.constrains("custom_is_hold", "custom_is_waiting_user", "custom_sla_clock")
    def _check_clock_coherence(self):
        for rec in self:
            if rec.custom_is_hold and rec.custom_sla_clock != "paused":
                raise ValidationError(_("Stage %s is marked as Hold, so its SLA clock must be 'paused'.", rec.name))
            if rec.custom_is_waiting_user and rec.custom_sla_clock != "user_side":
                raise ValidationError(_("Stage %s waits on the user, so its SLA clock must be 'user side'.", rec.name))
            if rec.custom_is_hold and rec.custom_is_waiting_user:
                raise ValidationError(_("A stage cannot be both Hold and Waiting User Verification."))

    @api.model
    def _stage_by_code(self, code):
        """Resolve a stage by its stable code. Returns an empty recordset if absent."""
        return self.search([("custom_code", "=", code)], limit=1)

    @api.model
    def _vaspmo_make_stages_shared(self):
        """Clear the stage owner on every VAS PMO stage.

        ``project.task.type.user_id`` defaults to ``self.env.uid``, and a stage that has
        an owner is a *personal* stage: the global record rule
        ``project.task_type_visibility_rule`` restricts it to ``user_id in (False,
        user.id)``. Being global, that rule is AND-ed, so not even the project manager
        group can see past it. Seeding these stages during install therefore made all
        seven the private property of the installing user, which hides the whole board
        from the team and makes the stage CMS unsavable.

        Odoo's own shared stages dodge this by carrying ``project_ids``, which blanks
        ``user_id`` through ``_compute_user_id``. VAS PMO stages are deliberately global
        (they apply to every project and to change requests), so the owner is cleared
        directly instead.

        Called from data on every install and upgrade, because the stage records live in
        a ``noupdate="1"`` block and would otherwise keep the owner they were born with.
        """
        stages = self.sudo().search([("custom_code", "!=", False), ("user_id", "!=", False)])
        if stages:
            stages.write({"user_id": False})
        return True
