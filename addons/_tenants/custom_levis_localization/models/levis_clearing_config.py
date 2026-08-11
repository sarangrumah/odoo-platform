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

    _company_uniq = models.Constraint(
        "unique(company_id)",
        "POS clearing accounts are already configured for this company.",
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
