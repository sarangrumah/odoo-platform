# -*- coding: utf-8 -*-
"""One settlement day, as the operator sees it.

The clearing runs over a month because that is the unit its accounting belongs
to: one sequence, one lock-date check, one balance simulation. But nobody works
a month. The question an operator actually has is "is the 12th done?", and until
now there was nowhere to ask it — status belonged to the run, not to the day.

This model answers it. It is a **projection, not a fourth posting stage**: it
books nothing, it is rebuilt wholesale every time the run recomputes, and
deleting every row would cost nothing but the screen. All the accounting stays on
``levis.pos.clearing`` / ``.line`` / ``.leg`` / ``.alloc``.

**Why a stored model rather than a grouped view.** The day compares two
populations that live in different places — the bank statement lines dated D
against the POS receivables dated D-1 — so no ``read_group`` over either can show
the other. It also needs a status that survives, buttons, and a place to put a
reviewer's note. A view has none of those.

**The green rule, and what it deliberately is not.** A day is green when every
bank line on it is fully allocated, or written off — ``unexplained_total`` is
nil. It is **not** green-because-``tally_variance``-is-zero, and that distinction
is the most important decision in this model.

A settlement legitimately draws on more than one trading day: that is precisely
why ``_candidate_dates`` walks a ladder of ±``lookback_days`` and why
``settlement_lag_days`` is called an assumption in its own help text. Gating the
colour on ``gross_total == sales_h1_total`` would paint days red for a reason no
operator can fix, and a red that cannot be cleared is quickly a red nobody reads.

So the H-1 comparison the business asked for is kept — it is exactly
``tally_variance``, and it has its own column and its own colour — but it is
supervisory information, not a workflow gate. Both are shown. They are not
merged.
"""

from datetime import timedelta

from odoo import _, api, fields, models

_EPS = 0.005


class LevisPosClearingDay(models.Model):
    _name = "levis.pos.clearing.day"
    _description = "POS Clearing Day"
    _order = "settlement_date desc, bank_journal_id"
    _rec_name = "settlement_date"

    run_id = fields.Many2one("levis.pos.clearing", required=True, ondelete="cascade", index=True)
    run_state = fields.Selection(related="run_id.state", store=True)
    company_id = fields.Many2one(related="run_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="run_id.currency_id")
    bank_journal_id = fields.Many2one("account.journal", string="Bank", index=True)

    settlement_date = fields.Date(string="Money In", required=True, index=True)
    trading_date = fields.Date(
        string="Sales Day (H-1)",
        help="The trading day the money is assumed to belong to — settlement date "
        "less the configured lag. An assumption, not a fact: a settlement may draw "
        "on several days.",
    )

    line_ids = fields.One2many("levis.pos.clearing.line", "day_id")

    # --- the bank side ------------------------------------------------------
    line_count = fields.Integer(string="Bank Lines")
    bank_in_total = fields.Monetary(string="Bank In", currency_field="currency_id")
    mdr_total = fields.Monetary(string="MDR", currency_field="currency_id")
    gross_total = fields.Monetary(
        string="Gross",
        currency_field="currency_id",
        help="Bank amount plus the fee the acquirer kept — what the sale was worth.",
    )

    # --- the sales side -----------------------------------------------------
    sales_h1_total = fields.Monetary(
        string="Sales H-1",
        currency_field="currency_id",
        help="POS receivables posted on the trading day, whether or not this run cleared them.",
    )
    tally_variance = fields.Monetary(
        string="Gross vs Sales",
        currency_field="currency_id",
        help="Gross received less the sales of the trading day. Informational: a "
        "settlement may legitimately span several days, so this is a supervisory "
        "check, not a reason the day cannot be finished.",
    )

    # --- how much of it is settled -----------------------------------------
    allocated_total = fields.Monetary(string="Allocated", currency_field="currency_id")
    short_total = fields.Monetary(string="Short", currency_field="currency_id")
    writeoff_total = fields.Monetary(string="Written Off", currency_field="currency_id")
    unexplained_total = fields.Monetary(
        string="Unexplained",
        currency_field="currency_id",
        help="What is left with no explanation and no decision. This is what has to reach nil before the day is done.",
    )

    unmapped_count = fields.Integer(string="Store Unknown")
    unparsed_count = fields.Integer(string="Unreadable")
    store_count = fields.Integer(string="Stores")
    store_ok_count = fields.Integer(string="Stores Settled")

    # --- status -------------------------------------------------------------
    is_balanced = fields.Boolean(string="Settled")
    state = fields.Selection(
        [
            ("todo", "To Do"),
            ("partial", "In Progress"),
            ("ok", "Settled"),
            ("posted", "Posted"),
        ],
        default="todo",
        required=True,
        index=True,
    )
    kanban_color = fields.Integer(string="Colour")
    reviewer_id = fields.Many2one("res.users", string="Reviewed By")
    review_note = fields.Text()

    _day_uniq = models.Constraint(
        "unique(run_id, settlement_date, bank_journal_id)",
        "That settlement day already exists on this run.",
    )

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    @api.model
    def _rebuild_for_run(self, run):
        """Recreate this run's days from its lines. Books nothing.

        Wholesale rather than incremental on purpose: the days are derived, and a
        derived thing that is patched in place eventually disagrees with what it
        was derived from. Recomputing a month of days is a few dozen rows.
        """
        run.ensure_one()
        self.search([("run_id", "=", run.id)]).unlink()
        buckets = {}
        for line in run.line_ids:
            if not line.settlement_date:
                continue
            buckets.setdefault((line.settlement_date, line.bank_journal_id.id), self.env["levis.pos.clearing.line"])
            buckets[(line.settlement_date, line.bank_journal_id.id)] |= line
        if not buckets:
            return self.browse()

        lag = run.config_id.settlement_lag_days or 0
        created = self.create(
            [
                {
                    "run_id": run.id,
                    "settlement_date": settlement_date,
                    "bank_journal_id": journal_id or False,
                    "trading_date": settlement_date - timedelta(days=lag),
                }
                for (settlement_date, journal_id) in sorted(buckets, key=lambda k: (k[0], k[1] or 0))
            ]
        )
        for day in created:
            lines = buckets[(day.settlement_date, day.bank_journal_id.id or False)]
            lines.write({"day_id": day.id})
        created._recompute_figures()
        return created

    def _recompute_figures(self):
        """Roll the lines up, and decide the colour."""
        for day in self:
            lines = day.line_ids
            settling = lines.filtered(lambda line: line.block in ("a", "b"))
            currency = day.currency_id or day.company_id.currency_id
            tolerance = day.run_id.config_id._match_tolerance(sum(settling.mapped("gross")) or 0.0)

            writeoff = sum(abs(line.short_amount) for line in settling if line.writeoff_account_id)
            short = sum(abs(line.short_amount) for line in settling)
            unexplained = short - writeoff

            values = {
                "line_count": len(lines),
                "bank_in_total": sum(settling.mapped("statement_amount")),
                "mdr_total": sum(settling.mapped("mdr")),
                "gross_total": sum(settling.mapped("gross")),
                "allocated_total": sum(settling.mapped("allocated")),
                "short_total": short,
                "writeoff_total": writeoff,
                "unexplained_total": unexplained,
                "unmapped_count": len(lines.filtered(lambda line: line.state == "unmapped")),
                "unparsed_count": len(lines.filtered(lambda line: line.state == "unparsed")),
            }
            values["sales_h1_total"] = day._sales_of_trading_day()
            values["tally_variance"] = values["gross_total"] - values["sales_h1_total"]

            stores = settling.mapped("analytic_account_id")
            values["store_count"] = len(stores)
            values["store_ok_count"] = len(
                [
                    store
                    for store in stores
                    if abs(
                        sum(
                            abs(line.short_amount)
                            for line in settling
                            if line.analytic_account_id == store and not line.writeoff_account_id
                        )
                    )
                    <= max(tolerance, _EPS)
                ]
            )

            balanced = (
                abs(unexplained) <= max(tolerance, _EPS)
                and not values["unmapped_count"]
                and not values["unparsed_count"]
            )
            values["is_balanced"] = balanced
            if day.run_id.state == "posted":
                values["state"] = "posted"
            elif balanced:
                values["state"] = "ok"
            elif values["allocated_total"] or values["writeoff_total"]:
                values["state"] = "partial"
            else:
                values["state"] = "todo"
            # 10 green / 3 amber / 1 red / 0 grey — the whole "green when it is
            # done" request, in one integer the kanban binds to.
            if values["state"] == "posted":
                values["kanban_color"] = 10
            elif balanced:
                values["kanban_color"] = 10
            elif values["unmapped_count"] or values["unparsed_count"]:
                values["kanban_color"] = 1
            elif values["state"] == "partial":
                values["kanban_color"] = 3
            else:
                values["kanban_color"] = 0
            day.write(values)
            _ = currency
        return True

    def _sales_of_trading_day(self):
        """POS receivables of this day's stores, on the trading day.

        Read straight from the ledger rather than from this run's allocations:
        the question is "did roughly the right amount of money show up", and
        answering it from what the run managed to match would make it agree with
        itself by construction.

        **Scoped to the stores this day actually settled**, which is not a
        refinement but a correctness fix. A date can carry more than one bank
        feed, and measured on real August data an IBNI feed holding a single
        Rp 1 line was being compared against the entire company's sales for the
        day — reporting a variance of minus 412 million for a row representing
        one rupiah. A comparison is only meaningful between the same population
        on both sides.
        """
        self.ensure_one()
        config = self.run_id.config_id
        accounts = config.pos_receivable_account_ids
        stores = self.line_ids.filtered(lambda line: line.block in ("a", "b")).mapped("analytic_account_id")
        if not accounts or not self.trading_date or not stores:
            return 0.0
        # The store lives in ``analytic_distribution``, a JSON map of analytic id
        # to percentage, so it is matched by key rather than by a column.
        self.env.cr.execute(
            """
            SELECT COALESCE(SUM(aml.debit), 0.0)
              FROM account_move_line aml
              JOIN account_move m ON m.id = aml.move_id
             WHERE aml.account_id = ANY(%s)
               AND aml.date = %s
               AND aml.company_id = %s
               AND m.state = 'posted'
               AND aml.analytic_distribution ?| %s
            """,
            (
                list(accounts.ids),
                self.trading_date,
                self.company_id.id,
                [str(store_id) for store_id in stores.ids],
            ),
        )
        return self.env.cr.fetchone()[0] or 0.0

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_refresh(self):
        self._recompute_figures()
        return True

    def action_open_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Settlements — %s", self.settlement_date),
            "res_model": "levis.pos.clearing.line",
            "view_mode": "list,form",
            "domain": [("day_id", "=", self.id)],
            "context": {"search_default_group_store": 1},
        }

    def action_open_unexplained(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Unexplained — %s", self.settlement_date),
            "res_model": "levis.pos.clearing.line",
            "view_mode": "list,form",
            "domain": [
                ("day_id", "=", self.id),
                ("short_amount", "!=", 0),
                ("writeoff_account_id", "=", False),
            ],
        }

    def action_open_run(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "levis.pos.clearing",
            "res_id": self.run_id.id,
            "view_mode": "form",
        }

    def action_write_off(self):
        """Hand this day's unexplained residuals to the write-off wizard."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: abs(line.short_amount) > _EPS and not line.writeoff_account_id)
        return lines.action_open_writeoff_wizard()
