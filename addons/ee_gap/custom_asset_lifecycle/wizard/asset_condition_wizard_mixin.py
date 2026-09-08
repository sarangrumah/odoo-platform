# -*- coding: utf-8 -*-
"""Shared plumbing for the condition-reporting wizards.

Both the damage and the missing wizard take a set of assets, refuse the ones
that make no sense, move serials and write history. Keeping that in one place
means the two wizards cannot drift apart on which assets they accept.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AssetConditionWizardMixin(models.AbstractModel):
    _name = "custom.asset.condition.wizard.mixin"
    _description = "Asset Condition Wizard Mixin"

    asset_ids = fields.Many2many(
        comodel_name="custom.fixed.asset",
        string="Assets",
        required=True,
    )
    event_date = fields.Date(required=True, default=fields.Date.context_today)
    description = fields.Text(required=True)
    reference = fields.Char(string="Document Reference")
    move_serial = fields.Boolean(
        string="Move Serial",
        default=True,
        help="Transfer each unit's serial number to the destination location. "
        "Register-only units with no serial in stock are simply skipped.",
    )
    asset_count = fields.Integer(compute="_compute_asset_count")
    without_serial_count = fields.Integer(compute="_compute_asset_count")

    @api.depends("asset_ids.lot_id")
    def _compute_asset_count(self):
        for wizard in self:
            wizard.asset_count = len(wizard.asset_ids)
            wizard.without_serial_count = len(wizard.asset_ids.filtered(lambda a: not a.lot_id))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("active_model") == "custom.fixed.asset":
            res["asset_ids"] = [(6, 0, self.env.context.get("active_ids", []))]
        return res

    def _validate_assets(self, forbidden_conditions):
        self.ensure_one()
        if not self.asset_ids:
            raise UserError(_("Select at least one asset."))
        disposed = self.asset_ids.filtered(lambda a: a.state in ("disposed", "cancelled"))
        if disposed:
            raise UserError(
                _(
                    "These assets are no longer in the register and cannot be reported on: %(codes)s",
                    codes=", ".join(disposed.mapped("code")),
                )
            )
        clash = self.asset_ids.filtered(lambda a: a.condition in forbidden_conditions)
        if clash:
            raise UserError(
                _(
                    "Already reported: %(codes)s",
                    codes=", ".join("%s (%s)" % (a.code, a.condition) for a in clash),
                )
            )

    def _destination_location(self, asset):
        raise NotImplementedError

    def _check_destination_company(self, asset, location):
        """Say which company is wrong here, rather than letting stock say it later.

        Core raises a generic company-inconsistency error deep inside picking
        validation. Naming the asset and both companies turns a puzzle into an
        instruction.
        """
        if location and location.company_id and location.company_id != asset.company_id:
            raise UserError(
                _(
                    "Asset %(code)s belongs to %(owner)s, but the destination "
                    "%(location)s belongs to %(other)s. Configure a destination of "
                    "%(owner)s under Accounting Settings > Asset Lifecycle.",
                    code=asset.code,
                    owner=asset.company_id.name,
                    location=location.complete_name,
                    other=location.company_id.name,
                )
            )

    def _apply(self, event_type, condition_to, extra_asset_vals=None):
        """Move the serials, write the condition, append the history rows."""
        self.ensure_one()
        logs = self.env["custom.asset.condition.log"]
        for asset in self.asset_ids:
            picking = self.env["stock.picking"]
            destination = self._destination_location(asset)
            self._check_destination_company(asset, destination)
            # Read the origin before moving: afterwards the unit is in the damage
            # or lost warehouse and where it came from is unrecoverable.
            origin = asset._resolve_serial_source_location()
            if self.move_serial and asset.lot_id:
                picking = asset._move_serial_to(destination, reference=self.reference or asset.code)
            logs |= asset._log_condition_event(
                event_type,
                condition_to=condition_to,
                event_date=self.event_date,
                description=self.description,
                reference=self.reference,
                picking_id=picking.id or None,
                location_id=destination.id or None,
                from_location_id=origin.id or None,
            )
            if extra_asset_vals:
                asset.write(extra_asset_vals)
            rental = asset.rental_asset_id
            if rental and rental.state != "on_rent":
                rental.state = "maintenance"
        return logs

    def _open_logs(self, logs):
        return {
            "type": "ir.actions.act_window",
            "name": _("Condition Events"),
            "res_model": "custom.asset.condition.log",
            "view_mode": "list,form",
            "domain": [("id", "in", logs.ids)],
            "context": {"create": False},
        }
