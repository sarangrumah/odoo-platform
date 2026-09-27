# -*- coding: utf-8 -*-
"""One store, one settlement day: money in against what the store sold.

``levis.pos.clearing.day`` answers "is the 12th done?" for a whole bank feed.
The question the store accountant actually asks is narrower and has no home yet:
*for this shop, did the money the bank paid on H match the tenders the shop rang
up on H-1, and if not, which transaction is missing?*

That question cannot be answered by grouping the settlement list. Both halves
live in different places — the bank side on ``levis.pos.clearing.line``, the
sales side in the X70D rows ``custom_retail_import`` staged — and no
``read_group`` over one can show the other. So the comparison is a stored
projection, exactly like the day model: rebuilt wholesale on every recompute,
booking nothing, safe to delete.

**What is compared, and why it is stated three ways.** The bank pays net of the
acquirer fee, the store rang up gross, so a single "statement vs sales" number
would report the MDR as a shortfall every single day. The row therefore carries
all three: what hit the bank (``statement_total``), what that was worth before
the fee (``gross_total``), and what the store actually sold (``x70d_total``).
``variance`` compares the two comparable ones — gross against X70D — and
``variance_bank`` is kept beside it for whoever is reading the bank book rather
than the ledger.

**Cash is included.** By instruction: the row shows every tender the store rang
up, cash among them, with cash split out into its own column so nobody mistakes
an undeposited till for a missing settlement. A store whose card money is
perfect and whose cash is still in the safe shows a variance exactly equal to
the cash — which is the point, not a defect.

**Two differences, and they are not merged.** ``variance`` weighs the bank
against the *staged X70D file*, and stays supervisory exactly as this docstring
has always said. ``proof_variance`` weighs it against the *open receivable in
the ledger*, and that one is a gate: ``proof_state`` is what decides whether a
store-day may be booked without a person reading it. (``short_total``, a third
figure nearby, is neither — it reports what the allocation managed to take.)
Merging them would be a mistake with a measured cost: X70D is missing for nine
stores and for two September days, so a gate built on ``variance`` would refuse
days that are perfectly clearable, for a reason that has nothing to do with the
money.

**H-1 is an assumption, not a fact.** The trading day is the settlement date
less the configured lag, the same assumption ``_candidate_dates`` walks a ladder
around. A settlement may legitimately draw on two days, so a variance here is
supervisory information — it never gates the clearing, and nothing here blocks a
posting.
"""

from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from .levis_pos_clearing import _SETTLING_KINDS

_EPS = 0.005
# Tender names that mean notes and coins rather than a card the bank settles.
_CASH_TENDERS = {"CASH", "TUNAI"}


class LevisPosClearingStoreDay(models.Model):
    _name = "levis.pos.clearing.store.day"
    _description = "POS Clearing Store Settlement Day"
    _order = "settlement_date desc, analytic_account_id"
    _rec_name = "display_name"

    run_id = fields.Many2one("levis.pos.clearing", required=True, ondelete="cascade", index=True)
    run_state = fields.Selection(related="run_id.state", store=True)
    company_id = fields.Many2one(related="run_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="run_id.currency_id")

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Store Operating Unit",
        required=True,
        index=True,
        ondelete="cascade",
    )
    settlement_date = fields.Date(string="Money In", required=True, index=True)
    trading_date = fields.Date(
        string="Trading Day (H-1)",
        help="The trading day this settlement is assumed to pay for — settlement date "
        "less the configured lag. An assumption: a settlement may draw on several days.",
    )

    line_ids = fields.One2many("levis.pos.clearing.line", "store_day_id")
    tender_ids = fields.One2many("levis.pos.clearing.store.day.tender", "store_day_id")

    # --- the bank side ------------------------------------------------------
    line_count = fields.Integer(string="Bank Lines")
    statement_total = fields.Monetary(
        string="Statement Amount",
        currency_field="currency_id",
        help="What actually reached the bank account on the settlement date, for this store.",
    )
    mdr_total = fields.Monetary(string="MDR", currency_field="currency_id")
    gross_total = fields.Monetary(
        string="Gross",
        currency_field="currency_id",
        help="Statement amount plus the fee the acquirer kept — comparable with what the store rang up.",
    )
    allocated_total = fields.Monetary(string="Allocated", currency_field="currency_id")
    short_total = fields.Monetary(string="Short", currency_field="currency_id")
    other_count = fields.Integer(string="Other Lines")
    other_total = fields.Monetary(
        string="Other Movements",
        currency_field="currency_id",
        help="Bank lines of this store and date that are not takings — a sweep to the main account, "
        "a bank charge. Shown so the day's statement can be tied out, never compared against sales.",
    )

    # --- the sales side -----------------------------------------------------
    x70d_total = fields.Monetary(
        string="X70D Tender (H-1)",
        currency_field="currency_id",
        help="Every tender this store rang up on the trading day, cash included, straight from the staged X70D rows.",
    )
    x70d_card_total = fields.Monetary(string="X70D Card", currency_field="currency_id")
    x70d_cash_total = fields.Monetary(
        string="X70D Cash",
        currency_field="currency_id",
        help="Cash tenders of the trading day. The bank does not settle these — they arrive as a deposit, "
        "usually on another date — so a variance of exactly this figure is a till, not a loss.",
    )
    x70d_count = fields.Integer(string="X70D Transactions")

    # --- the comparison -----------------------------------------------------
    variance = fields.Monetary(
        string="Difference",
        currency_field="currency_id",
        help="Gross received less what the store rang up on the trading day. Positive: the bank paid more "
        "than the day's sales. Negative: some of the day's sales have not arrived.",
    )
    variance_bank = fields.Monetary(
        string="Difference (bank)",
        currency_field="currency_id",
        help="Statement amount less X70D tender. Differs from Difference by the acquirer fee.",
    )
    is_balanced = fields.Boolean(string="Tallies")
    kanban_color = fields.Integer(string="Colour")

    # --- the ledger side, which is the one that gates --------------------
    ledger_open_total = fields.Monetary(
        string="Receivable Open",
        currency_field="currency_id",
        help="What this store's non-cash POS receivable still held open on the "
        "trading day when the run was computed. Not the same population as "
        "X70D: the file is missing for some stores and days, while the "
        "receivable is what the POS actually booked.",
    )
    proof_state = fields.Selection(
        [
            ("exact", "Ties"),
            ("subset", "Ties on one combination"),
            ("over", "More money than receivable"),
            ("under", "Less money than receivable"),
            ("no_sales", "No sales for that day"),
            ("blocked", "Unreadable line on the same bank day"),
        ],
        string="Proof",
        help="Whether this store-day may be booked without anyone reading it. Only a tie to the rupiah counts.",
    )
    proof_variance = fields.Monetary(
        string="Difference (ledger)",
        currency_field="currency_id",
        help="Gross received less the receivable still open on the trading day. "
        "This is the figure the proof weighs — Difference compares against X70D "
        "instead, and the two have different populations.",
    )

    x70d_txn_ids = fields.Many2many(
        "levis.pos.x70d.txn",
        string="X70D Transactions (H-1)",
        compute="_compute_x70d_txn_ids",
        help="The store's own transactions of the trading day, read live from the staged rows "
        "rather than copied — a re-imported day is right here the moment it is right there.",
    )

    display_name = fields.Char(compute="_compute_display_name")

    _store_day_uniq = models.Constraint(
        "unique(run_id, settlement_date, analytic_account_id)",
        "That store already has a settlement day on this run.",
    )

    @api.depends("analytic_account_id", "trading_date")
    def _compute_x70d_txn_ids(self):
        Txn = self.env["levis.pos.x70d.txn"]
        for row in self:
            row.x70d_txn_ids = (
                Txn.search(
                    [
                        ("analytic_account_id", "=", row.analytic_account_id.id),
                        ("trans_date", "=", row.trading_date),
                    ]
                )
                if row.analytic_account_id and row.trading_date
                else Txn
            )

    @api.depends("analytic_account_id", "settlement_date")
    def _compute_display_name(self):
        for row in self:
            store = row.analytic_account_id.name or _("Unknown store")
            row.display_name = "%s — %s" % (store, row.settlement_date or "")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    @api.model
    def _rebuild_for_run(self, run):
        """Recreate this run's store-days from its lines. Books nothing.

        Lines with no store are skipped rather than bucketed under a blank: a
        settlement whose merchant id is unmapped belongs to no shop yet, and
        inventing a row for it would put money against a store nobody chose.
        Those lines are already reported as ``unmapped`` on the run and on the
        day.
        """
        run.ensure_one()
        self.search([("run_id", "=", run.id)]).unlink()
        buckets = {}
        for line in run.line_ids:
            if not (line.settlement_date and line.analytic_account_id):
                continue
            key = (line.settlement_date, line.analytic_account_id.id)
            buckets.setdefault(key, self.env["levis.pos.clearing.line"])
            buckets[key] |= line
        if not buckets:
            return self.browse()

        lag = run.config_id.settlement_lag_days or 0
        created = self.create(
            [
                {
                    "run_id": run.id,
                    "settlement_date": settlement_date,
                    "analytic_account_id": store_id,
                    "trading_date": settlement_date - timedelta(days=lag),
                }
                for (settlement_date, store_id) in sorted(buckets)
            ]
        )
        for row in created:
            buckets[(row.settlement_date, row.analytic_account_id.id)].write({"store_day_id": row.id})
        created._recompute_figures()
        return created

    def _x70d_rows(self):
        """``{(store id, trading day): [(tender, ref, amount)]}`` for this recordset.

        One query for the whole set, through the matcher's own reader, so the
        reconciliation and the receipt matching can never disagree about what a
        trading day contains.
        """
        rows_wanted = self.filtered(lambda row: row.analytic_account_id and row.trading_date)
        if not rows_wanted:
            return {}
        dates = rows_wanted.mapped("trading_date")
        return self.env["levis.pos.clearing.alloc"]._x24_rows(
            set(rows_wanted.mapped("analytic_account_id").ids),
            min(dates),
            max(dates),
            rows_wanted.company_id[:1] or self.env.company,
        )

    def _recompute_figures(self):
        """Roll the bank lines up, read the trading day, and compare the two."""
        Tender = self.env["levis.pos.clearing.store.day.tender"]
        rows_by_key = self._x70d_rows()
        Tender.search([("store_day_id", "in", self.ids)]).unlink()
        tender_vals = []
        for row in self:
            lines = row.line_ids
            # Money in for this shop is a settlement or a cash deposit. A sweep
            # to the main bank and a bank charge are the same money leaving
            # again, and their ``gross`` is a sign artefact of the narrative
            # reader — counting either would compare a transfer with a sale.
            settling = lines.filtered(lambda line: line.kind in _SETTLING_KINDS)
            day_rows = rows_by_key.get((row.analytic_account_id.id, row.trading_date), ())
            tolerance = row.run_id.config_id._match_tolerance(sum(settling.mapped("gross")) or 0.0)

            by_tender = {}
            for tender, _ref, amount in day_rows:
                bucket = by_tender.setdefault(tender, {"amount": 0.0, "count": 0})
                bucket["amount"] = round(bucket["amount"] + amount, 2)
                bucket["count"] += 1
            booked = row._booked_by_tender()

            values = {
                "line_count": len(settling),
                # Cash deposits are counted alongside card settlements on
                # purpose: the comparison includes the day's cash tenders, so
                # the money side has to include the till reaching the bank.
                "statement_total": sum(settling.mapped("statement_amount")),
                "mdr_total": sum(settling.mapped("mdr")),
                "gross_total": sum(settling.mapped("gross")),
                "allocated_total": sum(settling.mapped("allocated")),
                "short_total": sum(abs(line.short_amount) for line in settling),
                "other_count": len(lines - settling),
                "other_total": sum((lines - settling).mapped("statement_amount")),
                "x70d_total": round(sum(bucket["amount"] for bucket in by_tender.values()), 2),
                "x70d_card_total": round(
                    sum(bucket["amount"] for tender, bucket in by_tender.items() if tender not in _CASH_TENDERS), 2
                ),
                "x70d_cash_total": round(
                    sum(bucket["amount"] for tender, bucket in by_tender.items() if tender in _CASH_TENDERS), 2
                ),
                "x70d_count": len(day_rows),
            }
            values["variance"] = round(values["gross_total"] - values["x70d_total"], 2)
            values["variance_bank"] = round(values["statement_total"] - values["x70d_total"], 2)
            values["is_balanced"] = abs(values["variance"]) <= max(tolerance, _EPS)
            values["kanban_color"] = 10 if values["is_balanced"] else (3 if values["x70d_count"] else 1)
            # The proof is not recomputed here — it was taken before allocation
            # spent the residual it reads, and every settlement of the group
            # carries the same verdict. Copying it up is all a projection may do.
            proofs = set(settling.mapped("proof_state")) - {False}
            values["proof_state"] = proofs.pop() if len(proofs) == 1 else False
            values["ledger_open_total"] = max(settling.mapped("proof_ledger_total") or [0.0])
            values["proof_variance"] = round(values["gross_total"] - values["ledger_open_total"], 2)
            row.write(values)

            for tender in sorted(set(by_tender) | set(booked)):
                bucket = by_tender.get(tender, {"amount": 0.0, "count": 0})
                tender_vals.append(
                    {
                        "store_day_id": row.id,
                        "tender": tender,
                        "x70d_amount": bucket["amount"],
                        "x70d_count": bucket["count"],
                        "booked_amount": round(booked.get(tender, 0.0), 2),
                        "variance": round(bucket["amount"] - booked.get(tender, 0.0), 2),
                    }
                )
        if tender_vals:
            Tender.create(tender_vals)
        return True

    def _booked_by_tender(self):
        """``{tender: amount}`` this store-day's settlements credited.

        Read off the receivable account name, which is where the tender survives
        — ``POS Receivable - OFFLINE_VISA`` and nothing else says Visa. This is
        the allocation's claim about the day; the X70D column beside it is what
        the store actually rang up, and the two disagreeing is precisely the
        thing this screen exists to show.
        """
        self.ensure_one()
        Alloc = self.env["levis.pos.clearing.alloc"]
        booked = {}
        for line in self.line_ids:
            for alloc in line.alloc_ids:
                tender = Alloc._x24_tender_of_account(alloc.account_id)
                if not tender:
                    continue
                booked[tender] = round(booked.get(tender, 0.0) + alloc.amount, 2)
        return booked

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
            "name": _("Statement lines — %s", self.display_name),
            "res_model": "levis.pos.clearing.line",
            "view_mode": "list,form",
            "domain": [("store_day_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_open_x70d(self):
        """The store's transactions of the trading day, as the matcher reads them."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("X70D transactions — %s", self.display_name),
            "res_model": "levis.pos.x70d.txn",
            "view_mode": "list",
            "domain": [
                ("analytic_account_id", "=", self.analytic_account_id.id),
                ("trans_date", "=", self.trading_date),
            ],
            "context": {"create": False, "search_default_group_tender": 1},
        }

    def action_open_matcher(self):
        """Both lists on one screen: the bank's credits and the till's receipts."""
        self.ensure_one()
        wizard = self.env["levis.clearing.match"]._build_for(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Match — %s", self.display_name),
            "res_model": "levis.clearing.match",
            "res_id": wizard.id,
            "view_mode": "form",
            # A full page, not a dialog: two lists of a day's transactions do not
            # fit in a modal, and this is read as much as it is clicked.
            "target": "current",
        }

    def action_clear(self):
        """Prepare a clearing for these store-days, and stop at the summary.

        A narrowed run rather than anything new: ``scope_analytic_ids`` keeps it
        to these stores and the dates keep it to these days, so every line
        outside is listed with its reason and left exactly as it was found. What
        the allocation can explain is booked; a store-day that does not tie
        settles what it can and leaves the remainder on suspense, which is what
        the wide run has always done with a short line.

        It computes and stops. Prepare Entries and Post & Reconcile stay where
        they are — a person who has read the summary.
        """
        if not self:
            raise UserError(_("Pick at least one store settlement day."))
        companies = self.mapped("company_id")
        if len(companies) > 1:
            raise UserError(_("Those store days belong to different companies."))
        dates = [row.settlement_date for row in self if row.settlement_date]
        if not dates:
            raise UserError(_("Those store days carry no settlement date."))
        config = self.env["levis.clearing.config"]._get(companies)
        run = self.env["levis.pos.clearing"].create(
            {
                "company_id": companies.id,
                "date_from": min(dates),
                "date_to": max(dates),
                "journal_id": config.journal_id.id,
                "bank_journal_ids": [Command.set(config.bank_journal_ids.ids)],
                "scope_analytic_ids": [Command.set(self.mapped("analytic_account_id").ids)],
            }
        )
        run.action_compute()
        return {
            "type": "ir.actions.act_window",
            "name": _("Clearing for %s store(s)", len(self.mapped("analytic_account_id"))),
            "res_model": "levis.pos.clearing",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_run(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "levis.pos.clearing",
            "res_id": self.run_id.id,
            "view_mode": "form",
        }


class LevisPosClearingStoreDayTender(models.Model):
    _name = "levis.pos.clearing.store.day.tender"
    _description = "POS Clearing Store Day Tender"
    _order = "store_day_id, tender"

    store_day_id = fields.Many2one("levis.pos.clearing.store.day", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="store_day_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="store_day_id.currency_id")
    tender = fields.Char(required=True)
    x70d_amount = fields.Monetary(string="X70D (H-1)", currency_field="currency_id")
    x70d_count = fields.Integer(string="Transactions")
    booked_amount = fields.Monetary(
        string="Cleared",
        currency_field="currency_id",
        help="What this run credited to that tender's receivable for this store and settlement date.",
    )
    variance = fields.Monetary(
        string="Difference",
        currency_field="currency_id",
        help="What the store rang up on that tender, less what the settlement was booked against. "
        "A pair of equal and opposite differences is one settlement booked to the wrong tender.",
    )
