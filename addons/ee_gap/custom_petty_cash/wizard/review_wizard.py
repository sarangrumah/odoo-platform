# -*- coding: utf-8 -*-
"""Finance review wizard — approve or refuse a batch of requests with a note.

The plain ``action_approve`` / ``action_refuse`` buttons stay on the form for
the single-record case. This wizard exists for the review queue, where Finance
works through several requests at once and the *reason* for a refusal has to
land in the chatter of each one rather than in a side conversation.
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PettyCashReviewWizard(models.TransientModel):
    _name = "petty.cash.review.wizard"
    _description = "Petty Cash Finance Review"

    request_ids = fields.Many2many("petty.cash.request", string="Requests", required=True)
    decision = fields.Selection(
        selection=[
            ("approve", "Approve"),
            ("send_back", "Send back to draft"),
            ("refuse", "Refuse"),
        ],
        required=True,
        default="approve",
    )
    reason = fields.Text(
        string="Note",
        help="Posted to each request's chatter. Required when sending back or refusing.",
    )
    summary = fields.Text(compute="_compute_summary")

    @api.depends("request_ids")
    def _compute_summary(self):
        for wiz in self:
            currency = self.env.company.currency_id
            total = sum(wiz.request_ids.mapped("amount_outstanding_company")) or sum(
                wiz.request_ids.mapped("amount_requested")
            )
            wiz.summary = _(
                "%(count)s request(s), %(total)s requested.",
                count=len(wiz.request_ids),
                total="%s %s" % (currency.symbol or currency.name, "{:,.2f}".format(currency.round(total))),
            )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        active_ids = self.env.context.get("active_ids")
        if active_ids and self.env.context.get("active_model") == "petty.cash.request":
            values["request_ids"] = [fields.Command.set(active_ids)]
        return values

    def action_apply(self):
        self.ensure_one()
        if self.decision in ("send_back", "refuse") and not (self.reason or "").strip():
            raise UserError(_("Give a reason — it is what the employee sees in the chatter."))
        requests = self.request_ids
        if self.decision == "approve":
            requests.action_approve()
        elif self.decision == "send_back":
            requests.action_reject()
        else:
            requests.action_refuse()
        if self.reason:
            for request in requests:
                request.message_post(
                    body=_("Finance review — %(decision)s: %(reason)s")
                    % {
                        "decision": dict(self._fields["decision"].selection)[self.decision],
                        "reason": self.reason,
                    },
                    subtype_xmlid="mail.mt_note",
                )
        return {"type": "ir.actions.act_window_close"}
