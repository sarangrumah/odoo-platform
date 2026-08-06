# -*- coding: utf-8 -*-
"""Catch the two payment mistakes that only surface at month-end.

**Duplicates.** Nothing in Odoo notices that the same vendor is about to be
paid the same amount on the same day twice. In prd_levis_begbal
``8282/2026/07/016`` (28 Jul) was never applied to its bills, so those bills
still read "Not Paid"; the next morning the same operator registered the
payment again as ``8282/2026/07/045``, which did apply. Two cash-outs of
Rp 142.957.500 for one obligation, and the only symptom was an AP-minus row in
the aged payable a month later. Posting now stops on the twin and names it; the
operator ticks ``duplicate_checked`` to say it is genuinely a second payment.

**Unapplied payments.** A posted vendor payment that settles no bill is a
legitimate thing (an advance, a deposit) but an expensive thing to lose track
of: it debits the payable account and sits in the aging as a negative that
never nets against anything. ``is_unapplied`` makes them searchable, so they
can be watched continuously instead of being discovered when the subledger
refuses to tie out.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import formatLang


class AccountPayment(models.Model):
    _inherit = "account.payment"

    duplicate_checked = fields.Boolean(
        string="Duplicate Checked",
        copy=False,
        help="Tick to confirm that an existing payment with the same partner, "
        "amount and date is not the same transaction, and post anyway.",
    )
    is_unapplied = fields.Boolean(
        string="Unapplied",
        compute="_compute_is_unapplied",
        store=True,
        help="Posted, but not applied to any invoice or bill — it sits in the "
        "aged report as an open item that nothing nets against.",
    )

    @api.depends("state", "is_reconciled")
    def _compute_is_unapplied(self):
        for payment in self:
            payment.is_unapplied = (
                payment.state in ("in_process", "paid") and not payment.is_reconciled
            )

    def _find_duplicates(self):
        """Posted payments that look like the same transaction as ``self``."""
        self.ensure_one()
        if not (self.partner_id and self.amount):
            return self.browse()
        return self.search(
            [
                ("id", "!=", self._origin.id or 0),
                ("company_id", "=", self.company_id.id),
                ("partner_id", "=", self.partner_id.id),
                ("payment_type", "=", self.payment_type),
                ("amount", "=", self.amount),
                ("date", "=", self.date),
                ("state", "in", ("in_process", "paid")),
            ]
        )

    def action_post(self):
        for payment in self:
            if payment.duplicate_checked:
                continue
            twins = payment._find_duplicates()
            if twins:
                raise UserError(
                    _(
                        "%(partner)s already has a posted payment of %(amount)s dated "
                        "%(date)s: %(twins)s.\n\n"
                        "If this is a second, genuinely separate payment, tick "
                        "\"Duplicate Checked\" and post again. If it is the same "
                        "transaction being entered twice, cancel this one — note that "
                        "a payment which settles no bill still leaves the bill "
                        "reading \"Not Paid\", which is exactly what invites a "
                        "duplicate.",
                        partner=payment.partner_id.display_name,
                        amount=formatLang(
                            self.env, payment.amount, currency_obj=payment.currency_id
                        ),
                        date=payment.date,
                        twins=", ".join(
                            t.move_id.name or str(t.id) for t in twins
                        ),
                    )
                )
        return super().action_post()
