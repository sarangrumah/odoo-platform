# -*- coding: utf-8 -*-
"""The store's cash takings, on their way to the bank.

Card money names itself: the acquirer prints a MID on the statement narrative and
``levis.bank.mid.map`` turns that into a store. Cash does not. A store pays its
takings in over the counter or at a CDM, and what reaches the statement is a
credit with a free-text memo — so until now the only way to tell whose money it
was, was a hand-written keyword rule guessing at that memo. Measured on July 2026
before the cash-account guard, 76.6% of cash-deposit allocations had landed on
the wrong receivable.

This model replaces the guess with a document. Finance (or the Area Manager) keys
what the store says it paid in, attaches the evidence, and validates it; the
clearing then matches a bank credit to *that*, by amount and date, and takes the
store from the document rather than from the prose.

**Who owns it.** Finance, not the store. There are no store users in this
database and this does not create any: the store sends its slip out of band and
someone in Finance keys it. The ``draft -> submitted -> validated`` split is
still worth its one Selection value, because it separates the person who typed a
number from the person who checked it against the evidence — which is the whole
control this document exists to provide.

**What it is not.** It books nothing. A deposit is a claim about cash that has
left the store, and the accounting for it happens where it always did: on the
bank statement line, through the clearing. If this record and the bank disagree,
that disagreement is the finding, and hiding it behind a journal entry would
destroy the only evidence that it happened.
"""

from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_SETTLED_STATES = ("validated", "matched")


class LevisStoreCashDeposit(models.Model):
    _name = "levis.store.cash.deposit"
    _description = "Store Cash Deposit"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deposit_date desc, id desc"

    name = fields.Char(default="/", copy=False, readonly=True, index=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    # --- who ----------------------------------------------------------------
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Store",
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    store_code = fields.Char(
        related="warehouse_id.l10n_store_code",
        store=True,
        readonly=True,
        index="btree_not_null",
    )
    analytic_account_id = fields.Many2one(
        related="warehouse_id.l10n_ou_analytic_id",
        string="Operating Unit",
        store=True,
        readonly=True,
        index="btree_not_null",
    )

    # --- what ---------------------------------------------------------------
    deposit_date = fields.Date(
        string="Deposit Date",
        required=True,
        tracking=True,
        default=fields.Date.context_today,
        help="The day the money left the store — not the day it was earned.",
    )
    trading_date_from = fields.Date(string="Takings From", required=True, tracking=True)
    trading_date_to = fields.Date(string="Takings To", required=True, tracking=True)
    amount = fields.Monetary(string="Amount Deposited", required=True, tracking=True)
    bank_journal_id = fields.Many2one(
        "account.journal",
        string="Bank",
        required=True,
        tracking=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
    )
    method = fields.Selection(
        [("teller", "Teller"), ("cdm", "CDM / ATM Setor"), ("transfer", "Transfer"), ("pickup", "Cash Pickup")],
        default="teller",
        tracking=True,
    )
    slip_ref = fields.Char(string="Slip / Reference", tracking=True)
    note = fields.Text()

    # --- the string that carries the store code to the bank -----------------
    berita_acara_ref = fields.Char(
        string="Transfer Reference",
        compute="_compute_berita_acara_ref",
        store=True,
        help="What the store must type on the transfer memo. It carries the store "
        "code, so the bank credit can name its own store instead of being guessed "
        "at from the narrative.",
    )

    # --- evidence -----------------------------------------------------------
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "levis_cash_deposit_attachment_rel",
        "deposit_id",
        "attachment_id",
        string="Evidence",
    )
    has_evidence = fields.Boolean(compute="_compute_has_evidence")

    # --- expectation, from the tills ----------------------------------------
    session_ids = fields.Many2many(
        "pos.session",
        "levis_cash_deposit_session_rel",
        "deposit_id",
        "session_id",
        string="POS Sessions",
        help="The sessions whose cash this deposit is. Filled by 'Pull Sessions', "
        "which reads the store's closed sessions over the trading days above.",
    )
    expected_amount = fields.Monetary(
        string="Expected From Tills",
        compute="_compute_expected_amount",
        store=True,
        help="What the closed sessions counted. Blank when no session is linked — "
        "an expectation nobody measured is not zero.",
    )
    variance = fields.Monetary(compute="_compute_expected_amount", store=True)

    # --- state and its consequences -----------------------------------------
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("validated", "Validated"),
            ("matched", "Matched to Bank"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    statement_line_id = fields.Many2one(
        "account.bank.statement.line",
        string="Bank Credit",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    validated_uid = fields.Many2one("res.users", string="Validated By", readonly=True, copy=False)
    validated_date = fields.Datetime(string="Validated On", readonly=True, copy=False)

    # A plain unique constraint is exactly right here: Postgres treats NULLs as
    # distinct, so any number of deposits may await a bank credit while a credit
    # that has been claimed cannot be claimed twice.
    _bank_credit_uniq = models.Constraint(
        "unique(statement_line_id)",
        "That bank credit is already matched to another cash deposit.",
    )
    _amount_positive = models.Constraint(
        "check(amount > 0)",
        "A cash deposit has to be for a positive amount.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("attachment_ids")
    def _compute_has_evidence(self):
        for deposit in self:
            deposit.has_evidence = bool(deposit.attachment_ids)

    @api.depends("store_code", "deposit_date", "name")
    def _compute_berita_acara_ref(self):
        for deposit in self:
            code = (deposit.store_code or "").strip().upper()
            if not code or not deposit.deposit_date or not deposit.name or deposit.name == "/":
                deposit.berita_acara_ref = False
                continue
            deposit.berita_acara_ref = "SETOR/%s/%s/%s" % (
                code,
                deposit.deposit_date.strftime("%Y%m%d"),
                deposit.name.rsplit("/", 1)[-1],
            )

    @api.depends("session_ids", "session_ids.cash_register_balance_end_real", "amount")
    def _compute_expected_amount(self):
        for deposit in self:
            if not deposit.session_ids:
                # Deliberately zero-and-no-variance rather than a made-up figure:
                # "nobody linked a session" must not read as "the store was short".
                deposit.expected_amount = 0.0
                deposit.variance = 0.0
                continue
            expected = sum(deposit.session_ids.mapped("cash_register_balance_end_real"))
            deposit.expected_amount = expected
            deposit.variance = deposit.amount - expected

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("trading_date_from", "trading_date_to", "deposit_date")
    def _check_dates_run_forwards(self):
        for deposit in self:
            if deposit.trading_date_from > deposit.trading_date_to:
                raise ValidationError(_("The takings period ends before it starts."))
            if deposit.trading_date_to > deposit.deposit_date:
                raise ValidationError(
                    _(
                        "Money cannot be paid in before it is taken: the deposit date is earlier than the last trading day."
                    )
                )

    @api.constrains("warehouse_id", "company_id")
    def _check_store_belongs_to_company(self):
        for deposit in self:
            if deposit.warehouse_id.company_id != deposit.company_id:
                raise ValidationError(_("That store belongs to a different company."))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("levis.store.cash.deposit") or "/"
        return super().create(vals_list)

    def write(self, vals):
        # Once a deposit has been matched to a bank credit, the figures that made
        # the match are evidence. Changing them would leave the clearing pointing
        # at a document that no longer says what it said.
        frozen = {"amount", "warehouse_id", "deposit_date", "bank_journal_id"}
        if frozen & set(vals):
            locked = self.filtered(lambda d: d.state == "matched")
            if locked:
                raise UserError(
                    _(
                        "%s is already matched to a bank credit. Unmatch it first if "
                        "the amount or the store was keyed wrongly.",
                        ", ".join(locked.mapped("name")),
                    )
                )
        return super().write(vals)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_pull_sessions(self):
        """Link the store's closed sessions over the stated trading days."""
        for deposit in self:
            if not deposit.warehouse_id:
                raise UserError(_("Choose the store first."))
            # stop_at is a datetime; the trading day is a date. Take the whole
            # of the last day rather than midnight on it, or every session that
            # closed after the tills were cashed up would be missed.
            start = datetime.combine(deposit.trading_date_from, time.min)
            end = datetime.combine(deposit.trading_date_to, time.min) + timedelta(days=1)
            sessions = self.env["pos.session"].search(
                [
                    ("config_id.warehouse_id", "=", deposit.warehouse_id.id),
                    ("state", "=", "closed"),
                    ("stop_at", ">=", start),
                    ("stop_at", "<", end),
                ]
            )
            deposit.session_ids = [(6, 0, sessions.ids)]
        return True

    def action_submit(self):
        for deposit in self:
            if deposit.state != "draft":
                raise UserError(_("Only a draft deposit can be submitted."))
            deposit.state = "submitted"
        return True

    def action_validate(self):
        for deposit in self:
            if deposit.state != "submitted":
                raise UserError(_("Only a submitted deposit can be validated."))
            if not deposit.has_evidence:
                raise UserError(
                    _(
                        "%s has no evidence attached. Validating is the moment "
                        "someone vouches for the slip, so there has to be a slip.",
                        deposit.name,
                    )
                )
            if not deposit.analytic_account_id:
                raise UserError(
                    _(
                        "%s names a store with no Operating Unit analytic, so the "
                        "clearing would have nothing to allocate against.",
                        deposit.name,
                    )
                )
            deposit.write(
                {
                    "state": "validated",
                    "validated_uid": self.env.user.id,
                    "validated_date": fields.Datetime.now(),
                }
            )
        return True

    def action_reset_to_draft(self):
        for deposit in self:
            if deposit.state == "matched":
                raise UserError(_("%s is matched to a bank credit. Unmatch it before reopening.", deposit.name))
            deposit.write({"state": "draft", "validated_uid": False, "validated_date": False})
        return True

    def action_cancel(self):
        for deposit in self:
            if deposit.state == "matched":
                raise UserError(_("%s is matched to a bank credit; unmatch it first.", deposit.name))
            deposit.state = "cancel"
        return True

    def action_unmatch(self):
        """Release the bank credit this deposit claimed."""
        for deposit in self:
            if deposit.state != "matched":
                continue
            deposit.write({"statement_line_id": False, "state": "validated"})
        return True

    def action_open_statement_line(self):
        self.ensure_one()
        if not self.statement_line_id:
            raise UserError(_("No bank credit is matched to this deposit yet."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.bank.statement.line",
            "res_id": self.statement_line_id.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------------
    # Matching — read by the clearing's store-inference ladder
    # ------------------------------------------------------------------
    @api.model
    def _find_for_statement_line(self, statement_line, tolerance=0.0, window_days=3):
        """The one validated deposit this bank credit pays in, or empty.

        Returns a single record only when exactly one candidate fits. Two
        deposits of the same amount in the same window is a real situation (two
        stores, one bank, one flat float) and it is not evidence for either — the
        caller is expected to leave the line unmapped rather than pick.
        """
        if not statement_line or statement_line.amount <= 0:
            return self.browse()
        date = statement_line.date
        if not date:
            return self.browse()
        # The money is paid in on or before the day it lands, never after.
        candidates = self.search(
            [
                ("company_id", "=", statement_line.company_id.id),
                ("state", "=", "validated"),
                ("statement_line_id", "=", False),
                ("bank_journal_id", "=", statement_line.journal_id.id),
                ("deposit_date", ">=", date - timedelta(days=max(window_days, 0))),
                ("deposit_date", "<=", date),
            ]
        )
        band = max(tolerance, 0.005)
        fits = candidates.filtered(lambda d: abs(d.amount - statement_line.amount) <= band)
        return fits if len(fits) == 1 else self.browse()

    def _claim(self, statement_line):
        """Bind this deposit to the credit that paid it in."""
        self.ensure_one()
        self.write({"statement_line_id": statement_line.id, "state": "matched"})
        return True
