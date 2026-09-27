# -*- coding: utf-8 -*-
"""Account wiring for the monthly POS clearing.

The clearing needs six control accounts plus the list of per-tender POS
receivable accounts. ``levis.categ.reclass`` resolves its single clearing
account from an ``ir.config_parameter``, which does not scale here: each of
these wants a domain, a label and a click-through, and one of them is a list of
ten accounts. So this is a per-company table, the same shape (and for the same
reason — account ids differ per database, only the code is stable) as
``levis.purchase.account.map``.

Seeded by code from ``models/setup.py`` on install; a code that does not exist
in the chart is left empty rather than guessed, and the clearing then refuses to
run and says which field is missing.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LevisClearingConfig(models.Model):
    _name = "levis.clearing.config"
    _description = "POS Clearing Accounts"
    _rec_name = "company_id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Clearing Journal",
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help="Journal the clearing entries are booked in (GLJV).",
    )
    bank_journal_ids = fields.Many2many(
        "account.journal",
        "levis_clearing_config_bank_journal_rel",
        "config_id",
        "journal_id",
        string="Bank Journals",
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        help="Statement sources the clearing reads. A bank journal left out here "
        "is never touched, and its settlements stay on suspense.",
    )
    suspense_account_id = fields.Many2one(
        "account.account",
        string="Bank Suspense",
        help="Where the imported statement lines park (every bank journal's "
        "Suspense Account). The clearing entry debits this account, mirroring "
        "the statement line's credit, so the two net out.",
    )
    mdr_account_id = fields.Many2one("account.account", string="MDR Expense")
    ar_account_id = fields.Many2one(
        "account.account",
        string="Trade Receivable",
        help="Used by block B, when a settlement collects a prior-month receivable.",
    )
    sweep_account_id = fields.Many2one(
        "account.account",
        string="Sweep Destination",
        help="Main bank account the collection account is swept into (ATS).",
    )
    bank_charge_account_id = fields.Many2one("account.account", string="Bank Charges")
    pos_receivable_account_ids = fields.Many2many(
        "account.account",
        "levis_clearing_config_posrec_rel",
        "config_id",
        "account_id",
        string="POS Receivable per Tender",
        help="The per-tender receivable accounts a POS session splits into. The "
        "clearing discovers which of them a settlement actually represents by "
        "consuming their open debits — the bank narrative cannot tell us, since "
        "one card MID covers every scheme.",
    )
    settlement_lag_days = fields.Integer(
        default=1,
        required=True,
        help="Assumed days between a sale and its settlement, used only when the "
        "bank narrative carries no transaction date.",
    )
    lookback_days = fields.Integer(
        default=10,
        required=True,
        help="How far before the period start the allocation may reach. Needed "
        "because a settlement early in the month pays for sales made in the "
        "previous one.",
    )

    currency_id = fields.Many2one(related="company_id.currency_id")

    # ------------------------------------------------------------------
    # Advanced matching — every one of these ships inert
    # ------------------------------------------------------------------
    # The defaults below reproduce today's behaviour exactly: no tolerance, no
    # subset search. Each tenant is switched on deliberately, after the before /
    # after measurement described in MODULE_KNOWLEDGE.md. If turning them off no
    # longer restores the old numbers, the defaults are not actually inert and
    # that is a bug, not a tuning question.
    suggest_tolerance_amount = fields.Monetary(
        string="Suggestion Tolerance",
        default=0.0,
        help="Widens which open items are OFFERED and how they are ranked. It "
        "never books anything: a difference inside this band still lands on "
        "suspense until someone writes it off. Zero disables it.",
    )
    suggest_tolerance_ratio = fields.Float(
        string="Suggestion Tolerance (%)",
        digits=(16, 4),
        default=0.0,
        help="Same as the amount above, but relative to the settlement gross. The wider of the two applies.",
    )
    advanced_matching = fields.Boolean(
        string="Advanced Matching",
        default=False,
        help="Master switch for subset matching and store inference. Off means "
        "allocation behaves exactly as it did before those were written.",
    )
    subset_max_items = fields.Integer(
        string="Subset — Max Items",
        default=24,
        help="Largest number of open items a single settlement may be composed "
        "of. Bigger pools are not searched; they fall through to the greedy "
        "allocation instead.",
    )
    subset_node_budget = fields.Integer(
        string="Subset — Node Budget",
        default=20000,
        help="Search effort ceiling per settlement. Exhausting it means 'no answer', never a partial guess.",
    )
    deposit_match_window_days = fields.Integer(
        string="Deposit Match Window (days)",
        default=3,
        help="How far a validated cash deposit may sit from the bank credit that pays it in.",
    )
    writeoff_limit_amount = fields.Monetary(
        string="Write-off Limit",
        default=0.0,
        help="Largest residual a single line may absorb into a chosen account. Zero means no limit.",
    )

    # --- automatic clearing -------------------------------------------
    # Four switches, all inert on arrival, in the same spirit as the block
    # above. They gate the *driver*, not the arithmetic: a proven store-day is
    # proven whether a cron or a person asked the question.
    auto_clear_enabled = fields.Boolean(
        string="Automatic Clearing",
        default=False,
        help="Let the scheduled driver prepare clearing runs on its own. It only "
        "ever prepares: a proven store-day still waits for someone to post it.",
    )
    auto_clear_dry_run = fields.Boolean(
        string="Automatic Clearing — Prepare Only",
        default=True,
        help="Stop after Compute, which creates nothing. Leave this on until the "
        "before/after numbers have been read on a real period.",
    )
    auto_clear_delay_days = fields.Integer(
        string="Automatic Clearing — Settle For (days)",
        default=2,
        help="How long a settlement date is left alone before the driver looks at "
        "it, so the acquirer's feed and the day's sales have both landed.",
    )
    auto_clear_max_dates = fields.Integer(
        string="Automatic Clearing — Dates Per Pass",
        default=5,
        help="Upper bound on how many settlement dates one pass may prepare. A "
        "backlog is worked off over several passes rather than in one long "
        "transaction.",
    )

    _company_uniq = models.Constraint(
        "unique(company_id)",
        "POS clearing accounts are already configured for this company.",
    )

    @api.constrains("suggest_tolerance_amount", "suggest_tolerance_ratio", "writeoff_limit_amount")
    def _check_tolerances_not_negative(self):
        for config in self:
            if (
                config.suggest_tolerance_amount < 0
                or config.suggest_tolerance_ratio < 0
                or config.writeoff_limit_amount < 0
            ):
                raise UserError(_("Tolerances and limits cannot be negative."))

    def _match_tolerance(self, amount):
        """The suggestion band around ``amount`` — the wider of the two settings.

        Note this is *not* ``_EPS``. ``_EPS`` is float noise; this is a business
        decision about how much difference is worth offering a human. Never let
        one stand in for the other: a tolerance-sized difference is money someone
        chose to absorb, and it has to stay visible as such.
        """
        self.ensure_one()
        return max(
            self.suggest_tolerance_amount or 0.0,
            abs(amount or 0.0) * (self.suggest_tolerance_ratio or 0.0) / 100.0,
        )

    @api.constrains("suspense_account_id", "bank_journal_ids")
    def _check_suspense_matches_journals(self):
        """The mirror leg only nets out if both sides use the same account."""
        for config in self:
            if not config.suspense_account_id:
                continue
            odd = config.bank_journal_ids.filtered(
                lambda j, c=config: j.suspense_account_id and j.suspense_account_id != c.suspense_account_id
            )
            if odd:
                raise UserError(
                    _(
                        "Bank journal(s) %(journals)s park their statement lines on a "
                        "different suspense account than %(account)s. The clearing "
                        "entry would debit an account the statement never credited, "
                        "leaving both open. Align the journals or exclude them.",
                        journals=", ".join(odd.mapped("code")),
                        account=config.suspense_account_id.display_name,
                    )
                )

    @api.model
    def _get(self, company):
        """The configuration for ``company``, or a readable error."""
        config = self.sudo().search([("company_id", "=", company.id)], limit=1)
        if not config:
            raise UserError(
                _(
                    "POS clearing is not configured for %s. Set the accounts under "
                    "Accounting > Configuration > POS Clearing Accounts first.",
                    company.display_name,
                )
            )
        return config

    def _check_complete(self):
        """Refuse to compute against a half-filled configuration."""
        self.ensure_one()
        required = {
            "suspense_account_id": _("Bank Suspense"),
            "mdr_account_id": _("MDR Expense"),
            "ar_account_id": _("Trade Receivable"),
            "sweep_account_id": _("Sweep Destination"),
            "bank_charge_account_id": _("Bank Charges"),
        }
        missing = [label for field, label in required.items() if not self[field]]
        if not self.pos_receivable_account_ids:
            missing.append(_("POS Receivable per Tender"))
        if not self.bank_journal_ids:
            missing.append(_("Bank Journals"))
        if missing:
            raise UserError(
                _(
                    "POS clearing configuration is incomplete — missing: %s.",
                    ", ".join(missing),
                )
            )
        return True

    def _pos_accounts_sorted(self):
        self.ensure_one()
        return self.pos_receivable_account_ids.sorted(lambda a: a.code or "")

    def _cash_receivable_account(self):
        """The per-tender receivable a cash deposit settles, or empty.

        Resolved by code from ``ir.config_parameter`` (default ``1106000101``) and
        required to be one of the configured tender accounts, so a typo cannot
        point the restriction at some unrelated account. Deliberately not a field
        here: that would be a column, and a column means upgrading every database
        that shares this addon.

        Lives on the config rather than on the run because the question is about
        a company, not about a run — a manual mapping has to be able to ask it
        before any run exists.
        """
        self.ensure_one()
        code = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("custom_levis_localization.pos_cash_receivable_code", "1106000101")
        )
        company = self.company_id
        return self.pos_receivable_account_ids.filtered(lambda a: (a.with_company(company).code or "") == code)[:1]
