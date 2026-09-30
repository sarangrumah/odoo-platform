# -*- coding: utf-8 -*-
"""What a store *called* the tender, mapped to the label the rate card uses.

``levis.mdr.rate`` is keyed on the PAYMENT label as the export writes it, which was
right while one store was sending. With 24 stores sending it stopped being one label
per rate: the same BCA QRIS transaction arrives as ``QRIS BCA``, ``BCA QRIS``,
``BCA-QRIS``, ``BCA - QRIS BCA`` and ``QRI BCA``. Each store types its own column
by hand, so the vocabulary is a property of the typist, not of the bank.

Two mechanisms keep that from turning into 39 rates per acquirer:

1. **Normalisation**, in the view: the comparison drops everything that is not a
   letter or a digit and upper-cases the rest, so ``BCA - QRIS``, ``BCA-QRIS``,
   ``BCA _ QRIS`` and ``bca qris`` are already the same key. Punctuation and spacing
   never need an alias row. Checked against the 39 seeded labels: no two of them
   collapse onto the same key.

2. **This table**, for the differences normalisation cannot see -- a different word
   order (``QRIS BCA`` vs ``BCA - QRIS``), a different wording (``CREDIT BCA OFF US``
   for ``BCA - REGULAR OFF US``) or a typo (``CRREDIT``, ``DEBT OTHER``, ``QRIA``).

An alias points at a **label**, not at a rate row: rates are effective-dated, so one
label owns several rows and the view still picks the one effective on the trading day.
The target must already exist as a rate label -- a typo in the target would silently
leave the transactions unpriced, which is the failure this table exists to remove.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


#: Same rule as the SQL in :mod:`levis_mdr_txn`. Kept here so a constraint can spot a
#: collision at write time instead of leaving it to be discovered in a report.
def mdr_norm(label):
    return "".join(ch for ch in (label or "").upper() if ch.isalnum())


class LevisMdrAlias(models.Model):
    _name = "levis.mdr.alias"
    _description = "Levi's Card MDR Label Alias"
    _order = "payment, alias"
    _rec_name = "alias"

    alias = fields.Char(
        required=True,
        index=True,
        string="As the store writes it",
        help="The PAYMENT text found in a store's X70D export, e.g. 'QRIS BCA'. "
        "Case, spacing and punctuation are ignored when matching, so only add a row "
        "when the wording or the word order differs.",
    )
    payment = fields.Char(
        required=True,
        index=True,
        string="Rate label",
        help="The label on the rate card this text means, e.g. 'BCA - QRIS'. "
        "Must be a label that exists in Card MDR Rates.",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda s: s.env.company,
        index=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Char()

    _unique_alias = models.Constraint(
        "unique(company_id, alias)",
        "That store wording is already mapped. Edit the existing row instead of adding a second meaning for it.",
    )

    @api.constrains("alias", "payment")
    def _check_target_exists(self):
        Rate = self.env["levis.mdr.rate"].sudo()
        for rec in self:
            if mdr_norm(rec.alias) == mdr_norm(rec.payment):
                # Not an error worth blocking on its own, but it does nothing: the
                # normalised comparison already matches it.
                continue
            rates = Rate.search([("company_id", "=", rec.company_id.id)])
            if not any(mdr_norm(r.payment) == mdr_norm(rec.payment) for r in rates):
                raise ValidationError(
                    _(
                        "'%(target)s' is not a label in Card MDR Rates, so mapping "
                        "'%(alias)s' onto it would leave those transactions unpriced. "
                        "Add the rate first, or fix the spelling.",
                        target=rec.payment or "",
                        alias=rec.alias or "",
                    )
                )

    @api.constrains("alias")
    def _check_alias_not_collision(self):
        """Two rows whose wording only differs by punctuation are the same key."""
        for rec in self:
            key = mdr_norm(rec.alias)
            if not key:
                raise ValidationError(_("An alias needs at least one letter or digit."))
            others = self.search([("id", "!=", rec.id), ("company_id", "=", rec.company_id.id)])
            clash = others.filtered(lambda o, k=key: mdr_norm(o.alias) == k)
            if clash:
                raise ValidationError(
                    _(
                        "'%(alias)s' matches '%(other)s' once case, spacing and "
                        "punctuation are ignored -- they are the same key.",
                        alias=rec.alias or "",
                        other=clash[0].alias or "",
                    )
                )
