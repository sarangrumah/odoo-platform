# -*- coding: utf-8 -*-
"""Send an identified residual somewhere other than suspense.

A settlement that does not fully explain itself leaves a residual, and the
clearing parks it on the bank suspense account: the statement line stays open,
and the gap stays visible. That is the right default and it stays the default
here — ``mode`` ships as ``suspense`` and changing nothing changes nothing.

But some residuals *are* explained: a rounding crumb, an admin fee the acquirer
took without printing, a store that banked less than it counted. Once someone has
identified one, leaving it on suspense stops being honest bookkeeping and starts
being a queue nobody can clear. This wizard is how that decision gets recorded —
with a reason, a name and the user who made it.

**Two paths, and the difference matters.**

*Before posting* — the ordinary case — the wizard books nothing at all. It writes
the chosen account onto the clearing line, and ``_counterpart_plan`` then names
that account on the residual leg instead of suspense. The plan stays the thing
that gets reviewed and the thing that gets posted, which is the whole point of
the three-stage design.

*After posting*, the residual is already a real suspense journal item. It cannot
be moved by editing a plan, and — because the suspense account ships with
``reconcile = False`` — it cannot be cleared by a separate journal entry either:
there is nothing to reconcile against. So the wizard does exactly what
``_apply_to_statement_lines`` does, and for the same reason: it replaces the
surviving suspense leg on the statement line's own move with a leg on the chosen
account. The line then goes reconciled on its own, which is the point.

That second path is the only place this module writes to a posted move outside
the clearing's own posting stage, and it is deliberately the narrower of the two.
Prefer the first.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_EPS = 0.005


class LevisClearingWriteoffWizard(models.TransientModel):
    _name = "levis.clearing.writeoff.wizard"
    _description = "Write Off a Clearing Residual"

    line_ids = fields.Many2many("levis.pos.clearing.line", string="Settlements")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    residual_total = fields.Monetary(compute="_compute_residual_total", string="Residual")
    line_count = fields.Integer(compute="_compute_residual_total")
    posted_count = fields.Integer(compute="_compute_residual_total")

    mode = fields.Selection(
        [("suspense", "Leave on suspense"), ("absorb", "Book to an account")],
        default="suspense",
        required=True,
        help="Leaving it on suspense is the default, and is what the clearing "
        "does on its own. Choose an account only for a difference someone has "
        "actually identified.",
    )
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        domain="[('company_ids', 'in', company_id), ('id', 'not in', forbidden_account_ids)]",
    )
    forbidden_account_ids = fields.Many2many(
        "account.account",
        compute="_compute_forbidden_account_ids",
        string="Not Allowed",
    )
    label = fields.Char(default=lambda self: _("Settlement difference"))
    reason = fields.Selection(
        [
            ("rounding", "Rounding"),
            ("admin_fee", "Bank / Admin Fee"),
            ("short_deposit", "Short Deposit"),
            ("overage", "Overage"),
            ("other", "Other"),
        ],
        default="rounding",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("line_ids", "line_ids.short_amount", "line_ids.run_id.state")
    def _compute_residual_total(self):
        for wizard in self:
            wizard.residual_total = sum(wizard.line_ids.mapped("short_amount"))
            wizard.line_count = len(wizard.line_ids)
            wizard.posted_count = len(wizard.line_ids.filtered(lambda l: l.run_id.state == "posted"))

    @api.depends("company_id")
    def _compute_forbidden_account_ids(self):
        """A residual may not be hidden back in the accounts it came from."""
        for wizard in self:
            config = (
                self.env["levis.clearing.config"].sudo().search([("company_id", "=", wizard.company_id.id)], limit=1)
            )
            wizard.forbidden_account_ids = config.suspense_account_id | config.pos_receivable_account_ids

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        line_ids = self.env.context.get("active_ids") or []
        if self.env.context.get("active_model") == "levis.pos.clearing.line" and line_ids:
            lines = self.env["levis.pos.clearing.line"].browse(line_ids)
            values["line_ids"] = [(6, 0, lines.ids)]
            if lines:
                values["company_id"] = lines[0].company_id.id
        return values

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def action_apply(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Nothing selected."))

        if self.mode == "suspense":
            # Checked BEFORE anything is cleared: a booked write-off cannot be
            # undone by blanking the field that described it, and finding that
            # out after the blanking would be no help to anyone.
            posted = self.line_ids.filtered(lambda line: line.run_id.state == "posted" and line.writeoff_account_id)
            if posted:
                raise UserError(
                    _(
                        "%s is already posted. A booked write-off is reversed with a "
                        "journal entry, not by clearing a field.",
                        ", ".join(posted.mapped("payment_ref") or [str(posted[0].id)]),
                    )
                )
            self.line_ids.write(
                {
                    "writeoff_account_id": False,
                    "writeoff_label": False,
                    "writeoff_reason": False,
                    "writeoff_uid": False,
                }
            )
            for run in self.line_ids.run_id.filtered(lambda r: r.state == "generated"):
                run._retarget_residual_legs(self.line_ids.filtered(lambda line, r=run: line.run_id == r))
            return {"type": "ir.actions.act_window_close"}

        if not self.account_id:
            raise UserError(_("Choose the account the difference should be booked to."))
        if self.account_id in self.forbidden_account_ids:
            raise UserError(
                _(
                    "%s is either the suspense account or a POS receivable. A "
                    "residual cannot be hidden back in the accounts it came from.",
                    self.account_id.display_name,
                )
            )

        idle = self.line_ids.filtered(lambda line: abs(line.short_amount) <= _EPS)
        if idle:
            raise UserError(
                _(
                    "These settlements have no residual to write off: %s",
                    ", ".join(idle.mapped("payment_ref") or [str(idle[0].id)]),
                )
            )

        cancelled = self.line_ids.filtered(lambda line: line.run_id.state == "cancel")
        if cancelled:
            raise UserError(_("Some of those settlements belong to a cancelled run."))

        vals = {
            "writeoff_account_id": self.account_id.id,
            "writeoff_label": self.label or False,
            "writeoff_reason": self.reason,
            "writeoff_uid": self.env.user.id,
        }
        pre_post = self.line_ids.filtered(lambda line: line.run_id.state != "posted")
        posted = self.line_ids - pre_post

        pre_post.write(vals)
        # A run already at "generated" carries a reviewed plan that now names the
        # wrong account. Rebuild the legs of the lines that changed rather than
        # letting the plan and the decision disagree.
        for run in pre_post.run_id.filtered(lambda r: r.state == "generated"):
            run._retarget_residual_legs(pre_post.filtered(lambda line: line.run_id == run))

        if posted:
            posted.write(vals)
            posted._apply_writeoff_to_posted_move()

        return {"type": "ir.actions.act_window_close"}
