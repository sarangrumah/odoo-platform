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

The clearing is written **onto the bank statement line itself**, not into a
separate entry. Odoo posts a statement line as ``Dr Bank / Cr Suspense`` and
expects reconciliation to *replace* that suspense leg with what the money
actually was — which is why the suspense account ships with ``reconcile =
False`` and can never be matched. Booking the counterpart in its own journal
entry leaves the suspense leg standing forever: the general ledger comes out
right, but every statement line stays ``is_reconciled = False`` and Odoo then
refuses to set a lock date over the period. That is what happened to July 2026
(2.526 lines). So the legs below go on the statement line's own move:

    Dr Bank                 (unchanged, what the bank paid)
    Dr MDR Expense          (what the acquirer kept)
        Cr POS Receivable   (per tender, gross)

and the suspense leg only survives when the settlement is short, by exactly the
amount nobody could explain.

Three stages, deliberately hard-separated because money moves:

1. ``action_compute`` — builds a summary and **creates nothing**. No journal
   entry, no write to a statement line or a receivable.
2. ``action_generate_moves`` — writes the intended legs to
   ``levis.pos.clearing.leg`` for the accountant to read. Still **no**
   accounting: not a draft entry, not a write to a statement line's ledger.
3. ``action_post`` — applies exactly those legs to the statement lines and
   reconciles each credit leg with exactly the receivable lines its allocation
   names.

Stage 2 persists the legs rather than recomputing them at stage 3 on purpose:
the accountant approves a specific set of numbers, and posting must book that
set, not whatever a fresh computation would produce days later.

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

# X70D stages one row per (store, trading day, register, transaction, tender), and
# X24DN posts that transaction as ``pos.order`` with ``pos_reference`` built from
# the same four keys. So the receipt numbers behind a settlement can be recovered
# from the staged rows, which is the one place the per-transaction detail survives:
# the receivable the settlement consumes is a per-store/day/tender total.
_X24_TENDER_FOLD = {"OFFLINE_OTHER_CARD": "OFFLINE_OTHER_CREDITCARD"}
_POS_RECV_PREFIX = "POS Receivable - "
# How many receipt numbers a cell spells out before it states the count instead.
_TRANS_REF_CAP_ALLOC = 20
_TRANS_REF_CAP_LINE = 6

# Bounded subset search. A tender's trading day with more transactions than this
# is left unidentified rather than searched: 2**20 halves already cost more than
# the answer is worth, and a bucket that large is ambiguous in practice anyway.
_SUBSET_MAX_ITEMS = 20
# Two solutions are enough to know the answer is not unique; the search stops
# there instead of enumerating a combinatorial pile it would only discard.
_SUBSET_MAX_SOLUTIONS = 2

# Two statement lines identical in journal, date, narrative and amount are
# normally the same money imported twice. They are only reported as duplicates
# when they arrived in DIFFERENT imports — rows created this far apart cannot
# have come from one file.
_DUP_BATCH_GAP_SECONDS = 3600
# Settlements exceeding the open receivable pool by more than this are reported:
# the money cannot have come from sales that were never booked.
_COVERAGE_TOLERANCE = 1.2

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
    ("dup_statement", "Bank statement imported more than once"),
    ("import_incomplete", "Bank statement stops before the period ends"),
    ("coverage", "Settlements exceed the open receivable pool"),
]

# Diagnostics answering "is the data fit to clear at all", as opposed to those
# describing what the clearing found. Only these run before Compute.
_READINESS_KINDS = ("dup_statement", "import_incomplete", "no_statement", "overlap", "coverage")

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
    # Nothing is booked here any more — the legs go onto the bank statement
    # lines. Kept because the column is NOT NULL on installed databases and
    # ``levis.clearing.config`` still keys configuration creation off a general
    # journal; dropping it needs a migration, not a field edit.
    journal_id = fields.Many2one(
        "account.journal",
        string="General Journal (unused)",
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        default=lambda self: self._default_journal(),
        help="Left over from when the clearing booked its own entries. It books "
        "nothing now: the journal items are written onto the bank statement "
        "lines themselves.",
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
    leg_ids = fields.One2many("levis.pos.clearing.leg", "run_id", copy=False)
    receipt_ids = fields.One2many("levis.pos.clearing.receipt", "run_id", copy=False)
    diag_ids = fields.One2many("levis.pos.clearing.diag", "run_id", copy=False)
    day_ids = fields.One2many("levis.pos.clearing.day", "run_id", copy=False)
    # The bank statement lines' own entries, tagged as this run touched them.
    # Only filled at posting: there is nothing of ours to look at before that.
    move_ids = fields.One2many("account.move", "levis_pos_clearing_id", readonly=True, copy=False)
    move_count = fields.Integer(compute="_compute_move_count")
    leg_count = fields.Integer(compute="_compute_move_count")

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
    # would leave "0 entries" on screen and the header buttons stale.
    @api.depends("move_ids", "leg_ids")
    def _compute_move_count(self):
        for run in self:
            run.move_count = len(run.move_ids)
            run.leg_count = len(run.leg_ids)

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

    # ------------------------------------------------------------------
    # Readiness — is the data fit to clear at all
    # ------------------------------------------------------------------
    def _duplicate_groups(self):
        """Statement lines the same import wrote twice.

        ``[(journal, date, ref, amount, kept id, [re-imported ids])]`` — the kept
        one is named too, because a copy is only skippable if the line it repeats
        can be pointed at.

        Measured on prd_levis_begbal in August 2026: the IBCA statement was
        imported four times, each file starting again at the 1st, leaving 3.145
        lines where 1.202 were real. Nothing in the clearing noticed — it simply
        reported that Rp 10,3 m of settlements had no receivable left, which was
        true of the duplicates and useless as a finding.

        The discriminator is the import, not the wording. Two genuine sales can
        share a store, a day, an amount and a narrative; two rows written **an
        hour or more apart** cannot have come from one file. So the group is
        keyed on what the bank said and split on when it was written.

        Raw SQL joins ``move_id`` for the date: ``account.bank.statement.line``
        has no ``date`` column of its own, only the delegated one.
        """
        self.ensure_one()
        journals = self._bank_journals()
        if not journals:
            return []
        self.env["account.bank.statement.line"].flush_model()
        self.env.cr.execute(
            """
            SELECT sl.journal_id, mv.date, sl.payment_ref, sl.amount,
                   array_agg(sl.id ORDER BY sl.create_date, sl.id),
                   array_agg(EXTRACT(EPOCH FROM sl.create_date) ORDER BY sl.create_date, sl.id)
              FROM account_bank_statement_line sl
              JOIN account_move mv ON mv.id = sl.move_id
             WHERE sl.journal_id IN %s
               AND sl.company_id = %s
               AND mv.state = 'posted'
               AND mv.date BETWEEN %s AND %s
             GROUP BY sl.journal_id, mv.date, sl.payment_ref, sl.amount
            HAVING count(*) > 1
             ORDER BY sum(abs(sl.amount)) DESC
            """,
            (tuple(journals.ids), self.company_id.id, self.date_from, self.date_to),
        )
        groups = []
        for journal_id, date, payment_ref, amount, ids, stamps in self.env.cr.fetchall():
            # Keep only what a second import added: rows written within the same
            # hour as the first are one file repeating itself, which is a real
            # pair of transactions rather than a re-import.
            first = stamps[0]
            extra = [line_id for line_id, stamp in zip(ids, stamps) if stamp - first >= _DUP_BATCH_GAP_SECONDS]
            if extra:
                groups.append((journal_id, date, payment_ref, amount, ids[0], extra))
        return groups

    def _duplicate_line_ids(self):
        """``{re-imported statement line: the line it repeats}``.

        The client imports the month cumulatively — 1–7, then 1–14, then 1–31 —
        so the same days arrive again and again by design. What must never happen
        is the second arrival being cleared: the bank moved that money once, and
        settling a receivable twice invents one. Reporting it was not enough,
        because a run with other findings is booked with "Ignore warnings" ticked
        and the copies would ride along with everything else.
        """
        self.ensure_one()
        return {
            extra_id: kept_id
            for _journal, _date, _ref, _amount, kept_id, extra in self._duplicate_groups()
            for extra_id in extra
        }

    def _diag_duplicates(self):
        """One row per repeated statement line, plus a per-journal total."""
        self.ensure_one()
        out = []
        by_journal = defaultdict(lambda: [0, 0.0])
        groups = self._duplicate_groups()
        for journal_id, date, payment_ref, amount, _kept_id, extra in groups:
            tally = by_journal[journal_id]
            tally[0] += len(extra)
            tally[1] += amount * len(extra)
            if len(out) < _DIAG_DETAIL_CAP:
                out.append(
                    {
                        "kind": "dup_statement",
                        "severity": "warning",
                        "date": date,
                        "bank_journal_id": journal_id,
                        "amount": amount * len(extra),
                        "count": len(extra),
                        "res_model": "account.bank.statement.line",
                        "res_id": extra[0],
                        "message": _(
                            "%(count)s later import(s) of the same line: %(ref)s",
                            count=len(extra),
                            ref=(payment_ref or "")[:100],
                        ),
                    }
                )
        for journal_id, (count, amount) in by_journal.items():
            out.append(
                {
                    "kind": "dup_statement",
                    "severity": "warning",
                    "bank_journal_id": journal_id,
                    "amount": amount,
                    "count": count,
                    "message": _(
                        "%(count)s statement line(s) in this period were imported again "
                        "later. The bank moved this money once, so the later copies are "
                        "listed and left out of the clearing — nothing here is booked.",
                        count=count,
                    ),
                }
            )
        return out

    def _diag_import_incomplete(self):
        """A journal whose statement stops before the period does.

        The August run read as a month and covered eighteen days. Nothing said
        so: the missing days were all at the end, where the interior-gap check by
        design does not look.
        """
        self.ensure_one()
        out = []
        today = fields.Date.context_today(self)
        horizon = min(self.date_to, today - timedelta(days=1))
        if horizon < self.date_from:
            return out
        self.env["account.bank.statement.line"].flush_model()
        for journal in self._bank_journals():
            last = self.env["account.bank.statement.line"].search(
                [
                    ("journal_id", "=", journal.id),
                    ("company_id", "=", self.company_id.id),
                    ("date", ">=", self.date_from),
                    ("date", "<=", self.date_to),
                    ("move_id.state", "=", "posted"),
                ],
                order="date desc",
                limit=1,
            )
            if not last:
                # Said here as well as in ``_diag_missing_days``, which reads the
                # run's own lines and so can only speak after a Compute — too
                # late to be a readiness check.
                out.append(
                    {
                        "kind": "no_statement",
                        "severity": "warning",
                        "bank_journal_id": journal.id,
                        "count": 1,
                        "message": _("No statement lines imported for this period."),
                    }
                )
                continue
            if last.date >= horizon:
                continue
            out.append(
                {
                    "kind": "import_incomplete",
                    "severity": "warning",
                    "date": last.date,
                    "bank_journal_id": journal.id,
                    "count": (horizon - last.date).days,
                    "message": _(
                        "The last statement line is dated %(last)s, %(days)s day(s) short "
                        "of %(horizon)s. Settlements for the missing days will read as "
                        "receivables nobody paid.",
                        last=last.date,
                        days=(horizon - last.date).days,
                        horizon=horizon,
                    ),
                }
            )
        return out

    def _diag_coverage(self, pool_total):
        """Settlements far larger than the receivable they can possibly settle.

        Stated as a ratio because the cause is never in this module: either the
        bank statement repeats itself, or the POS import that books the
        receivable has not run. Both leave the same footprint — money arriving
        against sales that were never recorded — and both make a clearing run
        meaningless before anyone starts ticking anything.
        """
        self.ensure_one()
        gross = round(
            sum(line.gross for line in self.line_ids if line.kind in _SETTLING_KINDS and line.block != "c"), 2
        )
        if not gross or not pool_total or gross <= pool_total * _COVERAGE_TOLERANCE:
            return []
        return [
            {
                "kind": "coverage",
                "severity": "warning",
                "amount": round(gross - pool_total, 2),
                "count": 1,
                "message": _(
                    "Settlements total %(gross)s against %(pool)s of open POS receivable "
                    "(%(ratio)s×). Either the bank statement was imported more than once "
                    "or the POS sales behind it were never booked.",
                    gross=round(gross),
                    pool=round(pool_total),
                    ratio=round(gross / pool_total, 2),
                ),
            }
        ]

    def action_check_readiness(self):
        """Answer "is this month fit to clear" without computing anything.

        Deliberately available in draft and cheap: the whole point is to be
        pressed before a month of work, not after it.
        """
        for run in self:
            run.diag_ids.filtered(lambda diag: diag.kind in _READINESS_KINDS).unlink()
            vals = run._diag_duplicates() + run._diag_import_incomplete() + run._diag_overlap()
            run.diag_ids = [(0, 0, item) for item in vals]
            blocking = [item for item in vals if item["severity"] == "blocking"]
            run.warning_text = (
                _(
                    "%(blocking)s blocking and %(warning)s other finding(s) — read the "
                    "Diagnostics tab before computing.",
                    blocking=len(blocking),
                    warning=len(vals) - len(blocking),
                )
                if vals
                else _("Nothing found: the statements in this period look complete and unrepeated.")
            )
        return True

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
        # Before allocation spends it: ``residual`` is mutated as lines consume it.
        pool_total = round(sum(residual.values()), 2)
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
        diag_vals = []
        prepared = []
        duplicates = self._duplicate_line_ids()
        for statement_line in self._statement_lines():
            journal = statement_line.journal_id
            if journal.id not in rules_cache:
                rules_cache[journal.id] = MidMap._candidates(self.company_id, journal)
            parsed = Narrative.parse(journal, statement_line.payment_ref, statement_line.amount, statement_line.date)
            prepared.append(
                {
                    "statement_line": statement_line,
                    "parsed": parsed,
                    "rules": rules_cache[journal.id],
                    "evidence": None,
                    "duplicate_of": duplicates.get(statement_line.id),
                }
            )
        self._attach_evidence(prepared, pos_accounts)

        line_vals = [None] * len(prepared)
        for index in self._allocation_order(prepared):
            prep = prepared[index]
            line_vals[index] = self._line_from_parsed(
                prep["statement_line"],
                prep["parsed"],
                prep["rules"],
                pool,
                residual,
                ar_pool,
                ar_residual,
                diag_vals,
                cash_account,
                prep=prep,
            )
        self.line_ids = [(0, 0, vals) for vals in line_vals]
        self.diag_ids = [(0, 0, vals) for vals in diag_config + diag_vals]
        self._build_diagnostics(residual, pool_total=pool_total)
        self._simulate_balances()
        # Only the ticks the amount proves. The rest of a trading day is offered
        # one bank line at a time, when someone actually opens it: a month is
        # ~36.000 candidate rows and two minutes of work for a question that is
        # asked line by line.
        self._generate_receipts(proven_only=True)
        # Days last: they are a projection over the finished lines, so they have
        # to see the receipts and diagnostics above, not race them.
        self.env["levis.pos.clearing.day"]._rebuild_for_run(self)
        self.state = "computed"
        return True

    # ------------------------------------------------------------------
    # Candidate receipts — the matching worksheet
    # ------------------------------------------------------------------
    def _generate_receipts(self, lines=None, proven_only=False):
        """Offer every receipt the store rang up that trading day, per bank line.

        Materialised rather than computed because the accountant ticks them: a
        settlement that pays part of a day cannot be identified by arithmetic
        (see ``_x24_identify``), so the last word has to be a human's, and a
        human's answer has to be storable.

        A receipt already ticked — on any line, in any run of this company — is
        not offered again. That is the whole point of the exclusivity: one
        transaction is paid once, and once it is claimed it must stop tempting
        every other statement line that happens to share its trading day.
        """
        self.ensure_one()
        Receipt = self.env["levis.pos.clearing.receipt"]
        Alloc = self.env["levis.pos.clearing.alloc"]
        lines = (lines if lines is not None else self.line_ids).filtered(
            lambda line: line.kind in _SETTLING_KINDS and line.analytic_account_id and line.trans_date
        )
        lines.receipt_ids.filtered(lambda receipt: not receipt.matched).unlink()
        if not lines:
            return True
        legs_by_line = {line.id: line._x24_alloc_legs() for line in lines}
        dates = list(lines.mapped("trans_date"))
        dates += [day for legs in legs_by_line.values() for _tender, day, _amount in legs]
        rows = Alloc._x24_rows(
            set(lines.mapped("analytic_account_id").ids),
            min(dates),
            max(dates),
            self.company_id,
        )
        if not rows:
            return True
        claimed = set(Receipt.search([("company_id", "=", self.company_id.id), ("matched", "=", True)]).mapped("ref"))
        to_create = []
        for line in lines:
            ou_id = line.analytic_account_id.id
            day = rows.get((ou_id, line.trans_date), ())
            _state, _tender, proven = Alloc._x24_identify(day, round(line.gross, 2))
            proven = {ref for ref in proven if ref not in claimed}
            # ``(tender, ref, amount, day)`` — the line's own trading day, which is
            # what a human ticks from, plus anything the legs proved on a
            # neighbouring day, which a human could not have found here at all.
            offer = [(tender, ref, amount, line.trans_date) for tender, ref, amount in day]
            if not proven:
                found, _proven_legs, _total = Alloc._x24_identify_legs(rows, ou_id, legs_by_line[line.id], claimed)
                proven = set(found)
                known = {ref for _tender, ref, _amount in day}
                offer += [
                    (tender, ref, amount, leg_day)
                    for ref, (tender, leg_day, amount) in found.items()
                    if ref not in known
                ]
            if not offer:
                continue
            # A line the amount already explains gets only its proven receipts.
            # Offering it the rest of the day's transactions as well would be
            # tens of thousands of rows answering a question nobody still has —
            # and unticking one puts the line back in play, so Refresh
            # Suggestions hands it the whole day again the moment it matters.
            settled = (
                proven and abs(round(sum(a for _t, r, a, _d in offer if r in proven), 2) - round(line.gross, 2)) <= _EPS
            )
            for tender, ref, amount, row_day in offer:
                tick = ref in proven
                if ref in claimed or ((settled or proven_only) and not tick):
                    continue
                if tick:
                    claimed.add(ref)
                to_create.append(
                    {
                        "line_id": line.id,
                        "ref": ref,
                        "tender": tender,
                        "trans_date": row_day,
                        "amount": amount,
                        "suggested": tick,
                        "matched": tick,
                    }
                )
        if to_create:
            # The generator already refuses a claimed receipt and never ticks one
            # twice, so the per-record release is dead weight here; one statement
            # afterwards sweeps the candidates a tick has just invalidated.
            Receipt.with_context(levis_skip_receipt_release=True).create(to_create)
            Receipt._sweep_claimed(self.company_id)
        return True

    def action_match_proven(self):
        """Re-tick everything the amounts prove, across the whole run.

        Compute already does this once, but the answer moves afterwards: a MID
        mapped in the wizard gives a line a store, and a store is what makes its
        trading day readable at all. Without this the accountant would have to
        recompute the month — which throws away every tick already made — to
        collect ticks that are free.
        """
        for run in self:
            if run.state not in ("computed", "generated"):
                raise UserError(_("Compute the summary first — there is nothing to match yet."))
            run._generate_receipts(proven_only=True)
        return True

    def action_view_receipts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Receipt Matching — %s", self.name),
            "res_model": "levis.pos.clearing.receipt",
            "view_mode": "list",
            "domain": [("run_id", "=", self.id)],
            "context": {"search_default_group_line": 1, "search_default_unmatched": 1, "create": False},
        }

    # ------------------------------------------------------------------
    # Evidence — what the receipts prove before the allocation guesses
    # ------------------------------------------------------------------
    def _resolve_target(self, statement_line, parsed, rules):
        """``(rule, trading day, day was inferred)`` for one settlement."""
        self.ensure_one()
        rule = self.env["levis.bank.mid.map"]._resolve(
            self.company_id, statement_line.journal_id, parsed, statement_line.date, candidates=rules
        )
        exact = parsed["confidence"] == "exact" and parsed["trans_date"]
        primary = (
            parsed["trans_date"]
            if exact
            else statement_line.date - timedelta(days=self.config_id.settlement_lag_days or 0)
        )
        return rule, primary, not exact

    def _tender_accounts(self, accounts):
        """``{tender name: account}`` for the tenders an account name spells out."""
        Alloc = self.env["levis.pos.clearing.alloc"]
        out = {}
        for account in accounts:
            tender = Alloc._x24_tender_of_account(account)
            if tender and tender not in out:
                out[tender] = account
        return out

    def _attach_evidence(self, prepared, pos_accounts):
        """Ask the receipts, per settlement, which tender and which day it paid.

        Two claims come out of this, and both were previously left to the greedy
        allocation to guess at:

        * **Which tender account.** The narrative cannot say — one card MID
          covers Visa, Mastercard, JCB and Amex — so the account used to be
          whichever had the largest residual. Where the day's transactions
          identify the settlement by arithmetic, they name the tender outright,
          and that beats a residual ordering: measured on August 2026, 377
          settlements had their tender named by the receipts and a *different*
          account credited by the allocation.
        * **Which trading day.** Most BCA narratives carry no transaction date,
          so the day is inferred from the settlement lag and then widened into a
          ladder. A day whose receipts add up exactly is not an inference.

        Both are recorded, neither is forced: a settlement nothing proves keeps
        the old behaviour exactly.
        """
        self.ensure_one()
        Alloc = self.env["levis.pos.clearing.alloc"]
        settling = []
        for prep in prepared:
            parsed = prep["parsed"]
            if parsed["kind"] not in _SETTLING_KINDS:
                continue
            rule, primary, derived = self._resolve_target(prep["statement_line"], parsed, prep["rules"])
            prep.update({"rule": rule, "trans_date": primary, "trans_date_is_derived": derived})
            if rule and parsed.get("gross"):
                settling.append(prep)
        if not settling:
            return prepared
        dates = [prep["trans_date"] for prep in settling]
        lookback = timedelta(days=(self.config_id.lookback_days or 0) + 1)
        rows = Alloc._x24_rows(
            set(prep["rule"].analytic_account_id.id for prep in settling),
            min(dates) - lookback,
            max(dates) + lookback,
            self.company_id,
        )
        if not rows:
            return prepared
        tender_accounts = self._tender_accounts(pos_accounts)
        # Hundreds of settlements share a store, a day and an amount — a card
        # terminal batches the same figures repeatedly — and the subset search is
        # the one expensive step in the run. Asked once, answered for all of them.
        cache = {}
        for prep in settling:
            analytic_id = prep["rule"].analytic_account_id.id
            gross = round(prep["parsed"]["gross"], 2)
            for day in self._candidate_dates(prep["trans_date"]):
                key = (analytic_id, day, gross)
                if key not in cache:
                    cache[key] = Alloc._x24_identify(rows.get((analytic_id, day), ()), gross)
                state, tender, refs = cache[key]
                if state not in ("exact", "batch", "subset"):
                    continue
                prep["evidence"] = {
                    "state": state,
                    "tender": tender,
                    "refs": refs,
                    "day": day,
                    "account": tender_accounts.get(tender) if tender else None,
                }
                # The proven day replaces the inferred one, and stays flagged as
                # inferred: the narrative still never said it. What changed is
                # that the guess now has receipts behind it.
                prep["trans_date"] = day
                break
        return prepared

    def _allocate_with_evidence(self, pool, residual, analytic_id, dates, gross, only, evidence, vals):
        """Spend the settlement on the tender the receipts name, then on the rest.

        The evidence account is not a restriction, it is a *priority*. Restricting
        outright would turn "these receipts prove the tender" into "this
        settlement may only ever clear that account", and a tender receivable
        that is already reconciled or short would then leave money unexplained
        that the old behaviour would have settled correctly. So the proven
        account is drained first and whatever it cannot cover falls back to the
        ordinary largest-residual search over the channel's pool.

        ``only_accounts`` still binds: a cash deposit may not consume a card
        receivable however its receipts read, because the channel restriction
        answers a question the receipts do not.
        """
        self.ensure_one()
        account = (evidence or {}).get("account")
        allowed = set(only.ids) if only else None
        if not account or (allowed is not None and account.id not in allowed):
            return self._allocate(pool, residual, analytic_id, dates, gross, only_accounts=only)
        day = evidence.get("day")
        taken, left = self._allocate(
            pool,
            residual,
            analytic_id,
            # The proven day first — the receipts belong to it — but the rest of
            # the ladder stays open, because a trading day can be booked a day
            # late without making the tender wrong.
            [day] + [other for other in dates if other != day] if day else dates,
            gross,
            only_accounts=account,
        )
        vals["tender_locked"] = bool(taken)
        if left > _EPS:
            rest, left = self._allocate(pool, residual, analytic_id, dates, left, only_accounts=only)
            taken += rest
        return taken, left

    def _allocation_order(self, prepared):
        """Indices to allocate in: what the receipts prove, before what they don't.

        Order decides who gets the money when the pool is thin, and a proven
        settlement has a better claim on a receivable than a settlement that
        merely wants one. Statement order is kept inside each group so a rerun
        allocates identically.
        """
        proven = [index for index, prep in enumerate(prepared) if (prep.get("evidence") or {}).get("account")]
        rest = [index for index, prep in enumerate(prepared) if not (prep.get("evidence") or {}).get("account")]
        return proven + rest

    def _line_from_parsed(
        self,
        statement_line,
        parsed,
        rules,
        pool,
        residual,
        ar_pool,
        ar_residual,
        diag_vals,
        cash_account=None,
        prep=None,
    ):
        """One statement line -> one clearing line, allocations included.

        Every statement line in scope produces a row, whatever happened to it.
        A narrative that could not be read is a visible ``unparsed`` row, not a
        gap in the list.
        """
        self.ensure_one()
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

        duplicate_of = (prep or {}).get("duplicate_of")
        if duplicate_of:
            # Left out before anything is allocated, not filtered at posting: a
            # copy that consumed a receivable here would make the original read
            # as short, and the run would then be wrong about the real line too.
            kept = self.env["account.bank.statement.line"].browse(duplicate_of)
            vals.update({"state": "skipped", "block": False})
            vals["note"] = _(
                "A later import of %(entry)s. The bank moved this money once, so this copy clears nothing.",
                entry=kept.move_id.name or kept.payment_ref or duplicate_of,
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
        prep = prep or {}
        if "rule" in prep:
            rule, primary, derived = prep["rule"], prep["trans_date"], prep["trans_date_is_derived"]
        else:
            rule, primary, derived = self._resolve_target(statement_line, parsed, rules)
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
        vals["trans_date"] = primary
        vals["trans_date_is_derived"] = derived
        dates = self._candidate_dates(primary)

        only = self._pool_accounts_for_channel(parsed, cash_account)
        taken, left = self._allocate_with_evidence(
            pool, residual, rule.analytic_account_id.id, dates, parsed["gross"], only, prep.get("evidence"), vals
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
    def _build_diagnostics(self, residual, pool_total=0.0):
        self.ensure_one()
        vals = []
        vals += self._diag_duplicates()
        vals += self._diag_import_incomplete()
        vals += self._diag_coverage(pool_total)
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
        # The clearing no longer has entries of its own to look for, so the claim
        # on a statement line is the marker it carries.
        clash = self.env["account.bank.statement.line"].search_count(
            [
                ("id", "in", self.line_ids.statement_line_id.ids),
                ("levis_clearing_line_id", "!=", False),
                ("levis_clearing_line_id.run_id", "!=", self.id),
            ]
        )
        if clash:
            raise UserError(
                _(
                    "%(count)s statement line(s) in %(period)s are already claimed by "
                    "another clearing run. Cancel it before generating a second set.",
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
            # A statement imported twice used to refuse the run outright. It no
            # longer has to: the copies are left out at compute time, so there is
            # nothing here for "Ignore warnings" to let through. They stay on the
            # Diagnostics tab, because the import is still worth fixing upstream.
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

    def _line_vals(self, account_id, label, balance, analytic):
        return {
            "account_id": account_id,
            "name": (label or "")[:200],
            "debit": balance if balance > 0 else 0.0,
            "credit": -balance if balance < 0 else 0.0,
            "analytic_distribution": dict(analytic) if analytic else False,
        }

    def action_generate_moves(self):
        """Stage 2: write down what stage 3 will book, and book nothing."""
        self.ensure_one()
        self._assert_generatable()
        self.leg_ids.unlink()
        # Built as one batch: a month of settlements is a few thousand legs, and
        # creating them one at a time is a few thousand round trips.
        to_create = []
        owners = []
        for line in self.line_ids:
            if line.block not in ("a", "b", "c"):
                continue
            if line.block in ("a", "b") and line.allocated <= _EPS:
                continue
            if line.block == "c" and abs(line.statement_amount) <= _EPS:
                continue
            for sequence, (allocs, role, vals) in enumerate(line._counterpart_plan()):
                to_create.append(
                    {
                        "run_id": self.id,
                        "line_id": line.id,
                        "sequence": sequence,
                        "role": role,
                        "account_id": vals["account_id"],
                        "name": vals["name"],
                        "balance": vals["debit"] - vals["credit"],
                        "analytic_distribution": vals["analytic_distribution"],
                    }
                )
                owners.append(allocs)
        legs = self.env["levis.pos.clearing.leg"].create(to_create) if to_create else False
        # create() returns the records in the order it was given them.
        for leg, allocs in zip(legs or [], owners):
            if allocs:
                allocs.write({"leg_id": leg.id})

        if not legs:
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

    def _mark_statement_lines(self):
        self.ensure_one()
        for line in self.line_ids:
            if line.statement_line_id:
                line.statement_line_id.levis_clearing_line_id = line.id
        return True

    # ------------------------------------------------------------------
    # Stage 3 — post and reconcile
    # ------------------------------------------------------------------
    def _assert_writeoffs_within_limit(self):
        """No single line may absorb more than Finance allowed.

        Modelled on the guard in ``custom_bank_reconcile``'s wizard, which refuses
        to let the MDR account absorb anything other than the printed fee. A
        write-off is a decision about money; a cap makes it a decision someone
        with authority signed off on, rather than one a tired operator could make
        by clicking through. Zero means no cap, which is the default.
        """
        self.ensure_one()
        limit = self.config_id.writeoff_limit_amount or 0.0
        if limit <= 0:
            return True
        currency = self.company_id.currency_id
        over = self.line_ids.filtered(
            lambda line: line.writeoff_account_id and currency.compare_amounts(abs(line.short_amount), limit) > 0
        )
        if over:
            raise UserError(
                _(
                    "These lines would write off more than the %(limit)s limit:\n%(lines)s",
                    limit=limit,
                    lines="\n".join(
                        "  %s — %s" % (line.payment_ref or line.id, abs(line.short_amount)) for line in over
                    ),
                )
            )
        return True

    def _preflight(self):
        self.ensure_one()
        if self.state != "generated":
            raise UserError(_("There is no reviewed plan to post — generate it first."))
        self._assert_period_open()
        if not self.leg_ids:
            raise UserError(_("The planned legs are gone. Cancel and generate them again."))
        self._assert_writeoffs_within_limit()

        company_currency = self.company_id.currency_id
        for line in self.leg_ids.line_id:
            st_line = line.statement_line_id
            if not (self.date_from <= st_line.date <= self.date_to):
                raise UserError(
                    _(
                        "Statement line %(ref)s is dated %(date)s, outside the period.",
                        ref=st_line.payment_ref or st_line.id,
                        date=st_line.date,
                    )
                )
            # Every leg is written in company currency, so a statement line in
            # anything else would need a rate applied per leg. Refuse rather than
            # invent one — all six Levi's bank journals are IDR.
            if st_line.foreign_currency_id or (st_line.currency_id and st_line.currency_id != company_currency):
                raise UserError(
                    _(
                        "Statement line %(ref)s is in %(currency)s. This clearing only books in %(company)s.",
                        ref=st_line.payment_ref or st_line.id,
                        currency=(st_line.foreign_currency_id or st_line.currency_id).name,
                        company=company_currency.name,
                    )
                )
            _liquidity, suspense, other = st_line._seek_for_lines()
            if not suspense or other:
                raise UserError(
                    _(
                        "Statement line %(ref)s is no longer sitting on suspense — "
                        "someone reconciled or edited it after this plan was made. "
                        "Cancel and recompute.",
                        ref=st_line.payment_ref or st_line.id,
                    )
                )
            planned = sum(self.leg_ids.filtered(lambda leg: leg.line_id == line).mapped("balance"))
            imbalance = round(planned + st_line.amount, 2)
            if abs(imbalance) > _EPS:
                raise UserError(
                    _(
                        "The legs planned for statement line %(ref)s total %(planned)s "
                        "against a bank amount of %(amount)s — off by %(diff)s.",
                        ref=st_line.payment_ref or st_line.id,
                        planned=planned,
                        amount=st_line.amount,
                        diff=imbalance,
                    )
                )
        # The plan may have waited days. Anything it promised must still be there.
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
        return True

    def action_post(self):
        self.ensure_one()
        self._preflight()
        self._apply_to_statement_lines()
        self._reconcile_allocations()
        self._snapshot_after()
        self.state = "posted"
        return True

    def _retarget_residual_legs(self, lines):
        """Point the residual leg at the chosen account, in place.

        Only the residual leg changes. The receivable and MDR legs of the same
        settlement were reviewed and are still right, so they are left exactly as
        they are — including their ids, so the allocations hanging off them keep
        pointing at the same records. Rebuilding the whole plan would throw away
        a review nobody asked to redo, and the balancing figure does not change
        just because its destination did.
        """
        self.ensure_one()
        lines = lines.filtered(lambda line: line.run_id == self)
        if not lines:
            return True
        if self.state != "generated":
            raise UserError(_("Legs can only be retargeted while the run is prepared but unposted."))
        config = self.config_id
        for line in lines:
            residual = self.leg_ids.filtered(lambda leg, l=line: leg.line_id == l and leg.role in ("short", "writeoff"))
            if not residual:
                # Nothing was left over on this settlement, so there is nothing
                # to send anywhere. Not an error: a fully explained line simply
                # has no residual leg.
                continue
            bank = line.bank_journal_id.code or ""
            store = line.analytic_account_id.display_name or ""
            if line.writeoff_account_id:
                residual.write(
                    {
                        "role": "writeoff",
                        "account_id": line.writeoff_account_id.id,
                        "name": line.writeoff_label
                        or _(
                            "Write-off %(bank)s %(date)s (%(store)s)",
                            bank=bank,
                            date=line.settlement_date,
                            store=store,
                        ),
                    }
                )
            else:
                residual.write(
                    {
                        "role": "short",
                        "account_id": config.suspense_account_id.id,
                        "name": _(
                            "Unsettled %(bank)s %(date)s (%(store)s)",
                            bank=bank,
                            date=line.settlement_date,
                            store=store,
                        ),
                    }
                )
        return True

    def _apply_to_statement_lines(self):
        """Swap each statement line's suspense leg for the legs planned in stage 2.

        The statement line's entry is already posted — that is normal, Odoo posts
        it the moment the line is imported, and its own reconciliation does
        exactly this write (see ``action_undo_reconciliation`` in core). Only the
        suspense leg is deleted; the liquidity leg is left alone rather than
        cleared and rebuilt, so nothing recomputes the bank amount or its
        currency behind our back.
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        for line in self.leg_ids.line_id:
            st_line = line.statement_line_id
            legs = self.leg_ids.filtered(lambda leg: leg.line_id == line).sorted(key=lambda leg: leg.sequence)
            _liquidity, suspense, _other = st_line._seek_for_lines()
            commands = [(2, suspense.id, 0)] if suspense else []
            for leg in legs:
                commands.append(
                    (
                        0,
                        0,
                        {
                            "name": leg.name,
                            "account_id": leg.account_id.id,
                            "partner_id": st_line.partner_id.id,
                            "currency_id": company_currency.id,
                            "amount_currency": leg.balance,
                            "debit": leg.balance if leg.balance > 0 else 0.0,
                            "credit": -leg.balance if leg.balance < 0 else 0.0,
                            "analytic_distribution": leg.analytic_distribution or False,
                        },
                    )
                )
            st_line.with_context(force_delete=True, skip_readonly_check=True).write({"line_ids": commands})
            st_line.move_id.levis_pos_clearing_id = self.id

            # Pair each planned leg with the journal item it became, by position:
            # two stores can legitimately produce the same account, amount and
            # analytic on one statement line, and looking the leg up afterwards
            # would hand both allocations the same item and over-reconcile it.
            created = (st_line.move_id.line_ids - _liquidity).sorted(key=lambda aml: aml.id)
            if len(created) != len(legs):
                _logger.warning(
                    "POS clearing %s: statement line %s has %s new items for %s legs — left unpaired.",
                    self.name,
                    st_line.id,
                    len(created),
                    len(legs),
                )
                continue
            for aml, leg in zip(created, legs):
                leg.move_line_id = aml.id
                if leg.alloc_ids:
                    leg.alloc_ids.write({"move_line_id": aml.id})
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
        if self.state == "posted":
            raise UserError(
                _(
                    "%s is posted. Its legs live on the bank statement lines now, so "
                    'undoing it means "Undo Reconciliation" on those lines — this record '
                    "cannot take the money back on their behalf.",
                    self.name,
                )
            )
        self.line_ids.mapped("statement_line_id").write({"levis_clearing_line_id": False})
        self.leg_ids.unlink()
        self.state = "cancel"
        return True

    def action_reset_to_draft(self):
        self.ensure_one()
        if self.leg_ids:
            raise UserError(_("Cancel the generated plan first."))
        self.state = "draft"
        return True

    def action_view_moves(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "name": _("Statement Entries Cleared"),
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

    def action_view_lines(self):
        """The run's settlements as a real list, with the search bar the form cannot have.

        An embedded one2many has no search panel, so on a month of eleven bank
        journals the Settlements tab is a thousand rows you can only scroll. This
        is the same records under a normal action: filter to the store, the bank,
        the tender or the ones still short, and group them.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "levis.pos.clearing.line",
            "name": _("Settlements — %s", self.name),
            "domain": [("run_id", "=", self.id)],
            "view_mode": "list,form",
            "context": {"search_default_group_store": 1},
        }

    def action_open_mapping_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "levis.bank.mid.map.wizard",
            "name": _("Map Unmapped Settlements"),
            "view_mode": "form",
            # Full page, not a modal: dozens of merchant ids, each needing its
            # amounts read against a bank statement, do not fit in a dialog.
            "target": "current",
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
    # Stored so the settlements can be searched and grouped away from their run's
    # form, where the parent's state is no longer on screen to read.
    run_state = fields.Selection(related="run_id.state", store=True, string="Run Status")
    run_period_ref = fields.Char(related="run_id.period_ref", store=True, string="Period")
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
    # --- write-off: where the residual goes instead of suspense ------------
    # Left empty, the residual lands on suspense exactly as it always has. This
    # is the whole of the write-off feature: the residual leg is already
    # computed as the balancing figure in ``_counterpart_plan``, so choosing a
    # different account for it is the only change the accounting needs.
    writeoff_account_id = fields.Many2one(
        "account.account",
        string="Write-off Account",
        copy=False,
        help="Where the unexplained residual is booked instead of suspense. "
        "Empty means it stays on suspense and the statement line stays open.",
    )
    writeoff_label = fields.Char(string="Write-off Label", copy=False)
    writeoff_reason = fields.Selection(
        [
            ("rounding", "Rounding"),
            ("admin_fee", "Bank / Admin Fee"),
            ("short_deposit", "Short Deposit"),
            ("overage", "Overage"),
            ("other", "Other"),
        ],
        string="Write-off Reason",
        copy=False,
    )
    writeoff_uid = fields.Many2one("res.users", string="Written Off By", readonly=True, copy=False)
    day_id = fields.Many2one(
        "levis.pos.clearing.day",
        string="Clearing Day",
        index="btree_not_null",
        ondelete="set null",
        copy=False,
        help="The settlement day this line belongs to. A projection for the "
        "operator; nothing about the accounting depends on it.",
    )
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
    leg_ids = fields.One2many("levis.pos.clearing.leg", "line_id", copy=False)
    # The statement line's own entry — where this clearing's legs are written.
    move_id = fields.Many2one(related="statement_line_id.move_id", string="Journal Entry")
    move_name = fields.Char(
        related="statement_line_id.move_id.name",
        store=True,
        string="Bank Entry No.",
        help="The journal entry number of the bank statement line itself — the "
        "number to quote when this settlement is looked up in the general ledger.",
    )
    x24_match = fields.Selection(
        [
            ("exact", "One transaction"),
            ("batch", "Whole tender batch"),
            ("subset", "Only possible combination"),
            ("leg", "Every receivable leg"),
            ("leg_partial", "Some receivable legs"),
            ("ambiguous", "Several possibilities"),
            ("none", "Not identified"),
        ],
        string="Receipt Match",
        compute="_compute_x24_trans",
        store=True,
        help="How the receipts below were established. Only arithmetic counts: one "
        "transaction of exactly this gross, one tender whose whole trading day sums "
        "to it, or — within one tender — the single combination of transactions "
        "that adds up to it. Where the gross names nothing because it paid two "
        "tenders at once, the same test is applied to each receivable leg instead, "
        "and the line reads as proven per leg — every leg, or only some. A day that "
        "can be composed more than one way is left unnamed, because picking one "
        "would be a guess.",
    )
    tender_locked = fields.Boolean(
        string="Tender Proven",
        help="The receivable credited here is the one the receipts name, not the "
        "one that merely had the largest open balance. Set where the trading day's "
        "transactions identify the settlement by amount.",
    )
    receipt_ids = fields.One2many("levis.pos.clearing.receipt", "line_id", copy=False)
    x24_trans_refs = fields.Char(
        string="X24DN Transactions",
        compute="_compute_matched_receipts",
        store=True,
        help="The receipts ticked as making up this bank line. Pre-ticked where the "
        "amount proves them (see Receipt Match); everything else is the "
        "accountant's to confirm on the Receipt Matching list.",
    )
    x24_trans_count = fields.Integer(
        string="Receipts",
        compute="_compute_matched_receipts",
        store=True,
    )
    matched_total = fields.Monetary(
        compute="_compute_matched_receipts",
        store=True,
        currency_field="currency_id",
        string="Receipts Ticked",
    )
    match_gap = fields.Monetary(
        compute="_compute_matched_receipts",
        store=True,
        currency_field="currency_id",
        string="Still Unmatched",
        help="Gross minus the receipts ticked. Zero means this bank line is fully accounted for by named transactions.",
    )
    x24_tender = fields.Char(
        string="Tender (evidence)",
        compute="_compute_x24_trans",
        store=True,
        help="The tender those receipts were paid with. The narrative never says "
        "this — one card MID covers Visa, Mastercard, JCB and Amex alike — so where "
        "the amount identifies the transaction, this is the only hard evidence of "
        "which tender receivable the settlement really pays.",
    )
    x24_tender_mismatch = fields.Boolean(
        string="Tender Disagrees",
        compute="_compute_x24_trans",
        store=True,
        help="The receipts name one tender and the allocation credited another. The "
        "allocation consumes open receivables largest-residual-first, which cannot "
        "see the tender; this flag is where that guess is contradicted by the money.",
    )

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

    @api.depends("receipt_ids.matched", "receipt_ids.amount", "gross")
    def _compute_matched_receipts(self):
        """What the accountant has actually confirmed, not what was suggested."""
        Alloc = self.env["levis.pos.clearing.alloc"]
        for line in self:
            matched = line.receipt_ids.filtered("matched").sorted(lambda receipt: receipt.ref)
            line.x24_trans_count = len(matched)
            line.x24_trans_refs = Alloc._x24_format_refs(matched.mapped("ref"), _TRANS_REF_CAP_LINE)
            line.matched_total = round(sum(matched.mapped("amount")), 2)
            line.match_gap = round(line.gross - line.matched_total, 2) if line.kind in _SETTLING_KINDS else 0.0

    def _x24_alloc_legs(self):
        """``[(tender, trading day, amount)]`` — what this settlement was booked against.

        One leg per tender per trading day, which is exactly the grain
        ``custom_retail_import`` books the POS receivable at, so every leg is a
        target the X70D transactions of that day can be matched against. The
        tender is read off the account name because that is the only place it
        survives: ``POS Receivable - OFFLINE_VISA`` and nothing else says Visa.
        """
        self.ensure_one()
        Alloc = self.env["levis.pos.clearing.alloc"]
        legs = defaultdict(float)
        for alloc in self.alloc_ids:
            tender = Alloc._x24_tender_of_account(alloc.account_id)
            if not tender or not alloc.source_date:
                continue
            legs[(_X24_TENDER_FOLD.get(tender, tender), alloc.source_date)] += alloc.amount
        return [(tender, day, round(amount, 2)) for (tender, day), amount in legs.items()]

    @api.depends(
        "analytic_account_id",
        "trans_date",
        "gross",
        "kind",
        "alloc_ids.account_id",
        "alloc_ids.amount",
        "alloc_ids.source_date",
    )
    def _compute_x24_trans(self):
        """Name the receipts this bank line proves it paid — or name none.

        Keyed on the settlement's own gross against the store's trading day, not
        on the receivable the allocation happened to consume. Those are different
        claims: the allocation picks by residual and cannot see a tender, so a
        250.900 settlement can end up crediting the card receivable that holds
        the day's 16.865.300 — and reading the receipts off *that* made the line
        look like it had paid ten transactions worth millions.
        """
        Alloc = self.env["levis.pos.clearing.alloc"]
        settling = self.filtered(
            lambda line: line.kind in _SETTLING_KINDS and line.analytic_account_id and line.trans_date
        )
        for line in self - settling:
            line.x24_match = "none"
            line.x24_tender = False
            line.x24_tender_mismatch = False
        if not settling:
            return
        legs_by_line = {line.id: line._x24_alloc_legs() for line in settling}
        # The legs can sit a day either side of the line's own trading day: the
        # allocation walks a ladder of candidate days, and a leg it settled on is
        # still the day whose receipts have to be read.
        dates = list(settling.mapped("trans_date"))
        dates += [day for legs in legs_by_line.values() for _tender, day, _amount in legs]
        rows = Alloc._x24_rows(
            set(settling.mapped("analytic_account_id").ids),
            min(dates),
            max(dates),
            settling.company_id[:1] or self.env.company,
        )
        cache = {}
        leg_cache = {}
        for line in settling:
            key = (line.analytic_account_id.id, line.trans_date, round(line.gross, 2))
            if key not in cache:
                cache[key] = Alloc._x24_identify(rows.get(key[:2], ()), key[2])
            state, tender, refs = cache[key]
            if state == "none":
                # Nothing adds up to the whole payment; ask the receivable it was
                # booked against instead. Same arithmetic, smaller question.
                legs = legs_by_line[line.id]
                leg_key = (line.analytic_account_id.id, tuple(sorted(legs)))
                if leg_key not in leg_cache:
                    leg_cache[leg_key] = Alloc._x24_identify_legs(rows, line.analytic_account_id.id, legs)
                found, proven_legs, total_legs = leg_cache[leg_key]
                if proven_legs:
                    state = "leg" if proven_legs == total_legs else "leg_partial"
                    tenders = {leg_tender for leg_tender, _day, _amount in found.values()}
                    tender = tenders.pop() if len(tenders) == 1 else False
            line.x24_match = state
            line.x24_tender = tender or False
            booked = {Alloc._x24_tender_of_account(alloc.account_id) for alloc in line.alloc_ids}
            booked.discard(None)
            line.x24_tender_mismatch = bool(tender and booked and tender not in booked)

    def _counterpart_plan(self):
        """The legs that replace this statement line's suspense leg.

        Odoo books a statement line of amount ``A`` as ``Dr Bank A / Cr Suspense
        A``. Clearing it means swapping that ``Cr Suspense A`` for what the money
        actually was, so the legs here must total ``-A``: the receivables the
        settlement pays (credit, gross), the fee the acquirer kept (debit), and —
        only when the settlement is short — whatever is left with no explanation,
        which stays on suspense.

        That last leg is the whole point of the sign arithmetic. Fully explained
        settlements end up with no suspense leg at all, and Odoo's own
        ``_compute_is_reconciled`` then marks the line reconciled without anyone
        reconciling anything. A short one keeps a suspense leg for exactly the
        shortfall and stays open, which is the truth about it.

        Returns ``[(alloc_recordset, role, line_vals)]``; the recordset is empty
        for the MDR, bank and shortfall legs, which settle nothing.
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
            plan.append((Alloc, "bank", run._line_vals(target.id, label, -self.statement_amount, False)))
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
                    "receivable",
                    run._line_vals(
                        account_id,
                        _("Settlement %(bank)s %(date)s (%(store)s)", bank=bank, date=source_date, store=store),
                        -round(sum(allocs.mapped("amount")), 2),
                        analytic,
                    ),
                )
            )
        if abs(self.mdr_booked) > _EPS:
            plan.append(
                (
                    Alloc,
                    "mdr",
                    run._line_vals(
                        config.mdr_account_id.id,
                        _("MDR %(bank)s %(date)s (%(store)s)", bank=bank, date=self.settlement_date, store=store),
                        round(self.mdr_booked, 2),
                        analytic,
                    ),
                )
            )
        # Whatever the legs above do not account for. Computed as the balancing
        # figure rather than from `short_amount` so that the entry is balanced by
        # construction: a rounding crumb anywhere above lands here instead of
        # making the move unpostable.
        residual = round(-self.statement_amount - sum(vals["debit"] - vals["credit"] for _a, _r, vals in plan), 2)
        if abs(residual) > _EPS:
            # An identified difference may be sent to an account someone chose;
            # anything else stays on suspense, which is the truth about it.
            target = self.writeoff_account_id or config.suspense_account_id
            role = "writeoff" if self.writeoff_account_id else "short"
            if self.writeoff_account_id:
                label = self.writeoff_label or _(
                    "Write-off %(bank)s %(date)s (%(store)s)",
                    bank=bank,
                    date=self.settlement_date,
                    store=store,
                )
            else:
                label = _(
                    "Unsettled %(bank)s %(date)s (%(store)s)",
                    bank=bank,
                    date=self.settlement_date,
                    store=store,
                )
            plan.append((Alloc, role, run._line_vals(target.id, label, residual, analytic)))
        return plan

    def _apply_writeoff_to_posted_move(self):
        """Move an already-posted residual off suspense, on the line's own move.

        Only reachable after posting, and deliberately the narrow path. A
        separate journal entry cannot help here: the suspense account ships with
        ``reconcile = False``, so a Dr write-off / Cr suspense entry would leave
        two open suspense items instead of one and clear nothing. What actually
        closes the statement line is the same write the clearing already does —
        replace the surviving suspense leg with a leg on the chosen account.

        Refuses rather than guesses when the line has moved on: no suspense leg
        left (someone reconciled it by hand), an amount that no longer matches, or
        a locked period. A residual that cannot be moved honestly stays where it
        is.
        """
        company_currency = self.env.company.currency_id
        for line in self:
            if not line.writeoff_account_id:
                continue
            config = line.run_id.config_id
            st_line = line.statement_line_id
            if not st_line:
                raise UserError(_("Settlement %s has no statement line.", line.id))
            line.run_id._assert_period_open()
            # The item to move is the one this clearing created, identified by
            # the leg that made it — not "whatever is sitting on suspense". Two
            # settlements can leave suspense items on the same statement line,
            # and picking by account would move the wrong one.
            residual_leg = line.leg_ids.filtered(lambda leg: leg.role in ("short", "writeoff"))
            suspense = residual_leg.move_line_id.filtered(lambda aml: aml.account_id == config.suspense_account_id)
            if not suspense:
                raise UserError(
                    _(
                        "Statement line %s has nothing left on suspense from this "
                        "clearing — it has been written off, reconciled or edited "
                        "since the run posted.",
                        st_line.payment_ref or st_line.id,
                    )
                )
            balance = sum(suspense.mapped("debit")) - sum(suspense.mapped("credit"))
            # Compare against the leg's own balance. ``short_amount`` is the
            # *gross* left unmatched; the residual is the balancing figure, which
            # is smaller by the fee that was pro-rated away. Confusing the two is
            # how this guard rejected every legitimate write-off on first write.
            planned = sum(residual_leg.mapped("balance"))
            if abs(balance - planned) > _EPS:
                raise UserError(
                    _(
                        "Statement line %(ref)s has %(actual)s on suspense but the "
                        "clearing planned %(expected)s. Refusing to book a difference "
                        "nobody has looked at.",
                        ref=st_line.payment_ref or st_line.id,
                        actual=balance,
                        expected=planned,
                    )
                )
            analytic = {str(line.analytic_account_id.id): 100.0} if line.analytic_account_id else False
            label = line.writeoff_label or _("Write-off %s", st_line.payment_ref or st_line.id)
            st_line.with_context(force_delete=True, skip_readonly_check=True).write(
                {
                    "line_ids": [
                        (2, suspense.id, 0),
                        (
                            0,
                            0,
                            {
                                "name": label,
                                "account_id": line.writeoff_account_id.id,
                                "partner_id": st_line.partner_id.id,
                                "currency_id": company_currency.id,
                                "amount_currency": balance,
                                "debit": balance if balance > 0 else 0.0,
                                "credit": -balance if balance < 0 else 0.0,
                                "analytic_distribution": analytic,
                            },
                        ),
                    ]
                }
            )
            booked = st_line.move_id.line_ids.filtered(lambda aml: aml.account_id == line.writeoff_account_id).sorted(
                key=lambda aml: aml.id
            )
            if booked:
                residual_leg.write({"role": "writeoff", "move_line_id": booked[-1].id})
        return True

    def action_open_writeoff_wizard(self):
        """Open the write-off screen for the selected settlements."""
        return {
            "type": "ir.actions.act_window",
            "name": _("Write Off Residual"),
            "res_model": "levis.clearing.writeoff.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "levis.pos.clearing.line",
                "active_ids": self.ids,
            },
        }

    def action_suggest_receipts(self):
        """Offer this bank line the whole trading day to tick from.

        Per line, on demand: a month holds ~36.000 candidates and generating them
        all took two minutes, while the question — which transactions make up
        *this* payment — is always asked about one line at a time. Ticked
        receipts are left alone; only the suggestions are refreshed, so a receipt
        freed on another line shows up here the next time this is pressed.

        Takes a recordset so a handful of lines can be worked as a batch from the
        settlement list: the cost is per line either way, and selecting one
        store's twenty lines beats opening them one at a time.
        """
        for run, lines in self.grouped("run_id").items():
            if run.state not in ("computed", "generated"):
                raise UserError(_("Compute the summary first — there is nothing to match yet."))
            run._generate_receipts(lines=lines)
        return True

    def action_open_receipts(self):
        self.ensure_one()
        self.action_suggest_receipts()
        return {
            "type": "ir.actions.act_window",
            "name": _("Receipt Matching — %s", self.move_name or self.payment_ref or ""),
            "res_model": "levis.pos.clearing.receipt",
            "view_mode": "list",
            "domain": [("line_id", "=", self.id)],
            "context": {"create": False},
        }

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
    leg_id = fields.Many2one(
        "levis.pos.clearing.leg",
        readonly=True,
        copy=False,
        ondelete="set null",
        string="Planned Leg",
        help="The planned credit leg that pays this receivable. Filled at stage 2.",
    )
    move_line_id = fields.Many2one(
        "account.move.line",
        readonly=True,
        copy=False,
        string="Clearing Leg",
        help="The credit leg written onto the statement line that pays this "
        "receivable. Filled at posting and used to reconcile the exact pair.",
    )

    @api.model
    def _x24_tender_of_account(self, account):
        """The X70D tender an account represents, from its name, or ``None``.

        ``custom_retail_import`` creates one receivable per tender named
        ``POS Receivable - <TENDER>``; that name is the only link back, since the
        account carries no tender field.
        """
        name = account.with_context(lang="en_US").name or ""
        if not name.startswith(_POS_RECV_PREFIX):
            return None
        return name[len(_POS_RECV_PREFIX) :].strip().upper() or None

    @api.model
    def _x24_rows(self, ou_ids, date_from, date_to, company):
        """``{(analytic_id, date): [(tender, receipt, amount)]}`` from staged X70D rows.

        Every tender of the store's trading day, in one query — the caller decides
        which of them the money actually proves. Silently empty when
        ``custom_retail_import`` is not installed, when its rows were never staged,
        or when a store code has no ``pos.config`` external id: the clearing does
        not depend on any of that, and a missing receipt list must never hold up a
        settlement.
        """
        if not (ou_ids and date_from and date_to) or "retail.import.line" not in self.env:
            return {}
        self.env["retail.import.line"].flush_model()
        self.env.cr.execute(
            """
            SELECT ou, trans_date, tender, store, register, transnum, amount
              FROM (
                    SELECT w.l10n_ou_analytic_id        AS ou,
                           -- A staged row may carry an empty transaction date. The
                           -- CASE is what keeps the cast from ever seeing it: a bare
                           -- WHERE would be free to run after the cast and blow up.
                           CASE WHEN r.j ->> 'trans_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                                THEN (r.j ->> 'trans_date')::date END AS trans_date,
                           upper(r.j ->> 'tender_type') AS tender,
                           r.j ->> 'store_code'         AS store,
                           r.j ->> 'register'           AS register,
                           r.j ->> 'transnum'           AS transnum,
                           CASE WHEN r.j ->> 'tender_amount' ~ '^-?[0-9]+([.][0-9]+)?$'
                                THEN (r.j ->> 'tender_amount')::numeric END AS amount
                      FROM (SELECT l.raw_data_json::json AS j
                              FROM retail_import_line l
                              JOIN retail_import_log g ON g.id = l.log_id
                              JOIN retail_import_profile p ON p.id = g.profile_id
                             WHERE p.file_type = 'x70d'
                               AND p.company_id = %s
                               AND l.raw_data_json IS NOT NULL
                               AND l.raw_data_json LIKE '{%%') r
                      JOIN ir_model_data d
                        ON d.model = 'pos.config'
                       AND d.name = 'posconfig_' || (r.j ->> 'store_code')
                      JOIN pos_config c ON c.id = d.res_id
                      JOIN stock_warehouse w ON w.id = c.warehouse_id
                     WHERE w.l10n_ou_analytic_id IN %s
                   ) s
             WHERE trans_date BETWEEN %s AND %s
               AND amount IS NOT NULL
             ORDER BY store, register, transnum
            """,
            (company.id, tuple(ou_ids), date_from, date_to),
        )
        rows = defaultdict(list)
        for ou, trans_date, tender, store, register, transnum, amount in self.env.cr.fetchall():
            tender = _X24_TENDER_FOLD.get(tender, tender)
            ref = "-".join(part for part in (store, register, transnum) if part)
            rows[(ou, trans_date)].append((tender, ref, round(float(amount), 2)))
        return rows

    @api.model
    def _x24_identify(self, rows, gross):
        """Which receipts of a trading day this settlement proves it paid.

        Returns ``(state, tender, [receipt])``. Only arithmetic counts as proof:

        * ``exact``  — one transaction of exactly this gross;
        * ``batch``  — one tender's whole day sums to exactly this gross;
        * ``ambiguous`` — several of either, all of them listed, none claimed;
        * ``none``   — nothing adds up, and nothing is named.

        Deliberately no subset search. A settlement of 250.900 out of a day
        holding 16.865.300 across ten card transactions can be composed many
        ways, and naming one of them would be a guess wearing a receipt number.
        Listing the day's whole bucket is worse still: that is what this method
        replaced, and it read as though a 250.900 line had paid 3 million.
        """
        if not rows or not gross:
            return "none", False, []
        singles = [(tender, ref) for tender, ref, amount in rows if abs(amount - gross) <= _EPS]
        if len(singles) == 1:
            return "exact", singles[0][0], [singles[0][1]]
        if len(singles) > 1:
            tenders = {tender for tender, _ref in singles}
            return "ambiguous", (tenders.pop() if len(tenders) == 1 else False), [ref for _t, ref in singles]
        buckets = defaultdict(list)
        totals = defaultdict(float)
        for tender, ref, amount in rows:
            buckets[tender].append(ref)
            totals[tender] = round(totals[tender] + amount, 2)
        hits = [tender for tender, total in totals.items() if abs(total - gross) <= _EPS]
        if len(hits) == 1:
            return "batch", hits[0], buckets[hits[0]]
        if len(hits) > 1:
            return "ambiguous", False, [ref for tender in hits for ref in buckets[tender]]
        return self._x24_subset(rows, gross)

    @api.model
    def _x24_subset(self, rows, gross):
        """The one combination of a trading day that adds up to this settlement.

        The doctrine here is unchanged — only arithmetic counts as proof — but a
        combination that is the **only** one possible is arithmetic, not a guess.
        That is the whole distinction: 250.900 out of a day holding 16.865.300
        across ten card transactions can be composed many ways and must stay
        unnamed, while 250.900 out of a day whose only subset summing to it is
        one pair of receipts is as certain as a single transaction of that
        amount.

        Searched per tender, because a combination spanning two tenders would
        name neither. Bounded twice over: buckets larger than
        ``_SUBSET_MAX_ITEMS`` are not searched at all (past that size a day is
        ambiguous in practice, whatever the search says), and the search stops at
        the second solution, which is all it takes to know there is no unique
        one. A tender with more than one solution poisons the whole
        identification rather than deferring to another tender's single one:
        two answers exist, and picking the tidier one would be exactly the guess
        this refuses to make.
        """
        if not rows or not gross:
            return "none", False, []
        target = int(round(gross * 100))
        buckets = defaultdict(list)
        for tender, ref, amount in rows:
            cents = int(round(amount * 100))
            if 0 < cents <= target:
                buckets[tender].append((ref, cents))
        found = []
        for tender, items in buckets.items():
            if len(items) > _SUBSET_MAX_ITEMS or sum(cents for _ref, cents in items) < target:
                continue
            solutions = self._subset_solutions(items, target)
            if not solutions:
                continue
            if len(solutions) > 1 or found:
                # More than one way to make the number: nothing is proven.
                return "none", False, []
            found = [(tender, solutions[0])]
        if not found:
            return "none", False, []
        tender, refs = found[0]
        return "subset", tender, refs

    @api.model
    def _subset_solutions(self, items, target):
        """Up to ``_SUBSET_MAX_SOLUTIONS`` subsets of ``items`` summing to ``target``.

        Meet in the middle rather than a dynamic table over the amount: rupiah
        targets run to eight digits, so a table indexed by money would be
        millions of cells wide, while halving twenty items is 1.024 sums a side.
        """
        half = len(items) // 2
        left, right = items[:half], items[half:]
        sums = defaultdict(list)
        for mask, total in self._subset_totals(left):
            if total <= target:
                sums[total].append(mask)
        out = []
        for mask, total in self._subset_totals(right):
            if total > target:
                continue
            for left_mask in sums.get(target - total, ()):
                if not left_mask and not mask:
                    continue
                refs = [ref for index, (ref, _cents) in enumerate(left) if left_mask >> index & 1]
                refs += [ref for index, (ref, _cents) in enumerate(right) if mask >> index & 1]
                out.append(sorted(refs))
                if len(out) >= _SUBSET_MAX_SOLUTIONS:
                    return out
        return out

    @api.model
    def _subset_totals(self, items):
        """``(mask, total)`` for every subset, each total one addition away from a known one.

        Summing each mask from scratch is 2**n * n additions and turns the search
        into the slowest thing in the run; clearing the lowest bit reaches a
        subset already totalled, which makes it 2**n.
        """
        totals = [0] * (1 << len(items))
        yield 0, 0
        for mask in range(1, 1 << len(items)):
            low = mask & -mask
            totals[mask] = totals[mask ^ low] + items[low.bit_length() - 1][1]
            yield mask, totals[mask]

    @api.model
    def _x24_identify_legs(self, rows, ou_id, legs, claimed=()):
        """Identify the receipts leg by leg, when nothing names the whole payment.

        ``_x24_identify`` asks one question — which transactions add up to the
        *bank's* gross — and answers it inside a single tender, because a
        combination spanning two would name neither. So a settlement that pays
        two tenders at once stays unnamed, even though the split is not in doubt:
        the receivable it consumes is booked per tender per trading day out of
        the very X70D file the receipts come from, and the allocation already
        holds that split as its legs. What the whole-gross question has to search
        for, the legs are given.

        This asks the smaller question once per leg — which of *this* tender's
        transactions on *this* trading day add up to *this* receivable — and
        settles it with the same arithmetic, so nothing weaker than a proof is
        accepted. A leg the day cannot compose names nothing and leaves its share
        of the settlement to the accountant, which is the honest answer: the leg
        amount is a residual whenever several bank lines share one day's
        receivable, and a residual need not be a sum of whole transactions.

        Returns ``({ref: (tender, day, amount)}, legs proven, legs in total)``.
        """
        found = {}
        resolved = 0
        taken = set(claimed)
        for tender, day, amount in legs:
            bucket = [row for row in rows.get((ou_id, day), ()) if row[0] == tender and row[1] not in taken]
            state, _tender, refs = self._x24_identify(bucket, amount)
            if state not in ("exact", "batch", "subset"):
                continue
            resolved += 1
            refs = set(refs)
            for row_tender, ref, row_amount in bucket:
                if ref in refs:
                    found[ref] = (row_tender, day, row_amount)
                    taken.add(ref)
        return found, resolved, len(legs)

    @api.model
    def _x24_format_refs(self, refs, cap):
        """``a, b, c (+7 more)`` — never a silently shortened list."""
        if not refs:
            return False
        if len(refs) <= cap:
            return ", ".join(refs)
        return _("%(refs)s (+%(rest)s more)", refs=", ".join(refs[:cap]), rest=len(refs) - cap)


class LevisPosClearingLeg(models.Model):
    """One journal item the clearing intends to write onto a statement line.

    Stage 2 fills these in and stage 3 books exactly them. Keeping the plan as
    records rather than recomputing it at posting time is what makes the
    accountant's review mean something: what was approved is what gets booked,
    even if the underlying receivables have shifted in the meantime — and if
    they have, the preflight refuses rather than quietly booking something else.
    """

    _name = "levis.pos.clearing.leg"
    _description = "POS Clearing Planned Leg"
    _order = "line_id, sequence, id"

    run_id = fields.Many2one("levis.pos.clearing", required=True, ondelete="cascade", index=True)
    line_id = fields.Many2one("levis.pos.clearing.line", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="run_id.company_id", store=True)
    currency_id = fields.Many2one(related="run_id.currency_id")
    statement_line_id = fields.Many2one(related="line_id.statement_line_id", store=True, string="Statement Line")
    bank_journal_id = fields.Many2one(related="line_id.bank_journal_id", store=True, string="Bank")
    settlement_date = fields.Date(related="line_id.settlement_date", store=True)
    sequence = fields.Integer(default=0)
    role = fields.Selection(
        [
            ("receivable", "POS Receivable"),
            ("mdr", "MDR Expense"),
            ("bank", "Sweep / Charge"),
            ("short", "Left on Suspense"),
            ("writeoff", "Written Off"),
        ],
        required=True,
    )
    account_id = fields.Many2one("account.account", required=True)
    name = fields.Char()
    balance = fields.Monetary(currency_field="currency_id", help="Debit when positive, credit when negative.")
    analytic_distribution = fields.Json()
    alloc_ids = fields.One2many("levis.pos.clearing.alloc", "leg_id", copy=False)
    move_line_id = fields.Many2one(
        "account.move.line",
        readonly=True,
        copy=False,
        string="Journal Item",
        help="What this leg became once posted onto the statement line.",
    )


class LevisPosClearingReceipt(models.Model):
    """One X24DN transaction offered to one bank line, with the tick that settles it.

    The clearing can prove which receipts a settlement paid only when the
    arithmetic is unambiguous — one transaction equal to the gross, or one
    tender's whole trading day. Roughly half of a month's settlements are
    neither: they pay part of a day, and a part can be composed many ways. That
    remainder is precisely the manual work this model exists to hold, so the
    answer lands on a record with an owner and a date instead of in someone's
    spreadsheet.

    Ticked rows are exclusive company-wide: a receipt is paid once. The unique
    index enforces it even against two people ticking at the same moment, and
    ``write`` clears the same receipt off every other line so it stops being
    offered where it can no longer belong.
    """

    _name = "levis.pos.clearing.receipt"
    _description = "POS Clearing Candidate Receipt"
    _order = "line_id, trans_date, ref"

    line_id = fields.Many2one("levis.pos.clearing.line", required=True, ondelete="cascade", index=True)
    run_id = fields.Many2one(related="line_id.run_id", store=True, index=True)
    company_id = fields.Many2one(related="line_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="line_id.currency_id")
    statement_line_id = fields.Many2one(related="line_id.statement_line_id", string="Statement Line")
    bank_journal_id = fields.Many2one(related="line_id.bank_journal_id", string="Bank")
    move_name = fields.Char(related="line_id.move_name", store=True, string="Bank Entry No.")
    settlement_date = fields.Date(related="line_id.settlement_date")
    analytic_account_id = fields.Many2one(related="line_id.analytic_account_id", store=True, string="Operating Unit")
    ref = fields.Char(
        string="Transaction No.",
        required=True,
        index=True,
        help="``store-register-transaction`` — the same reference the POS order carries.",
    )
    tender = fields.Char(help="The tender X70D recorded for this transaction.")
    trans_date = fields.Date(string="Trading Day")
    amount = fields.Monetary(currency_field="currency_id")
    matched = fields.Boolean(
        string="Matched",
        help="This transaction is part of what the bank paid on this line. Ticking "
        "it removes it from every other statement line's suggestions.",
    )
    suggested = fields.Boolean(
        readonly=True,
        help="Ticked by the amount itself: this receipt, or its tender's whole "
        "trading day, equals the settlement exactly.",
    )

    def init(self):
        # A partial unique index, which `_sql_constraints` cannot express: only
        # *ticked* rows are exclusive. Every candidate row is a duplicate of some
        # other line's candidate by design — that is what being offered means.
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS levis_pos_clearing_receipt_matched_uniq
                ON levis_pos_clearing_receipt (company_id, ref) WHERE matched
            """
        )

    def _assert_unclaimed(self, refs_by_company):
        """Refuse a second claim on a receipt, before the database has to.

        The partial unique index is the real guarantee — two people ticking at
        once is exactly what it exists for — but it fires as an integrity error
        halfway through a flush. Checking first is what turns that into a
        sentence naming the bank line that already has this transaction.
        """
        for company_id, refs in refs_by_company.items():
            if not refs:
                continue
            claimed = (
                self.search([("company_id", "=", company_id), ("ref", "in", list(refs)), ("matched", "=", True)]) - self
            )
            if claimed:
                raise UserError(
                    _(
                        "Transaction %(ref)s is already matched to %(entry)s. One "
                        "transaction is paid once — untick it there first.",
                        ref=claimed[0].ref,
                        entry=claimed[0].move_name or claimed[0].line_id.display_name,
                    )
                )
        return True

    def _release_elsewhere(self):
        """Drop these receipts from every other line that was still offering them."""
        matched = self.filtered("matched")
        if not matched:
            return True
        self.search(
            [
                ("company_id", "in", matched.company_id.ids),
                ("ref", "in", matched.mapped("ref")),
                ("id", "not in", matched.ids),
            ]
        ).unlink()
        return True

    @api.model
    def _sweep_claimed(self, company):
        """Delete every candidate whose transaction is ticked on another line.

        One statement instead of a search per receipt: generation creates tens of
        thousands of rows, and the ORM round trips were most of the wall clock.
        """
        self.flush_model()
        self.env.cr.execute(
            """
            DELETE FROM levis_pos_clearing_receipt loose
                  USING levis_pos_clearing_receipt taken
                  WHERE loose.company_id = %s
                    AND NOT loose.matched
                    AND taken.matched
                    AND taken.company_id = loose.company_id
                    AND taken.ref = loose.ref
            """,
            (company.id,),
        )
        self.invalidate_model()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        Line = self.env["levis.pos.clearing.line"]
        wanted = defaultdict(set)
        seen = set()
        for vals in vals_list:
            if not vals.get("matched"):
                continue
            company = Line.browse(vals.get("line_id")).company_id
            key = (company.id, vals.get("ref"))
            if key in seen:
                raise UserError(_("Transaction %s cannot be matched to two bank lines at once.", vals.get("ref")))
            seen.add(key)
            wanted[company.id].add(vals.get("ref"))
        self._assert_unclaimed(wanted)
        receipts = super().create(vals_list)
        if not self.env.context.get("levis_skip_receipt_release"):
            receipts._release_elsewhere()
        return receipts

    def write(self, vals):
        if vals.get("matched"):
            wanted = defaultdict(set)
            for receipt in self.filtered(lambda r: not r.matched):
                wanted[receipt.company_id.id].add(receipt.ref)
            self._assert_unclaimed(wanted)
        result = super().write(vals)
        if vals.get("matched"):
            self._release_elsewhere()
        return result

    def action_match(self):
        self.write({"matched": True})
        return True

    def action_unmatch(self):
        """Untick it. It is free again everywhere the next time a line asks.

        Deliberately does not re-offer it across the run here: the suggestions
        are built per bank line on demand, so the receipt reappears wherever it
        belongs as soon as that line is opened — without a two-minute sweep of a
        month's transactions on the way out of a checkbox.
        """
        self.write({"matched": False})
        return True


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
