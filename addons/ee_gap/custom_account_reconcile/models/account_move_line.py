# -*- coding: utf-8 -*-
"""Refuse the line edits that quietly invalidate a reconciliation.

``account.move.line._check_reconciliation`` exists in Odoo 19 but is dead code
-- nothing calls it, and it would only have covered posted lines anyway. That
left the draft window wide open: reset a payment to draft (which, see
``account_move.py``, used to keep the partials alive) and the account or the
partner of a matched line could be changed with no complaint at all. A
reconciliation only means something when both sides sit on the same account for
the same partner, so those two edits destroy it silently.

Amounts are deliberately *not* guarded here. Odoo's own matching machinery
writes ``debit``/``credit``/``amount_currency`` on reconciled lines when it
books exchange differences, and refusing those would break write-offs and
multi-currency settlement.
"""

from odoo import _, models
from odoo.exceptions import UserError


#: Fields that make a reconciliation meaningless if they change underneath it.
STRUCTURAL_FIELDS = ("account_id", "partner_id")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def write(self, vals):
        if not self.env.context.get("skip_reconciliation_guard"):
            self._assert_not_matched(vals)
        return super().write(vals)

    def _assert_not_matched(self, vals):
        """Raise when a line still carrying a match would really change one of
        :data:`STRUCTURAL_FIELDS`, in any move state.

        Compares against the stored value rather than trusting the key's
        presence: Odoo rewrites whole line dicts in plenty of places, and
        refusing a no-op write would block ordinary edits to the fields next to
        it.
        """
        touched = [f for f in STRUCTURAL_FIELDS if f in vals]
        if not touched:
            return
        for line in self:
            if not (line.matched_debit_ids or line.matched_credit_ids):
                continue
            changed = [f for f in touched if (line[f].id or False) != (vals[f] or False)]
            if not changed:
                continue
            raise UserError(
                _(
                    "%(fields)s cannot be changed on a journal item that is still "
                    "reconciled -- the match would survive as a link between two "
                    "documents that no longer belong together, and neither the "
                    "trial balance nor the aged reports would show it.\n\n"
                    "Unreconcile %(entry)s first, make the change, then re-apply it.",
                    fields=", ".join(self._fields[f].string for f in changed),
                    entry=line.move_id.name or _("this entry"),
                )
            )
