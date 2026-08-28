# -*- coding: utf-8 -*-
"""The number an operator recognises a journal item by.

The matching screen already names the *entry* (``RIREC/2026/08/0023``), which is
Odoo's own sequence and says nothing to whoever is holding the bank statement.
What Finance reconciles against is the transaction number the document carries:
the settlement reference the retail feed wrote on the line, the customer
reference on an invoice, the number of the payment. So it is read off the
document, most specific first, and only falls back to the entry name when the
document has nothing else to offer.
"""

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    levis_transaction_ref = fields.Char(
        string="Transaction No.",
        compute="_compute_levis_transaction_ref",
        help="The number this item can be traced by outside Odoo: the reference "
        "on the line or its entry, the payment reference of an invoice, or the "
        "source document. The entry name only when there is nothing better.",
    )

    @api.depends("ref", "move_id.ref", "move_id.payment_reference", "move_id.invoice_origin", "move_id.name")
    def _compute_levis_transaction_ref(self):
        for line in self:
            move = line.move_id
            candidates = (
                line.ref,
                move.ref,
                move.payment_reference if move.is_invoice(include_receipts=True) else None,
                move.invoice_origin,
                move.name,
            )
            line.levis_transaction_ref = next((str(c).strip() for c in candidates if c and str(c).strip()), False)
