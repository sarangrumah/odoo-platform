# -*- coding: utf-8 -*-
"""Store code surfaced on the POS configuration.

A convenience mirror of ``stock.warehouse.l10n_store_code`` so the code is
visible where a POS manager already works.

**Deliberately not stored.** A stored related would force a full recompute of
every ``pos.config`` row on ``-u`` in each of the ~10 databases carrying this
addon, and nothing needs it in SQL: the clearing's raw queries already join
``ir_model_data`` -> ``pos_config`` -> ``stock_warehouse`` and can read the
column off the warehouse directly.
"""

from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    l10n_store_code = fields.Char(
        related="warehouse_id.l10n_store_code",
        string="Store Code",
        readonly=True,
    )
