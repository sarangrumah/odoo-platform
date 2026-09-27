# -*- coding: utf-8 -*-
"""``levis.clearing.match`` — the bank on the left, the till on the right.

A store-day that ties needs nobody. One that does not is a question about two
lists: which of this store's transactions did that particular bank credit pay?
The arithmetic answers it where it can (``_x24_identify``); the rest is a person
reading both columns, which is what this screen is.

Three rules shape it, and each is the same rule the engine already keeps:

* **Pairing names one bank line.** A receipt belongs to the credit that paid it,
  so the left column takes exactly one tick before *Pasangkan* means anything.
  Ticking two would leave the assignment ambiguous, and an ambiguous tick is
  worse than none.
* **A transaction is paid once.** One already claimed — by any credit, this
  store-day's own included — is shown named with the entry holding it and cannot
  be ticked: the exclusivity the partial unique index enforces, made visible
  instead of hit as an error on the way out. Moving one means releasing it on the
  credit that holds it first.
* **The answer outlives the run.** It is written to
  ``levis.clearing.manual.map`` as well as to the run's receipts, because
  ``action_compute`` rebuilds receipts and would otherwise drop it.

The screen writes no accounting at all. It records what pays what; clearing is
still the run's three stages.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_EPS = 0.005


class LevisClearingMatch(models.TransientModel):
    _name = "levis.clearing.match"
    _description = "Match Bank Settlements to Store Transactions"

    store_day_id = fields.Many2one("levis.pos.clearing.store.day", required=True, ondelete="cascade")
    run_id = fields.Many2one(related="store_day_id.run_id")
    company_id = fields.Many2one(related="store_day_id.company_id")
    currency_id = fields.Many2one(related="store_day_id.currency_id")
    analytic_account_id = fields.Many2one(related="store_day_id.analytic_account_id", string="Store")
    settlement_date = fields.Date(related="store_day_id.settlement_date", string="Money In")
    trading_date = fields.Date(related="store_day_id.trading_date", string="Sales Of")

    bank_ids = fields.One2many("levis.clearing.match.bank", "wizard_id", string="Bank Settlements")
    txn_ids = fields.One2many("levis.clearing.match.txn", "wizard_id", string="Store Transactions")

    bank_selected = fields.Monetary(compute="_compute_totals", currency_field="currency_id", string="Bank Selected")
    txn_selected = fields.Monetary(
        compute="_compute_totals", currency_field="currency_id", string="Transactions Selected"
    )
    gap = fields.Monetary(compute="_compute_totals", currency_field="currency_id", string="Difference")
    ties = fields.Boolean(compute="_compute_totals", string="Tallies")
    note = fields.Char(string="Note", help="Kept on the mapping, for whoever reads this next month.")

    # ------------------------------------------------------------------
    # Building the two columns
    # ------------------------------------------------------------------
    @api.model
    def _build_for(self, store_day):
        """A wizard holding both of this store-day's lists."""
        Receipt = self.env["levis.pos.clearing.receipt"]
        claimed = {
            receipt.ref: receipt
            for receipt in Receipt.search([("company_id", "=", store_day.company_id.id), ("matched", "=", True)])
        }
        bank_vals = [
            (
                0,
                0,
                {
                    "line_id": line.id,
                    # A settlement's own figure is the gross the acquirer paid on,
                    # not the net the bank moved: the transactions add up to gross.
                    "target": line.gross or abs(line.statement_amount),
                },
            )
            for line in store_day.line_ids.sorted(lambda line: (line.settlement_date, line.id))
        ]
        txn_vals = []
        for txn in store_day.x70d_txn_ids.sorted(lambda t: (t.tender or "", t.ref or "")):
            holder = claimed.get(txn.ref)
            txn_vals.append(
                (
                    0,
                    0,
                    {
                        "ref": txn.ref,
                        "tender": txn.tender,
                        "trans_date": txn.trans_date,
                        "amount": txn.amount,
                        # Every holder locks it, including a credit on this same
                        # store-day. Half a lock is worse than none: it lets a tick
                        # look available and then fail at the database on the way
                        # out. Moving a receipt means releasing it on the credit
                        # that holds it, which is what "Lepas Semua" is for.
                        "claimed_by": holder.move_name if holder else False,
                        "claimed_line_id": holder.line_id.id if holder else False,
                    },
                )
            )
        return self.create({"store_day_id": store_day.id, "bank_ids": bank_vals, "txn_ids": txn_vals})

    @api.depends("bank_ids.selected", "bank_ids.target", "txn_ids.selected", "txn_ids.amount")
    def _compute_totals(self):
        for wizard in self:
            bank = sum(row.target for row in wizard.bank_ids if row.selected)
            txn = sum(row.amount for row in wizard.txn_ids if row.selected)
            wizard.bank_selected = bank
            wizard.txn_selected = txn
            wizard.gap = round(bank - txn, 2)
            wizard.ties = bool(bank) and abs(wizard.gap) <= _EPS

    # ------------------------------------------------------------------
    # Pairing
    # ------------------------------------------------------------------
    def action_match(self):
        """Record that the ticked transactions are what the ticked credit paid."""
        self.ensure_one()
        banks = self.bank_ids.filtered("selected")
        if len(banks) != 1:
            raise UserError(
                _(
                    "Tick exactly one bank settlement on the left. A transaction is paid by "
                    "one credit, so pairing several at once would not say which paid which."
                )
            )
        line = banks.line_id
        chosen = self.txn_ids.filtered("selected")
        blocked = chosen.filtered(lambda row: row.claimed_by)
        if blocked:
            raise UserError(
                _(
                    "%(ref)s is already matched to %(entry)s. Untick it there first — one transaction is paid once.",
                    ref=blocked[0].ref,
                    entry=blocked[0].claimed_by,
                )
            )
        refs = chosen.mapped("ref")
        self._write_mapping(line, refs)
        self._apply_receipts(line, refs)
        return self._reopen()

    def action_unmatch_all(self):
        """Take back every tick this store-day holds, on the selected credit."""
        self.ensure_one()
        banks = self.bank_ids.filtered("selected")
        if len(banks) != 1:
            raise UserError(_("Tick the bank settlement whose matches you want to clear."))
        line = banks.line_id
        self._write_mapping(line, [])
        self.env["levis.pos.clearing.receipt"].search([("line_id", "=", line.id), ("matched", "=", True)]).write(
            {"matched": False}
        )
        return self._reopen()

    def _write_mapping(self, line, refs):
        """The durable half: a recompute rebuilds receipts, not this."""
        ManualMap = self.env["levis.clearing.manual.map"]
        existing = ManualMap.search(
            [
                ("company_id", "=", self.company_id.id),
                ("statement_line_id", "=", line.statement_line_id.id),
            ],
            limit=1,
        )
        vals = {"receipt_refs": ",".join(refs) if refs else False}
        if self.note:
            vals["note"] = self.note
        if existing:
            existing.write(vals)
            return existing
        vals.update(
            {
                "company_id": self.company_id.id,
                "statement_line_id": line.statement_line_id.id,
                "statement_date": line.settlement_date,
                "statement_amount": line.statement_amount,
                "source": "ui",
                "user_id": self.env.user.id,
            }
        )
        return ManualMap.create(vals)

    def _apply_receipts(self, line, refs):
        """And the visible half: the run's own worksheet, ticked to match."""
        Receipt = self.env["levis.pos.clearing.receipt"]
        mine = Receipt.search([("line_id", "=", line.id)])
        mine.filtered(lambda r: r.matched and r.ref not in refs).write({"matched": False})
        known = {row.ref: row for row in self.txn_ids}
        for ref in refs:
            row = mine.filtered(lambda r, ref=ref: r.ref == ref)
            if row:
                row.matched = True
                continue
            source = known.get(ref)
            Receipt.create(
                {
                    "line_id": line.id,
                    "ref": ref,
                    "tender": source.tender if source else False,
                    "trans_date": source.trans_date if source else line.trans_date,
                    "amount": source.amount if source else 0.0,
                    "suggested": False,
                    "matched": True,
                }
            )
        return True

    def _reopen(self):
        """Rebuilt rather than refreshed: both columns have just changed."""
        self.ensure_one()
        return self.store_day_id.action_open_matcher()


class LevisClearingMatchBank(models.TransientModel):
    _name = "levis.clearing.match.bank"
    _description = "Match Screen — Bank Settlement"
    _order = "id"

    wizard_id = fields.Many2one("levis.clearing.match", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    line_id = fields.Many2one("levis.pos.clearing.line", required=True, ondelete="cascade")
    selected = fields.Boolean(string="Pick")
    move_name = fields.Char(related="line_id.move_name", string="Bank Entry")
    payment_ref = fields.Char(related="line_id.payment_ref", string="Narrative")
    channel = fields.Selection(related="line_id.channel")
    statement_amount = fields.Monetary(related="line_id.statement_amount", currency_field="currency_id")
    mdr = fields.Monetary(related="line_id.mdr", currency_field="currency_id")
    target = fields.Monetary(currency_field="currency_id", string="Gross")
    matched_total = fields.Monetary(related="line_id.matched_total", currency_field="currency_id")
    match_gap = fields.Monetary(related="line_id.match_gap", currency_field="currency_id", string="Unmatched")
    state = fields.Selection(related="line_id.state")


class LevisClearingMatchTxn(models.TransientModel):
    _name = "levis.clearing.match.txn"
    _description = "Match Screen — Store Transaction"
    _order = "tender, ref"

    wizard_id = fields.Many2one("levis.clearing.match", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    ref = fields.Char(string="Transaction No.", required=True)
    tender = fields.Char()
    trans_date = fields.Date(string="Trading Day")
    amount = fields.Monetary(currency_field="currency_id")
    selected = fields.Boolean(string="Pick")
    claimed_by = fields.Char(
        string="Already Paid By",
        readonly=True,
        help="Another bank credit already names this transaction. It cannot be ticked here until it is released there.",
    )
    claimed_line_id = fields.Many2one("levis.pos.clearing.line", readonly=True)
