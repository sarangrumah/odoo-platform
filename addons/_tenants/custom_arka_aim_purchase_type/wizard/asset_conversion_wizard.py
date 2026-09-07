# -*- coding: utf-8 -*-
"""Transfer to Asset from a Non-Trade goods receipt.

``custom_asset_from_receipt`` decides what to capitalise from the *product*
master (``Create Fixed Asset on Receipt`` / ``Is Rental Asset``). At ARKA-AIM the
signal is the *receipt*: anything bought on a Non-Trade purchase order is
operational or capex spend, and the buyer should be able to register it as an
asset straight off the goods receipt without editing the product first.

So on a Non-Trade receipt every received line is offered, pre-selected, as a
pooled asset (one asset carrying the received quantity). Products that ARE
configured on their master keep their own mode, so per-serial conversion still
wins where it has been set up.
"""

from odoo import models


class AssetConversionWizard(models.TransientModel):
    _inherit = "custom.asset.conversion.wizard"

    def _asset_conversion_mode_for(self, product):
        mode = super()._asset_conversion_mode_for(product)
        if mode:
            return mode
        if self.picking_id._arka_is_nontrade_receipt():
            # Pooled, not per-serial: a serial-mode line is silently skipped when
            # the move line carries no lot, which would quietly drop exactly the
            # lines this override exists to offer.
            return "quantity"
        return mode

    def _default_asset_group(self, line):
        group = super()._default_asset_group(line)
        if group:
            return group
        return self.picking_id.company_id.x_nontrade_asset_group_id
