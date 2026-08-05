# -*- coding: utf-8 -*-
"""Advance type — the per-company map from a kind of advance to its accounting.

One record per (company, type). A tenant that runs both a *Cash Advance*
(uang muka karyawan, a receivable) and an operational *Petty Cash* float
(a prepayment) charges them to different COA accounts and, in a multi-company
group, often through different journals — ARKA-AIM's second company has no
cash journal at all, so a single set of ``res.company`` fields cannot express
it.

The legacy ``res.company.petty_cash_*`` fields are kept as the bottom of the
resolution chain (request → type → company), so tenants that configured the
module before this model existed keep working with ``advance_type_id`` unset.
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PettyCashType(models.Model):
    _name = "petty.cash.type"
    _description = "Cash Advance / Petty Cash Type"
    _order = "company_id, sequence, id"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="Short code used for the document sequence prefix, e.g. CA / PC.",
    )
    kind = fields.Selection(
        selection=[
            ("cash_advance", "Cash Advance"),
            ("petty_cash", "Petty Cash"),
            ("other", "Other"),
        ],
        string="Kind",
        required=True,
        default="cash_advance",
        help="Behavioural family. Drives default labelling and voucher titles "
        "only — the accounting comes from the fields below.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    # ------------------------------------------------------------------
    # Accounting map — every field optional, falls back to res.company
    # ------------------------------------------------------------------
    advance_account_id = fields.Many2one(
        "account.account",
        string="Advance Account",
        check_company=True,
        domain="[('reconcile', '=', True)]",
        help="Reconcilable asset account debited on disbursement and credited "
        "as the employee realizes or returns the money.",
    )
    bank_out_journal_id = fields.Many2one(
        "account.journal",
        string="Bank-Out Journal",
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="Journal used to pay third-party vendor bills out of the advance. "
        "MUST be dedicated to petty cash: posting a realization rewrites this "
        "journal's payment-method outstanding accounts to point at the advance "
        "account, so sharing it with an ordinary bank journal would silently "
        "redirect every vendor payment on that bank.",
    )
    expense_journal_id = fields.Many2one(
        "account.journal",
        string="Expense Journal",
        check_company=True,
        domain="[('type', '=', 'general')]",
    )
    sequence_id = fields.Many2one(
        "ir.sequence",
        string="Document Sequence",
        copy=False,
        help="Numbering for requests of this type. Falls back to the global 'petty.cash.request' sequence when unset.",
    )

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
    limit_enforcement = fields.Selection(
        selection=[("off", "Off"), ("warn", "Warn only"), ("block", "Block")],
        string="Limit Enforcement",
        required=True,
        default="off",
        help="Off — no limit checking at all (the pre-0.5.0 behaviour). "
        "Warn — the breach is logged in the chatter and the document proceeds. "
        "Block — submission / disbursement is refused.",
    )
    limit_per_request = fields.Monetary(
        string="Limit per Request",
        currency_field="currency_id",
        help="Maximum a single request may ask for. 0 = unlimited.",
    )
    limit_outstanding = fields.Monetary(
        string="Outstanding Ceiling",
        currency_field="currency_id",
        help="Maximum total open advances one employee may hold for this type. "
        "0 = unlimited. Overridden by a limit set on the employee or job.",
    )
    max_open_requests = fields.Integer(
        string="Max Open Requests",
        help="Maximum number of simultaneously open advances per employee. 0 = unlimited.",
    )
    block_when_overdue = fields.Boolean(
        string="Block when Overdue",
        help="Refuse a new advance while the employee still holds one past its realization deadline.",
    )
    realization_days = fields.Integer(
        string="Realization Deadline (days)",
        help="Overrides the global deadline parameter for this type. 0 = use global.",
    )
    allow_third_party = fields.Boolean(
        string="Allow Third-Party Realization",
        default=True,
        help="When off, realizations of this type may only carry plain expense lines — no vendor bill is generated.",
    )
    is_default = fields.Boolean(
        string="Default",
        help="Pre-selected on new requests for this company.",
    )
    request_count = fields.Integer(compute="_compute_request_count")

    # Odoo 19 silently ignores the legacy ``_sql_constraints`` list — the
    # declarative ``models.Constraint`` is the only form that reaches Postgres.
    _code_company_uniq = models.Constraint(
        "unique(code, company_id)",
        "The type code must be unique per company.",
    )

    def _compute_request_count(self):
        counts = dict(
            self.env["petty.cash.request"]._read_group(
                [("advance_type_id", "in", self.ids)],
                groupby=["advance_type_id"],
                aggregates=["__count"],
            )
        )
        for rec in self:
            rec.request_count = counts.get(rec, 0)

    @api.constrains("is_default", "company_id")
    def _check_single_default(self):
        for rec in self.filtered("is_default"):
            other = self.search(
                [
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("is_default", "=", True),
                ],
                limit=1,
            )
            if other:
                raise UserError(
                    _(
                        "%(other)s is already the default type for %(company)s.",
                        other=other.name,
                        company=rec.company_id.name,
                    )
                )

    def name_get(self):
        return [(rec.id, "[%s] %s" % (rec.code, rec.name) if rec.code else rec.name) for rec in self]

    def action_view_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Requests"),
            "res_model": "petty.cash.request",
            "domain": [("advance_type_id", "=", self.id)],
            "view_mode": "list,form",
            "context": {"default_advance_type_id": self.id},
        }
