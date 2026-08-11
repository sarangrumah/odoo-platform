# -*- coding: utf-8 -*-
"""Which store a bank settlement belongs to.

The bank narrative names the store, but truncated and inconsistently — the same
outlet appears as ``LEVIS PLAZA SENAYA``, ``LEVIS SENAYAN CITY`` and
``LEVIS SENAYA``, and BRI cuts at 13 characters (``LEVIS KE`` is Kelapa Gading).
Matching on that text would silently attribute one store's money to another, so
it is never used as the key. The merchant/terminal id is: it is numeric, stable,
and printed on every card and QRIS settlement.

Cash deposits are the exception — they arrive as an internet-banking transfer
whose only clue is free text a cashier typed (``cash sales pvj``,
``setoran ols CP``, ``WSID:ZT481``). Those are matched by an explicit keyword
rule that Finance creates once per wording. A deposit matching no rule is left
unattributed on suspense rather than guessed onto a store.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Shorter than this and a "suffix match" would collide across merchants.
_MIN_SUFFIX_LEN = 6


class LevisBankMidMap(models.Model):
    _name = "levis.bank.mid.map"
    _description = "Bank MID / Terminal to Store Mapping"
    _order = "sequence, match_type, key"

    name = fields.Char(required=True, help='Free label, e.g. "BCA debit — Senayan City".')
    company_id = fields.Many2one(
        "res.company",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank Journal",
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        help="Restrict this rule to one bank feed. Leave empty to match any.",
    )
    match_type = fields.Selection(
        [
            ("mid", "Bank MID"),
            ("tid", "Terminal / TID"),
            ("keyword", "Narrative Keyword"),
        ],
        required=True,
        default="mid",
    )
    key = fields.Char(
        required=True,
        help="For MID/TID the number as the bank prints it — leading zeros and "
        "the acquirer prefix are ignored when matching. For a keyword, any text "
        "that appears in the narrative (case-insensitive).",
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        required=True,
        help="The store analytic stamped on every leg of this settlement's entry.",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        help="Convenience only: picking a warehouse fills the Operating Unit from it.",
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
        help="Reporting only — the receivable account is discovered from the open POS lines, never from this field.",
    )
    sequence = fields.Integer(default=10, help="Precedence between competing keyword rules.")
    active = fields.Boolean(default=True)
    date_start = fields.Date(help="First settlement date this rule applies to.")
    date_end = fields.Date(help="Last settlement date this rule applies to, e.g. when a MID is reassigned.")
    note = fields.Text()

    _key_uniq = models.Constraint(
        # Present in Postgres, and it has never once fired: ``journal_id`` is NULL
        # on every rule anyone has created, and Postgres treats NULLs as
        # distinct, so the row simply never collides. It also compares the raw
        # string, so ``1999632289`` and ``001999632289`` are two values to it and
        # one terminal to us. Kept because it costs nothing and does catch the
        # journal-scoped case; the real guard is ``_check_no_colliding_rule``.
        "unique(company_id, journal_id, match_type, key)",
        "This MID / terminal / keyword is already mapped for that bank journal.",
    )

    # ------------------------------------------------------------------
    # No two rules may claim the same terminal
    # ------------------------------------------------------------------
    @api.constrains("key", "match_type", "company_id", "journal_id", "date_start", "date_end", "active")
    def _check_no_colliding_rule(self):
        """Refuse a rule that competes with an existing one for the same feed.

        The point is not tidiness. Two rules for one terminal pointing at
        different stores means ``_resolve`` picks by sort order, so which shop
        gets the money is an accident of ``sequence, match_type, key`` — and this
        has already happened here: ``4608375`` and ``885004608375`` once sat side
        by side in prd_levis_begbal, saved only by both naming the same store.

        The comparison is ``_keys_match``, the resolver's own function, rather
        than a re-implementation. A unique index cannot express this: the
        resolver accepts a suffix from six digits up, so ``4608375`` and
        ``885004608375`` are one terminal to it and two values to an index.

        Three things deliberately do NOT collide:

        * **Non-overlapping dates.** ``date_end`` exists so a MID can be handed
          from one store to another; refusing that would break the feature the
          field was added for.
        * **Disjoint journals.** Two rules restricted to different bank feeds
          never compete — ``_resolve`` only considers ``journal_id in (False,
          this feed)``. A global rule does compete with everything.
        * **Keyword substrings.** Cash narratives are matched by containment and
          ordered by ``sequence``; "ols" inside "setoran ols pvj" is the design,
          not a fault. Only an identical keyword is refused.
        """
        for rule in self:
            for other in rule._colliding_rules():
                raise ValidationError(rule._collision_message(other))

    def _colliding_rules(self):
        """Existing rules this one would compete with. Empty when it is safe."""
        self.ensure_one()
        if self.env.context.get("levis_skip_mid_map_guard"):
            # Deliberate override, e.g. a data migration that knows it is moving
            # a terminal. Logged, because a silent escape hatch becomes the
            # normal way in about three months.
            _logger.warning(
                "levis.bank.mid.map: collision guard skipped for %s (key %s) by user %s",
                self.display_name,
                self.key,
                self.env.user.login,
            )
            return self.browse()
        if not self.active:
            return self.browse()
        candidates = self.search(
            [
                ("id", "!=", self.id),
                ("company_id", "=", self.company_id.id),
                ("match_type", "=", self.match_type),
            ]
        )
        return candidates.filtered(lambda other: self._competes_with(other))

    def _competes_with(self, other):
        """True when ``other`` could answer for the same settlement as this rule."""
        self.ensure_one()
        if not self._journals_overlap(other) or not self._dates_overlap(other):
            return False
        if self.match_type == "keyword":
            return (self.key or "").strip().lower() == (other.key or "").strip().lower()
        return self._keys_match(self._normalise_key(other.key), self._normalise_key(self.key))

    def _journals_overlap(self, other):
        """A rule with no journal competes with every feed, hence with all rules."""
        self.ensure_one()
        return not self.journal_id or not other.journal_id or self.journal_id == other.journal_id

    def _dates_overlap(self, other):
        """Half-open on both ends: an empty bound means "forever" in that direction."""
        self.ensure_one()
        starts_after_other_ended = self.date_start and other.date_end and self.date_start > other.date_end
        ends_before_other_started = self.date_end and other.date_start and self.date_end < other.date_start
        return not (starts_after_other_ended or ends_before_other_started)

    def _collision_shape(self, other):
        """Which of the three collisions this is — they need different fixes."""
        self.ensure_one()
        if self.match_type == "keyword":
            return _("the same keyword")
        mine, theirs = self._normalise_key(self.key), self._normalise_key(other.key)
        if mine == theirs:
            if (self.key or "") == (other.key or ""):
                return _("the same key")
            return _("the same terminal written differently (%(mine)s vs %(theirs)s)", mine=self.key, theirs=other.key)
        return _("a terminal whose digits end the same (%(mine)s vs %(theirs)s)", mine=self.key, theirs=other.key)

    def _collision_message(self, other):
        self.ensure_one()
        same_store = self.analytic_account_id == other.analytic_account_id
        return _(
            "%(shape)s is already mapped by %(other)s → %(other_store)s.\n\n"
            "This rule would send it to %(mine_store)s instead. The settlement "
            "would be attributed by sort order, not by evidence — which store "
            "gets the money would be an accident.\n\n"
            "%(advice)s",
            shape=self._collision_shape(other).capitalize(),
            other=other.name or other.key,
            other_store=other.analytic_account_id.display_name or _("no Operating Unit"),
            mine_store=self.analytic_account_id.display_name or _("no Operating Unit"),
            advice=(
                _(
                    "Both rules name the same store, so nothing is misdirected today — "
                    "but keep only one, or a later edit will change one and leave the other."
                )
                if same_store
                else _(
                    "Correct whichever is wrong, or close the old one with an end date "
                    "if the terminal really was handed over to another store."
                )
            ),
        )

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        for rec in self:
            if rec.warehouse_id.l10n_ou_analytic_id:
                rec.analytic_account_id = rec.warehouse_id.l10n_ou_analytic_id

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------
    @api.model
    def _normalise_key(self, raw):
        """Digits only, without the leading zeros the bank pads with."""
        digits = "".join(ch for ch in (raw or "") if ch.isdigit())
        return digits.lstrip("0")

    @api.model
    def _keys_match(self, mapped, parsed):
        """True when two merchant ids denote the same terminal.

        BCA prints the same merchant as ``885004608375`` on the debit feed and
        ``004608375`` on the credit-card feed — the longer form carries an
        acquirer prefix. So a suffix match is accepted, but only from
        ``_MIN_SUFFIX_LEN`` digits up, below which distinct merchants collide.
        """
        if not (mapped and parsed):
            return False
        if mapped == parsed:
            return True
        long_key, short_key = (mapped, parsed) if len(mapped) >= len(parsed) else (parsed, mapped)
        return len(short_key) >= _MIN_SUFFIX_LEN and long_key.endswith(short_key)

    @api.model
    def _candidates(self, company, journal):
        return self.search(
            [
                ("company_id", "=", company.id),
                ("journal_id", "in", [False, journal.id]),
            ]
        )

    @api.model
    def _resolve(self, company, journal, parsed, date, candidates=None):
        """The rule for one parsed narrative, or an empty recordset.

        MID beats TID beats keyword, because a number is evidence and a word is
        a convention. Returns at most one record.
        """
        rules = candidates if candidates is not None else self._candidates(company, journal)
        rules = rules.filtered(
            lambda r: (
                (not r.date_start or not date or r.date_start <= date)
                and (not r.date_end or not date or date <= r.date_end)
            )
        )
        for match_type, value in (("mid", parsed.get("mid")), ("tid", parsed.get("tid"))):
            if not value:
                continue
            wanted = self._normalise_key(value)
            hit = rules.filtered(
                lambda r, w=wanted, t=match_type: r.match_type == t and self._keys_match(self._normalise_key(r.key), w)
            )
            if hit:
                return hit[0]
        # A MID that exists but is unmapped must not fall through to a keyword:
        # the free text of a card settlement is the truncated store name, and
        # fuzzy-matching that is exactly what this model exists to avoid.
        if parsed.get("mid") or parsed.get("tid"):
            return self.browse()
        haystack = (parsed.get("keyword") or parsed.get("raw") or "").lower()
        if not haystack:
            return self.browse()
        hits = rules.filtered(lambda r: r.match_type == "keyword" and r.key and r.key.lower() in haystack)
        if not hits:
            return self.browse()
        # The most specific keyword wins, not the first row off the recordset.
        #
        # ``_order`` is "sequence, match_type, key", and every keyword rule in
        # prd_levis_begbal carries sequence 20 — so the tie was being broken
        # ALPHABETICALLY. "SMB SOPIAN PERMANA" beat "SOPIAN PERMANA" only because
        # M sorts before O; rename the store prefix to something late in the
        # alphabet and the generic rule wins instead, sending one shop's cash to
        # another. The two rules name different stores, and "SMB SOPIAN PERMANA"
        # is sitting in the not-yet-mapped list waiting to be added.
        #
        # Sequence stays the primary discriminator so it keeps meaning what its
        # help text says — an explicit override. Length only settles the tie,
        # and the key itself only makes the outcome deterministic.
        return min(hits, key=lambda r: (r.sequence, -len(r.key or ""), r.key or ""))

    def _ou_distribution(self):
        self.ensure_one()
        return {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else False

    @api.depends("match_type", "key", "analytic_account_id")
    def _compute_display_name(self):
        labels = dict(self._fields["match_type"]._description_selection(self.env))
        for rec in self:
            rec.display_name = _(
                "%(label)s [%(kind)s %(key)s]",
                label=rec.name or rec.analytic_account_id.display_name or "",
                kind=labels.get(rec.match_type, rec.match_type or ""),
                key=rec.key or "",
            )
