# -*- coding: utf-8 -*-
"""Cash advance / petty cash request — pengajuan + pencairan (Bank Out) + settlement.

Lifecycle::

    draft ─submit─▶ to_approve ─approve─▶ approved ─disburse─▶ disbursed
        ─(realizations posted)─▶ in_realization ─settle─▶ settled

Approval routes through the generic ``custom_approval_engine`` matrix; when
no matrix matches the request is approved directly by a Finance user.

Accounting (per employee, via the advance account of the request's type)::

    Disburse    Dr Uang Muka / Cr Bank
    Realize 3rd Dr Expense+PPN / Cr AP   then   Dr AP / Cr Uang Muka
    Realize exp Dr Expense / Cr Uang Muka
    Return      Dr Bank / Cr Uang Muka
    Reimburse   Dr Uang Muka / Cr Bank
    Settle      advance lines net to zero and are reconciled

Every generated journal item carries ``currency_id`` + ``amount_currency`` so a
foreign-currency advance books its IDR counter-value correctly and settles
through the company's exchange-difference journal.
"""

from __future__ import annotations

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .petty_cash_type import FLOAT_KINDS, KIND_CLAIM, KIND_INITIAL, KIND_REALIZATION

DEFAULT_OU_PLAN = "Operating Unit"

# States in which a request's money is spoken for. A Realisasi reservation
# starts at *draft* on purpose: the store must not be able to queue up several
# drafts that each look affordable in isolation.
FLOAT_OPEN_STATES = ("draft", "to_approve", "approved", "disbursed", "in_realization")


class PettyCashRequest(models.Model):
    _name = "petty.cash.request"
    _description = "Cash Advance / Petty Cash Request"
    _inherit = ["mail.thread", "mail.activity.mixin", "approval.mixin", "pdp.audited.mixin"]
    _order = "request_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Reference",
        required=True,
        default=lambda self: self.env._("New"),
        copy=False,
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        tracking=True,
        default=lambda self: self.env.user.employee_id,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company Currency")
    advance_type_id = fields.Many2one(
        "petty.cash.type",
        string="Type",
        index=True,
        tracking=True,
        check_company=True,
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self._default_advance_type(),
        help="Kind of advance — drives which advance account, journals and "
        "limits apply. Leave empty to fall back to the company-wide "
        "configuration in Accounting Settings.",
    )
    advance_type_kind = fields.Selection(related="advance_type_id.kind", store=True, string="Type Kind")
    pc_ou_allowed_ids = fields.Many2many(
        "account.analytic.account",
        string="Allowed Operating Units",
        compute="_compute_pc_ou_allowed",
        compute_sudo=True,
        help="Technical: drives the Operating Unit domain. See _compute_pc_ou_allowed.",
    )
    l10n_ou_analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        domain="[('id', 'in', pc_ou_allowed_ids)]",
        tracking=True,
        help="Operating Unit the advance is requested for. Stamped onto "
        "every generated journal item when the localization is installed.",
    )
    request_date = fields.Date(
        string="Request Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    purpose = fields.Char(string="Purpose", tracking=True)
    line_ids = fields.One2many(
        "petty.cash.request.line",
        "request_id",
        string="Estimate Breakdown",
    )
    amount_requested = fields.Monetary(
        string="Amount Requested",
        currency_field="currency_id",
        tracking=True,
        help="Amount the employee is asking for. When an estimate breakdown is entered it must match this total.",
    )
    realization_deadline = fields.Date(
        string="Realization Deadline",
        tracking=True,
        help="Date by which the employee must submit the realization.",
    )
    bank_journal_id = fields.Many2one(
        "account.journal",
        string="Bank-Out Journal",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    advance_account_id = fields.Many2one(
        "account.account",
        string="Advance Account",
        domain="[('reconcile', '=', True)]",
    )

    disburse_move_id = fields.Many2one("account.move", string="Disbursement Entry", copy=False, readonly=True)
    move_ids = fields.One2many("account.move", "petty_cash_request_id", string="Journal Entries")
    move_count = fields.Integer(compute="_compute_move_count")
    realization_ids = fields.One2many("petty.cash.realization", "request_id", string="Realizations")
    realization_count = fields.Integer(compute="_compute_realization_count")

    amount_disbursed = fields.Monetary(currency_field="currency_id", compute="_compute_amounts", store=True)
    amount_realized = fields.Monetary(currency_field="currency_id", compute="_compute_amounts", store=True)
    amount_outstanding = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        help="Net balance of the advance account still tied to this request, "
        "in the request's own currency (positive = employee holds cash to "
        "return; negative = company owes the employee).",
    )
    amount_outstanding_company = fields.Monetary(
        string="Outstanding (Company Currency)",
        currency_field="company_currency_id",
        compute="_compute_amounts",
        store=True,
        help="The same balance in company currency. This is the figure to "
        "aggregate — summing amount_outstanding across requests in different "
        "currencies is meaningless.",
    )

    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("to_approve", "To Approve"),
            ("approved", "Approved"),
            ("disbursed", "Disbursed"),
            ("in_realization", "In Realization"),
            ("settled", "Settled"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    is_overdue = fields.Boolean(compute="_compute_is_overdue", search="_search_is_overdue")

    # ------------------------------------------------------------------
    # Store float (0.6.0) — only meaningful for the pc_* kinds
    # ------------------------------------------------------------------
    float_id = fields.Many2one(
        "petty.cash.float",
        string="Store Float",
        compute="_compute_float_id",
        store=True,
        index=True,
        readonly=True,
        help="The Operating Unit's petty cash float this request draws on. "
        "Resolved from the company + Operating Unit; the float itself is only "
        "created by an explicit Finance action.",
    )
    amount_float_granted = fields.Monetary(
        string="Float Granted",
        currency_field="company_currency_id",
        compute="_compute_float_amounts",
        store=True,
        help="What this request adds to the store's float — the approved amount "
        "of a 'Petty Cash Awal' request, zero for anything else.",
    )
    amount_float_consumed = fields.Monetary(
        string="Float Reserved",
        currency_field="company_currency_id",
        compute="_compute_float_amounts",
        store=True,
        help="What this request currently takes out of the store's float: the "
        "requested amount less whatever has already been realized. Counted from "
        "draft, and released entirely once the request is settled or cancelled.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    def _compute_realization_count(self):
        for rec in self:
            rec.realization_count = len(rec.realization_ids)

    @api.depends(
        "move_ids.state",
        "move_ids.line_ids.debit",
        "move_ids.line_ids.credit",
        "move_ids.line_ids.amount_currency",
        "advance_account_id",
        "advance_type_id",
        "currency_id",
        "realization_ids.state",
        "realization_ids.amount_total",
    )
    def _compute_amounts(self):
        for rec in self:
            adv_lines = rec._advance_move_lines(posted_only=True)
            debit = sum(adv_lines.mapped("debit"))
            credit = sum(adv_lines.mapped("credit"))
            rec.amount_outstanding_company = debit - credit
            if rec.currency_id == rec.company_id.currency_id:
                rec.amount_disbursed = debit
                rec.amount_outstanding = debit - credit
            else:
                # Foreign-currency advance: debit-credit is the IDR
                # counter-value; showing it under the request's own currency
                # label would be off by the exchange rate. Read the document
                # amounts instead.
                same = adv_lines.filtered(lambda line: line.currency_id == rec.currency_id)
                rec.amount_disbursed = sum(line.amount_currency for line in same if line.amount_currency > 0)
                rec.amount_outstanding = sum(same.mapped("amount_currency"))
            rec.amount_realized = sum(
                rec.realization_ids.filtered(lambda r: r.state == "posted").mapped("amount_total")
            )

    @api.depends("company_id")
    def _compute_pc_ou_allowed(self):
        """Resolve which analytic accounts the Operating Unit field may offer.

        The plan was hard-coded to "Operating Unit", which is how the Levi's
        localization names it. ARKA-AIM has no such plan (only "Project"), so
        the field was a dead control there. The plan name is now a parameter,
        and an unresolvable plan *widens* to every analytic account rather than
        blocking the field — a misconfiguration should not make the document
        un-fillable.
        """
        params = self.env["ir.config_parameter"].sudo()
        plan_name = (
            params.get_param("custom_petty_cash.ou_plan_name")
            or params.get_param("custom_accounting_reports.branch_plan_name")
            or DEFAULT_OU_PLAN
        )
        Analytic = self.env["account.analytic.account"]
        plan = self.env["account.analytic.plan"].sudo().search([("name", "=", plan_name)], limit=1)
        for rec in self:
            domain = [("plan_id", "=", plan.id)] if plan else []
            if rec.company_id:
                domain = domain + ["|", ("company_id", "=", False), ("company_id", "=", rec.company_id.id)]
            rec.pc_ou_allowed_ids = Analytic.search(domain)

    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = bool(
                rec.state in ("disbursed", "in_realization")
                and rec.realization_deadline
                and rec.realization_deadline < today
                and not rec.currency_id.is_zero(rec.amount_outstanding)
            )

    def _search_is_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        overdue_domain = [
            ("state", "in", ("disbursed", "in_realization")),
            ("realization_deadline", "<", today),
        ]
        # `is_overdue = True` → overdue domain; `= False` → its inverse.
        if (operator == "=" and value) or (operator == "!=" and not value):
            return overdue_domain
        return ["!", "&"] + overdue_domain[:1] + overdue_domain[1:]

    # ------------------------------------------------------------------
    # Store float
    # ------------------------------------------------------------------
    @api.depends("company_id", "l10n_ou_analytic_id", "advance_type_kind")
    def _compute_float_id(self):
        """Look the OU's float up — never create one.

        A compute that created records would spawn a float every time an
        employee opened a blank request form, so creation is left to
        ``action_approve`` on a Petty Cash Awal request and to the Finance
        Configuration screen.
        """
        Float = self.env["petty.cash.float"]
        for rec in self:
            if rec.advance_type_kind in FLOAT_KINDS and rec.l10n_ou_analytic_id and rec.company_id:
                rec.float_id = Float._pc_get_float(rec.company_id, rec.l10n_ou_analytic_id)
            else:
                rec.float_id = False

    @api.depends("advance_type_kind", "state", "amount_requested", "amount_realized", "currency_id", "request_date")
    def _compute_float_amounts(self):
        for rec in self:
            granted = consumed = 0.0
            kind = rec.advance_type_kind
            # A *settled* Petty Cash Awal means the store handed the float back,
            # so it stops granting — which is why "settled" is absent here.
            if kind == KIND_INITIAL and rec.state in ("approved", "disbursed", "in_realization"):
                granted = rec._pc_conv(rec.amount_requested, rec.request_date)
            elif kind == KIND_REALIZATION and rec.state in FLOAT_OPEN_STATES:
                # "Saldo pulih sesuai nilai yang direalisasikan": every rupiah
                # realized frees a rupiah of the reservation immediately. The
                # unrealized remainder stays reserved until Finance settles or
                # cancels the request.
                outstanding = rec.amount_requested - rec.amount_realized
                consumed = max(0.0, rec._pc_conv(outstanding, rec.request_date))
            rec.amount_float_granted = granted
            rec.amount_float_consumed = consumed

    def _pc_float_plafon(self):
        """Ceiling for a Petty Cash Awal request in this OU."""
        self.ensure_one()
        if self.float_id:
            return self.float_id.amount_plafon
        return self.env["petty.cash.float"]._default_plafon()

    def _pc_float_available(self):
        """The store's available balance, excluding this request's own reservation."""
        self.ensure_one()
        pc_float = self.float_id
        if not pc_float:
            return 0.0
        mine = self.amount_float_consumed if self.id else 0.0
        return pc_float.amount_available + mine

    @api.constrains("advance_type_id", "l10n_ou_analytic_id", "amount_requested", "state", "company_id")
    def _check_store_float(self):
        """Gate the store float. Runs from draft — that is the whole point.

        ``pc_claim`` is deliberately exempt: a Claim *is* the escape hatch for a
        spend the float cannot cover, so checking it against the float would
        make the type useless.
        """
        currency = self.env.company.currency_id
        for rec in self:
            kind = rec.advance_type_kind
            if kind not in FLOAT_KINDS or rec.state in ("settled", "cancelled"):
                continue
            if not rec.l10n_ou_analytic_id:
                raise UserError(
                    _(
                        "Request %(name)s is of type %(type)s — pick the Operating Unit (store) it belongs to first.",
                        name=rec.name,
                        type=rec.advance_type_id.name,
                    )
                )
            company_currency = rec.company_id.currency_id or currency
            amount = rec._pc_conv(rec.amount_requested, rec.request_date)
            if kind == KIND_INITIAL:
                plafon = rec._pc_float_plafon()
                granted_elsewhere = sum(
                    peer.amount_float_granted
                    for peer in rec._pc_float_peers()
                    if peer.advance_type_kind == KIND_INITIAL
                )
                if plafon and company_currency.compare_amounts(granted_elsewhere + amount, plafon) > 0:
                    raise UserError(
                        _(
                            "Initial petty cash for %(ou)s is capped at %(plafon)s "
                            "(already granted: %(granted)s). Finance can raise the "
                            "plafon on the store's float.",
                            ou=rec.l10n_ou_analytic_id.display_name,
                            plafon=rec._pc_money(plafon),
                            granted=rec._pc_money(granted_elsewhere),
                        )
                    )
            elif kind == KIND_REALIZATION:
                if not rec.float_id or company_currency.is_zero(rec.float_id.amount_granted):
                    raise UserError(
                        _(
                            "%(ou)s has no petty cash float yet. Submit and get an "
                            "approved 'Petty Cash Awal' request for this store before "
                            "raising a Realisasi.",
                            ou=rec.l10n_ou_analytic_id.display_name,
                        )
                    )
                available = rec._pc_float_available()
                if company_currency.compare_amounts(amount, available) > 0:
                    raise UserError(
                        _(
                            "%(ou)s only has %(available)s left of its petty cash "
                            "float; this request asks for %(amount)s. Realize an open "
                            "request to free the balance, or raise a Claim instead.",
                            ou=rec.l10n_ou_analytic_id.display_name,
                            available=rec._pc_money(available),
                            amount=rec._pc_money(amount),
                        )
                    )

    def _pc_float_peers(self):
        """Other requests drawing on the same store float."""
        self.ensure_one()
        if not self.l10n_ou_analytic_id:
            return self.browse()
        return self.search(
            [
                ("id", "!=", self.id or 0),
                ("company_id", "=", self.company_id.id),
                ("l10n_ou_analytic_id", "=", self.l10n_ou_analytic_id.id),
                ("advance_type_kind", "in", list(FLOAT_KINDS)),
            ]
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _advance_move_lines(self, posted_only=True):
        """Journal items on the advance account tied to this request."""
        self.ensure_one()
        advance = self._pc_advance_account(soft=True)
        if not advance:
            return self.env["account.move.line"]
        lines = self.move_ids.line_ids.filtered(lambda l: l.account_id == advance)
        if posted_only:
            lines = lines.filtered(lambda l: l.parent_state == "posted")
        return lines

    # Resolution is always request → type → company. The ``res.company``
    # fields predate ``petty.cash.type`` and are kept as the bottom of the
    # chain so tenants configured before 0.5.0 keep working untouched with
    # ``advance_type_id`` unset.
    def _pc_advance_account(self, soft=False):
        self.ensure_one()
        account = (
            self.advance_account_id
            or self.advance_type_id.advance_account_id
            or self.company_id.petty_cash_advance_account_id
        )
        if not account and not soft:
            raise UserError(_("Set an Advance account on the request, on its Type, or in Accounting Settings first."))
        return account

    def _pc_bank_journal(self):
        self.ensure_one()
        journal = (
            self.bank_journal_id
            or self.advance_type_id.bank_out_journal_id
            or self.company_id.petty_cash_bank_out_journal_id
        )
        if not journal:
            raise UserError(_("Set a Bank-Out journal on the request, on its Type, or in Accounting Settings first."))
        # A journal pinned to one currency forces that currency onto its
        # liquidity line; a mismatch fails deep inside account.move with an
        # opaque message, so refuse it up front.
        if journal.currency_id and journal.currency_id != self.currency_id:
            raise UserError(
                _(
                    "Journal %(journal)s only accepts %(jcur)s, but this request is in %(rcur)s.",
                    journal=journal.name,
                    jcur=journal.currency_id.name,
                    rcur=self.currency_id.name,
                )
            )
        return journal

    def _pc_payment_journal(self):
        """Journal used to pay third-party bills out of the advance.

        Resolved here rather than on the realization so every account/journal
        lookup is type-aware in one place.
        """
        self.ensure_one()
        journal = self.advance_type_id.payment_journal_id or self.company_id.petty_cash_payment_journal_id
        if not journal:
            raise UserError(
                _(
                    "Set a Payment journal on the advance Type or in Accounting Settings "
                    "before posting third-party lines."
                )
            )
        return journal

    def _pc_expense_journal(self):
        self.ensure_one()
        journal = self.advance_type_id.expense_journal_id or self.company_id.petty_cash_expense_journal_id
        if not journal:
            journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", self.company_id.id)], limit=1
            )
        if not journal:
            raise UserError(_("No general journal found for the expense entry. Configure an Expense journal."))
        return journal

    # ------------------------------------------------------------------
    # Currency helpers
    # ------------------------------------------------------------------
    def _pc_conv(self, amount, date=None):
        """Convert ``amount`` from the request currency to company currency."""
        self.ensure_one()
        company_currency = self.company_id.currency_id
        if self.currency_id == company_currency:
            return company_currency.round(amount)
        return self.currency_id._convert(
            amount,
            company_currency,
            self.company_id,
            date or fields.Date.context_today(self),
        )

    def _pc_leg(self, amount_cur, amount_comp):
        """Move-line ``vals`` fragment for one side of a balanced pair.

        ``amount_cur`` is signed in the *request* currency and ``amount_comp``
        signed in *company* currency, both positive on the debit side — Odoo's
        invariant is ``sign(amount_currency) == sign(debit - credit)``.

        ``currency_id`` is always set, even when it equals the company
        currency: Odoo stores it on same-currency lines too, and leaving it
        empty parks ``amount_currency`` at 0, which breaks foreign-currency
        reconciliation and the FX revaluation report.

        Callers must convert **once** per pair and pass the two halves of that
        single figure, otherwise independent rounding leaves the move unbalanced
        by a cent.
        """
        self.ensure_one()
        return {
            "currency_id": self.currency_id.id,
            "amount_currency": amount_cur,
            "debit": amount_comp if amount_comp > 0 else 0.0,
            "credit": -amount_comp if amount_comp < 0 else 0.0,
        }

    def _pc_employee_partner(self):
        self.ensure_one()
        emp = self.employee_id
        partner = emp.work_contact_id or (emp.user_id and emp.user_id.partner_id)
        if not partner:
            raise UserError(
                _("Employee %s has no linked contact (Work Contact / User) to book the advance against.") % emp.name
            )
        return partner

    def _pc_analytic_distribution(self, base=None):
        """Merge the Operating Unit and the Employee analytic accounts into
        ``base`` as two *separate plan tags* on the same 100% slice.

        analytic_distribution keys are comma-joined analytic-account ids (one
        per plan); OU (plan "Operating Unit") and Employee (plan "Employee")
        each contribute one id, so a line carries e.g. ``{"<ou>,<emp>": 100}``.
        Both dimensions stay independently groupable in analytic reporting.
        Built directly (not via the ``l10n_ou_analytic_id`` line field) so no
        recompute can clobber the employee tag.
        """
        self.ensure_one()
        ids = []
        if self.l10n_ou_analytic_id:
            ids.append(self.l10n_ou_analytic_id.id)
        if self.employee_id:
            ids.append(self.employee_id._pc_get_analytic_account().id)
        if not ids:
            return dict(base or {})
        add = ",".join(str(i) for i in ids)
        dist = dict(base or {})
        if not dist:
            return {add: 100.0}
        # Append our plan ids to every existing key (idempotent per id).
        merged = {}
        for key, pct in dist.items():
            key_ids = key.split(",")
            for i in add.split(","):
                if i not in key_ids:
                    key_ids.append(i)
            merged[",".join(key_ids)] = pct
        return merged

    def _pc_line_analytic(self, vals=None):
        """Return move-line ``vals`` with the combined OU+Employee analytic
        distribution stamped in."""
        self.ensure_one()
        vals = dict(vals or {})
        dist = self._pc_analytic_distribution(vals.get("analytic_distribution"))
        if dist:
            vals["analytic_distribution"] = dist
        return vals

    # ------------------------------------------------------------------
    # CRUD / onchange
    # ------------------------------------------------------------------
    @api.model
    def _default_advance_type(self):
        Type = self.env["petty.cash.type"]
        company = self.env.company
        return Type.search([("company_id", "=", company.id), ("is_default", "=", True)], limit=1) or Type.search(
            [("company_id", "=", company.id)], limit=1
        )

    def _pc_type_sequence_code(self, vals):
        """Sequence to number a request created with ``vals``."""
        type_id = vals.get("advance_type_id")
        if type_id:
            pc_type = self.env["petty.cash.type"].browse(type_id)
            if pc_type.sequence_id:
                return pc_type.sequence_id
        return self.env["ir.sequence"].search([("code", "=", "petty.cash.request")], limit=1)

    def _pc_assign_default_type(self):
        """Back-fill ``advance_type_id`` on records that predate the field."""
        Type = self.env["petty.cash.type"]
        for rec in self.filtered(lambda r: not r.advance_type_id):
            rec.advance_type_id = Type.search(
                [("company_id", "=", rec.company_id.id), ("is_default", "=", True)], limit=1
            ) or Type.search([("company_id", "=", rec.company_id.id)], limit=1)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                sequence = self._pc_type_sequence_code(vals)
                vals["name"] = (sequence and sequence.next_by_id()) or _("New")
        return super().create(vals_list)

    @api.onchange("company_id")
    def _onchange_company_defaults(self):
        for rec in self:
            if rec.advance_type_id.company_id != rec.company_id:
                rec.advance_type_id = False
            if not rec.advance_type_id:
                rec.advance_type_id = self.env["petty.cash.type"].search(
                    [("company_id", "=", rec.company_id.id), ("is_default", "=", True)], limit=1
                )
            rec._onchange_advance_type_defaults()

    @api.onchange("advance_type_id")
    def _onchange_advance_type_defaults(self):
        for rec in self:
            rec.advance_account_id = (
                rec.advance_type_id.advance_account_id or rec.company_id.petty_cash_advance_account_id
            )
            rec.bank_journal_id = (
                rec.advance_type_id.bank_out_journal_id or rec.company_id.petty_cash_bank_out_journal_id
            )

    @api.constrains("line_ids", "amount_requested")
    def _check_breakdown_total(self):
        for rec in self:
            if rec.line_ids:
                total = sum(rec.line_ids.mapped("amount"))
                if not rec.currency_id.is_zero(total - rec.amount_requested):
                    raise UserError(
                        _(
                            "The estimate breakdown (%(bd)s) does not match the requested amount (%(req)s).",
                            bd=total,
                            req=rec.amount_requested,
                        )
                    )

    # ------------------------------------------------------------------
    # Limit control
    # ------------------------------------------------------------------
    def _pc_outstanding_limit(self):
        """Ceiling on the employee's total open advances, in company currency.

        Resolved employee → job → type; ``0.0`` means "no limit at this level"
        and falls through to the next. Returns 0.0 when nothing is set.
        """
        self.ensure_one()
        employee = self.employee_id
        return (
            employee.pc_advance_limit
            or employee.job_id.pc_advance_limit
            or self.advance_type_id.limit_outstanding
            or 0.0
        )

    def _pc_open_peers(self):
        """The employee's other advances whose money is already committed.

        ``approved`` is deliberately included: the cash has not left yet, but
        it is spoken for. Excluding it would let two requests submitted the
        same afternoon each slip under the ceiling.
        """
        self.ensure_one()
        return self.search(
            [
                ("id", "!=", self.id or 0),
                ("employee_id", "=", self.employee_id.id),
                ("company_id", "=", self.company_id.id),
                ("state", "in", ("approved", "disbursed", "in_realization")),
            ]
        )

    def _pc_committed_company(self):
        """How much of the ceiling this request is currently consuming.

        An ``approved`` request has no journal entries yet, so its GL
        outstanding is zero — but the money is spoken for. Fall back to the
        requested amount until disbursement gives us a real balance, otherwise
        two same-day requests would each see an empty ledger and both pass.
        """
        self.ensure_one()
        if self.state == "approved":
            return self._pc_conv(self.amount_requested, self.request_date)
        return self.amount_outstanding_company

    def _pc_check_limits(self, stage):
        """Enforce the advance ceilings. ``stage`` is 'submit' or 'disburse'."""
        self.ensure_one()
        mode = self.advance_type_id.limit_enforcement or "off"
        if mode == "off":
            return True
        if self.env.user.has_group("custom_petty_cash.group_petty_cash_limit_override"):
            return True

        pc_type = self.advance_type_id
        company_currency = self.company_id.currency_id
        amount = self._pc_conv(self.amount_requested, self.request_date)
        peers = self._pc_open_peers()
        problems = []

        if pc_type.limit_per_request and company_currency.compare_amounts(amount, pc_type.limit_per_request) > 0:
            problems.append(
                _(
                    "Requested %(amount)s exceeds the per-request limit %(limit)s for type %(type)s.",
                    amount=self._pc_money(amount),
                    limit=self._pc_money(pc_type.limit_per_request),
                    type=pc_type.name,
                )
            )

        ceiling = self._pc_outstanding_limit()
        if ceiling:
            open_total = sum(peer._pc_committed_company() for peer in peers)
            if company_currency.compare_amounts(open_total + amount, ceiling) > 0:
                problems.append(
                    _(
                        "Total open advances would reach %(total)s, over the %(limit)s ceiling for %(employee)s.",
                        total=self._pc_money(open_total + amount),
                        limit=self._pc_money(ceiling),
                        employee=self.employee_id.name,
                    )
                )

        if pc_type.max_open_requests and len(peers) >= pc_type.max_open_requests:
            problems.append(
                _(
                    "%(employee)s already holds %(count)s open advances (maximum %(max)s).",
                    employee=self.employee_id.name,
                    count=len(peers),
                    max=pc_type.max_open_requests,
                )
            )

        if pc_type.block_when_overdue:
            today = fields.Date.context_today(self)
            overdue = peers.filtered(
                lambda r: (
                    r.realization_deadline
                    and r.realization_deadline < today
                    and not r.currency_id.is_zero(r.amount_outstanding)
                )
            )
            if overdue:
                problems.append(
                    _(
                        "Advance(s) past their realization deadline and not yet cleared: %s.",
                        ", ".join(overdue.mapped("name")),
                    )
                )

        if not problems:
            return True
        message = "\n".join([_("Cash advance limit check failed:")] + ["• %s" % p for p in problems])
        if mode == "block":
            raise UserError(message)
        self.message_post(body=message, subtype_xmlid="mail.mt_note")
        return True

    def _pc_money(self, amount):
        """Format ``amount`` in company currency for a user-facing message."""
        self.ensure_one()
        currency = self.company_id.currency_id
        return "%s %s" % (currency.symbol or currency.name, "{:,.2f}".format(currency.round(amount)))

    # ------------------------------------------------------------------
    # Workflow — approval
    # ------------------------------------------------------------------
    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft requests can be submitted."))
            if rec.amount_requested <= 0:
                raise UserError(_("Enter the amount requested before submitting."))
            # Checked here so the employee learns early, while they can still
            # fix the amount; re-checked at disbursement, which is the
            # authoritative gate.
            rec._pc_check_limits("submit")
            rec.state = "to_approve"
            # Auto-create + submit an approval request when a matrix matches;
            # otherwise the request just waits for a Finance user to approve.
            rec._approval_request_or_proceed()
            rec.message_post(body=_("Submitted for approval."), subtype_xmlid="mail.mt_note")
        return True

    def _approval_on_granted(self):
        """Engine hook: advance to approved once every tier passes."""
        return self.action_approve()

    def action_approve(self):
        for rec in self:
            if rec.state not in ("to_approve", "draft"):
                raise UserError(_("Only requests awaiting approval can be approved."))
            rec._approval_check_required()
            if rec.advance_type_kind == KIND_INITIAL and rec.l10n_ou_analytic_id:
                # First approved Petty Cash Awal for the store materialises its
                # float. Done here, on an explicit Finance action, rather than
                # in the compute — see petty_cash_float.__doc__.
                self.env["petty.cash.float"]._pc_get_float(rec.company_id, rec.l10n_ou_analytic_id, create=True)
                # The float did not exist when float_id was last computed, and
                # creating it is not a dependency change the ORM can see.
                rec._compute_float_id()
            rec.state = "approved"
            rec.message_post(body=_("Approved."), subtype_xmlid="mail.mt_note")
        return True

    def action_refuse(self):
        """Finance rejects the request outright (as opposed to sending it back)."""
        for rec in self:
            if rec.state in ("settled", "cancelled"):
                raise UserError(_("%s is already closed.") % rec.name)
            if rec.move_ids.filtered(lambda m: m.state == "posted"):
                raise UserError(_("This request already has posted journal entries. Reverse them before refusing."))
            rec.action_cancel_approval()
            rec.state = "cancelled"
            rec.message_post(body=_("Refused by Finance."), subtype_xmlid="mail.mt_note")
        return True

    def action_reject(self):
        for rec in self:
            rec.action_cancel_approval()
            rec.state = "draft"
            rec.message_post(body=_("Sent back to draft."), subtype_xmlid="mail.mt_note")
        return True

    # ------------------------------------------------------------------
    # Workflow — disbursement (Bank Out)
    # ------------------------------------------------------------------
    def action_disburse(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Approve the request before disbursing."))
        # The authoritative gate: both the amount and the employee's other
        # open advances can have moved since submission, and this is the
        # moment the cash actually leaves.
        self._pc_check_limits("disburse")
        amount = self.amount_requested
        if amount <= 0:
            raise UserError(_("Nothing to disburse."))
        advance = self._pc_advance_account()
        journal = self._pc_bank_journal()
        partner = self._pc_employee_partner()

        via_payment = self.env["ir.config_parameter"].sudo().get_param("custom_petty_cash.disburse_via_payment") in (
            "1",
            "true",
            "True",
        )
        if via_payment:
            move = self._disburse_via_payment(amount, advance, journal, partner)
        else:
            move = self._disburse_via_entry(amount, advance, journal, partner)

        self.disburse_move_id = move.id
        if not self.realization_deadline:
            days = self.advance_type_id.realization_days or int(
                self.env["ir.config_parameter"].sudo().get_param("custom_petty_cash.realization_days") or 14
            )
            self.realization_deadline = fields.Date.context_today(self) + timedelta(days=days)
        self.state = "disbursed"
        self.message_post(
            body=_("Disbursed %(amt)s via %(journal)s (entry %(move)s).")
            % {"amt": amount, "journal": journal.name, "move": move.name},
            subtype_xmlid="mail.mt_note",
        )
        return self._action_open_move(move)

    def _disburse_via_entry(self, amount, advance, journal, partner):
        self.ensure_one()
        bank_account = journal.default_account_id
        if not bank_account:
            raise UserError(_("Journal %s has no bank/cash account configured.") % journal.name)
        label = _("Cash advance disbursement — %s") % self.name
        date = fields.Date.context_today(self)
        # One conversion, split into the two legs — converting each side
        # independently can round apart and leave the move unbalanced.
        amount_company = self._pc_conv(amount, date)
        move = (
            self.env["account.move"]
            .with_company(self.company_id)
            .create(
                {
                    "move_type": "entry",
                    "journal_id": journal.id,
                    "date": date,
                    "ref": self.name,
                    "petty_cash_request_id": self.id,
                    "line_ids": [
                        fields.Command.create(
                            self._pc_line_analytic(
                                {
                                    "name": label,
                                    "account_id": advance.id,
                                    "partner_id": partner.id,
                                    **self._pc_leg(amount, amount_company),
                                }
                            )
                        ),
                        fields.Command.create(
                            {
                                "name": label,
                                "account_id": bank_account.id,
                                "partner_id": partner.id,
                                **self._pc_leg(-amount, -amount_company),
                            }
                        ),
                    ],
                }
            )
        )
        move.action_post()
        return move

    def _disburse_via_payment(self, amount, advance, journal, partner):
        self.ensure_one()
        payment = (
            self.env["account.payment"]
            .with_company(self.company_id)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": partner.id,
                    "amount": amount,
                    "currency_id": self.currency_id.id,
                    "journal_id": journal.id,
                    "destination_account_id": advance.id,
                    "date": fields.Date.context_today(self),
                    "memo": self.name,
                }
            )
        )
        payment.action_post()
        move = payment.move_id
        move.petty_cash_request_id = self.id
        return move

    # ------------------------------------------------------------------
    # Realization
    # ------------------------------------------------------------------
    def _pc_realizable_states(self):
        """States from which a realization may be recorded.

        A Realisasi request draws on cash the store already holds, so there is
        no Bank-Out step to wait for: the employee accounts for the spend as
        soon as Finance approves. Every other kind still has to be disbursed
        first.
        """
        self.ensure_one()
        if self.advance_type_kind in (KIND_REALIZATION, KIND_CLAIM):
            return ("approved", "disbursed", "in_realization")
        return ("disbursed", "in_realization")

    def action_open_realization(self):
        self.ensure_one()
        if self.state not in self._pc_realizable_states():
            raise UserError(
                _("Approve the request before recording a realization.")
                if self.advance_type_kind in (KIND_REALIZATION, KIND_CLAIM)
                else _("Disburse the request before recording a realization.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("New Realization"),
            "res_model": "petty.cash.realization",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_request_id": self.id,
                "default_employee_id": self.employee_id.id,
                "default_company_id": self.company_id.id,
            },
        }

    def _on_realization_posted(self):
        """Called by a realization when it posts — flip to in_realization."""
        for rec in self:
            if rec.state == "disbursed" or (
                rec.state == "approved" and rec.advance_type_kind in (KIND_REALIZATION, KIND_CLAIM)
            ):
                rec.state = "in_realization"

    # ------------------------------------------------------------------
    # Return / reimburse / settle
    # ------------------------------------------------------------------
    def action_return_balance(self):
        """Employee returns the outstanding cash: Dr Bank / Cr Advance."""
        self.ensure_one()
        outstanding = self.amount_outstanding
        if outstanding <= 0:
            raise UserError(_("There is no cash to return on this request."))
        move = self._book_bank_advance_transfer(outstanding, direction="return")
        self.message_post(
            body=_("Returned %(amt)s to the bank (entry %(move)s).") % {"amt": outstanding, "move": move.name},
            subtype_xmlid="mail.mt_note",
        )
        return self._action_open_move(move)

    def action_reimburse_shortfall(self):
        """Company reimburses over-spend: Dr Advance / Cr Bank."""
        self.ensure_one()
        outstanding = self.amount_outstanding
        if outstanding >= 0:
            raise UserError(_("There is no shortfall to reimburse on this request."))
        move = self._book_bank_advance_transfer(-outstanding, direction="reimburse")
        self.message_post(
            body=_("Reimbursed %(amt)s to the employee (entry %(move)s).") % {"amt": -outstanding, "move": move.name},
            subtype_xmlid="mail.mt_note",
        )
        return self._action_open_move(move)

    def _book_bank_advance_transfer(self, amount, direction):
        """Move ``amount`` (positive, request currency) between bank and advance.

        ``direction='return'`` credits the advance, ``'reimburse'`` debits it.
        Expressing the pair as one signed number rather than four dr/cr
        variables keeps the currency legs impossible to get out of step.
        """
        self.ensure_one()
        advance = self._pc_advance_account()
        journal = self._pc_bank_journal()
        partner = self._pc_employee_partner()
        bank_account = journal.default_account_id
        if not bank_account:
            raise UserError(_("Journal %s has no bank/cash account configured.") % journal.name)
        date = fields.Date.context_today(self)
        amount_company = self._pc_conv(amount, date)
        if direction == "return":
            label = _("Cash advance return — %s") % self.name
            advance_cur, advance_comp = -amount, -amount_company
        else:
            label = _("Cash advance reimbursement — %s") % self.name
            advance_cur, advance_comp = amount, amount_company
        move = (
            self.env["account.move"]
            .with_company(self.company_id)
            .create(
                {
                    "move_type": "entry",
                    "journal_id": journal.id,
                    "date": date,
                    "ref": self.name,
                    "petty_cash_request_id": self.id,
                    "line_ids": [
                        fields.Command.create(
                            self._pc_line_analytic(
                                {
                                    "name": label,
                                    "account_id": advance.id,
                                    "partner_id": partner.id,
                                    **self._pc_leg(advance_cur, advance_comp),
                                }
                            )
                        ),
                        fields.Command.create(
                            {
                                "name": label,
                                "account_id": bank_account.id,
                                "partner_id": partner.id,
                                **self._pc_leg(-advance_cur, -advance_comp),
                            }
                        ),
                    ],
                }
            )
        )
        move.action_post()
        return move

    def action_settle(self):
        self.ensure_one()
        if self.advance_type_kind in (KIND_REALIZATION, KIND_CLAIM):
            return self._settle_float_request()
        if self.state not in ("disbursed", "in_realization"):
            raise UserError(_("Only disbursed requests can be settled."))
        if not self.currency_id.is_zero(self.amount_outstanding):
            raise UserError(
                _(
                    "The advance is not cleared yet (outstanding %(amt)s). Record the "
                    "remaining realizations, a return, or a reimbursement first.",
                    amt=self.amount_outstanding,
                )
            )
        if self.currency_id != self.company_id.currency_id and not self.company_id.currency_exchange_journal_id:
            raise UserError(
                _(
                    "Company %s has no Exchange Difference journal. A foreign-currency "
                    "advance cannot be settled without one.",
                    self.company_id.name,
                )
            )
        # Reconcile the advance-account lines so the ledger closes for this request.
        adv_lines = self._advance_move_lines(posted_only=True).filtered(lambda l: not l.reconciled)
        if adv_lines and adv_lines.mapped("account_id").reconcile:
            try:
                result = adv_lines.reconcile()
            except UserError:
                # Non-fatal: settlement stands even if auto-reconcile can't match.
                pass
            else:
                self._pc_tag_exchange_moves(result)
        self.state = "settled"
        self.message_post(body=_("Settled — advance cleared."), subtype_xmlid="mail.mt_note")
        return True

    def action_close_release(self):
        """Header button for the Realisasi / Claim kinds — same as Settle.

        A separate method rather than a second ``action_settle`` button so the
        two buttons in the form header stay distinguishable.
        """
        self.ensure_one()
        return self.action_settle()

    def _settle_float_request(self):
        """Close a Realisasi / Claim request and release its reservation.

        These requests never receive a Bank-Out, so there is no advance balance
        to reconcile to zero: the money was already sitting in the store's
        float. Closing one drops ``amount_float_consumed`` to zero, which hands
        any unrealized remainder back to the store's available balance — the
        cash for it never left the drawer.
        """
        self.ensure_one()
        if self.state not in ("approved", "disbursed", "in_realization"):
            raise UserError(_("Only an approved request can be closed."))
        if self.realization_ids.filtered(lambda r: r.state in ("draft", "submitted")):
            raise UserError(_("Post or cancel the pending realizations on %s first.") % self.name)
        unrealized = self.amount_requested - self.amount_realized
        self.state = "settled"
        if not self.currency_id.is_zero(unrealized):
            self.message_post(
                body=_(
                    "Closed — %(amt)s was never realized and has been released back to the store's petty cash balance.",
                    amt=self._pc_money(self._pc_conv(unrealized, self.request_date)),
                ),
                subtype_xmlid="mail.mt_note",
            )
        else:
            self.message_post(body=_("Closed — fully realized."), subtype_xmlid="mail.mt_note")
        return True

    def _pc_tag_exchange_moves(self, reconcile_result):
        """Tag the FX entry ``reconcile()`` may have created with this request.

        Settling a foreign-currency advance nets the document currency to zero
        while the company-currency legs still differ; Odoo books the remainder
        through the exchange-difference journal. Untagged, that entry would be
        invisible on the smart button and missing from the Kartu Uang Muka —
        making the card look like it does not close.

        The return shape differs between the full and partial reconcile paths,
        so read it defensively.
        """
        self.ensure_one()
        if not isinstance(reconcile_result, dict):
            return
        partials = reconcile_result.get("exchange_partials")
        moves = self.env["account.move"]
        if partials is not None:
            moves |= partials.mapped("exchange_move_id")
        full = reconcile_result.get("full_reconcile")
        if full is not None:
            moves |= full.mapped("exchange_move_id")
        moves = moves.filtered(lambda m: not m.petty_cash_request_id)
        if moves:
            moves.write({"petty_cash_request_id": self.id})

    # ------------------------------------------------------------------
    # Cancel / reset
    # ------------------------------------------------------------------
    def action_cancel(self):
        for rec in self:
            if rec.state == "settled":
                raise UserError(_("Cannot cancel a settled request."))
            if rec.move_ids.filtered(lambda m: m.state == "posted"):
                raise UserError(_("This request already has posted journal entries. Reverse them before cancelling."))
            rec.action_cancel_approval()
            rec.state = "cancelled"
        return True

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ("cancelled", "to_approve"):
                raise UserError(_("Only cancelled or awaiting-approval requests can be reset."))
            rec.action_cancel_approval()
            rec.state = "draft"
        return True

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def _action_open_move(self, move):
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entries"),
            "res_model": "account.move",
            "domain": [("petty_cash_request_id", "=", self.id)],
            "view_mode": "list,form",
        }

    def action_view_realizations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Realizations"),
            "res_model": "petty.cash.realization",
            "domain": [("request_id", "=", self.id)],
            "view_mode": "list,form",
            "context": {"default_request_id": self.id, "default_employee_id": self.employee_id.id},
        }

    # ------------------------------------------------------------------
    # Cron — overdue reminder
    # ------------------------------------------------------------------
    @api.model
    def _cron_realization_reminder(self):
        today = fields.Date.context_today(self)
        overdue = self.search(
            [
                ("state", "in", ("disbursed", "in_realization")),
                ("realization_deadline", "<", today),
            ]
        )
        template = self.env.ref("custom_petty_cash.mail_template_realization_reminder", raise_if_not_found=False)
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for rec in overdue:
            if rec.currency_id.is_zero(rec.amount_outstanding):
                continue
            user = rec.employee_id.user_id
            if (
                user
                and activity_type
                and not rec.activity_ids.filtered(lambda a: a.activity_type_id == activity_type and a.user_id == user)
            ):
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary=_("Petty cash realization overdue"),
                    note=_("Please submit the realization for %s.") % rec.name,
                )
            if template and user:
                template.send_mail(rec.id, force_send=False)
        return True
