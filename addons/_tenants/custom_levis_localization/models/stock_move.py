# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.constrains("purchase_line_id", "picking_id")
    def _check_levis_receipt_line_from_po(self):
        # Requirement: on a PO-linked goods receipt only lines that originate
        # from the purchase order (i.e. carry a purchase_line_id) may be
        # received. Any manually added line -- even for a product that is
        # already on the PO -- is rejected the moment it is saved.
        for move in self:
            picking = move.picking_id
            if not picking or picking.picking_type_code != "incoming":
                continue
            if move.purchase_line_id:
                # Line originates from a PO line -> allowed.
                continue
            orders = picking._levis_purchase_orders()
            if not orders:
                # Receipt not tied to any purchase order -> no restriction.
                continue
            raise ValidationError(
                _(
                    "Line '%(product)s' was not created from purchase order "
                    "%(orders)s and cannot be added to this receipt.\n"
                    "Only lines that come from the purchase order may be "
                    "received here.",
                    product=move.product_id.display_name,
                    orders=", ".join(orders.mapped("name")) or "-",
                )
            )

    def _is_levis_goods_receipt(self):
        """A vendor goods receipt: stock entering from a supplier location.

        This deliberately excludes internal transfers, manufacturing receipts
        and customer returns — only true vendor receipts skip GL posting.
        """
        self.ensure_one()
        return self.location_id.usage == "supplier"

    # Config switch (ir.config_parameter) that decides whether vendor goods
    # receipts skip the GL posting. Default OFF -> Automated valuation posts the
    # GR journal natively (Dr Inventory / Cr Stock-Input/GRIR). Set to "1" to
    # restore the periodic behaviour (no GR journal + Inventory Reconciliation).
    _SUPPRESS_GR_PARAM = "custom_levis_localization.suppress_gr_journal"

    def _levis_suppress_gr_journal(self):
        param = self.env["ir.config_parameter"].sudo().get_param(self._SUPPRESS_GR_PARAM, "0")
        return str(param).strip().lower() not in ("0", "false", "", "none")

    def _should_create_account_move(self):
        # Requirement 3 (now opt-in): suppress the inventory journal on Goods
        # Receipt confirm ONLY when the periodic switch is enabled. When it is
        # off (default), Automated valuation posts the GR journal normally; the
        # stock valuation layer is produced by stock_account either way.
        self.ensure_one()
        if self._levis_suppress_gr_journal() and self._is_levis_goods_receipt():
            return False
        return super()._should_create_account_move()
