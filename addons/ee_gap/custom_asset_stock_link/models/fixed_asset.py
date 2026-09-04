# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class CustomFixedAsset(models.Model):
    _inherit = "custom.fixed.asset"

    # ------------------------------------------------------------------
    # Where the unit physically is.
    #
    # Stored and maintained by ``_sync_stock_from_lots`` so the register can
    # be grouped and filtered by warehouse without a compute over thousands
    # of rows. ``location_id`` -- the accounting-side asset location that the
    # opname report reads -- is deliberately NEVER written here: Finance owns
    # that field, the warehouse owns this one.
    # ------------------------------------------------------------------
    stock_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Physical Location",
        readonly=True,
        index=True,
        copy=False,
        help="Internal warehouse location currently holding this unit's serial number. "
        "Maintained automatically whenever a stock move involving the serial is validated.",
    )
    stock_state = fields.Selection(
        selection=[
            ("untracked", "Not In Stock"),
            ("in_stock", "In Stock"),
            ("in_transit", "In Transit"),
            ("out", "Gone From Stock"),
        ],
        string="Stock Status",
        default="untracked",
        readonly=True,
        index=True,
        copy=False,
    )
    stock_qty = fields.Float(
        string="On Hand",
        readonly=True,
        copy=False,
        digits="Product Unit of Measure",
    )
    stock_synced_on = fields.Datetime(readonly=True, copy=False)
    move_line_count = fields.Integer(compute="_compute_move_line_count")

    rental_asset_id = fields.Many2one(
        comodel_name="rental.asset",
        string="Rental Unit",
        compute="_compute_rental_asset_id",
        store=True,
        compute_sudo=True,
    )
    rental_state = fields.Selection(
        related="rental_asset_id.state",
        string="Rental Status",
        readonly=True,
        store=True,
    )
    is_rentable = fields.Boolean(
        string="Available To Rent",
        compute="_compute_is_rentable",
        store=True,
        index=True,
        help="Running asset, physically in stock, with a rental unit that is free.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("rental_asset_ids")
    def _compute_rental_asset_id(self):
        for asset in self:
            asset.rental_asset_id = asset.rental_asset_ids[:1]

    @api.depends("state", "stock_state", "rental_asset_id.state", "rental_asset_id.active")
    def _compute_is_rentable(self):
        for asset in self:
            rental = asset.rental_asset_id
            asset.is_rentable = bool(
                asset.state == "running"
                and asset.stock_state == "in_stock"
                and rental
                and rental.active
                and rental.state == "available"
            )

    @api.depends("lot_id")
    def _compute_move_line_count(self):
        counts = {}
        lots = self.lot_id
        if lots:
            groups = self.env["stock.move.line"]._read_group(
                domain=[("lot_id", "in", lots.ids), ("state", "=", "done")],
                groupby=["lot_id"],
                aggregates=["__count"],
            )
            counts = {lot.id: count for lot, count in groups}
        for asset in self:
            asset.move_line_count = counts.get(asset.lot_id.id, 0)

    # ------------------------------------------------------------------
    # Sync engine -- the single entry point used by the move hook, the cron,
    # the resync button and the backfill script.
    # ------------------------------------------------------------------
    @api.model
    def _sync_stock_from_lots(self, lot_ids):
        """Refresh the stock position of every asset carrying one of ``lot_ids``.

        One read_group for the whole batch; these registers run to thousands of
        assets, so a per-record quant search is not an option.
        """
        lot_ids = [lot_id for lot_id in (lot_ids or []) if lot_id]
        if not lot_ids:
            return self.browse()
        assets = self.with_context(active_test=False).sudo().search([("lot_id", "in", lot_ids)])
        if not assets:
            return assets

        positions = {}
        groups = (
            self.env["stock.quant"]
            .sudo()
            ._read_group(
                domain=[
                    ("lot_id", "in", assets.lot_id.ids),
                    ("location_id.usage", "in", ("internal", "transit")),
                    ("quantity", ">", 0),
                ],
                groupby=["lot_id", "location_id"],
                aggregates=["quantity:sum"],
            )
        )
        for lot, location, qty in groups:
            current = positions.get(lot.id)
            # A serial should sit in exactly one place. If the data says
            # otherwise, report the location holding the most.
            if not current or qty > current[1]:
                positions[lot.id] = (location, qty)

        now = fields.Datetime.now()
        empty = self.env["stock.location"]
        for asset in assets:
            location, qty = positions.get(asset.lot_id.id, (empty, 0.0))
            if location:
                state = "in_transit" if location.usage == "transit" else "in_stock"
            else:
                state = "out"
            vals = {
                "stock_location_id": location.id,
                "stock_qty": qty,
                "stock_state": state,
                "stock_synced_on": now,
            }
            if any(asset[key] != vals[key] for key in ("stock_qty", "stock_state")) or (
                asset.stock_location_id.id != location.id
            ):
                asset.write(vals)
            else:
                asset.stock_synced_on = now
        return assets

    @api.model
    def _cron_sync_stock_locations(self, batch=2000):
        """Nightly safety net for positions changed outside ``_action_done``."""
        assets = self.with_context(active_test=False).search(
            [("lot_id", "!=", False)], limit=batch, order="stock_synced_on ASC NULLS FIRST, id"
        )
        if assets:
            self._sync_stock_from_lots(assets.lot_id.ids)
        _logger.info("custom_asset_stock_link: synced %s assets from stock", len(assets))
        return len(assets)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_resync_stock_location(self):
        self._sync_stock_from_lots(self.lot_id.ids)
        return True

    def action_view_stock_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Movements of %s", self.display_name),
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            "domain": [("lot_id", "=", self.lot_id.id), ("state", "=", "done")],
            "context": {"create": False},
        }
