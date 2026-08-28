# -*- coding: utf-8 -*-
"""What a narrative meant last time somebody decided.

``levis.bank.mid.map`` holds rules a human wrote deliberately. This holds
something weaker: an observation that a particular wording has, more than once,
turned out to belong to one store. It exists because the same free-text memo
comes back month after month — a store's cash deposit is banked with the same
words every week — and re-deciding it every time is the manual work this feature
is meant to remove.

**It is a suggestion, never an attribution.** A hint can put a store in front of
an operator to confirm; it cannot map money on its own. That distinction is the
whole safety story, and it is enforced by the caller: hints resolve at
``strong`` confidence, and anything short of an exact identification leaves the
line unmapped until a human says otherwise.

The fingerprint is ``levis.bank.narrative._strip_noise`` of the payment
reference, lowered. That helper already removes transfer-reference blobs, dates
and every number, which is exactly right here: what remains is the words a
cashier typed, and those are what repeat. Two deposits of different amounts on
different days from the same store fingerprint identically, which is the point.

**A hint that has ever been wrong is worse than no hint**, so a fingerprint seen
pointing at two different stores is deactivated rather than re-scored. Being
occasionally right is not a useful property for something that names whose money
this is.
"""

import hashlib

from odoo import _, api, fields, models


class LevisBankNarrativeHint(models.Model):
    _name = "levis.bank.narrative.hint"
    _description = "Learned Bank Narrative Hint"
    _order = "hit_count desc, last_seen desc"

    company_id = fields.Many2one("res.company", required=True, ondelete="cascade", index=True)
    journal_id = fields.Many2one("account.journal", string="Bank Journal", index=True)
    fingerprint = fields.Char(required=True, index=True)
    sample_text = fields.Char(
        string="Sample Wording",
        help="A narrative that produced this fingerprint, kept so a human can see what the hint is actually about.",
    )
    analytic_account_id = fields.Many2one("account.analytic.account", string="Operating Unit", required=True)
    hit_count = fields.Integer(default=1)
    last_seen = fields.Date()
    source = fields.Selection(
        [
            ("store_code", "Store Code in Narrative"),
            ("deposit", "Validated Cash Deposit"),
            ("keyword", "Keyword Rule"),
            ("manual", "Confirmed by Hand"),
        ],
        required=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Char()

    _fingerprint_uniq = models.Constraint(
        "unique(company_id, journal_id, fingerprint)",
        "That narrative fingerprint is already recorded for this bank.",
    )

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------
    @api.model
    def _fingerprint_of(self, payment_ref):
        """A stable key for the words in a narrative, or empty.

        Empty when the narrative reduces to nothing — an all-numeric memo has no
        words to learn from, and hashing the empty string would collide every
        such line onto one hint.
        """
        stripped = (self.env["levis.bank.narrative"]._strip_noise(payment_ref or "") or "").strip().lower()
        if len(stripped) < 4:
            return False
        # usedforsecurity=False: this is a dedup key for a piece of free text, not
        # a signature or a password. Nothing trusts it, nothing authenticates
        # with it, and a collision would at worst offer the wrong store to a
        # human who has to confirm it anyway. Saying so explicitly beats
        # suppressing bandit's warning.
        return hashlib.sha1(stripped.encode("utf-8"), usedforsecurity=False).hexdigest()

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------
    @api.model
    def _learn(self, company, journal, payment_ref, analytic, source, when=None):
        """Record, or reinforce, what this wording turned out to mean."""
        fingerprint = self._fingerprint_of(payment_ref)
        if not fingerprint or not analytic or not company:
            return self.browse()
        existing = self.sudo().search(
            [
                ("company_id", "=", company.id),
                ("journal_id", "=", journal.id if journal else False),
                ("fingerprint", "=", fingerprint),
            ],
            limit=1,
        )
        if not existing:
            return self.sudo().create(
                {
                    "company_id": company.id,
                    "journal_id": journal.id if journal else False,
                    "fingerprint": fingerprint,
                    "sample_text": (payment_ref or "")[:200],
                    "analytic_account_id": analytic.id,
                    "hit_count": 1,
                    "last_seen": when or fields.Date.context_today(self),
                    "source": source,
                }
            )
        if existing.analytic_account_id != analytic:
            # Seen pointing two ways. Retire it rather than let the newer
            # observation win: whichever store it names now, it has already
            # named the other, and a hint that has been wrong once cannot be
            # trusted to be right the next time.
            existing.sudo().write(
                {
                    "active": False,
                    "note": _(
                        "Deactivated: also seen as %s.",
                        analytic.display_name,
                    ),
                }
            )
            return existing
        existing.sudo().write(
            {
                "hit_count": existing.hit_count + 1,
                "last_seen": when or fields.Date.context_today(self),
            }
        )
        return existing

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    @api.model
    def _suggest(self, company, journal, payment_ref, min_hits=2):
        """The store this wording has meant before, or empty.

        Requires the fingerprint to have been seen at least ``min_hits`` times:
        one observation is a coincidence, and this is offered to an operator as
        though it were a pattern.
        """
        fingerprint = self._fingerprint_of(payment_ref)
        if not fingerprint or not company:
            return self.env["account.analytic.account"]
        hits = self.sudo().search(
            [
                ("company_id", "=", company.id),
                ("journal_id", "in", [journal.id, False] if journal else [False]),
                ("fingerprint", "=", fingerprint),
                ("hit_count", ">=", min_hits),
            ]
        )
        stores = hits.mapped("analytic_account_id")
        return stores if len(stores) == 1 else self.env["account.analytic.account"]
