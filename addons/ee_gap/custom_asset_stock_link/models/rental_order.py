# -*- coding: utf-8 -*-
from odoo import models


class RentalOrder(models.Model):
    _inherit = "rental.order"

    def _loaned_fixed_asset(self):
        """The fixed asset behind this rental, when there is one with a serial."""
        self.ensure_one()
        asset = self.asset_id.fixed_asset_id
        return asset if asset and asset.lot_id else self.env["custom.fixed.asset"]

    def _resolve_picking_type_and_locations(self, direction):
        """Send the unit out from where it actually is, and bring it back home.

        ``custom_rental`` sources from the first internal picking type's default
        location -- in a multi-step warehouse that is the Input dock, which is
        not where the drone is sitting. Validating from there books a negative
        quant on the dock and leaves the unit's real location untouched. When
        the rental unit is a fixed asset we know its serial's exact location, so
        use it, and use the warehouse's own Internal Transfers type rather than
        whichever internal type happened to sort first.
        """
        ptype, loc_src, loc_dst = super()._resolve_picking_type_and_locations(direction)
        asset = self._loaned_fixed_asset()
        on_loan = self.on_loan_location_id
        if not (self.is_internal_loan and asset and on_loan):
            return ptype, loc_src, loc_dst
        # Home is the accounting asset location's stock counterpart -- stable
        # across the loan, unlike the unit's current position.
        home = asset.location_id.stock_location_id or loc_src
        current = asset.stock_location_id or home
        warehouse = current.warehouse_id or home.warehouse_id
        ptype = warehouse.int_type_id or ptype
        if direction == "outgoing":
            return ptype, current, on_loan
        return ptype, on_loan, home

    def _create_stock_picking(self, direction):
        """Pre-assign the unit's serial on the pickup/return move.

        ``custom_rental`` builds the move without any move line, which for a
        serial-tracked product means nobody can validate the picking without
        retyping the serial -- and ``_check_returned_serials`` short-circuits on
        an empty pickup, silently disabling the return-integrity check. Once a
        rental unit is backed by a fixed asset with a serial, we know exactly
        which one is going out.
        """
        picking = super()._create_stock_picking(direction)
        if not picking:
            return picking
        lot = self._loaned_fixed_asset().lot_id
        product = self._resolve_rental_product()
        if not lot or product.tracking != "serial" or lot.product_id != product:
            return picking
        move = picking.move_ids.filtered(lambda m: not m.is_loan)[:1]
        if not move:
            return picking
        move.move_line_ids.unlink()
        self.env["stock.move.line"].sudo().create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "lot_id": lot.id,
                "quantity": 1.0,
                "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id,
                "company_id": move.company_id.id,
            }
        )
        return picking
