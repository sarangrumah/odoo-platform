# -*- coding: utf-8 -*-
"""Lock Dates wizard — the CE gap left by EE ``account_accountant``.

Odoo 19 CE carries the four soft lock-date fields on ``res.company``
(``fiscalyear_lock_date``, ``tax_lock_date``, ``sale_lock_date``,
``purchase_lock_date``) and enforces them everywhere, but ships **no UI**
for them: the only way to set one is the company form, which needs
Settings access, or a shell. Accountants close periods, not sysadmins, so
this wizard hands the four dates to ``account.group_account_manager``
behind a menu.

``hard_lock_date`` is deliberately absent. It is irreversible — core
refuses to remove or decrease it — and a tenant that sets it by accident
has no way back short of a database edit. Period closing is done with the
soft dates, which an accounting manager can still move if a correction
turns out to be necessary.

The write goes through ``res.company.write``, so core's own guards still
run: the unreconciled-bank-statement-line check on the global lock date,
the field ``tracking=True`` chatter entry on the company, and the
re-creation of any active ``account.lock_exception``.
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


LOCK_FIELDS = (
    "fiscalyear_lock_date",
    "tax_lock_date",
    "sale_lock_date",
    "purchase_lock_date",
)


class AccountLockDateWizard(models.TransientModel):
    _name = "custom.account.lock.date.wizard"
    _description = "Set Accounting Lock Dates"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [("id", "in", self.env.companies.ids)],
        help="Lock dates are per company. Switch company to lock another one.",
    )

    # Plain (transient-stored) fields rather than readonly=False computes: a
    # non-stored compute has nowhere to keep what the user types, so create()
    # would silently drop it. The defaults seed today's values and the onchange
    # reloads them when another company is picked.
    fiscalyear_lock_date = fields.Date(
        string="Global Lock Date",
        default=lambda self: self.env.company.fiscalyear_lock_date,
        help="Every journal entry up to and including this date is locked for "
        "everyone, whatever the journal. This is the period-close lock.",
    )
    tax_lock_date = fields.Date(
        string="Tax Return Lock Date",
        default=lambda self: self.env.company.tax_lock_date,
        help="Entries carrying taxes are locked up to and including this date, "
        "so a reported PPN/PPh period can no longer move.",
    )
    sale_lock_date = fields.Date(
        string="Sales Lock Date",
        default=lambda self: self.env.company.sale_lock_date,
        help="Customer invoices and credit notes are locked up to and including this date.",
    )
    purchase_lock_date = fields.Date(
        string="Purchase Lock Date",
        default=lambda self: self.env.company.purchase_lock_date,
        help="Vendor bills and refunds are locked up to and including this date.",
    )

    draft_move_count = fields.Integer(
        string="Draft Entries in Locked Period",
        compute="_compute_draft_move_count",
    )
    unreconciled_stmt_count = fields.Integer(
        string="Unreconciled Statement Lines",
        compute="_compute_unreconciled_stmt_count",
    )
    company_summary = fields.Html(
        string="Current Lock Dates",
        compute="_compute_company_summary",
        sanitize=False,
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for wiz in self:
            company = wiz.company_id
            for fname in LOCK_FIELDS:
                wiz[fname] = company[fname] if company else False

    @api.depends("company_id", "fiscalyear_lock_date")
    def _compute_draft_move_count(self):
        Move = self.env["account.move"]
        for wiz in self:
            if not wiz.company_id or not wiz.fiscalyear_lock_date:
                wiz.draft_move_count = 0
                continue
            wiz.draft_move_count = Move.search_count(
                [
                    ("company_id", "child_of", wiz.company_id.id),
                    ("state", "=", "draft"),
                    ("date", "<=", wiz.fiscalyear_lock_date),
                ]
            )

    @api.depends("company_id", "fiscalyear_lock_date")
    def _compute_unreconciled_stmt_count(self):
        """Pre-flight the check core runs inside ``res.company.write``.

        Core raises a RedirectWarning for these, which is a dead end: the user
        has already filled the form in and gets bounced out of it. Counting them
        up front lets the wizard say so before Apply is pressed.
        """
        Line = self.env["account.bank.statement.line"]
        for wiz in self:
            if not wiz.company_id or not wiz.fiscalyear_lock_date:
                wiz.unreconciled_stmt_count = 0
                continue
            domain = wiz.company_id._get_unreconciled_statement_lines_domain(wiz.fiscalyear_lock_date)
            wiz.unreconciled_stmt_count = Line.search_count(domain)

    def action_show_unreconciled_statement_lines(self):
        self.ensure_one()
        domain = self.company_id._get_unreconciled_statement_lines_domain(self.fiscalyear_lock_date)
        return {
            "name": _("Unreconciled Transactions"),
            "type": "ir.actions.act_window",
            "res_model": "account.bank.statement.line",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": domain,
            "context": {"create": False},
        }

    @api.depends("company_id")
    def _compute_company_summary(self):
        labels = [
            (_("Global"), "fiscalyear_lock_date"),
            (_("Tax"), "tax_lock_date"),
            (_("Sales"), "sale_lock_date"),
            (_("Purchase"), "purchase_lock_date"),
        ]
        companies = self.env.companies
        head = "".join("<th class='text-end'>%s</th>" % label for label, _f in labels)
        for wiz in self:
            rows = []
            for company in companies:
                cells = "".join("<td class='text-end'>%s</td>" % (company[fname] or "—") for _label, fname in labels)
                rows.append("<tr><td>%s</td>%s</tr>" % (company.name, cells))
            wiz.company_summary = (
                "<table class='table table-sm o_list_table'>"
                "<thead><tr><th>%s</th>%s</tr></thead><tbody>%s</tbody></table>" % (_("Company"), head, "".join(rows))
            )

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Only an Accounting Manager may change the lock dates."))
        if self.company_id not in self.env.companies:
            raise AccessError(_("You do not have access to company '%s'.") % self.company_id.name)

        company = self.company_id
        vals = {fname: self[fname] or False for fname in LOCK_FIELDS if self[fname] != company[fname]}
        if not vals:
            raise UserError(_("Nothing to change — the lock dates are already set to these values."))

        # sudo: res.company is writable only by Settings admins, but closing a
        # period is an accountant's job. The group check above is the gate.
        company.sudo().write(vals)
        self._audit(company, vals)
        return {"type": "ir.actions.act_window_close"}

    def _audit(self, company, vals):
        try:
            self.env["pdp.audited.mixin"]._pdp_audit_write(
                "lock_date",
                company.id,
                {
                    "company": company.name,
                    **{fname: str(value or "") for fname, value in vals.items()},
                },
            )
        except Exception:  # noqa: BLE001 - audit must never block a period close
            pass
