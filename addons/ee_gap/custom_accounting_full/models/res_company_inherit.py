# -*- coding: utf-8 -*-
"""Mark a company as part of an intercompany group + helpers for partner linkage."""

from __future__ import annotations

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    x_custom_ic_enabled = fields.Boolean(
        string="Intercompany Mirror Enabled",
        default=True,
        help="Globally enable / disable automatic intercompany mirroring for this "
        "company. Useful as a kill-switch during migration.",
    )

    def _get_unreconciled_statement_lines_redirect_action(self, unreconciled_statement_lines):
        """Add the missing ``views`` key to core's lock-date redirect action.

        Core builds this action as a plain dict and hands it straight to
        ``RedirectWarning``. The web client receives it as an object, so
        ``_loadAction`` returns it untouched and never derives ``views`` from
        ``view_mode`` the way ``/web/action/load`` would for a stored
        ``ir.actions.act_window``. ``_preprocessAction`` then does
        ``action.views.map(...)`` on ``undefined`` and the whole click dies with
        an uncaught ``TypeError`` — the user sees the warning but can never open
        the offending statement lines.

        Core's own hard-lock-date redirect a few lines up in the same method
        spells ``views`` out explicitly; this one just forgot.
        """
        action = super()._get_unreconciled_statement_lines_redirect_action(unreconciled_statement_lines)
        if action.get("type") == "ir.actions.act_window" and not action.get("views"):
            view_mode = action.get("view_mode") or "list,form"
            action["views"] = [(False, mode) for mode in view_mode.split(",")]
        return action

    @api.model
    def _sister_companies(self):
        """Return companies in the same intercompany perimeter as ``self.env.company``."""
        if not self.env.company.x_custom_ic_enabled:
            return self.browse()
        # All companies where there's a rule from/to current company
        Rule = self.env["account.intercompany.rule"].sudo()
        rules = Rule.search(
            [
                ("active", "=", True),
                "|",
                ("company_from_id", "=", self.env.company.id),
                ("company_to_id", "=", self.env.company.id),
            ]
        )
        return (rules.mapped("company_from_id") | rules.mapped("company_to_id")) - self.env.company
