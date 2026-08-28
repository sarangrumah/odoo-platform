# -*- coding: utf-8 -*-
"""Turn a period's unmapped settlements into mapping rules, biggest money first.

Mapping 44 merchant ids by hand from a bank statement is the kind of task that
gets abandoned halfway, and a half-mapped table means money silently parked on
suspense. So the wizard does the reading: it parses the period, keeps only what
no rule matches, groups it, and asks for the one thing it cannot know — which
store each id belongs to.

The truncated store name from the narrative is offered as a *suggestion* for the
Operating Unit. It is never applied on its own: ``LEVIS PLAZA SENAYA`` and
``LEVIS SENAYAN CITY`` are different shops whose names collide under truncation,
which is the whole reason this table exists.
"""

from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LevisBankMidMapWizard(models.TransientModel):
    _name = "levis.bank.mid.map.wizard"
    _description = "Map Unmapped Bank Settlements"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    run_id = fields.Many2one("levis.pos.clearing", string="Clearing Run")
    date_from = fields.Date(required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(required=True, default=lambda self: self._default_date_to())
    journal_ids = fields.Many2many(
        "account.journal",
        string="Bank Journals",
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
    )
    line_ids = fields.One2many("levis.bank.mid.map.wizard.line", "wizard_id")
    unmapped_line_count = fields.Integer(compute="_compute_unmapped", string="Statement Lines")
    unmapped_total = fields.Monetary(
        compute="_compute_unmapped",
        currency_field="currency_id",
        string="Bank Amount",
        help="What the bank actually moved on those statement lines \u2014 the figure "
        "that ties to the account mutation, net of the acquirer fee.",
    )
    unmapped_gross = fields.Monetary(
        compute="_compute_unmapped",
        currency_field="currency_id",
        string="Narrative Gross",
        help="The takings the narratives claim, before the acquirer fee.",
    )
    unmapped_mdr = fields.Monetary(
        compute="_compute_unmapped",
        currency_field="currency_id",
        string="Narrative MDR",
    )
    unmapped_gap = fields.Monetary(
        compute="_compute_unmapped",
        currency_field="currency_id",
        string="Unexplained",
        help="Bank amount minus (gross \u2212 MDR). Anything other than zero means a "
        "narrative does not add up to the money that moved.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    scanned = fields.Boolean(default=False)

    @api.depends(
        "line_ids.line_count",
        "line_ids.total_amount",
        "line_ids.gross_total",
        "line_ids.mdr_total",
        "line_ids.narrative_gap",
    )
    def _compute_unmapped(self):
        for wizard in self:
            wizard.unmapped_line_count = sum(wizard.line_ids.mapped("line_count"))
            wizard.unmapped_total = sum(wizard.line_ids.mapped("total_amount"))
            wizard.unmapped_gross = sum(wizard.line_ids.mapped("gross_total"))
            wizard.unmapped_mdr = sum(wizard.line_ids.mapped("mdr_total"))
            wizard.unmapped_gap = sum(wizard.line_ids.mapped("narrative_gap"))

    @api.model
    def _default_date_from(self):
        """Last month, so the standalone menu entry opens on something real."""
        return (fields.Date.context_today(self).replace(day=1) - timedelta(days=1)).replace(day=1)

    @api.model
    def _default_date_to(self):
        return fields.Date.context_today(self).replace(day=1) - timedelta(days=1)

    # ------------------------------------------------------------------
    def action_scan(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("The end date precedes the start date."))
        self.line_ids.unlink()
        Narrative = self.env["levis.bank.narrative"]
        MidMap = self.env["levis.bank.mid.map"]
        journals = self.journal_ids or self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.company_id.id)]
        )
        statement_lines = self.env["account.bank.statement.line"].search(
            [
                ("journal_id", "in", journals.ids),
                ("company_id", "=", self.company_id.id),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("move_id.state", "=", "posted"),
            ]
        )
        rules_cache = {}
        buckets = defaultdict(
            lambda: {
                "count": 0,
                "amount": 0.0,
                "gross": 0.0,
                "mdr": 0.0,
                "sample": "",
                "narrative": "",
                "statement_ids": [],
            }
        )
        for statement_line in statement_lines:
            journal = statement_line.journal_id
            if journal.id not in rules_cache:
                rules_cache[journal.id] = MidMap._candidates(self.company_id, journal)
            parsed = Narrative.parse(journal, statement_line.payment_ref, statement_line.amount, statement_line.date)
            if parsed["kind"] not in ("settlement", "cash_deposit"):
                continue
            if MidMap._resolve(
                self.company_id, journal, parsed, statement_line.date, candidates=rules_cache[journal.id]
            ):
                continue
            # Channel is deliberately NOT part of the key. One merchant id serves
            # the debit, credit-card and QRIS feeds of the same shop, and the rule
            # answers "which store", not "which tender" — the tender is discovered
            # from the open receivables.
            if parsed["mid"]:
                key = (journal.id, "mid", MidMap._normalise_key(parsed["mid"]))
            elif parsed["tid"]:
                key = (journal.id, "tid", MidMap._normalise_key(parsed["tid"]))
            else:
                key = (journal.id, "keyword", (parsed["keyword"] or "")[:80])
            bucket = buckets[key]
            bucket["count"] += 1
            bucket["amount"] += statement_line.amount
            # The narrative's own figures, kept next to the bank's. A group is a
            # sum over many statement lines while only one narrative is shown as a
            # sample, so the bank amount on its own cannot be checked against any
            # single line of the account mutation. Gross and MDR alongside it can:
            # gross - MDR is what the bank should have moved.
            bucket["gross"] += parsed["gross"] or 0.0
            bucket["mdr"] += parsed["mdr"] or 0.0
            bucket["statement_ids"].append(statement_line.id)
            bucket.setdefault("channels", set()).add(parsed["channel"])
            # What to look for in the stores' own takings: the gross the narrative
            # quotes where there is one, and the bank amount where there is not —
            # a cash deposit quotes nothing, and the sum banked IS the takings.
            bucket.setdefault("probes", []).append(
                (
                    round(parsed["gross"] or statement_line.amount, 2),
                    statement_line.date,
                    parsed["kind"] == "cash_deposit",
                )
            )
            if not bucket["sample"]:
                bucket["sample"] = statement_line.payment_ref or ""
                bucket["narrative"] = self._store_hint(statement_line.payment_ref or "")

        buckets = self._merge_equivalent_keys(buckets)
        # Biggest money first: if the mapping session is cut short, the part that
        # got done is the part that matters.
        ordered = sorted(buckets.items(), key=lambda item: -abs(item[1]["amount"]))
        analytics = self.env["account.analytic.account"].search([])
        evidence = self._evidence_suggestions(buckets)
        self.line_ids = [
            (
                0,
                0,
                {
                    "journal_id": journal_id,
                    "match_type": match_type,
                    "key": key,
                    "channel": self._dominant_channel(bucket.get("channels")),
                    "line_count": bucket["count"],
                    "total_amount": bucket["amount"],
                    "gross_total": bucket["gross"],
                    "mdr_total": bucket["mdr"],
                    "statement_line_ids": [(6, 0, bucket["statement_ids"])],
                    "sample_narrative": bucket["sample"],
                    # Evidence first, the name only as a last resort: store names
                    # in narratives are abbreviations that collide, which is the
                    # reason this table exists at all.
                    "analytic_account_id": (
                        evidence.get((journal_id, match_type, key), {}).get("analytic_id")
                        or self._suggest_analytic(bucket["narrative"], analytics).id
                        or False
                    ),
                    "evidence_note": evidence.get((journal_id, match_type, key), {}).get("note") or False,
                },
            )
            for (journal_id, match_type, key), bucket in ordered
        ]
        self.scanned = True
        return self._reopen()

    @api.model
    def _merge_equivalent_keys(self, buckets):
        """Fold merchant ids that denote the same terminal into one proposal.

        BCA prints one merchant two ways — ``885004608375`` on the debit feed and
        ``004608375`` on the credit-card feed. They are the same shop, and
        ``_keys_match`` resolves both against the longer form, so proposing two
        rules would just be two chances to disagree with yourself (and they would
        collide on the uniqueness constraint if the shorter one were kept too).
        """
        MidMap = self.env["levis.bank.mid.map"]
        merged = {}
        for key, bucket in sorted(buckets.items(), key=lambda item: -len(item[0][2] or "")):
            journal_id, match_type, value = key
            if match_type == "keyword":
                merged[key] = bucket
                continue
            target = None
            for existing in merged:
                if existing[0] != journal_id or existing[1] != match_type:
                    continue
                if MidMap._keys_match(existing[2], value):
                    target = existing
                    break
            if target is None:
                merged[key] = dict(bucket)
                continue
            into = merged[target]
            into["count"] += bucket["count"]
            into["amount"] += bucket["amount"]
            into["gross"] += bucket.get("gross") or 0.0
            into["mdr"] += bucket.get("mdr") or 0.0
            into["statement_ids"] = list(into.get("statement_ids") or ()) + list(bucket.get("statement_ids") or ())
            into.setdefault("channels", set()).update(bucket.get("channels") or ())
            into.setdefault("probes", []).extend(bucket.get("probes") or ())
            if not into.get("sample"):
                into["sample"] = bucket.get("sample")
                into["narrative"] = bucket.get("narrative")
        return merged

    @api.model
    def _dominant_channel(self, channels):
        """One label for a rule that may cover several tenders."""
        channels = set(channels or ())
        if not channels:
            return False
        for preferred in ("cash", "credit", "debit", "qris", "transfer"):
            if preferred in channels:
                return preferred if len(channels) == 1 else "other"
        return "other"

    @api.model
    def _store_hint(self, payment_ref):
        """The part of a narrative that looks like a store name."""
        text = " ".join((payment_ref or "").split())
        for marker in ("TGH", "QR ", "QR:", "AMT", "ADM", "DDR", "MDR"):
            index = text.upper().find(marker)
            if index > 0:
                text = text[:index]
        return " ".join(word for word in text.split() if not word.isdigit())

    def _evidence_suggestions(self, buckets):
        """Which store's own takings account for this group's money.

        The narrative names a store the way a cashier would — ``LEVIS GANCIT``
        for Gandaria City, ``LEVIS BIP`` for Bandung Indah Plaza — and most cash
        deposits name only the person who walked to the bank. Neither can be
        matched against an Operating Unit called ``OLS SES - ...``: there is no
        word in common, and guessing from initials misdirects money between
        shops.

        The takings can be matched. X70D stages every transaction per store, day
        and tender, so a deposit of 1.234.567 that equals exactly one store's
        cash for exactly one trading day says which shop it came from — without
        reading the name at all. A figure that fits two shops proves nothing and
        is dropped rather than broken by a tie-break.

        Returns ``{bucket key: {analytic_id, note}}`` and stays silent when
        ``custom_retail_import`` is absent or its rows were never staged.
        """
        self.ensure_one()
        Alloc = self.env["levis.pos.clearing.alloc"]
        # The Operating Unit lives on the warehouse, and that field belongs to the
        # OU module. Absent it there is no store axis at all, and the wizard falls
        # back to reading names — which is where it started.
        if "l10n_ou_analytic_id" not in self.env["stock.warehouse"]._fields:
            return {}
        analytic_ids = set(
            self.env["stock.warehouse"]
            .search([("company_id", "=", self.company_id.id)])
            .mapped("l10n_ou_analytic_id")
            .ids
        )
        if not analytic_ids:
            return {}
        lag = timedelta(days=7)
        rows = Alloc._x24_rows(analytic_ids, self.date_from - lag, self.date_to, self.company_id)
        if not rows:
            return {}
        # Two indexes, both keyed on money: one transaction of that amount, and
        # one tender's whole day of that amount. Cash is banked as a day's total,
        # cards settle either way.
        singles = defaultdict(set)
        tender_days = defaultdict(set)
        for (analytic_id, _day), items in rows.items():
            totals = defaultdict(float)
            for tender, _ref, amount in items:
                singles[round(amount, 2)].add(analytic_id)
                totals[tender] = round(totals[tender] + amount, 2)
            for tender, total in totals.items():
                tender_days[(self._is_cash_tender(tender), total)].add(analytic_id)
        out = {}
        for key, bucket in buckets.items():
            votes = defaultdict(int)
            for amount, _date, is_cash in bucket.get("probes") or ():
                if not amount:
                    continue
                # A day's total for cash, a day's total or a single transaction
                # for cards. Only a figure that fits ONE store votes.
                fits = set(tender_days.get((is_cash, amount), ()))
                if not is_cash:
                    fits |= singles.get(amount, set())
                if len(fits) == 1:
                    votes[fits.pop()] += 1
            if not votes:
                continue
            ranked = sorted(votes.items(), key=lambda item: -item[1])
            best, best_votes = ranked[0]
            runner_up = ranked[1][1] if len(ranked) > 1 else 0
            # A clear winner, not a plurality: a store that explains half this
            # group's lines while another explains the other half is two rules
            # sharing one merchant id, and that has to be looked at by a person.
            if best_votes <= runner_up:
                continue
            out[key] = {
                "analytic_id": best,
                "note": _(
                    "%(votes)s of %(total)s statement line(s) match this store's own "
                    "takings exactly%(rival)s.",
                    votes=best_votes,
                    total=len(bucket.get("probes") or ()),
                    rival=_(", against %s for the next best", runner_up) if runner_up else "",
                ),
            }
        return out

    @api.model
    def _is_cash_tender(self, tender):
        """X70D names the cash tender in its own words; only the word is certain."""
        return "CASH" in (tender or "").upper()

    @api.model
    def _suggest_analytic(self, hint, analytics):
        """Longest word-overlap with an Operating Unit name — a suggestion only."""
        words = {word for word in (hint or "").upper().split() if len(word) > 2 and word != "LEVIS"}
        if not words:
            return self.env["account.analytic.account"]
        best, best_score = self.env["account.analytic.account"], 0
        for analytic in analytics:
            name = (analytic.display_name or "").upper()
            score = sum(len(word) for word in words if word in name)
            if score > best_score:
                best, best_score = analytic, score
        return best

    def action_apply(self):
        self.ensure_one()
        todo = self.line_ids.filtered(lambda line: line.analytic_account_id and not line.skip)
        if not todo:
            raise UserError(_("Nothing to apply — no Operating Unit was picked."))
        self.env["levis.bank.mid.map"].create(
            [
                {
                    "name": line.suggested_name(),
                    "company_id": self.company_id.id,
                    "journal_id": line.journal_id.id,
                    "match_type": line.match_type,
                    "key": line.key,
                    "channel": line.channel,
                    "analytic_account_id": line.analytic_account_id.id,
                    "note": _(
                        "Created from statement scan %(start)s..%(end)s. Sample: %(sample)s",
                        start=self.date_from,
                        end=self.date_to,
                        sample=line.sample_narrative,
                    ),
                }
                for line in todo
            ]
        )
        if self.run_id and self.run_id.state in ("draft", "computed"):
            self.run_id.action_compute()
            return {
                "type": "ir.actions.act_window",
                "res_model": "levis.pos.clearing",
                "res_id": self.run_id.id,
                "view_mode": "form",
            }
        return {"type": "ir.actions.act_window_close"}

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }


class LevisBankMidMapWizardLine(models.TransientModel):
    _name = "levis.bank.mid.map.wizard.line"
    _description = "Unmapped Bank Settlement Group"
    _order = "total_amount desc"

    wizard_id = fields.Many2one("levis.bank.mid.map.wizard", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    journal_id = fields.Many2one("account.journal", string="Bank", readonly=True)
    match_type = fields.Selection(
        [("mid", "Bank MID"), ("tid", "Terminal / TID"), ("keyword", "Narrative Keyword")],
        readonly=True,
    )
    key = fields.Char(
        help="Editable for keyword rules: shorten it to the part that actually names "
        'the store (e.g. just "pvj") so next month\'s deposits match the same rule '
        "instead of needing a new one. MID and terminal keys should be left alone.",
    )
    channel = fields.Selection(
        [
            ("debit", "Debit Card"),
            ("credit", "Credit Card"),
            ("qris", "QRIS"),
            ("cash", "Cash Deposit"),
            ("transfer", "Transfer"),
            ("other", "Other"),
        ],
        readonly=True,
    )
    line_count = fields.Integer(string="Statement Lines", readonly=True)
    total_amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        string="Bank Amount",
        help="The sum of the account mutation over every statement line in this "
        "group \u2014 net of the acquirer fee, which is why it is smaller than the "
        "gross the narratives quote. Open the lines to see them one by one.",
    )
    gross_total = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        string="Narrative Gross",
        help="What the narratives (TGH) claim was taken, before the fee.",
    )
    mdr_total = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        string="Narrative MDR",
        help="What the narratives (ADM / DDR) claim the acquirer kept.",
    )
    narrative_gap = fields.Monetary(
        compute="_compute_narrative_gap",
        currency_field="currency_id",
        string="Unexplained",
        help="Bank amount minus (gross \u2212 MDR). Zero means every narrative in "
        "this group adds up to the money the bank moved. A cash deposit quotes no "
        "gross at all, so its whole amount shows here \u2014 that is expected.",
    )
    statement_line_ids = fields.Many2many(
        "account.bank.statement.line",
        string="Bank Lines",
        readonly=True,
        help="Every statement line behind this group's totals.",
    )
    sample_narrative = fields.Char(readonly=True, string="Sample Narrative")
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        help="Pre-filled from the store's own takings where the amounts identify "
        "it, and from the store name in the narrative otherwise. Check it — "
        "abbreviated names collide between stores.",
    )
    evidence_note = fields.Char(
        readonly=True,
        string="Why",
        help="How the Operating Unit was arrived at, when it was the takings that "
        "said so rather than the wording. Empty means the name was guessed and "
        "nothing corroborates it.",
    )
    warehouse_id = fields.Many2one("stock.warehouse")
    skip = fields.Boolean(help="Leave unmapped for now; the money stays on suspense.")

    @api.depends("total_amount", "gross_total", "mdr_total")
    def _compute_narrative_gap(self):
        for line in self:
            line.narrative_gap = line.total_amount - (line.gross_total - line.mdr_total)

    def action_open_statement_lines(self):
        """The mutation behind the total, so the figure can be checked line by line.

        A proposal is a sum over a whole period's feed for one merchant id; the
        sample narrative next to it belongs to exactly one of those lines. Without
        this the two can never be reconciled by eye, and the total reads as if it
        disagreed with the bank.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bank Lines \u2014 %s", self.key or self.journal_id.display_name),
            "res_model": "account.bank.statement.line",
            "domain": [("id", "in", self.statement_line_ids.ids)],
            "view_mode": "list,form",
            "target": "current",
        }

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        for line in self:
            if line.warehouse_id.l10n_ou_analytic_id:
                line.analytic_account_id = line.warehouse_id.l10n_ou_analytic_id

    def suggested_name(self):
        self.ensure_one()
        labels = dict(self._fields["channel"]._description_selection(self.env))
        return "%s %s — %s" % (
            self.journal_id.code or "",
            labels.get(self.channel, self.channel or ""),
            self.analytic_account_id.display_name or "",
        )
