# -*- coding: utf-8 -*-
"""Monthly POS clearing: settle the per-tender receivables against the bank.

A Levi's store sells on cards, QRIS and cash. The POS session books one
receivable per tender (``1106000101``..``110``); days later the acquirer pays,
net of its fee, and the bank statement lands on the suspense account. Clearing
means matching the two:

    Dr Bank Suspense        (what the bank actually paid)
    Dr MDR Expense          (what the acquirer kept)
        Cr POS Receivable   (per tender, gross)

Until now this was three host scripts hardcoded to July 2026, driven by the
client's EBR workbook. Two things make it a feature instead:

* **The bank narrative already carries gross and fee** per settlement
  (``TGH``/``DDR``, ``AMT``/``MDR``), so no workbook is needed and the fee is
  exact per settlement instead of a monthly figure spread pro-rata.
* **Which tender account to credit cannot be read anywhere.** One card MID
  covers Visa, Mastercard, JCB and Amex alike, and ``levis.mdr.bin`` is empty. So
  the split is *discovered*: the settlement consumes that store's open receivable
  debits for the trading day, largest residual first. Odoo's own open lines are
  the source of truth, which is also why anything left over is reported as a
  shortfall rather than forced somewhere.

Three stages, deliberately hard-separated because money moves:

1. ``action_compute`` — builds a summary and **creates nothing**. No journal
   entry, no write to a statement line or a receivable.
2. ``action_generate_moves`` — creates DRAFT entries for the accountant to read.
3. ``action_post`` — posts them and reconciles each credit leg with exactly the
   receivable lines its allocation names.

That last point matters. The scripts reconciled per account across all stores,
which let one store's excess absorb another's shortfall and made per-store
residuals unreadable afterwards. Persisting the allocation (``levis.pos.clearing.alloc``)
is what allows exact pairing instead.

Nothing here is ever automatic: there is no cron, ``action_compute`` does not
generate, and ``action_generate_moves`` does not post.
"""

import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Half a cent: below this, a difference is float noise, not money.
# Channels whose money demonstrably did not arrive as cash.
_CARD_CHANNELS = ("debit", "credit", "qris")

_EPS = 0.005

# Above this many identical findings, the diagnostic is aggregated into one row
# that states the count — never silently shortened.
_DIAG_DETAIL_CAP = 200

_BLOCKS = [
    ("a", "A Settlement"),
    ("b", "B Prior-Month AR"),
    ("c", "C Sweep & Charges"),
]

_DIAG_KINDS = [
    ("missing_day", "Missing statement day"),
    ("no_statement", "Bank journal has no statement lines"),
    ("no_analytic", "Posted receivable without Operating Unit"),
    ("unmapped_mid", "Unmapped MID / terminal"),
    ("unmapped_cash", "Unattributed cash deposit"),
    ("unparsed", "Unparsed narrative"),
    ("amount_mismatch", "Narrative disagrees with the money"),
    ("short", "Short of open POS receivable"),
    ("unsettled", "POS receivable left open"),
    ("consumed", "Statement line already used by another run"),
    ("sweep_double", "Sweep destination is also a statement source"),
    ("no_cash_account", "No CASH tender receivable configured"),
    ("overlap", "Another run covers part of this period"),
]

# Statement kinds that settle a receivable (block A/B).
_SETTLING_KINDS = ("settlement", "cash_deposit")
# Statement kinds that only move money between the bank's own accounts (block C).
_BANK_KINDS = ("sweep", "charge")


class LevisPosClearing(models.Model):
    _name = "levis.pos.clearing"
    _description = "Monthly POS Clearing"
    _order = "date_to desc, id desc"

    name = fields.Char(default="/", copy=False, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, readonly=True)
    config_id = fields.Many2one(
        "levis.clearing.config",
        string="Accounts",
        compute="_compute_config_id",
        store=True,
        readonly=True,
    )
    date_from = fields.Date(required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(required=True, default=lambda self: self._default_date_to())
    journal_id = fields.Many2one(
        "account.journal",
        string="Clearing Journal",
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        default=lambda self: self._default_journal(),
    )
    bank_journal_ids = fields.Many2many(
        "account.journal",
        "levis_pos_clearing_bank_journal_rel",
        "clearing_id",
        "journal_id",
        string="Bank Journals",
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        default=lambda self: self._default_bank_journals(),
    )
    period_ref = fields.Char(compute="_compute_period_ref", store=True, readonly=True)
    ar_fallback = fields.Boolean(
        string="Allow Prior-Month AR",
        default=True,
        help="When a store's POS receivable for the day is exhausted, let the "
        "remainder settle an open Trade Receivable instead (block B). Switch off "
        "to report the remainder as a shortfall.",
    )
    ignore_warnings = fields.Boolean(
        default=False,
        copy=False,
        help="Generate the entries even though unparsed lines, unmapped MIDs or "
        "amount mismatches remain. Recorded so the decision stays auditable.",
    )

    line_ids = fields.One2many("levis.pos.clearing.line", "run_id", copy=False)
    diag_ids = fields.One2many("levis.pos.clearing.diag", "run_id", copy=False)
    move_ids = fields.One2many("account.move", "levis_pos_clearing_id", readonly=True, copy=False)
    move_count = fields.Integer(compute="_compute_move_count")
    draft_move_count = fields.Integer(compute="_compute_move_count")
    posted_move_count = fields.Integer(compute="_compute_move_count")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("computed", "Computed"),
            ("generated", "Generated"),
            ("posted", "Posted"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        copy=False,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    # --- summary -------------------------------------------------------
    total_gross = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_mdr = fields.Monetary(compute="_compute_totals", currency_field="currency_id", string="Total MDR")
    total_cash_in = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_allocated = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_short = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    block_a_total = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    block_b_total = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    block_c_total = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    unparsed_count = fields.Integer(compute="_compute_totals")
    unparsed_amount = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    unmapped_count = fields.Integer(compute="_compute_totals")
    unmapped_amount = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    short_count = fields.Integer(compute="_compute_totals")
    mismatch_count = fields.Integer(compute="_compute_totals")
    consumed_elsewhere_count = fields.Integer(compute="_compute_totals")
    missing_day_count = fields.Integer(compute="_compute_totals")
    no_analytic_count = fields.Integer(compute="_compute_totals")
    no_analytic_amount = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    derived_date_count = fields.Integer(compute="_compute_totals")
    warning_text = fields.Text(readonly=True, copy=False)

    # --- before / after ------------------------------------------------
    bal_suspense_before = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_suspense_after_sim = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_suspense_after_actual = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_mdr_before = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_mdr_after_sim = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_mdr_after_actual = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_ar_before = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_ar_after_sim = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    bal_ar_after_actual = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    posrec_open_before = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    posrec_open_after_sim = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    posrec_open_after_actual = fields.Monetary(readonly=True, copy=False, currency_field="currency_id")
    posrec_lines_before = fields.Integer(readonly=True, copy=False)
    posrec_lines_after_actual = fields.Integer(readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return (today.replace(day=1) - timedelta(days=1)).replace(day=1)

    @api.model
    def _default_date_to(self):
        return fields.Date.context_today(self).replace(day=1) - timedelta(days=1)

    @api.model
    def _default_journal(self):
        config = self.env["levis.clearing.config"].sudo().search([("company_id", "=", self.env.company.id)], limit=1)
        if config.journal_id:
            return config.journal_id
        Journal = self.env["account.journal"]
        domain = [("company_id", "=", self.env.company.id)]
        return Journal.search(domain + [("code", "=", "GLJV")], limit=1) or Journal.search(
            domain + [("type", "=", "general")], limit=1
        )

    @api.model
    def _default_bank_journals(self):
        config = self.env["levis.clearing.config"].sudo().search([("company_id", "=", self.env.company.id)], limit=1)
        return config.bank_journal_ids.ids

    @api.depends("company_id")
    def _compute_config_id(self):
        Config = self.env["levis.clearing.config"].sudo()
        for run in self:
            run.config_id = Config.search([("company_id", "=", run.company_id.id)], limit=1)

    @api.depends("date_from", "date_to")
    def _compute_period_ref(self):
        for run in self:
            if not (run.date_from and run.date_to):
                run.period_ref = False
                continue
            whole_month = (
                run.date_from.day == 1
                and run.date_from.year == run.date_to.year
                and run.date_from.month == run.date_to.month
                and (run.date_to + timedelta(days=1)).month != run.date_to.month
            )
            if whole_month:
                run.period_ref = "POSCLR-%s" % run.date_from.strftime("%Y-%m")
            else:
                run.period_ref = "POSCLR-%s-%s" % (
                    run.date_from.strftime("%Y%m%d"),
                    run.date_to.strftime("%Y%m%d"),
                )

    # Without the depends these stay at whatever they were first read as — posting
    # the entries would leave "posted: 0" on screen and the header buttons stale.
    @api.depends("move_ids", "move_ids.state")
    def _compute_move_count(self):
        for run in self:
            run.move_count = len(run.move_ids)
            run.draft_move_count = len(run.move_ids.filtered(lambda m: m.state == "draft"))
            run.posted_move_count = len(run.move_ids.filtered(lambda m: m.state == "posted"))

    @api.depends(
        "line_ids.gross",
        "line_ids.mdr",
        "line_ids.allocated",
        "line_ids.short_amount",
        "line_ids.state",
        "line_ids.block",
        "line_ids.statement_amount",
        "line_ids.trans_date_is_derived",
        "diag_ids.kind",
        "diag_ids.count",
        "diag_ids.amount",
    )
    def _compute_totals(self):
        for run in self:
            lines = run.line_ids
            settling = lines.filtered(lambda line: line.kind in _SETTLING_KINDS)
            run.total_gross = sum(settling.mapped("gross"))
            run.total_mdr = sum(settling.mapped("mdr"))
            run.total_cash_in = sum(settling.mapped("cash_in"))
            run.total_allocated = sum(lines.mapped("allocated"))
            run.total_short = sum(lines.mapped("short_amount"))
            run.block_a_total = sum(lines.filtered(lambda line: line.block == "a").mapped("allocated"))
            run.block_b_total = sum(lines.filtered(lambda line: line.block == "b").mapped("allocated"))
            run.block_c_total = sum(
                abs(amount) for amount in lines.filtered(lambda line: line.block == "c").mapped("statement_amount")
            )
            unparsed = lines.filtered(lambda line: line.state == "unparsed")
            run.unparsed_count = len(unparsed)
            run.unparsed_amount = sum(unparsed.mapped("statement_amount"))
            unmapped = lines.filtered(lambda line: line.state == "unmapped")
            run.unmapped_count = len(unmapped)
            run.unmapped_amount = sum(unmapped.mapped("statement_amount"))
            run.short_count = len(lines.filtered(lambda line: line.short_amount > _EPS))
            run.mismatch_count = len(lines.filtered(lambda line: abs(line.mismatch_amount) > _EPS))
            run.derived_date_count = len(lines.filtered("trans_date_is_derived"))
            diags = run.diag_ids
            run.consumed_elsewhere_count = sum(diags.filtered(lambda d: d.kind == "consumed").mapped("count"))
            run.missing_day_count = len(diags.filtered(lambda d: d.kind == "missing_day"))
            no_analytic = diags.filtered(lambda d: d.kind == "no_analytic")
            run.no_analytic_count = sum(no_analytic.mapped("count")) or len(no_analytic)
            run.no_analytic_amount = sum(no_analytic.mapped("amount"))

    @api.constrains("date_from", "date_to")
    def _check_period(self):
        for run in self:
            if run.date_from and run.date_to and run.date_to < run.date_from:
                raise UserError(_("The end date precedes the start date."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("levis.pos.clearing") or "/"
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Period policy — the same contract as levis.categ.reclass
    # ------------------------------------------------------------------
    def _lock_date(self):
        self.ensure_one()
        dates = [d for d in (self.company_id.fiscalyear_lock_date, self.company_id.hard_lock_date) if d]
        return max(dates) if dates else None

    def _assert_period_open(self):
        """Never lifts a lock date — a closed period is simply refused."""
        self.ensure_one()
        lock = self._lock_date()
        if lock and self.date_from <= lock:
            raise UserError(
                _(
                    "The period starts on %(start)s but the books are locked up to "
                    "%(lock)s. Clearing a reported period would change figures that "
                    "have already been filed. Move the period, or have the lock "
                    "date changed deliberately.",
                    start=self.date_from,
                    lock=lock,
                )
            )
        return True

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------
    def _bank_journals(self):
        self.ensure_one()
        return self.bank_journal_ids or self.config_id.bank_journal_ids

    def _statement_lines(self):
        """Posted statement lines in scope, oldest first.

        ``date`` is usable in a domain even though ``account.bank.statement.line``
        has no such SQL column — it is delegated from ``account.move``. Raw SQL
        must join ``move_id`` instead.
        """
        self.ensure_one()
        lines = self.env["account.bank.statement.line"].search(
            [
                ("journal_id", "in", self._bank_journals().ids),
                ("company_id", "=", self.company_id.id),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("move_id.state", "=", "posted"),
            ]
        )
        return lines.sorted(key=lambda sl: (sl.date, sl.journal_id.id, sl.id))

    def _promised_elsewhere(self):
        """Amounts other DRAFT-generating runs have already earmarked per AML.

        A posted run needs no accounting for here: its reconciliation has already
        reduced ``amount_residual``. A generated-but-unposted one has not, so its
        promises must be subtracted or two runs would spend the same money.
        """
        self.ensure_one()
        allocs = self.env["levis.pos.clearing.alloc"].search(
            [
                ("line_id.run_id.company_id", "=", self.company_id.id),
                ("line_id.run_id.state", "=", "generated"),
                ("line_id.run_id", "!=", self.id),
            ]
        )
        promised = defaultdict(float)
        for alloc in allocs:
            promised[alloc.source_aml_id.id] += alloc.amount
        return promised

    def _open_pool(self, accounts, date_from, date_to, promised):
        """``{(analytic_id, date): [aml]}`` plus ``{aml_id: unallocated}``.

        Keyed on the analytic *id*, not its name: the host script round-tripped
        through the name and broke whenever an Operating Unit was renamed.
        """
        self.ensure_one()
        if not accounts:
            return {}, {}
        amls = self.env["account.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id", "in", accounts.ids),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("debit", ">", 0),
                ("reconciled", "=", False),
            ]
        )
        pool = defaultdict(list)
        residual = {}
        for aml in amls:
            remaining = round(aml.amount_residual - promised.get(aml.id, 0.0), 2)
            if remaining <= _EPS:
                continue
            analytic_id = next(iter(aml.analytic_distribution or {}), None)
            analytic_id = int(analytic_id) if analytic_id else False
            pool[(analytic_id, aml.date)].append(aml)
            residual[aml.id] = remaining
        for key in pool:
            pool[key].sort(key=lambda aml: -residual.get(aml.id, 0.0))
        return pool, residual

    def _open_ar_pool(self, promised):
        """Open Trade Receivable debits per store, largest residual first.

        Not keyed by date, unlike the POS pool: a trade receivable is a running
        balance, and the invoice it came from may be months older than anything
        the settlement's date ladder could reach.
        """
        self.ensure_one()
        config = self.config_id
        if not (self.ar_fallback and config.ar_account_id):
            return {}, {}
        amls = self.env["account.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id", "=", config.ar_account_id.id),
                ("date", "<=", self.date_to),
                ("debit", ">", 0),
                ("reconciled", "=", False),
            ]
        )
        pool = defaultdict(list)
        residual = {}
        for aml in amls:
            remaining = round(aml.amount_residual - promised.get(aml.id, 0.0), 2)
            if remaining <= _EPS:
                continue
            analytic_id = next(iter(aml.analytic_distribution or {}), None)
            analytic_id = int(analytic_id) if analytic_id else False
            pool[analytic_id].append(aml)
            residual[aml.id] = remaining
        for key in pool:
            pool[key].sort(key=lambda aml: -residual.get(aml.id, 0.0))
        return pool, residual

    def _allocate_flat(self, pool, residual, analytic_id, amount):
        """Like ``_allocate`` but without a trading-day dimension."""
        taken = []
        left = round(amount, 2)
        for aml in pool.get(analytic_id, ()):
            if left <= _EPS:
                break
            remaining = residual.get(aml.id, 0.0)
            if remaining <= _EPS:
                continue
            take = round(min(left, remaining), 2)
            residual[aml.id] = round(remaining - take, 2)
            taken.append((aml.account_id.id, aml.id, aml.date, take))
            left = round(left - take, 2)
        return taken, round(left, 2)

    def _candidate_dates(self, primary):
        """Trading days a settlement may draw on, best guess first.

        1 484 of July's 2 111 BCA lines carry no transaction date, so the day has
        to be inferred from the settlement lag and then widened. Whichever day is
        actually drawn on is recorded on the allocation row, so an approximation
        stays visible instead of becoming a claim.
        """
        self.ensure_one()
        config = self.config_id
        earliest = self.date_from - timedelta(days=config.lookback_days or 0)
        dates = []
        for offset in range(0, (config.lookback_days or 0) + 2):
            for step in (0,) if offset == 0 else (-offset, offset):
                candidate = primary + timedelta(days=step)
                if earliest <= candidate <= self.date_to and candidate not in dates:
                    dates.append(candidate)
        return dates

    def _allocate(self, pool, residual, analytic_id, dates, amount, only_accounts=None):
        """Spend ``amount`` on open debits, largest residual first.

        Returns ``([(account_id, aml_id, date, amount)], shortfall)``. The greedy
        order is what discovers which tender account a settlement represents; the
        shortfall is reported, never absorbed.

        ``only_accounts`` restricts which tender receivables may be consumed, and
        is passed **only where the tender is certain** — see
        ``_allowed_accounts_for``. Left empty, every configured tender account is
        eligible, which is what a card settlement needs.
        """
        taken = []
        left = round(amount, 2)
        allowed = set(only_accounts.ids) if only_accounts else None
        for date in dates:
            if left <= _EPS:
                break
            for aml in pool.get((analytic_id, date), ()):
                if left <= _EPS:
                    break
                if allowed is not None and aml.account_id.id not in allowed:
                    continue
                remaining = residual.get(aml.id, 0.0)
                if remaining <= _EPS:
                    continue
                take = round(min(left, remaining), 2)
                residual[aml.id] = round(remaining - take, 2)
                taken.append((aml.account_id.id, aml.id, date, take))
                left = round(left - take, 2)
        return taken, round(left, 2)

    def _cash_receivable_account(self):
        """The per-tender receivable a cash deposit settles, or empty.

        Resolved by code from ``ir.config_parameter`` (default ``1106000101``) and
        required to be one of the configured tender accounts, so a typo cannot
        point the restriction at some unrelated account. Deliberately not a new
        field on ``levis.clearing.config``: that would be a column, and a column
        means upgrading every database that shares this addon.
        """
        self.ensure_one()
        code = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("custom_levis_localization.pos_cash_receivable_code", "1106000101")
        )
        company = self.company_id
        return self.config_id.pos_receivable_account_ids.filtered(
            lambda a: (a.with_company(company).code or "") == code
        )[:1]

    def _pool_accounts_for_channel(self, parsed, cash_account):
        """Which tender receivables this settlement is allowed to consume.

        Empty result means "no restriction". The rule is deliberately narrow:
        restrict only where the narrative settles the question outright.

        * **Cash deposit** — certain. The money arrived as a bank transfer of
          takings, so it settles the CASH receivable and nothing else. Letting it
          consume a card receivable clears the wrong account: measured on July
          2026 before this guard, 76.6% of cash-deposit allocations landed on card
          receivables, leaving the real cash receivable open and the card one
          over-cleared.
        * **Card** — genuinely undecidable, and that is the design, not a gap. One
          MID covers Visa, Mastercard, JCB and Amex alike, so the split has to be
          discovered from the open debits.
        * **QRIS** — not narrowed to one account. It looks decidable, but there is
          no evidence that QRIS always lands on one specific tender account here:
          measured over July, QRIS settlements matched debits across SEVEN of the
          ten accounts (102 46%, 106 23%, 105 17%, 108 12%, the rest ~1% each),
          with no concentration at all. Guessing would reintroduce exactly the
          error this fixes.
        * **Card and QRIS still may not touch the CASH receivable**, which is a
          different question from the one above and has a definite answer: the
          account holds takings paid in cash, so card money settling it clears an
          account the customer never used. Over July only 3 of 358 unambiguously
          matched card/QRIS settlements landed there (0.8%, Rp 2.6 m) — small, but
          wrong by construction rather than by measurement, and it hides a real
          cash shortfall behind a card over-clear.

        Note the asymmetry is deliberate: cash is restricted to ONE account
        because its channel is certain, while card/QRIS is merely denied ONE
        account, because which card account it belongs to remains undecidable.
        """
        self.ensure_one()
        if not cash_account:
            return self.env["account.account"]
        if parsed.get("kind") == "cash_deposit":
            return cash_account
        # Positive test on the channels we mean, never "not cash": a narrative
        # that could not be read carries channel "other", and must keep the old
        # unrestricted behaviour rather than being narrowed on a guess.
        if parsed.get("kind") == "settlement" and parsed.get("channel") in _CARD_CHANNELS:
            return self.config_id.pos_receivable_account_ids - cash_account
        return self.env["account.account"]

    # ------------------------------------------------------------------
    # Stage 1 — summary. Creates nothing.
    # ------------------------------------------------------------------
    def action_compute(self):
        for run in self:
            run._compute_one()
        return True

    def _compute_one(self):
        self.ensure_one()
        if self.state in ("generated", "posted"):
            raise UserError(
                _(
                    "%s has already generated its entries. Cancel it first, or start "
                    "a new run — recomputing would silently disagree with the drafts.",
                    self.name,
                )
            )
        config = self.config_id or self.env["levis.clearing.config"]._get(self.company_id)
        config._check_complete()
        self.config_id = config.id
        self.line_ids.unlink()
        self.diag_ids.unlink()
        self.warning_text = False
        self._snapshot_before()

        Narrative = self.env["levis.bank.narrative"]
        MidMap = self.env["levis.bank.mid.map"]
        pos_accounts = config._pos_accounts_sorted()
        promised = self._promised_elsewhere()
        pool, residual = self._open_pool(
            pos_accounts,
            self.date_from - timedelta(days=config.lookback_days or 0),
            self.date_to,
            promised,
        )
        ar_pool, ar_residual = self._open_ar_pool(promised)
        cash_account = self._cash_receivable_account()
        if not cash_account:
            # Say so rather than quietly falling back to consuming any tender:
            # that fallback is the bug this guard exists to prevent.
            diag_config = [
                {
                    "kind": "no_cash_account",
                    "severity": "warning",
                    "count": 1,
                    "message": _(
                        "No CASH tender receivable is configured, so cash deposits may "
                        "clear a card receivable instead. Set the account code in "
                        "custom_levis_localization.pos_cash_receivable_code."
                    ),
                }
            ]
        else:
            diag_config = []

        rules_cache = {}
        line_vals = []
        diag_vals = []
        for statement_line in self._statement_lines():
            journal = statement_line.journal_id
            if journal.id not in rules_cache:
                rules_cache[journal.id] = MidMap._candidates(self.company_id, journal)
            parsed = Narrative.parse(journal, statement_line.payment_ref, statement_line.amount, statement_line.date)
            line_vals.append(
                self._line_from_parsed(
                    statement_line,
                    parsed,
                    rules_cache[journal.id],
                    pool,
                    residual,
                    ar_pool,
                    ar_residual,
                    diag_vals,
                    cash_account,
                )
            )
        self.line_ids = [(0, 0, vals) for vals in line_vals]
        self.diag_ids = [(0, 0, vals) for vals in diag_config + diag_vals]
        self._build_diagnostics(residual)
        self._simulate_balances()
        self.state = "computed"
        return True

    def _line_from_parsed(
        self, statement_line, parsed, rules, pool, residual, ar_pool, ar_residual, diag_vals, cash_account=None
    ):
        """One statement line -> one clearing line, allocations included.

        Every statement line in scope produces a row, whatever happened to it.
        A narrative that could not be read is a visible ``unparsed`` row, not a
        gap in the list.
        """
        self.ensure_one()
        config = self.config_id
        vals = {
            "statement_line_id": statement_line.id,
            "settlement_date": statement_line.date,
            "kind": parsed["kind"],
            "channel": parsed["channel"],
            "mid_key": parsed["mid"],
            "tid_key": parsed["tid"],
            "statement_amount": statement_line.amount,
            "gross": parsed["gross"],
            "mdr": parsed["mdr"],
            "note": parsed.get("note"),
            "alloc_ids": [],
        }
        other_run = statement_line.levis_clearing_run_id
        if other_run and other_run.id != self.id:
            vals.update({"state": "skipped", "block": False})
            vals["note"] = _("Already used by clearing %s.", other_run.name)
            diag_vals.append(
                {
                    "kind": "consumed",
                    "severity": "blocking",
                    "date": statement_line.date,
                    "bank_journal_id": statement_line.journal_id.id,
                    "amount": statement_line.amount,
                    "count": 1,
                    "res_model": "account.bank.statement.line",
                    "res_id": statement_line.id,
                    "message": _("Consumed by %s.", other_run.name),
                }
            )
            return vals

        if parsed["kind"] == "unknown":
            vals.update({"state": "unparsed", "block": False})
            return vals

        if parsed["kind"] == "interest":
            # Bank interest is income, not a clearing item: booking it here would
            # quietly turn a P&L decision into a reconciliation side effect.
            vals.update({"state": "skipped", "block": False})
            vals["note"] = parsed.get("note") or _("Bank interest — book separately.")
            return vals

        if parsed["kind"] in _BANK_KINDS:
            vals.update({"state": "ok", "block": "c"})
            return vals

        # --- a settlement: it must belong to a store ---------------------
        rule = self.env["levis.bank.mid.map"]._resolve(
            self.company_id, statement_line.journal_id, parsed, statement_line.date, candidates=rules
        )
        if not rule:
            vals.update(
                {
                    "state": "unmapped",
                    "block": False,
                    "note": _("No mapping for this MID / terminal / wording."),
                }
            )
            diag_vals.append(
                {
                    "kind": "unmapped_mid" if (parsed["mid"] or parsed["tid"]) else "unmapped_cash",
                    "severity": "blocking",
                    "date": statement_line.date,
                    "bank_journal_id": statement_line.journal_id.id,
                    "amount": statement_line.amount,
                    "count": 1,
                    "res_model": "account.bank.statement.line",
                    "res_id": statement_line.id,
                    "message": parsed["mid"] or parsed["tid"] or (parsed["keyword"] or "")[:120],
                }
            )
            return vals

        vals["map_id"] = rule.id
        vals["analytic_account_id"] = rule.analytic_account_id.id
        exact = parsed["confidence"] == "exact" and parsed["trans_date"]
        primary = (
            parsed["trans_date"] if exact else statement_line.date - timedelta(days=config.settlement_lag_days or 0)
        )
        vals["trans_date"] = primary
        vals["trans_date_is_derived"] = not exact
        dates = self._candidate_dates(primary)

        only = self._pool_accounts_for_channel(parsed, cash_account)
        taken, left = self._allocate(
            pool, residual, rule.analytic_account_id.id, dates, parsed["gross"], only_accounts=only
        )
        block = "a"
        if left > _EPS and ar_pool:
            ar_taken, left = self._allocate_flat(ar_pool, ar_residual, rule.analytic_account_id.id, left)
            if ar_taken and not taken:
                # Nothing of this store's POS receivable was open: the settlement is
                # collecting an older trade receivable, not this month's sales.
                block = "b"
            taken += ar_taken

        # The fee is only earned on what was actually settled: crediting the full
        # MDR against a partial allocation would overstate the expense.
        ratio = (sum(item[3] for item in taken) / parsed["gross"]) if parsed["gross"] else 0.0
        vals["mdr_booked"] = round(parsed["mdr"] * ratio, 2)
        vals["block"] = block
        if abs(round(statement_line.amount - (parsed["gross"] - parsed["mdr"]), 2)) > _EPS:
            vals["state"] = "mismatch"
        elif left > _EPS:
            vals["state"] = "short"
        else:
            vals["state"] = "ok"
        vals["alloc_ids"] = [
            (0, 0, {"account_id": account_id, "source_aml_id": aml_id, "source_date": date, "amount": amount})
            for account_id, aml_id, date, amount in taken
        ]
        if left > _EPS:
            diag_vals.append(
                {
                    "kind": "short",
                    "severity": "warning",
                    "date": statement_line.date,
                    "bank_journal_id": statement_line.journal_id.id,
                    "analytic_account_id": rule.analytic_account_id.id,
                    "amount": left,
                    "count": 1,
                    "res_model": "account.bank.statement.line",
                    "res_id": statement_line.id,
                    "message": _(
                        "No open receivable left for %(store)s around %(date)s.",
                        store=rule.analytic_account_id.display_name,
                        date=primary,
                    ),
                }
            )
        return vals

    # ------------------------------------------------------------------
    # Diagnostics — findings, never repairs
    # ------------------------------------------------------------------
    def _build_diagnostics(self, residual):
        self.ensure_one()
        vals = []
        vals += self._diag_mismatch()
        vals += self._diag_missing_days()
        vals += self._diag_no_analytic()
        vals += self._diag_unsettled(residual)
        vals += self._diag_sweep_double()
        vals += self._diag_overlap()
        if vals:
            self.diag_ids = [(0, 0, item) for item in vals]
        return True

    def _diag_mismatch(self):
        out = []
        for line in self.line_ids:
            if line.kind not in _SETTLING_KINDS or abs(line.mismatch_amount) <= _EPS:
                continue
            out.append(
                {
                    "kind": "amount_mismatch",
                    "severity": "blocking",
                    "date": line.settlement_date,
                    "bank_journal_id": line.bank_journal_id.id,
                    "amount": line.mismatch_amount,
                    "count": 1,
                    "res_model": "account.bank.statement.line",
                    "res_id": line.statement_line_id.id,
                    "message": _(
                        "Narrative says %(net)s, the bank moved %(amount)s.",
                        net=line.cash_in,
                        amount=line.statement_amount,
                    ),
                }
            )
        return out

    def _diag_missing_days(self):
        """Interior gaps only.

        A weekend has no settlements anywhere, so flagging every empty date would
        bury the real finding. What matters is a day *between* two days that do
        have lines — that is an import that stopped halfway.
        """
        self.ensure_one()
        out = []
        by_journal = defaultdict(set)
        for line in self.line_ids:
            by_journal[line.bank_journal_id].add(line.settlement_date)
        for journal in self._bank_journals():
            dates = by_journal.get(journal)
            if not dates:
                out.append(
                    {
                        "kind": "no_statement",
                        "severity": "warning",
                        "bank_journal_id": journal.id,
                        "message": _("No statement lines imported for this period."),
                        "count": 1,
                    }
                )
                continue
            day = min(dates)
            while day <= max(dates):
                if day not in dates:
                    out.append(
                        {
                            "kind": "missing_day",
                            "severity": "warning",
                            "date": day,
                            "bank_journal_id": journal.id,
                            "message": _("No statement line on this date, though surrounding days have some."),
                            "count": 1,
                        }
                    )
                day += timedelta(days=1)
        return out

    def _diag_no_analytic(self):
        """Posted receivables with no Operating Unit — listed, not patched.

        These can never be allocated (the pool is keyed by store), so they would
        otherwise show up only as an unexplained shortfall.
        """
        self.ensure_one()
        config = self.config_id
        amls = self.env["account.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id", "in", config.pos_receivable_account_ids.ids),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("debit", ">", 0),
                ("reconciled", "=", False),
            ]
        )
        orphans = amls.filtered(lambda aml: not aml.analytic_distribution)
        if not orphans:
            return []
        if len(orphans) > _DIAG_DETAIL_CAP:
            # One row per line would drown the list. Say so instead of truncating
            # quietly, and give the total so the size of the problem is still visible.
            return [
                {
                    "kind": "no_analytic",
                    "severity": "warning",
                    "amount": round(sum(orphans.mapped("amount_residual")), 2),
                    "count": len(orphans),
                    "message": _(
                        "%(count)s posted POS receivable lines carry no Operating Unit, so "
                        "no settlement can reach them. Too many to list individually — "
                        "filter the journal items on an empty Analytic Distribution.",
                        count=len(orphans),
                    ),
                }
            ]
        return [
            {
                "kind": "no_analytic",
                "severity": "warning",
                "date": aml.date,
                "amount": aml.amount_residual,
                "count": 1,
                "res_model": "account.move.line",
                "res_id": aml.id,
                "message": _(
                    "%(account)s has no Operating Unit, so no settlement can reach it.",
                    account=aml.account_id.code,
                ),
            }
            for aml in orphans
        ]

    def _diag_unsettled(self, residual):
        """What stays open after this run — expected at a month boundary."""
        self.ensure_one()
        left = sum(value for value in residual.values() if value > _EPS)
        if left <= _EPS:
            return []
        return [
            {
                "kind": "unsettled",
                "severity": "info",
                "amount": left,
                "count": sum(1 for value in residual.values() if value > _EPS),
                "message": _(
                    "POS receivable still open after this clearing. Sales on the last "
                    "trading days settle next month and are cleared by the next run."
                ),
            }
        ]

    def _diag_sweep_double(self):
        """The sweep destination must not also be a statement source.

        Block C debits the destination account directly. If that account's own
        journal also imports statements, both sides would hit it and the balance
        would double.
        """
        self.ensure_one()
        config = self.config_id
        if not config.sweep_account_id:
            return []
        clashing = self._bank_journals().filtered(lambda j: j.default_account_id == config.sweep_account_id)
        out = []
        for journal in clashing:
            if any(line.bank_journal_id == journal for line in self.line_ids):
                out.append(
                    {
                        "kind": "sweep_double",
                        "severity": "blocking",
                        "bank_journal_id": journal.id,
                        "count": 1,
                        "message": _(
                            "%(journal)s posts to the sweep destination %(account)s and also "
                            "imports statements in this period. Booking block C would count "
                            "the sweep twice.",
                            journal=journal.code,
                            account=config.sweep_account_id.code,
                        ),
                    }
                )
        return out

    def _diag_overlap(self):
        self.ensure_one()
        others = self.search(
            [
                ("id", "!=", self.id),
                ("company_id", "=", self.company_id.id),
                ("state", "not in", ("cancel", "draft")),
                ("date_from", "<=", self.date_to),
                ("date_to", ">=", self.date_from),
            ]
        )
        return [
            {
                "kind": "overlap",
                "severity": "warning",
                "count": 1,
                "res_model": "levis.pos.clearing",
                "res_id": other.id,
                "message": _(
                    "%(name)s covers %(start)s..%(end)s.", name=other.name, start=other.date_from, end=other.date_to
                ),
            }
            for other in others
        ]

    # ------------------------------------------------------------------
    # Balances
    # ------------------------------------------------------------------
    def _balance(self, account, upto):
        self.ensure_one()
        if not account:
            return 0.0
        groups = self.env["account.move.line"]._read_group(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id", "in", account.ids),
                ("date", "<=", upto),
            ],
            [],
            ["balance:sum"],
        )
        return round(groups[0][0] or 0.0, 2) if groups else 0.0

    def _posrec_open(self):
        self.ensure_one()
        amls = self.env["account.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id", "in", self.config_id.pos_receivable_account_ids.ids),
                ("date", ">=", self.date_from - timedelta(days=self.config_id.lookback_days or 0)),
                ("date", "<=", self.date_to),
                ("reconciled", "=", False),
            ]
        )
        return round(sum(amls.mapped("amount_residual")), 2), len(amls)

    def _snapshot_before(self):
        self.ensure_one()
        config = self.config_id
        open_amount, open_lines = self._posrec_open()
        self.write(
            {
                "bal_suspense_before": self._balance(config.suspense_account_id, self.date_to),
                "bal_mdr_before": self._balance(config.mdr_account_id, self.date_to),
                "bal_ar_before": self._balance(config.ar_account_id, self.date_to),
                "posrec_open_before": open_amount,
                "posrec_lines_before": open_lines,
                "bal_suspense_after_sim": 0.0,
                "bal_mdr_after_sim": 0.0,
                "bal_ar_after_sim": 0.0,
                "posrec_open_after_sim": 0.0,
                "bal_suspense_after_actual": 0.0,
                "bal_mdr_after_actual": 0.0,
                "bal_ar_after_actual": 0.0,
                "posrec_open_after_actual": 0.0,
                "posrec_lines_after_actual": 0,
            }
        )
        return True

    def _simulate_balances(self):
        """What the three control accounts become if these entries are posted."""
        self.ensure_one()
        config = self.config_id
        suspense_delta = mdr_delta = ar_delta = posrec_delta = 0.0
        for line in self.line_ids:
            if line.block == "c":
                suspense_delta += line.statement_amount
                continue
            if line.block not in ("a", "b"):
                continue
            allocated = line.allocated
            if allocated <= _EPS:
                continue
            suspense_delta += allocated - line.mdr_booked
            mdr_delta += line.mdr_booked
            for alloc in line.alloc_ids:
                if alloc.account_id == config.ar_account_id:
                    ar_delta -= alloc.amount
                else:
                    posrec_delta -= alloc.amount
        self.write(
            {
                "bal_suspense_after_sim": round(self.bal_suspense_before + suspense_delta, 2),
                "bal_mdr_after_sim": round(self.bal_mdr_before + mdr_delta, 2),
                "bal_ar_after_sim": round(self.bal_ar_before + ar_delta, 2),
                "posrec_open_after_sim": round(self.posrec_open_before + posrec_delta, 2),
            }
        )
        return True

    # ------------------------------------------------------------------
    # Stage 2 — DRAFT entries
    # ------------------------------------------------------------------
    def _assert_generatable(self):
        self.ensure_one()
        if self.state != "computed":
            raise UserError(_("Compute the summary first — there is nothing reviewed to book."))
        self._assert_period_open()
        clash = self.env["account.move"].search_count(
            [
                ("company_id", "=", self.company_id.id),
                ("ref", "=like", "%s-%%" % self.period_ref),
                ("levis_pos_clearing_id", "!=", self.id),
            ]
        )
        if clash:
            raise UserError(
                _(
                    "%(count)s entries already exist for %(period)s. Cancel or delete "
                    "them before generating a second set.",
                    count=clash,
                    period=self.period_ref,
                )
            )
        blockers = self.diag_ids.filtered(lambda d: d.severity == "blocking" and d.kind == "consumed")
        if blockers:
            raise UserError(
                _(
                    "%s statement line(s) in this period are already used by another "
                    "clearing. Recompute — this run must not spend them twice.",
                    len(blockers),
                )
            )
        if not self.ignore_warnings:
            problems = []
            if self.unparsed_count:
                problems.append(_("%s unparsed narrative(s)", self.unparsed_count))
            if self.unmapped_count:
                problems.append(_("%s unmapped MID/terminal(s)", self.unmapped_count))
            if self.mismatch_count:
                problems.append(_("%s amount mismatch(es)", self.mismatch_count))
            if self.diag_ids.filtered(lambda d: d.kind == "sweep_double"):
                problems.append(_("the sweep destination is also a statement source"))
            if problems:
                raise UserError(
                    _(
                        "Not booking yet: %(problems)s. Money behind those lines would "
                        "stay on suspense with no record of why. Map or fix them, or "
                        'tick "Ignore warnings" to book the rest deliberately.',
                        problems="; ".join(problems),
                    )
                )
        return True

    def _move_ref(self, block, date):
        self.ensure_one()
        return "%s-%s-%s" % (self.period_ref, block.upper(), date)

    def _line_vals(self, account_id, label, balance, analytic):
        return {
            "account_id": account_id,
            "name": (label or "")[:200],
            "debit": balance if balance > 0 else 0.0,
            "credit": -balance if balance < 0 else 0.0,
            "analytic_distribution": dict(analytic) if analytic else False,
        }

    def action_generate_moves(self):
        self.ensure_one()
        self._assert_generatable()
        config = self.config_id
        moves = self.env["account.move"]
        per_key = defaultdict(lambda: self.env["levis.pos.clearing.line"])
        for line in self.line_ids:
            if line.block in ("a", "b") and line.allocated > _EPS:
                per_key[(line.block, line.settlement_date)] |= line
            elif line.block == "c" and abs(line.statement_amount) > _EPS:
                per_key[("c", line.settlement_date)] |= line

        for (block, date), lines in sorted(per_key.items(), key=lambda item: (item[0][1], item[0][0])):
            plan = []
            for line in lines:
                plan += line._move_line_plan()
            if not plan:
                continue
            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "journal_id": self.journal_id.id,
                    "company_id": self.company_id.id,
                    "date": date,
                    "ref": self._move_ref(block, date),
                    "levis_pos_clearing_id": self.id,
                    "line_ids": [(0, 0, vals) for _allocs, vals in plan],
                }
            )
            moves |= move
            lines.write({"move_id": move.id})
            self._attach_alloc_move_lines(plan, move)

        if not moves:
            raise UserError(
                _(
                    "Nothing to book. Either no settlement could be matched to an open "
                    "receivable, or every statement line is unparsed or unmapped — the "
                    "diagnostics list says which."
                )
            )
        self._mark_statement_lines()
        self.state = "generated"
        return True

    def _attach_alloc_move_lines(self, plan, move):
        """Link each allocation to the credit leg that carries it.

        Paired by position, not by looking the leg up afterwards: two stores can
        legitimately produce a credit on the same account with the same analytic
        in one entry, and a lookup would hand both allocations the same leg and
        then over-reconcile it. The move's lines are created in the order of the
        command list, so walking both in ascending id keeps the pairing exact.
        """
        self.ensure_one()
        created = move.line_ids.sorted(key=lambda aml: aml.id)
        if len(created) != len(plan):
            # Something added or merged a line; fall back to no pairing rather than
            # a wrong one. Stage 3 then reports the allocations as unreconcilable.
            _logger.warning(
                "POS clearing %s: entry %s has %s lines for %s planned — allocations left unpaired.",
                self.name,
                move.ref,
                len(created),
                len(plan),
            )
            return False
        for move_line, (allocs, _vals) in zip(created, plan):
            if allocs:
                allocs.write({"move_line_id": move_line.id})
        return True

    def _mark_statement_lines(self):
        self.ensure_one()
        for line in self.line_ids:
            if line.statement_line_id:
                line.statement_line_id.levis_clearing_line_id = line.id
        return True

    # ------------------------------------------------------------------
    # Stage 3 — post and reconcile
    # ------------------------------------------------------------------
    def _preflight(self):
        self.ensure_one()
        if self.state != "generated":
            raise UserError(_("There are no generated draft entries to post."))
        self._assert_period_open()
        drafts = self.move_ids.filtered(lambda m: m.state == "draft")
        if not drafts:
            raise UserError(_("No draft entries left — they were posted or deleted elsewhere."))
        for move in drafts:
            if not (self.date_from <= move.date <= self.date_to):
                raise UserError(_("Entry %(ref)s is dated %(date)s, outside the period.", ref=move.ref, date=move.date))
            imbalance = sum(move.line_ids.mapped("debit")) - sum(move.line_ids.mapped("credit"))
            if abs(imbalance) > _EPS:
                raise UserError(_("Entry %(ref)s is out of balance by %(amount)s.", ref=move.ref, amount=imbalance))
        # The drafts may have waited days. Anything they promised must still be there.
        stale = []
        for alloc in self.line_ids.alloc_ids:
            aml = alloc.source_aml_id
            if not aml or aml.parent_state != "posted" or aml.reconciled:
                stale.append(alloc)
            elif aml.amount_residual + _EPS < alloc.amount:
                stale.append(alloc)
        if stale:
            raise UserError(
                _(
                    "%(count)s receivable line(s) this clearing promised have since been "
                    "reconciled or changed (first: %(entry)s). Cancel and recompute — "
                    "posting now would settle them twice.",
                    count=len(stale),
                    entry=stale[0].source_aml_id.move_id.name or stale[0].source_aml_id.id,
                )
            )
        return drafts

    def action_post(self):
        self.ensure_one()
        drafts = self._preflight()
        drafts.action_post()
        self._reconcile_allocations()
        self._snapshot_after()
        self.state = "posted"
        return True

    def _reconcile_allocations(self):
        """Pair each credit leg with exactly the receivables it settles.

        Not a per-account sweep: that is what made per-store residuals unreadable
        after the July run, because a store that came up short was silently
        covered by another store's excess in the same account.
        """
        self.ensure_one()
        buckets = defaultdict(lambda: self.env["account.move.line"])
        for alloc in self.line_ids.alloc_ids:
            if not (alloc.move_line_id and alloc.source_aml_id):
                continue
            buckets[alloc.move_line_id] |= alloc.source_aml_id
        for credit_line, debits in buckets.items():
            pairing = credit_line | debits
            pairing = pairing.filtered(lambda aml: not aml.reconciled and aml.account_id.reconcile)
            if len(pairing) > 1:
                pairing.reconcile()
        return True

    def _snapshot_after(self):
        self.ensure_one()
        config = self.config_id
        open_amount, open_lines = self._posrec_open()
        self.write(
            {
                "bal_suspense_after_actual": self._balance(config.suspense_account_id, self.date_to),
                "bal_mdr_after_actual": self._balance(config.mdr_account_id, self.date_to),
                "bal_ar_after_actual": self._balance(config.ar_account_id, self.date_to),
                "posrec_open_after_actual": open_amount,
                "posrec_lines_after_actual": open_lines,
            }
        )
        deltas = []
        for label, simulated, actual in (
            (config.suspense_account_id.display_name, self.bal_suspense_after_sim, self.bal_suspense_after_actual),
            (config.mdr_account_id.display_name, self.bal_mdr_after_sim, self.bal_mdr_after_actual),
            (config.ar_account_id.display_name, self.bal_ar_after_sim, self.bal_ar_after_actual),
        ):
            if abs(round(actual - simulated, 2)) > _EPS:
                deltas.append(
                    _("%(label)s: expected %(sim)s, got %(actual)s", label=label, sim=simulated, actual=actual)
                )
        self.warning_text = _("Posted balances differ from the simulation:\n%s", "\n".join(deltas)) if deltas else False
        if deltas:
            _logger.warning("POS clearing %s: post-balance drift %s", self.name, deltas)
        return True

    # ------------------------------------------------------------------
    # Cancel / navigation
    # ------------------------------------------------------------------
    def action_cancel(self):
        self.ensure_one()
        if self.move_ids.filtered(lambda m: m.state != "draft"):
            raise UserError(
                _(
                    "Entries of %s are already posted. In Odoo 19 resetting them to draft "
                    "does not release their reconciliation, so this record cannot undo "
                    "them — reverse the entries themselves.",
                    self.name,
                )
            )
        self.line_ids.mapped("statement_line_id").write({"levis_clearing_line_id": False})
        self.move_ids.unlink()
        self.state = "cancel"
        return True

    def action_reset_to_draft(self):
        self.ensure_one()
        if self.move_ids:
            raise UserError(_("Cancel the generated entries first."))
        self.state = "draft"
        return True

    def action_view_moves(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "name": _("Clearing Entries"),
            "domain": [("id", "in", self.move_ids.ids)],
            "view_mode": "list,form",
        }
        if len(self.move_ids) == 1:
            action.update({"view_mode": "form", "res_id": self.move_ids.id})
        return action

    def action_view_statement_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.bank.statement.line",
            "name": _("Statement Lines"),
            "domain": [("id", "in", self.line_ids.mapped("statement_line_id").ids)],
            "view_mode": "list,form",
        }

    def action_open_mapping_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "levis.bank.mid.map.wizard",
            "name": _("Map Unmapped Settlements"),
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_run_id": self.id,
                "default_date_from": self.date_from,
                "default_date_to": self.date_to,
                "default_journal_ids": self._bank_journals().ids,
            },
        }


class LevisPosClearingLine(models.Model):
    _name = "levis.pos.clearing.line"
    _description = "POS Clearing Line"
    _order = "settlement_date, bank_journal_id, id"

    run_id = fields.Many2one("levis.pos.clearing", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="run_id.company_id", store=True)
    currency_id = fields.Many2one(related="run_id.currency_id")
    statement_line_id = fields.Many2one("account.bank.statement.line", required=True, ondelete="cascade", index=True)
    bank_journal_id = fields.Many2one(related="statement_line_id.journal_id", store=True, string="Bank")
    payment_ref = fields.Char(related="statement_line_id.payment_ref", string="Narrative")
    settlement_date = fields.Date(required=True)
    trans_date = fields.Date(string="Trading Day")
    trans_date_is_derived = fields.Boolean(
        string="Trading Day Guessed",
        help="The narrative carried no transaction date, so it was inferred from "
        "the settlement lag. The account and the store are still exact.",
    )
    block = fields.Selection(_BLOCKS)
    kind = fields.Selection(
        [
            ("settlement", "Card / QRIS Settlement"),
            ("cash_deposit", "Cash Deposit"),
            ("sweep", "Sweep"),
            ("charge", "Bank Charge"),
            ("interest", "Bank Interest"),
            ("unknown", "Unrecognised"),
        ]
    )
    channel = fields.Selection(
        [
            ("debit", "Debit Card"),
            ("credit", "Credit Card"),
            ("qris", "QRIS"),
            ("cash", "Cash"),
            ("transfer", "Transfer"),
            ("other", "Other"),
        ]
    )
    mid_key = fields.Char(string="MID")
    tid_key = fields.Char(string="Terminal")
    map_id = fields.Many2one("levis.bank.mid.map", string="Mapping")
    analytic_account_id = fields.Many2one("account.analytic.account", string="Operating Unit")
    statement_amount = fields.Monetary(currency_field="currency_id", string="Bank Amount")
    gross = fields.Monetary(currency_field="currency_id")
    mdr = fields.Monetary(currency_field="currency_id", string="MDR (narrative)")
    mdr_booked = fields.Monetary(currency_field="currency_id", string="MDR Booked")
    cash_in = fields.Monetary(compute="_compute_narrative_amounts", currency_field="currency_id", store=True)
    allocated = fields.Monetary(compute="_compute_allocated", currency_field="currency_id", store=True)
    short_amount = fields.Monetary(compute="_compute_allocated", currency_field="currency_id", store=True)
    mismatch_amount = fields.Monetary(
        compute="_compute_narrative_amounts",
        currency_field="currency_id",
        store=True,
        string="Narrative vs Bank",
        help="Bank amount minus (gross - MDR). Anything other than zero means the "
        "narrative was misread or the acquirer's arithmetic differs.",
    )
    state = fields.Selection(
        [
            ("ok", "OK"),
            ("short", "Short"),
            ("unmapped", "No Store Mapping"),
            ("unparsed", "Not Parsed"),
            ("mismatch", "Amount Mismatch"),
            ("skipped", "Out of Scope"),
        ],
        default="ok",
    )
    note = fields.Text()
    alloc_ids = fields.One2many("levis.pos.clearing.alloc", "line_id", copy=False)
    move_id = fields.Many2one("account.move", readonly=True, copy=False)

    _stmt_uniq = models.Constraint(
        "unique(run_id, statement_line_id)",
        "A statement line can only appear once in a clearing run.",
    )

    @api.depends("gross", "mdr", "statement_amount", "kind")
    def _compute_narrative_amounts(self):
        for line in self:
            line.cash_in = round(line.gross - line.mdr, 2)
            line.mismatch_amount = (
                round(line.statement_amount - line.cash_in, 2) if line.kind in _SETTLING_KINDS else 0.0
            )

    @api.depends("gross", "kind", "state", "alloc_ids.amount")
    def _compute_allocated(self):
        for line in self:
            line.allocated = round(sum(line.alloc_ids.mapped("amount")), 2)
            # A shortfall means "this store had no open receivable left", which is a
            # different problem from "we do not know the store". Counting an unmapped
            # line as short would inflate the figure and hide which of the two it is.
            shortable = line.kind in _SETTLING_KINDS and line.state in ("ok", "short", "mismatch")
            line.short_amount = max(round(line.gross - line.allocated, 2), 0.0) if shortable else 0.0

    def _move_line_plan(self):
        """The journal legs for this statement line, each with the allocations it pays.

        Sign convention: a statement line of amount ``A`` moves the suspense
        account by ``-A``, so the clearing leg on suspense is always ``+A``. That
        holds for a settlement coming in and for a sweep going out, which is why
        blocks A/B and C can share one rule.

        Returns ``[(alloc_recordset, line_vals)]``; the recordset is empty for the
        suspense and MDR legs, which settle nothing.
        """
        self.ensure_one()
        run = self.run_id
        config = run.config_id
        Alloc = self.env["levis.pos.clearing.alloc"]
        analytic = {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else False
        bank = self.bank_journal_id.code or ""
        plan = []

        if self.block == "c":
            target = config.bank_charge_account_id if self.kind == "charge" else config.sweep_account_id
            if not target:
                raise UserError(
                    _(
                        "No account configured for %s lines.",
                        dict(self._fields["kind"].selection).get(self.kind),
                    )
                )
            label = (self.payment_ref or "")[:120] or _("Bank movement %s", self.settlement_date)
            plan.append((Alloc, run._line_vals(config.suspense_account_id.id, label, self.statement_amount, False)))
            plan.append((Alloc, run._line_vals(target.id, label, -self.statement_amount, False)))
            return plan

        store = self.analytic_account_id.display_name or ""
        grouped = defaultdict(lambda: Alloc)
        for alloc in self.alloc_ids:
            grouped[(alloc.account_id.id, alloc.source_date)] |= alloc
        for key in sorted(grouped, key=lambda item: (item[1] or self.settlement_date, item[0])):
            account_id, source_date = key
            allocs = grouped[key]
            plan.append(
                (
                    allocs,
                    run._line_vals(
                        account_id,
                        _("Settlement %(bank)s %(date)s (%(store)s)", bank=bank, date=source_date, store=store),
                        -round(sum(allocs.mapped("amount")), 2),
                        analytic,
                    ),
                )
            )
        cash_in = round(self.allocated - self.mdr_booked, 2)
        if abs(cash_in) > _EPS:
            plan.append(
                (
                    Alloc,
                    run._line_vals(
                        config.suspense_account_id.id,
                        _("Cash in %(bank)s %(date)s (%(store)s)", bank=bank, date=self.settlement_date, store=store),
                        cash_in,
                        analytic,
                    ),
                )
            )
        if abs(self.mdr_booked) > _EPS:
            plan.append(
                (
                    Alloc,
                    run._line_vals(
                        config.mdr_account_id.id,
                        _("MDR %(bank)s %(date)s (%(store)s)", bank=bank, date=self.settlement_date, store=store),
                        round(self.mdr_booked, 2),
                        analytic,
                    ),
                )
            )
        return plan

    def action_open_statement_line(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.bank.statement.line",
            "res_id": self.statement_line_id.id,
            "view_mode": "form",
        }


class LevisPosClearingAlloc(models.Model):
    _name = "levis.pos.clearing.alloc"
    _description = "POS Clearing Allocation"
    _order = "line_id, account_id, source_date"

    line_id = fields.Many2one("levis.pos.clearing.line", required=True, ondelete="cascade", index=True)
    run_id = fields.Many2one(related="line_id.run_id", store=True, index=True)
    company_id = fields.Many2one(related="line_id.company_id", store=True)
    currency_id = fields.Many2one(related="line_id.currency_id")
    account_id = fields.Many2one("account.account", required=True, string="Receivable Account")
    source_aml_id = fields.Many2one(
        "account.move.line",
        required=True,
        index=True,
        ondelete="cascade",
        string="Open Receivable",
        help="The posted POS receivable debit this settlement consumes.",
    )
    source_date = fields.Date(string="Trading Day Used")
    amount = fields.Monetary(currency_field="currency_id")
    move_line_id = fields.Many2one(
        "account.move.line",
        readonly=True,
        copy=False,
        string="Clearing Leg",
        help="The credit leg of the generated entry that pays this receivable. "
        "Filled at generation and used to reconcile the exact pair.",
    )


class LevisPosClearingDiag(models.Model):
    _name = "levis.pos.clearing.diag"
    _description = "POS Clearing Diagnostic"
    _order = "severity desc, kind, date, id"

    run_id = fields.Many2one("levis.pos.clearing", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="run_id.company_id", store=True)
    currency_id = fields.Many2one(related="run_id.currency_id")
    kind = fields.Selection(_DIAG_KINDS, required=True)
    severity = fields.Selection(
        [("info", "Info"), ("warning", "Warning"), ("blocking", "Blocking")],
        default="warning",
        required=True,
    )
    date = fields.Date()
    bank_journal_id = fields.Many2one("account.journal")
    analytic_account_id = fields.Many2one("account.analytic.account", string="Operating Unit")
    amount = fields.Monetary(currency_field="currency_id")
    count = fields.Integer(default=1)
    res_model = fields.Char()
    res_id = fields.Integer()
    message = fields.Char()

    def action_open_record(self):
        self.ensure_one()
        if not (self.res_model and self.res_id):
            raise UserError(_("This finding does not point at a single record."))
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
        }


class AccountMove(models.Model):
    _inherit = "account.move"

    levis_pos_clearing_id = fields.Many2one(
        "levis.pos.clearing",
        string="POS Clearing",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
