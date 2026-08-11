# -*- coding: utf-8 -*-
"""What a bank statement line says, and which clearing run has spent it.

Two independent things live here.

The first is the *reading* of the line: the acquirer already prints the store's
merchant id, the gross it billed and the fee it withheld on every settlement
narrative, so ``levis.bank.narrative`` + ``levis.bank.mid.map`` can turn
``payment_ref`` into (Operating Unit, gross, MDR) without anyone opening a
workbook. The monthly clearing computes that on the fly; storing it on the line
itself is what lets a human do the same job one line at a time — filter the
statement by store, see that Rp 4.722.112 arrived as Rp 4.689.356 net of a
Rp 32.755 fee, and match against the tender receivable at its *gross*.

The second is the marker below. The bank suspense account is not reconcilable,
so a settled statement line never becomes ``is_reconciled`` — in
prd_levis_begbal all 2 111 July BCA lines are still False.

Without a marker, next month's run would happily consume July's settlements a
second time and book the whole thing twice.

So consumption is recorded explicitly. The marker is written when the DRAFT
entries are generated, never when a summary is computed: previewing a period must
leave the database exactly as it was.
"""

from odoo import api, fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    # ------------------------------------------------------------------
    # What the narrative says
    # ------------------------------------------------------------------
    levis_narrative_kind = fields.Selection(
        [
            ("settlement", "Card / QRIS Settlement"),
            ("cash_deposit", "Cash Deposit"),
            ("sweep", "Sweep to Main Account"),
            ("charge", "Bank Charge"),
            ("interest", "Interest"),
            ("unknown", "Not Recognised"),
        ],
        string="Narrative Type",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
    )
    levis_channel = fields.Selection(
        [
            ("debit", "Debit Card"),
            ("credit", "Credit Card"),
            ("qris", "QRIS"),
            ("cash", "Cash"),
            ("transfer", "Transfer"),
            ("other", "Other"),
        ],
        string="Tender Channel",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
    )
    levis_mid = fields.Char(
        string="Merchant / Terminal",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
        help="The MID or TID the acquirer printed on this line — the only safe "
        "key to the store, since the narrative truncates store names.",
    )
    levis_gross = fields.Monetary(
        string="Gross (Narrative)",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
        currency_field="currency_id",
        help="What the acquirer billed before its fee. The tender receivable is "
        "carried at this amount, not at the net that hit the bank.",
    )
    levis_mdr = fields.Monetary(
        string="MDR (Narrative)",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
        currency_field="currency_id",
        help="The fee the acquirer withheld: gross minus the amount received.",
    )
    levis_trans_date = fields.Date(
        string="Trading Day",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
        help="Sale date read from the narrative, when it carries one. Empty means "
        "the settlement lag has to be assumed instead.",
    )
    levis_ou_analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
        index="btree_not_null",
        help="Store this settlement belongs to, resolved from the Bank MID "
        "Mapping. Empty means the merchant id is not mapped yet — the line is "
        "left unattributed rather than guessed onto a store.",
    )
    levis_mid_map_id = fields.Many2one(
        "levis.bank.mid.map",
        string="Matched Mapping",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
    )
    levis_narrative_note = fields.Char(
        string="Narrative Note",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
    )
    levis_amount_matches_narrative = fields.Boolean(
        string="Amount Agrees",
        compute="_compute_levis_narrative",
        store=True,
        readonly=True,
        help="True when gross minus MDR equals the amount that actually landed. "
        "A mismatch is a finding, not a rounding to absorb.",
    )

    @api.depends("payment_ref", "amount", "date", "journal_id.levis_clearing_format")
    def _compute_levis_narrative(self):
        """Read every line through its journal's grammar, then map it to a store.

        Recomputed whenever the narrative, amount or the journal's format
        changes. It deliberately does *not* depend on ``levis.bank.mid.map``:
        adding a mapping for one store must not silently rewrite the whole
        statement history, so Finance re-reads the affected lines explicitly with
        the button below (the mapping wizard's usual follow-up).
        """
        parser = self.env["levis.bank.narrative"]
        mapper = self.env["levis.bank.mid.map"]
        by_journal = {}
        for line in self:
            parsed = parser.parse(line.journal_id, line.payment_ref, line.amount, line.date)
            company = line.company_id or self.env.company
            cache_key = (company.id, line.journal_id.id)
            if cache_key not in by_journal:
                by_journal[cache_key] = mapper._candidates(company, line.journal_id)
            rule = mapper._resolve(company, line.journal_id, parsed, line.date, candidates=by_journal[cache_key])
            line.levis_narrative_kind = parsed["kind"]
            line.levis_channel = parsed["channel"]
            line.levis_mid = parsed["mid"] or parsed["tid"] or False
            line.levis_gross = parsed["gross"]
            line.levis_mdr = parsed["mdr"]
            line.levis_trans_date = parsed["trans_date"] or False
            line.levis_mid_map_id = rule.id if rule else False
            line.levis_ou_analytic_id = rule.analytic_account_id.id if rule else False
            line.levis_narrative_note = parsed["note"] or False
            currency = line.currency_id or company.currency_id
            line.levis_amount_matches_narrative = (
                parsed["kind"] != "settlement"
                or not currency
                or currency.is_zero(parsed["gross"] - parsed["mdr"] - (line.amount or 0.0))
            )

    def action_levis_reread_narrative(self):
        """Re-read these lines — used after a MID mapping is added or corrected.

        Goes through ``add_to_compute`` rather than calling the compute directly,
        so the ORM owns the write and the values actually reach the database.
        """
        for field in self._fields.values():
            if field.compute == "_compute_levis_narrative" and field.store:
                self.env.add_to_compute(field, self)
        self.flush_recordset()
        return True

    # ------------------------------------------------------------------
    # Which clearing run spent the line
    # ------------------------------------------------------------------
    levis_clearing_line_id = fields.Many2one(
        "levis.pos.clearing.line",
        string="POS Clearing Line",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    levis_clearing_run_id = fields.Many2one(
        "levis.pos.clearing",
        # Not "POS Clearing": account.move already contributes a field by that
        # label through _inherits, and two same-labelled fields on one model are
        # ambiguous in the UI.
        string="Cleared By Run",
        related="levis_clearing_line_id.run_id",
        store=True,
        readonly=True,
        index="btree_not_null",
    )
