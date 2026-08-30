# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_rental_asset = fields.Boolean(
        string="Is Rental Asset",
        help="When set, units received for this product can be bulk-converted "
        "to custom.fixed.asset records (and rental.asset records) via the "
        "'Convert to Assets' wizard on the receipt picking.",
    )
    asset_group_id = fields.Many2one(
        comodel_name="custom.fixed.asset.group",
        string="Asset Group",
        help="Default depreciation template applied to assets created from this product.",
    )
    is_fixed_asset = fields.Boolean(
        string="Create Fixed Asset on Receipt",
        help="When set, units received for this product can be converted to "
        "custom.fixed.asset records from the receipt. Use this for plain capex "
        "items (bought on a non-trade PO) that are not rented out.",
    )
    asset_tracking_mode = fields.Selection(
        selection=[
            ("serial", "One asset per serial number"),
            ("quantity", "One pooled asset for the received quantity"),
        ],
        string="Asset Tracking",
        default="serial",
        required=True,
        help="Serial: every unit gets its own asset number (needs lot/serial "
        "tracking). Pooled: the whole received quantity is maintained under a "
        "single asset number carrying that quantity — e.g. 5 waste bins bought "
        "together. Broken units are taken out later with 'Retire Units'.",
    )
    auto_create_rental_asset = fields.Boolean(
        string="Also Create Rental Asset",
        default=True,
        help="When converting received units to fixed assets, also create a rental.asset record per serial number.",
    )

    @api.constrains("is_rental_asset", "is_fixed_asset", "asset_tracking_mode", "asset_group_id", "tracking")
    def _check_rental_asset_config(self):
        for tmpl in self:
            mode = tmpl._asset_conversion_mode()
            if not mode:
                continue
            if not tmpl.asset_group_id:
                raise ValidationError(
                    _('Product "%s" is flagged for asset conversion but has no Asset Group set.') % tmpl.display_name
                )
            # Only the per-serial mode needs stock tracking: a pooled asset is
            # counted, not identified, so a plain untracked product is fine.
            if mode == "serial" and tmpl.tracking not in ("lot", "serial"):
                raise ValidationError(
                    _(
                        'Product "%s" creates one asset per serial number; tracking must be '
                        'set to "By Lots" or "By Unique Serial Number". Switch Asset Tracking '
                        "to the pooled mode for untracked products."
                    )
                    % tmpl.display_name
                )

    def _asset_conversion_mode(self):
        """Return ``'serial'``, ``'quantity'`` or ``False`` for this product.

        ``is_rental_asset`` predates the pooled mode and keeps meaning one asset
        (and one rental unit) per serial number, so it is honoured as-is.
        """
        self.ensure_one()
        if self.is_fixed_asset:
            return self.asset_tracking_mode or "serial"
        if self.is_rental_asset:
            return "serial"
        return False
