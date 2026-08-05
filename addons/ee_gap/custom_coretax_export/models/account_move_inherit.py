# -*- coding: utf-8 -*-
"""e-Faktur Keluaran (FK/OF) export straight off the invoice.

One multi-record method serves both entry points: the form button calls it on a
single invoice, the list-view ``Action`` calls it on the whole selection. The
work itself lives in ``custom.coretax.fk.builder``, which the masa-pajak and
date-range wizards share.
"""

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_coretax_fk_export(self):
        """Download an FK/OF workbook for ``self`` (one invoice or many).

        Validation — posted, out_invoice, dated, single company — lives in
        ``_coretax_fk_check_moves`` so the list action, which cannot hide itself
        per record, refuses with the same message as the form button.
        """
        return self.env["custom.coretax.fk.builder"]._coretax_fk_export(self)
