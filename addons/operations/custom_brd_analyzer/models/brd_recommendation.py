# -*- coding: utf-8 -*-
"""Proposed custom_<x> module to fill a BRD gap."""

from __future__ import annotations

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BrdRecommendation(models.Model):
    _name = "brd.recommendation"
    _inherit = ["mail.thread"]
    _description = "BRD Module Recommendation"
    _order = "document_id, sequence, id"

    document_id = fields.Many2one("brd.document", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help="Proposed module technical name (snake_case, e.g. custom_xyz).")
    scope = fields.Text()
    capability_tag_ids = fields.Many2many(
        "custom.module.capability.tag",
        "brd_recommendation_tag_rel",
        "recommendation_id",
        "tag_id",
        string="Capability Tags",
    )
    related_section_ids = fields.Many2many(
        "brd.document.section",
        "brd_recommendation_section_rel",
        "recommendation_id",
        "section_id",
        string="Related Sections",
    )
    depends_on_module_ids = fields.Many2many(
        "custom.module.capability.entry",
        "brd_recommendation_depends_rel",
        "recommendation_id",
        "module_id",
        string="Depends on Existing Modules",
    )
    depends_on_proposed_ids = fields.Many2many(
        "brd.recommendation",
        "brd_recommendation_sibling_rel",
        "recommendation_id",
        "sibling_id",
        string="Depends on Proposed",
    )
    impact_module_ids = fields.Many2many(
        "custom.module.capability.entry",
        "brd_recommendation_impact_rel",
        "recommendation_id",
        "module_id",
        string="Impacts Existing Modules",
    )
    estimated_md = fields.Integer(default=0, string="Estimated MD")
    severity = fields.Selection(
        [
            ("must_have", "Must Have"),
            ("should_have", "Should Have"),
            ("nice_to_have", "Nice to Have"),
        ],
        default="should_have",
        index=True,
    )
    justification = fields.Text()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("approved", "Approved"),
            ("in_backlog", "In Backlog"),
            ("built", "Built"),
            ("canceled", "Canceled"),
        ],
        default="draft",
        tracking=True,
    )
    assigned_user_id = fields.Many2one("res.users", string="Assignee")
    project_task_id = fields.Many2one("project.task", string="Backlog Task", ondelete="set null", copy=False)

    _sql_constraints = [
        (
            "name_doc_uniq",
            "unique(document_id, name)",
            "Each recommendation name must be unique within a single BRD.",
        ),
    ]

    @api.constrains("name")
    def _check_name_format(self):
        for rec in self:
            if rec.name and not rec.name.replace("_", "").isalnum():
                raise UserError(_("Recommendation name must be snake_case (alphanumerics and underscore only): %s") % rec.name)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def action_approve(self):
        self.write({"state": "approved"})

    def action_cancel(self):
        self.write({"state": "canceled"})

    def action_mark_built(self):
        self.write({"state": "built"})

    # ------------------------------------------------------------------
    # Push to backlog
    # ------------------------------------------------------------------

    def action_push_to_project(self):
        Project = self.env["project.project"].sudo()
        Task = self.env["project.task"]
        backlog = Project.search([("name", "=", "Hub Backlog - BRD")], limit=1)
        if not backlog:
            backlog = Project.create({"name": "Hub Backlog - BRD"})
        for rec in self:
            if rec.project_task_id:
                continue
            description = (
                f"<h3>Scope</h3><p>{rec.scope or ''}</p>"
                f"<h3>Justification</h3><p>{rec.justification or ''}</p>"
                f"<h3>Impact Modules</h3><p>{', '.join(rec.impact_module_ids.mapped('module_name')) or '—'}</p>"
                f"<h3>Depends On</h3><p>{', '.join(rec.depends_on_module_ids.mapped('module_name')) or '—'}</p>"
                f"<p><b>Source BRD:</b> {rec.document_id.display_name} ({rec.document_id.reference})</p>"
            )
            deadline = fields.Date.context_today(self) + timedelta(days=max(1, (rec.estimated_md or 1)) * 2)
            task_vals = {
                "name": rec.name,
                "description": description,
                "project_id": backlog.id,
                "date_deadline": deadline,
                "brd_recommendation_id": rec.id,
            }
            if rec.assigned_user_id:
                task_vals["user_ids"] = [(6, 0, [rec.assigned_user_id.id])]
            task = Task.sudo().create(task_vals)
            rec.write({"project_task_id": task.id, "state": "in_backlog"})
        return {
            "type": "ir.actions.act_window",
            "name": _("Backlog Tasks"),
            "res_model": "project.task",
            "view_mode": "list,form",
            "domain": [("brd_recommendation_id", "in", self.ids)],
        }
