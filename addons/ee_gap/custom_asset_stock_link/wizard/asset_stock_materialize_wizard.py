# -*- coding: utf-8 -*-
"""Turn fixed assets that already exist into serial numbers sitting in a warehouse.

The accounting value of these units is already in the GL (they were loaded from
an opening balance, or capitalised by hand). Materialising them into stock must
therefore post **nothing**. In Odoo 19 a stock move only reaches the GL through
``stock_account.stock_move._should_create_account_move()``, which needs all three
of: a storable valued product, a location carrying a ``valuation_account_id``,
and ``product.valuation == 'real_time'``. ``_assert_zero_valuation`` below
refuses to run unless every one of those is false -- plus a zero standard price,
which is what also keeps the *periodic* year-end valuation entry at zero.
"""

import logging
import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

PRODUCT_CODE_PREFIX = "FA"
CATEGORY_XMLID = "custom_asset_stock_link.product_category_fixed_asset_non_valued"


def slug_code(name):
    """``Damoda Drone DMD`` -> ``DAMODA-DRONE-DMD``."""
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "-", ascii_name.upper()).strip("-")[:40] or "ASSET"


class AssetStockMaterializeWizard(models.TransientModel):
    _name = "custom.asset.stock.materialize.wizard"
    _description = "Materialise Fixed Assets Into Stock"

    asset_ids = fields.Many2many(
        comodel_name="custom.fixed.asset",
        string="Assets",
        required=True,
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Destination Location",
        domain="[('usage', '=', 'internal')]",
        help="Leave empty to use the stock location mapped on each asset's asset location.",
    )
    categ_id = fields.Many2one(
        comodel_name="product.category",
        string="Product Category",
        required=True,
        default=lambda self: self.env.ref(CATEGORY_XMLID, raise_if_not_found=False),
        help="Must be a non-valuated category -- the units are already capitalised in the GL.",
    )
    create_rental_asset = fields.Boolean(
        string="Create Rental Units",
        default=True,
        help="Also create one rental.asset per unit so it shows up in rental availability.",
    )
    pending_count = fields.Integer(compute="_compute_counts")
    linked_count = fields.Integer(compute="_compute_counts")

    @api.depends("asset_ids.lot_id")
    def _compute_counts(self):
        for wizard in self:
            linked = wizard.asset_ids.filtered("lot_id")
            wizard.linked_count = len(linked)
            wizard.pending_count = len(wizard.asset_ids) - len(linked)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("active_model") == "custom.fixed.asset":
            res["asset_ids"] = [(6, 0, self.env.context.get("active_ids", []))]
        return res

    # ------------------------------------------------------------------
    # Guard
    # ------------------------------------------------------------------
    @api.model
    def _assert_zero_valuation(self, companies, categories, locations, products):
        """Refuse to touch stock if anything could post an inventory journal entry."""
        problems = []
        for company in companies:
            if company.inventory_valuation == "real_time":
                problems.append(_("company %s: valuation is Perpetual", company.name))
            for category in categories:
                if category.with_company(company).property_valuation == "real_time":
                    problems.append(
                        _(
                            "category %(categ)s in %(company)s: valuation is Perpetual",
                            categ=category.display_name,
                            company=company.name,
                        )
                    )
        for location in locations:
            if location.valuation_account_id:
                problems.append(_("location %s carries a valuation account", location.complete_name))
        for product in products:
            if product.valuation == "real_time":
                problems.append(_("product %s: valuation is Perpetual", product.display_name))
            if product.lot_valuated:
                problems.append(_("product %s: serials are valued individually", product.display_name))
            if not float_is_zero(product.standard_price, precision_digits=2):
                problems.append(
                    _(
                        "product %(name)s: cost is %(cost)s, must be 0",
                        name=product.display_name,
                        cost=product.standard_price,
                    )
                )
        if problems:
            raise UserError(
                _(
                    "Refusing to materialise: stock valuation would reach the general "
                    "ledger and double-count assets that are already capitalised.\n\n- %s",
                    "\n- ".join(problems),
                )
            )

    # ------------------------------------------------------------------
    # Helpers -- also the API the tenant backfill scripts call.
    # ------------------------------------------------------------------
    def _resolve_location(self, asset):
        if self.location_id:
            return self.location_id
        return asset.location_id.stock_location_id

    @api.model
    def _ensure_category_valuation(self, category, companies):
        """Pin the category to periodic valuation and standard cost per company.

        Both fields are ``company_dependent``; an unset value falls back to
        ``res.company.inventory_valuation``, so leaving it blank would silently
        follow a later company-wide switch to Perpetual.
        """
        for company in companies:
            category.with_company(company).write({"property_valuation": "periodic", "property_cost_method": "standard"})

    @api.model
    def _ensure_product(self, company, name, asset_group, categ, auto_rental=True):
        """One serial-tracked, zero-cost product per (company, asset name)."""
        Product = self.env["product.product"]
        code = "%s/%s" % (PRODUCT_CODE_PREFIX, slug_code(name))
        product = Product.with_context(active_test=False).search(
            [("default_code", "=", code), ("company_id", "in", (False, company.id))],
            limit=1,
        )
        if product:
            return product
        return Product.create(
            {
                "name": name,
                "default_code": code,
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "lot_valuated": False,
                "categ_id": categ.id,
                "company_id": company.id,
                "standard_price": 0.0,
                "list_price": 0.0,
                "purchase_ok": False,
                "sale_ok": False,
                "is_rental_asset": True,
                "asset_group_id": asset_group.id,
                "auto_create_rental_asset": auto_rental,
            }
        )

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        assets = self.asset_ids.filtered(lambda a: not a.lot_id)
        if not assets:
            raise UserError(_("Every selected asset is already linked to a serial number."))

        missing_location = assets.filtered(lambda a: not self._resolve_location(a))
        if missing_location:
            raise UserError(
                _(
                    "No destination location for %(count)s asset(s), e.g. %(name)s. Either pick a "
                    "location on this wizard or set the Stock Location on their asset location.",
                    count=len(missing_location),
                    name=missing_location[:1].display_name,
                )
            )
        no_group = assets.filtered(lambda a: not a.group_id)
        if no_group:
            raise UserError(
                _("Asset %s has no asset group; a product cannot be configured without one.", no_group[:1].display_name)
            )

        companies = assets.company_id
        locations = self.env["stock.location"].union(*[self._resolve_location(a) for a in assets])
        self._ensure_category_valuation(self.categ_id, companies)
        self._assert_zero_valuation(companies, self.categ_id, locations, self.env["product.product"])

        products = {}
        for asset in assets:
            key = (asset.company_id.id, asset.name)
            if key not in products:
                products[key] = self._ensure_product(
                    asset.company_id,
                    asset.name,
                    asset.group_id,
                    self.categ_id,
                    auto_rental=self.create_rental_asset,
                )
        # Re-check after creation: a pre-existing product could be misconfigured.
        self._assert_zero_valuation(
            companies,
            self.categ_id,
            locations,
            self.env["product.product"].union(*products.values()),
        )

        lots = self._create_lots(assets, products)
        self._seed_quants(assets)
        if self.create_rental_asset:
            self._create_rental_assets(assets)
        self.env["custom.fixed.asset"]._sync_stock_from_lots(lots.ids)
        _logger.info(
            "custom_asset_stock_link: materialised %s assets into %s products",
            len(assets),
            len(products),
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Materialised Assets"),
            "res_model": "custom.fixed.asset",
            "view_mode": "list,form",
            "domain": [("id", "in", assets.ids)],
        }

    def _create_lots(self, assets, products):
        """One ``stock.lot`` per asset, named after the asset code.

        The register's ``serial_number`` column is usually blank, so the asset
        code is the unique per-unit identifier. It is copied onto
        ``serial_number`` as well, which is what the asset opname report matches
        rental status on.
        """
        Lot = self.env["stock.lot"]
        lots = Lot
        # ``serial_number`` is added by tenant register modules, so it may not
        # exist here. The asset code always does, and is unique per unit.
        has_serial_field = "serial_number" in assets._fields
        for asset in assets:
            product = products[(asset.company_id.id, asset.name)]
            serial = (has_serial_field and asset.serial_number) or asset.code
            lot = Lot.search([("name", "=", serial), ("product_id", "=", product.id)], limit=1)
            if not lot:
                lot = Lot.create(
                    {
                        "name": serial,
                        "product_id": product.id,
                        "company_id": asset.company_id.id,
                    }
                )
            vals = {"lot_id": lot.id, "product_id": product.id}
            if has_serial_field:
                # what the asset opname report matches rental status on
                vals["serial_number"] = serial
            asset.write(vals)
            lots |= lot
        return lots

    def _seed_quants(self, assets):
        """Put one unit of each serial in its destination through an adjustment.

        An inventory adjustment is the only way in without inventing a purchase
        document. ``skip_asset_stock_sync`` suppresses one sync per line; the
        caller does a single bulk sync afterwards.
        """
        Quant = self.env["stock.quant"].with_context(inventory_mode=True, skip_asset_stock_sync=True)
        vals_list = []
        for asset in assets:
            vals_list.append(
                {
                    "product_id": asset.product_id.id,
                    "lot_id": asset.lot_id.id,
                    "location_id": self._resolve_location(asset).id,
                    "inventory_quantity": 1.0,
                }
            )
        if vals_list:
            Quant.create(vals_list).action_apply_inventory()

    def _create_rental_assets(self, assets):
        Rental = self.env["rental.asset"]
        vals_list = []
        for asset in assets:
            if asset.rental_asset_ids:
                continue
            serial = asset.lot_id.name
            code = "RA/%s" % serial
            if Rental.with_context(active_test=False).search_count([("code", "=", code)]):
                continue
            vals_list.append(
                {
                    "name": "%s %s" % (asset.name, serial),
                    "code": code,
                    "product_id": asset.product_id.id,
                    "serial_number": serial,
                    "fixed_asset_id": asset.id,
                    "company_id": asset.company_id.id,
                    "daily_rate": 0.0,
                    "state": "available",
                }
            )
        return Rental.create(vals_list) if vals_list else Rental
