# -*- coding: utf-8 -*-
"""Keep a reset-to-draft from silently orphaning a reconciliation.

Odoo 19's ``account.move.button_draft``
(``addons/account/models/account_move.py``) unlinks analytic lines, flips
``state`` to ``draft`` and detaches attachments -- and that is all. The
``remove_move_reconcile()`` call earlier versions made is gone, and
``account.payment.action_draft`` merely delegates to it. Its companion guard
``account.move.line._check_reconciliation`` still exists but is **never called
by anything**, so nothing stops the follow-up either.

Two ways that bites, both observed in prd_levis_begbal (July 2026):

* Reset a paid vendor payment to draft and leave it there. The partial
  reconciliations survive, so the bill still reads ``amount_residual = 0`` and
  payment_state ``paid`` -- while the payment itself is out of the trial
  balance, which only sees posted moves. TB and the aged payable then differ by
  exactly that amount, and the bill is simply absent from the aging rather than
  flagged anywhere. (``8282/2026/07/042``, Rp 75.405.550.)
* Reset to draft, then hand-edit the lines. In draft the account of a line that
  still carries partials can be swapped freely, which mangles the match beyond
  repair; re-posting does not bring it back. The bill reopens, the payment sits
  unapplied, and the aged payable shows the two as separate rows that never net
  to zero -- which is what Accounting reported as "nomor bill tidak punya
  relasi". (``8282/2026/07/009`` and ``8282/2026/07/017``.)

So: unreconcile up front, the way Odoo used to, and record what was undone in
the chatter. Once the match is gone there is nothing left for a draft edit to
corrupt, and the operator can see that resetting cost them the application.
"""

from odoo import _, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def button_draft(self):
        """Undo the reconciliations before handing over to Odoo.

        Deliberately *before* ``super()``: while the move is still posted the
        partials are consistent and ``remove_move_reconcile`` can walk them
        cleanly, and any lock-date refusal surfaces before the state changes.
        """
        for move in self:
            matched = move.line_ids.filtered(
                lambda line: line.matched_debit_ids or line.matched_credit_ids
            )
            if not matched:
                continue
            counterparts = (
                matched.matched_debit_ids.debit_move_id
                | matched.matched_debit_ids.credit_move_id
                | matched.matched_credit_ids.debit_move_id
                | matched.matched_credit_ids.credit_move_id
            ).move_id - move
            matched.remove_move_reconcile()
            move.message_post(
                body=_(
                    "Reset to draft: the reconciliation was undone first, so the "
                    "matched documents are open again. Re-apply this payment after "
                    "re-posting it. Documents released: %(docs)s",
                    docs=", ".join(sorted(counterparts.mapped("name"))) or _("n/a"),
                )
            )
        return super().button_draft()
