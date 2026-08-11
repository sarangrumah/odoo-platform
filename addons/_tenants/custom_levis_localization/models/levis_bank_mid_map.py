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

from odoo import _, api, fields, models

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
        "unique(company_id, journal_id, match_type, key)",
        "This MID / terminal / keyword is already mapped for that bank journal.",
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
        hit = rules.filtered(lambda r: r.match_type == "keyword" and r.key and r.key.lower() in haystack)
        return hit[0] if hit else self.browse()

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
