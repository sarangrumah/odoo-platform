# -*- coding: utf-8 -*-
"""Add ERASPACE mirror move types to custom.ppob.wallet.move."""

from odoo import fields, models


class PpobWalletMove(models.Model):
    _inherit = "custom.ppob.wallet.move"

    type = fields.Selection(
        selection_add=[
            ("eraspace_sale", "ERASPACE Sale (mirror)"),
            ("eraspace_topup", "ERASPACE Top-up (mirror)"),
            ("eraspace_refund", "ERASPACE Refund (mirror)"),
            ("eraspace_sync", "ERASPACE Balance Sync (mirror)"),
        ],
        ondelete={
            "eraspace_sale": "cascade",
            "eraspace_topup": "cascade",
            "eraspace_refund": "cascade",
            "eraspace_sync": "cascade",
        },
    )
