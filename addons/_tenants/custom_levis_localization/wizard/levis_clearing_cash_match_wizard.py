# -*- coding: utf-8 -*-
"""``levis.clearing.cash.match`` — the till on one side, the deposits on the other.

A card settlement names its shop: the acquirer prints a merchant id and
``levis.bank.mid.map`` turns that into a store. A cash deposit names nothing.
"SETORAN TUNAI", and the money is in the account — no merchant id, no terminal,
often not even a store word in the memo. Measured on September 2026 in
prd_levis_begbal, 70 credits worth Rp 106.059.800 reached the clearing that way:
attributed to nobody, allocated against nothing, while the store-day screen
reported the same money a second time as a till that never arrived.

``_attribute_cash_deposits`` closes the half of that which arithmetic can close
on its own — one store, one trading day, one deposit, exact to the rupiah. This
screen is the other half, and it exists because the arithmetic deliberately
refuses to guess: two shops banking the same round float on the same morning,
a till banked in two parts, a week's takings paid in at once. All of those are
a person's call, and all of them are visible here beside the figure they have
to add up to.

**It writes an answer, not an entry.** Confirming records the decision on
``levis.clearing.manual.map`` — the store, and the trading day whose till it is —
because that is the only place a decision survives the next Compute, which
rebuilds every line from scratch. The money is then booked by the ordinary
allocation on the recompute this wizard asks for, against the CASH receivable
and nothing else, exactly as a deposit the narrative had named.

**Why it recomputes rather than patching the line.** A clearing line is a
reading of the ledger, not a record: its allocation, its store-day, its proof
and its diagnostics are all derived together. Writing a store onto one line and
leaving the rest of that derivation stale would produce a row that claims a
store and settles nothing, which is precisely the state this screen is meant to
end. A run that has already generated its entries is refused instead — there,
the answer is still recorded, and it is picked up by the next run.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_EPS = 0.005


class LevisClearingCashMatch(models.TransientModel):
    _name = "levis.clearing.cash.match"
    _description = "Match Cash Deposits to a Store's Till"

    store_day_id = fields.Many2one("levis.pos.clearing.store.day", required=True, ondelete="cascade")
    run_id = fields.Many2one(related="store_day_id.run_id")
    company_id = fields.Many2one(related="store_day_id.company_id")
    currency_id = fields.Many2one(related="store_day_id.currency_id")
    analytic_account_id = fields.Many2one(related="store_day_id.analytic_account_id", string="Store")
    trading_date = fields.Date(related="store_day_id.trading_date", string="Trading Day")

    x70d_cash_total = fields.Monetary(
        related="store_day_id.x70d_cash_total",
        currency_field="currency_id",
        string="Till Rang Up",
    )
    cash_deposit_total = fields.Monetary(
        related="store_day_id.cash_deposit_total",
        currency_field="currency_id",
        string="Already Banked",
    )
    outstanding = fields.Monetary(
        compute="_compute_totals",
        currency_field="currency_id",
        string="Still Out",
        help="The till of this trading day that no deposit pays yet. What the ticks below have to add up to.",
    )
    selected_total = fields.Monetary(compute="_compute_totals", currency_field="currency_id", string="Ticked")
    gap = fields.Monetary(compute="_compute_totals", currency_field="currency_id", string="Difference")
    ties = fields.Boolean(compute="_compute_totals", string="Tallies")

    line_ids = fields.One2many("levis.clearing.cash.match.line", "wizard_id", string="Unattributed Deposits")

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    @api.model
    def _build_for(self, store_day):
        """Every deposit of this run that could be this store-day's till.

        The window runs forward from the trading day, never back: cash is rung
        up first and banked afterwards. Its width is the same
        ``cash_match_lookback_days`` the automatic pass uses, read from the
        other end, plus the settlement lag — so anything the matcher could have
        taken is on this list.

        It is deliberately **one day wider at the near end**: the automatic pass
        starts at the settlement lag and so never considers a till banked the
        same evening it was rung up, where X70D may still be growing and an
        exact sum would be luck. A person looking at the slip knows, so the
        screen offers it.
        """
        store_day.ensure_one()
        config = store_day.run_id.config_id
        lookback = max(config.cash_match_lookback_days or 0, 0)
        lag = config.settlement_lag_days or 0
        candidates = store_day.run_id.line_ids.filtered(
            lambda line: (
                line.kind == "cash_deposit"
                and not line.analytic_account_id
                and line.settlement_date
                and store_day.trading_date
                and 0 <= (line.settlement_date - store_day.trading_date).days <= lookback + lag
            )
        )
        return self.create(
            {
                "store_day_id": store_day.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "line_id": line.id,
                            "statement_line_id": line.statement_line_id.id,
                            "amount": line.statement_amount,
                        },
                    )
                    # Closest to what is still out first: the answer is usually
                    # the whole till in one credit, and when it is not, the
                    # biggest part of it is the row to start from.
                    for line in candidates.sorted(
                        lambda line: (
                            abs(line.statement_amount - (store_day.x70d_cash_total - store_day.cash_deposit_total)),
                            line.settlement_date,
                        )
                    )
                ],
            }
        )

    @api.depends(
        "line_ids.selected",
        "line_ids.amount",
        "store_day_id.x70d_cash_total",
        "store_day_id.cash_deposit_total",
    )
    def _compute_totals(self):
        for wizard in self:
            outstanding = round(wizard.x70d_cash_total - wizard.cash_deposit_total, 2)
            ticked = round(sum(line.amount for line in wizard.line_ids if line.selected), 2)
            wizard.outstanding = outstanding
            wizard.selected_total = ticked
            wizard.gap = round(outstanding - ticked, 2)
            wizard.ties = bool(ticked) and abs(wizard.gap) <= _EPS

    # ------------------------------------------------------------------
    # Applying
    # ------------------------------------------------------------------
    def action_apply(self):
        """Record the decision, then let the run read it back.

        No tie is demanded. A shop that banks half its till on Monday and the
        rest on Wednesday is ordinary, and refusing the Monday half until the
        Wednesday one appears would leave real money unattributed for the sake
        of a round number. What is refused is a deposit bigger than the till it
        claims to pay: that is not a partial answer, it is a wrong one.
        """
        self.ensure_one()
        picked = self.line_ids.filtered("selected")
        if not picked:
            raise UserError(_("Tick the deposit that pays this store's till first."))
        run = self.run_id
        if run.state in ("generated", "posted"):
            raise UserError(
                _(
                    "%s has already generated its entries, so its lines can no longer be "
                    "re-read. The answer is worth keeping anyway — record it on the "
                    "mapping list, and the next run will pick it up.",
                    run.name,
                )
            )
        if self.selected_total - self.outstanding > _EPS:
            raise UserError(
                _(
                    "%(ticked)s is more cash than %(store)s rang up on %(day)s (%(till)s still "
                    "out). A deposit cannot pay a till bigger than itself — check the trading "
                    "day, or leave it for the store-day it really belongs to.",
                    ticked=self.selected_total,
                    store=self.analytic_account_id.display_name,
                    day=self.trading_date,
                    till=self.outstanding,
                )
            )
        ManualMap = self.env["levis.clearing.manual.map"]
        for row in picked:
            statement_line = row.statement_line_id
            existing = ManualMap.search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("statement_line_id", "=", statement_line.id),
                ],
                limit=1,
            )
            vals = {
                "analytic_account_id": self.analytic_account_id.id,
                "trading_date": self.trading_date,
                "note": _(
                    "Cash deposit matched by hand to the till of %(day)s.",
                    day=self.trading_date,
                ),
            }
            if existing:
                existing.write(vals)
            else:
                ManualMap.create(
                    dict(
                        vals,
                        company_id=self.company_id.id,
                        statement_line_id=statement_line.id,
                        statement_date=statement_line.date,
                        statement_amount=statement_line.amount,
                        source="ui",
                    )
                )
        # The answer is written; this is what turns it into an allocation. Note
        # the recompute *destroys* this store-day row — the projection is rebuilt
        # wholesale — so the way back is its key, never its id.
        key = (run.id, self.store_day_id.settlement_date, self.analytic_account_id.id)
        run.action_compute()
        rebuilt = self.env["levis.pos.clearing.store.day"].search(
            [
                ("run_id", "=", key[0]),
                ("settlement_date", "=", key[1]),
                ("analytic_account_id", "=", key[2]),
            ],
            limit=1,
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "levis.pos.clearing.store.day",
            "res_id": rebuilt.id,
            "view_mode": "form",
            "target": "current",
        }


class LevisClearingCashMatchLine(models.TransientModel):
    _name = "levis.clearing.cash.match.line"
    _description = "Cash Deposit Candidate"
    _order = "id"

    wizard_id = fields.Many2one("levis.clearing.cash.match", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    line_id = fields.Many2one("levis.pos.clearing.line", string="Clearing Line", ondelete="cascade")
    statement_line_id = fields.Many2one("account.bank.statement.line", required=True, ondelete="cascade")
    move_name = fields.Char(related="statement_line_id.move_id.name", string="Bank Entry")
    date = fields.Date(related="statement_line_id.date", string="Money In")
    journal_id = fields.Many2one(related="statement_line_id.journal_id", string="Bank")
    payment_ref = fields.Char(related="statement_line_id.payment_ref", string="Narrative")
    amount = fields.Monetary(currency_field="currency_id", string="Amount")
    selected = fields.Boolean(string="Pays this till")
