# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_purchase_type = fields.Selection(
        [("trade", "Trade"), ("non_trade", "Non-Trade")],
        string="Purchase Type",
        copy=False,
        tracking=True,
        help="Purchase stream this vendor bill belongs to. Filled from the purchase "
        "order; set it by hand on a bill entered without a PO so the payable lands "
        "on the right AP control account.",
    )
