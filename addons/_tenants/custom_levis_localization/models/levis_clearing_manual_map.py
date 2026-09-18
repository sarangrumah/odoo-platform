# -*- coding: utf-8 -*-
"""``levis.clearing.manual.map`` — the answers a person gave, kept out of the run.

The clearing rebuilds itself from scratch every time it is computed: ``_compute_one``
unlinks ``line_ids`` and ``_generate_receipts`` drops every candidate receipt that
is not ticked. That is correct — a run is a reading of the ledger at a moment, and
a stale reading is worse than none — but it means a decision written onto a
clearing line does not survive the next Compute. On 9 September 2026 exactly that
happened: a recompute took 3.005 receipts with it and 44 human ticks had to be
recovered from a dump and re-keyed on ``statement_line_id``, because line ids are
not stable across a rebuild.

So the answers a person gives — which store a settlement belongs to, which tender
receivable it pays, which receipts it covers — live here instead: one row per bank
statement line, keyed on the statement line, outliving the run entirely. Compute
reads them back in; the round-trip spreadsheet writes them; nothing else may.

What this model deliberately does **not** do is decide anything. It carries a
person's answer to the engine and the engine treats it as evidence with priority,
the same way ``_attach_evidence`` treats a receipt that names a tender. The one
exception is the channel restriction: a cash deposit may not be pointed at a card
receivable however emphatically the spreadsheet says so, because that restriction
answers a question the person was not asked (see ``_pool_accounts_for_channel``).
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LevisClearingManualMap(models.Model):
    _name = "levis.clearing.manual.map"
    _description = "POS Clearing Manual Mapping"
    _order = "statement_date desc, id desc"
    _rec_name = "display_name"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
    )
    statement_line_id = fields.Many2one(
        "account.bank.statement.line",
        required=True,
        index=True,
        ondelete="cascade",
        string="Bank Line",
    )
    journal_id = fields.Many2one(related="statement_line_id.journal_id", store=True, string="Bank")
    move_name = fields.Char(related="statement_line_id.move_id.name", store=True, string="Bank Entry No.")
    payment_ref = fields.Char(related="statement_line_id.payment_ref", string="Narrative")
    # Snapshot of what the spreadsheet was looking at. A file filled in last week
    # against figures that have since changed is the one thing a round trip can
    # get silently wrong, so the upload compares these before it applies a row.
    statement_date = fields.Date(string="Bank Date")
    statement_amount = fields.Monetary(currency_field="currency_id", string="Bank Amount")
    currency_id = fields.Many2one(related="company_id.currency_id")

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        help="The store this bank line belongs to, decided by a person where the "
        "MID, the terminal and the wording did not say.",
    )
    tender_account_id = fields.Many2one(
        "account.account",
        string="Tender Receivable",
        help="The per-tender POS receivable this settlement pays. Drained first, "
        "exactly like a tender the receipts prove; whatever it cannot cover falls "
        "back to the ordinary search over the channel's pool.",
    )
    receipt_refs = fields.Char(
        string="X24DN Transactions",
        help="``store-register-transaction`` references, comma separated. Ticked "
        "again after every Compute, because a tick on the run itself does not survive one.",
    )
    note = fields.Char(string="Note")
    source = fields.Selection(
        [("upload", "Recon upload"), ("ui", "Entered in Odoo")],
        default="ui",
        required=True,
    )
    upload_log_id = fields.Many2one("levis.clearing.upload.log", string="Upload", ondelete="set null")
    user_id = fields.Many2one("res.users", string="Decided By", default=lambda self: self.env.user)
    active = fields.Boolean(default=True)
    display_name = fields.Char(compute="_compute_display_name")

    _line_uniq = models.Constraint(
        "unique(company_id, statement_line_id)",
        "One bank line carries one manual mapping — edit the existing one instead.",
    )

    @api.depends("move_name", "analytic_account_id", "statement_line_id")
    def _compute_display_name(self):
        for record in self:
            label = record.move_name or record.statement_line_id.payment_ref or str(record.statement_line_id.id or "")
            store = record.analytic_account_id.display_name
            record.display_name = "%s — %s" % (label, store) if store else label

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    @api.constrains("tender_account_id", "statement_line_id", "company_id")
    def _check_tender_account(self):
        """A tender may be chosen; it may not be an account of the wrong kind.

        Two separate refusals, and the second is the one that matters. An account
        outside the configured POS receivables is a typo. A *card* receivable on a
        *cash deposit* is the July-2026 defect being reintroduced by hand: the
        deposit clears a Visa receivable, the real cash receivable stays open, and
        both accounts are misstated while the store total still looks right.
        """
        for record in self.filtered("tender_account_id"):
            config = self.env["levis.clearing.config"].search([("company_id", "=", record.company_id.id)], limit=1)
            if not config:
                continue
            if record.tender_account_id not in config.pos_receivable_account_ids:
                raise ValidationError(
                    _(
                        "%s is not one of the POS tender receivables configured for this company.",
                        record.tender_account_id.display_name,
                    )
                )
            cash_account = config._cash_receivable_account()
            if not cash_account:
                continue
            is_cash = record.statement_line_id.levis_narrative_kind == "cash_deposit"
            if is_cash and record.tender_account_id != cash_account:
                raise ValidationError(
                    _(
                        "%(entry)s is a cash deposit, so it settles %(cash)s and nothing else. "
                        "Pointing it at %(chosen)s would clear a card receivable with cash and "
                        "leave the cash receivable open.",
                        entry=record.move_name or record.statement_line_id.payment_ref or "",
                        cash=cash_account.display_name,
                        chosen=record.tender_account_id.display_name,
                    )
                )
            if not is_cash and record.tender_account_id == cash_account:
                raise ValidationError(
                    _(
                        "%(entry)s is card or QRIS money, so it may not settle the cash receivable %(cash)s.",
                        entry=record.move_name or record.statement_line_id.payment_ref or "",
                        cash=cash_account.display_name,
                    )
                )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    @api.model
    def _for_lines(self, company, statement_line_ids):
        """``{statement line id: record}`` for a Compute to consult."""
        if not statement_line_ids:
            return {}
        records = self.search(
            [
                ("company_id", "=", company.id),
                ("statement_line_id", "in", list(statement_line_ids)),
            ]
        )
        return {record.statement_line_id.id: record for record in records}

    def _refs(self):
        """The receipt references this mapping names, cleaned of spacing and blanks."""
        self.ensure_one()
        return [ref.strip() for ref in (self.receipt_refs or "").replace(";", ",").split(",") if ref.strip()]

    def action_open_statement_line(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.bank.statement.line",
            "res_id": self.statement_line_id.id,
            "view_mode": "form",
            "target": "current",
        }
