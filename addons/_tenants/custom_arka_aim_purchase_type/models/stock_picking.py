# -*- coding: utf-8 -*-
"""Carry the purchase stream onto the receipt.

Stored (so it is filterable / groupable on the transfer list) and read by the
asset-conversion wizard: a Non-Trade goods receipt offers every one of its lines
for capitalisation, not only the products flagged on their master.
"""

from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    l10n_purchase_type = fields.Selection(
        [("trade", "Trade"), ("non_trade", "Non-Trade")],
        string="Purchase Type",
        compute="_compute_l10n_purchase_type",
        store=True,
    )

    @api.depends("purchase_id.l10n_purchase_type", "move_ids.purchase_line_id")
    def _compute_l10n_purchase_type(self):
        for picking in self:
            orders = picking._arka_purchase_orders()
            picking.l10n_purchase_type = orders[:1].l10n_purchase_type or False

    def _arka_purchase_orders(self):
        """Purchase order(s) behind this transfer.

        Combines the direct ``purchase_id`` link with the orders reached through
        each move's ``purchase_line_id``, which covers a receipt grouping several
        orders. Empty for a standalone (non-PO) incoming transfer.
        """
        self.ensure_one()
        return self.move_ids.purchase_line_id.order_id | self.purchase_id

    def _arka_is_nontrade_receipt(self):
        """True for a validated Non-Trade goods receipt -- the capex case."""
        self.ensure_one()
        return (
            self.state == "done" and self.picking_type_id.code == "incoming" and self.l10n_purchase_type == "non_trade"
        )

    # Re-declaring @api.depends REPLACES the inherited set, so the base triggers
    # (from custom_asset_from_receipt) are relisted here alongside the stream.
    @api.depends(
        "move_line_ids.product_id.is_rental_asset",
        "move_line_ids.product_id.is_fixed_asset",
        "state",
        "picking_type_id.code",
        "l10n_purchase_type",
    )
    def _compute_has_rental_asset_lines(self):
        """Also show 'Convert to Assets' on any validated Non-Trade receipt.

        The base module only shows the button when a product is flagged for asset
        conversion on its master. Non-Trade spend is where capex arrives at ARKA-AIM,
        and the buyer should not have to edit the product master first -- so the
        stream itself is enough to offer the conversion.
        """
        super()._compute_has_rental_asset_lines()
        for picking in self:
            if not picking.has_rental_asset_lines and picking._arka_is_nontrade_receipt():
                picking.has_rental_asset_lines = bool(picking.move_line_ids)
