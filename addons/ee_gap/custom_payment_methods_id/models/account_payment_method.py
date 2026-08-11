# -*- coding: utf-8 -*-
"""Register GIRO and BANK TRANSFER as manual-style payment methods.

A method's ``code`` must be known to ``_get_payment_method_information()``
before a record carrying it can be created — core reads that dict in
``account.payment.method.create`` to decide the method's mode and the journal
types it may attach to. Hence this override; the records themselves are created
by ``hooks.post_init_hook``.
"""

from odoo import models

# mode='multi' -> can be added to any number of journals; type=('bank',) ->
# bank journals only, same shape core uses for 'manual'.
ID_PAYMENT_METHODS = ("giro", "bank_transfer")


class AccountPaymentMethod(models.Model):
    _inherit = "account.payment.method"

    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        for code in ID_PAYMENT_METHODS:
            res[code] = {"mode": "multi", "type": ("bank",)}
        return res
