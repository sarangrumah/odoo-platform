# -*- coding: utf-8 -*-
"""Extend custom.ppob.transaction as a mirror container for the ERASPACE POS
feed. No dispatch runs for these rows; they are created terminal by the bridge
and carry the POS-side sell/status for reporting and the daily rollup faktur.

The presence of ``eraspace_txn_id`` marks a row as an ERASPACE mirror (a plain
M2o owned by this module -- avoids colliding with ``inbound_source``, which the
oracle bridge defines independently).
"""
from odoo import fields, models


class PpobTransaction(models.Model):
    _inherit = "custom.ppob.transaction"

    eraspace_txn_id = fields.Many2one(
        comodel_name="custom.ppob.eraspace.txn",
        string="ERASPACE Join Row", index=True, copy=False,
        help="Set when this transaction is a mirror of an ERASPACE POS sale.",
    )
