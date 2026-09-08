# -*- coding: utf-8 -*-
"""Condition, repair history and replacement lineage on the fixed-asset register.

The one rule that shapes this whole file: **condition is not state**. An asset
that is damaged, sitting in the repair shop or reported missing but not yet
derecognised stays ``state = 'running'`` and keeps depreciating. IAS 16.55 /
PSAK 16: depreciation does not cease while an asset is idle or retired from
active use; it ceases at derecognition. So nothing here writes ``state`` --
that is the disposal wizard's job -- and the monthly depreciation cron, which
searches on ``state = 'running'``, keeps picking these assets up.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .asset_condition_log import CONDITIONS

# Conditions that mean the unit is not available for work right now.
UNAVAILABLE_CONDITIONS = ("damaged", "in_repair", "repaired", "missing", "written_off")


class CustomFixedAsset(models.Model):
    _inherit = "custom.fixed.asset"

    # ------------------------------------------------------------------
    # Condition
    # ------------------------------------------------------------------
    condition = fields.Selection(
        selection=CONDITIONS,
        default="ok",
        required=True,
        index=True,
        tracking=True,
        copy=False,
        help="Physical condition of the unit. Independent of the accounting state: "
        "a damaged or under-repair asset stays running and keeps depreciating.",
    )
    condition_note = fields.Text(
        string="Condition Note",
        copy=False,
        help="Narrative from the most recent condition event.",
    )
    condition_changed_on = fields.Datetime(readonly=True, copy=False)
    condition_changed_by = fields.Many2one(
        comodel_name="res.users",
        string="Condition Reported By",
        readonly=True,
        copy=False,
    )
    condition_log_ids = fields.One2many(
        comodel_name="custom.asset.condition.log",
        inverse_name="asset_id",
        string="Condition History",
    )
    condition_log_count = fields.Integer(compute="_compute_condition_log_count")

    # ------------------------------------------------------------------
    # Missing
    # ------------------------------------------------------------------
    missing_reported_on = fields.Date(readonly=True, copy=False)
    missing_reference = fields.Char(
        string="Missing Report Ref.",
        readonly=True,
        copy=False,
        help="BAP / incident report number backing the loss.",
    )

    # ------------------------------------------------------------------
    # Maintenance & repair
    # ------------------------------------------------------------------
    equipment_id = fields.Many2one(
        comodel_name="maintenance.equipment",
        string="Equipment Card",
        copy=False,
        index=True,
        help="Maintenance equipment record carrying this unit's failure history.",
    )
    repair_order_ids = fields.One2many(
        comodel_name="repair.order",
        inverse_name="x_fixed_asset_id",
        string="Repair Orders",
    )
    repair_count = fields.Integer(compute="_compute_repair_figures")
    repair_cost_total = fields.Monetary(
        string="Lifetime Repair Cost",
        compute="_compute_repair_figures",
        currency_field="currency_id",
        help="Repair cost actually borne by the company. Warranty claims are excluded.",
    )
    open_repair_id = fields.Many2one(
        comodel_name="repair.order",
        string="Open Repair",
        compute="_compute_repair_figures",
    )

    # ------------------------------------------------------------------
    # Replacement lineage
    # ------------------------------------------------------------------
    replaces_asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        string="Replaces Asset",
        copy=False,
        index=True,
        help="The unit this asset was brought in to replace.",
    )
    replaced_by_asset_ids = fields.One2many(
        comodel_name="custom.fixed.asset",
        inverse_name="replaces_asset_id",
        string="Replaced By",
    )
    replaced_by_asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        string="Replacement Unit",
        compute="_compute_replaced_by_asset_id",
        store=True,
    )
    is_replacement = fields.Boolean(
        compute="_compute_is_replacement",
        store=True,
        index=True,
        help="This unit entered the register as a replacement for another one.",
    )
    replacement_reason = fields.Selection(
        selection=[("damage", "Beyond Repair"), ("missing", "Lost / Missing")],
        copy=False,
    )
    replacement_claim_ref = fields.Char(
        string="Client Claim Ref.",
        copy=False,
        help="Client claim / correspondence reference behind the replacement.",
    )
    replacement_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Replacement Acquisition Entry",
        readonly=True,
        copy=False,
        help="Journal entry that capitalised this replacement unit at fair value. "
        "The register posts no acquisition entry of its own, so without this the "
        "register would grow while the GL stood still.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("condition_log_ids")
    def _compute_condition_log_count(self):
        counts = {}
        if self.ids:
            groups = self.env["custom.asset.condition.log"]._read_group(
                domain=[("asset_id", "in", self.ids)],
                groupby=["asset_id"],
                aggregates=["__count"],
            )
            counts = {asset.id: count for asset, count in groups}
        for asset in self:
            asset.condition_log_count = counts.get(asset.id, 0)

    @api.depends(
        "repair_order_ids.state",
        "repair_order_ids.x_total_repair_cost",
        "repair_order_ids.x_repair_channel",
    )
    def _compute_repair_figures(self):
        for asset in self:
            repairs = asset.repair_order_ids
            asset.repair_count = len(repairs)
            # A warranty claim costs the company nothing, so it must not inflate
            # the unit's lifetime repair cost -- that figure is what Finance uses
            # to decide whether a unit is worth keeping.
            billable = repairs.filtered(lambda r: r.x_repair_channel != "warranty")
            asset.repair_cost_total = sum(billable.mapped("x_total_repair_cost"))
            asset.open_repair_id = repairs.filtered(lambda r: r.state not in ("done", "cancel"))[:1]

    @api.depends("replaced_by_asset_ids")
    def _compute_replaced_by_asset_id(self):
        for asset in self:
            asset.replaced_by_asset_id = asset.replaced_by_asset_ids[:1]

    @api.depends("replaces_asset_id")
    def _compute_is_replacement(self):
        for asset in self:
            asset.is_replacement = bool(asset.replaces_asset_id)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("replaces_asset_id")
    def _check_replaces_asset(self):
        for asset in self:
            replaced = asset.replaces_asset_id
            if not replaced:
                continue
            if replaced == asset:
                raise UserError(_("An asset cannot replace itself."))
            if replaced.company_id != asset.company_id:
                raise UserError(
                    _(
                        "Replacement %(new)s and replaced unit %(old)s belong to different companies.",
                        new=asset.code or asset.name,
                        old=replaced.code or replaced.name,
                    )
                )

    # ------------------------------------------------------------------
    # Condition engine -- every transition goes through here
    # ------------------------------------------------------------------
    def _log_condition_event(self, event_type, condition_to=None, **vals):
        """Write the condition, stamp the asset and append a history row.

        Returns the created logs. Never touches ``state``: see the module
        docstring on why depreciation must keep running.
        """
        Log = self.env["custom.asset.condition.log"]
        logs = Log.browse()
        now = fields.Datetime.now()
        for asset in self:
            log_vals = {
                "asset_id": asset.id,
                "event_type": event_type,
                "condition_from": asset.condition,
                "condition_to": condition_to or asset.condition,
                "event_date": vals.get("event_date") or fields.Date.context_today(self),
                "description": vals.get("description"),
                "reference": vals.get("reference"),
                "repair_order_id": vals.get("repair_order_id"),
                "maintenance_request_id": vals.get("maintenance_request_id"),
                "picking_id": vals.get("picking_id"),
                "location_id": vals.get("location_id"),
                "from_location_id": vals.get("from_location_id"),
                "move_id": vals.get("move_id"),
                "replacement_asset_id": vals.get("replacement_asset_id"),
            }
            logs |= Log.create({k: v for k, v in log_vals.items() if v is not None})
            asset_vals = {
                "condition_changed_on": now,
                "condition_changed_by": self.env.user.id,
            }
            if condition_to and condition_to != asset.condition:
                asset_vals["condition"] = condition_to
            if vals.get("description"):
                asset_vals["condition_note"] = vals["description"]
            asset.write(asset_vals)
            asset.message_post(
                body=_(
                    "Condition event: %(event)s. %(note)s",
                    event=dict(Log._fields["event_type"].selection).get(event_type, event_type),
                    note=vals.get("description") or "",
                )
            )
        return logs

    # ------------------------------------------------------------------
    # Derecognition closes the lifecycle
    # ------------------------------------------------------------------
    def write(self, vals):
        """Mirror derecognition into the condition field.

        The disposal wizard writes ``state = 'disposed'`` and knows nothing about
        conditions. Catching it here means a written-off unit can never be left
        showing as merely *missing*, which is what an Ops user would otherwise
        see forever on the damaged/missing dashboards.
        """
        becoming_disposed = self.filtered(lambda a: vals.get("state") == "disposed" and a.state != "disposed")
        res = super().write(vals)
        for asset in becoming_disposed:
            if asset.condition == "written_off":
                continue
            asset._log_condition_event(
                "write_off",
                condition_to="written_off",
                description=_("Derecognised on disposal."),
                event_date=asset.disposal_date,
                reference=asset.missing_reference,
                move_id=asset.disposal_move_id.id or None,
            )
        return res

    # ------------------------------------------------------------------
    # Serial movement helpers
    # ------------------------------------------------------------------
    def _home_stock_location(self):
        """Where a repaired or recovered unit goes back to.

        Three answers, best first. The unit's current position is never one of
        them -- by the time we ask, it is sitting in the damage warehouse.

        1. **Where it actually was.** Recorded on the condition event that took
           it away. Nothing else knows this as precisely, and it survives a fleet
           that is spread across several locations.
        2. The accounting asset location's stock counterpart, where Finance has
           mapped one.
        3. The company warehouse's stock location, as a last resort.
        """
        self.ensure_one()
        origin = self.condition_log_ids.filtered("from_location_id")[:1].from_location_id
        if origin:
            return origin
        mapped = self.location_id.stock_location_id
        if mapped:
            return mapped
        return self._fleet_home_location()

    def _fleet_home_location(self):
        """Last resort: wherever the rest of this company's fleet lives.

        Picking "the company's warehouse" with an unordered ``search(limit=1)``
        is the same class of assumption as the cross-company bug: PT Aero Inovasi
        Media has four warehouses, all on sequence 10, so the winner is decided by
        id -- and two of the four are the damage and lost warehouses, which is the
        last place a returning unit should be sent.

        Ask the register instead. Only reached when the unit has no recorded
        origin and its asset location maps to no warehouse location.
        """
        self.ensure_one()
        groups = self.sudo()._read_group(
            domain=[
                ("company_id", "=", self.company_id.id),
                ("stock_location_id", "!=", False),
                ("condition", "=", "ok"),
            ],
            groupby=["stock_location_id"],
            aggregates=["__count"],
        )
        if groups:
            return sorted(groups, key=lambda pair: pair[1], reverse=True)[0][0]
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1, order="sequence, id"
        )
        return warehouse.lot_stock_id if warehouse else self.env["stock.location"]

    def _resolve_serial_source_location(self):
        """Where the serial *net* sits right now.

        Not the same question as ``stock_location_id``, which picks the largest
        positive quant. A serial whose history includes a badly-sourced picking
        ends up with, say, +1 in one place and +1/-1 in another: the largest
        positive quant then names a location the unit is not actually in, and
        moving from there just mints another negative. prd_arkaaim carries
        exactly that shape on part of the fleet, so the source is resolved from
        the net per location and a unit that is nowhere is refused outright.
        """
        self.ensure_one()
        if not self.lot_id:
            return self.env["stock.location"]
        groups = (
            self.env["stock.quant"]
            .sudo()
            ._read_group(
                domain=[
                    ("lot_id", "=", self.lot_id.id),
                    ("location_id.usage", "in", ("internal", "transit")),
                ],
                groupby=["location_id"],
                aggregates=["quantity:sum"],
            )
        )
        positive = [(loc, qty) for loc, qty in groups if qty > 0]
        if not positive:
            return self.env["stock.location"]
        positive.sort(key=lambda pair: pair[1], reverse=True)
        return positive[0][0]

    def _move_serial_to(self, location, reference=None):
        """Validate an internal transfer of this unit's serial into ``location``.

        Returns the picking, or an empty recordset when the unit has no serial
        in stock (register-only assets, of which the ARKA-AIM register has 490).
        No valuation can result: these units live in a non-valuated category
        with a zero cost -- see ``custom_asset_stock_link``.
        """
        self.ensure_one()
        lot = self.lot_id
        source = self._resolve_serial_source_location()
        if lot and not source and self.stock_location_id:
            raise UserError(
                _(
                    "Serial %(serial)s of asset %(code)s is not on hand anywhere: its "
                    "quants net to zero or below. Fix the stock position with an "
                    "inventory adjustment first, or untick Move Serial to record the "
                    "condition without moving anything.",
                    serial=lot.name,
                    code=self.code,
                )
            )
        # Nothing to move: register-only units carry no serial in stock (490 of
        # them on the ARKA-AIM register). Ask for a destination only once we know
        # there is something to send there.
        if not lot or not source:
            return self.env["stock.picking"]
        if not location:
            raise UserError(
                _(
                    "No destination location configured. Set the damage and "
                    "lost/missing locations under Accounting Settings > Asset Lifecycle."
                )
            )
        if source == location:
            return self.env["stock.picking"]
        warehouse = location.warehouse_id or source.warehouse_id
        picking_type = warehouse.int_type_id if warehouse else False
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search(
                [("code", "=", "internal"), ("company_id", "=", self.company_id.id)], limit=1
            )
        if not picking_type:
            raise UserError(_("No internal transfer operation type found for %s.", self.company_id.name))

        product = self.product_id or lot.product_id
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": location.id,
                "origin": reference or self.code,
                "company_id": self.company_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 1.0,
                            "product_uom": product.uom_id.id,
                            "description_picking": _("Asset %(code)s", code=self.code),
                            "location_id": source.id,
                            "location_dest_id": location.id,
                            "company_id": self.company_id.id,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        move = picking.move_ids[:1]
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "lot_id": lot.id,
                "quantity": 1.0,
                "location_id": source.id,
                "location_dest_id": location.id,
                "company_id": self.company_id.id,
            }
        )
        picking.button_validate()
        return picking

    # ------------------------------------------------------------------
    # Maintenance equipment provisioning
    # ------------------------------------------------------------------
    def _ensure_equipment(self, category=None):
        """Create the maintenance.equipment card backing this unit's history.

        Also fills ``rental.asset.equipment_id`` where a rental unit exists, so
        the quality/maintenance hook that already ships in
        ``custom_rental_quality_hook`` has something to hang failures on.

        ``serial_no`` gets the **asset code**, not the physical serial. Core
        maintenance puts a global ``unique(serial_no)`` on that column, and the
        physical serials are not unique -- the ARKA-AIM listing repeats eight
        battery serials, so keying cards on them fails outright partway through
        the fleet. The asset code is unique per company, is already what each
        unit's ``stock.lot`` is named, and so is the identifier the rest of the
        platform recognises. The physical serial goes in the note, where it stays
        readable and searchable without a constraint on it.
        """
        Equipment = self.env["maintenance.equipment"]
        created = Equipment.browse()
        # One query for the whole batch: 3,180 cards at a time is the normal case.
        candidates = [asset.code for asset in self if not asset.equipment_id]
        taken = set(
            Equipment.with_context(active_test=False)
            .sudo()
            .search([("serial_no", "in", candidates)])
            .mapped("serial_no")
        )
        for asset in self:
            if asset.equipment_id:
                continue
            # Asset codes are unique per company; the constraint is global. Two
            # companies sharing a code is unlikely but not impossible.
            serial_no = asset.code
            if serial_no in taken:
                serial_no = "%s/%s" % (asset.code, asset.company_id.id)
            taken.add(serial_no)
            note = _("Physical serial: %s", asset.serial_number) if asset.serial_number else False
            equipment = Equipment.create(
                {
                    "name": "%s [%s]" % (asset.name, asset.code),
                    "serial_no": serial_no,
                    "category_id": (category or asset.company_id.asset_equipment_category_id).id or False,
                    "company_id": asset.company_id.id,
                    "partner_ref": asset.serial_number or asset.code,
                    "effective_date": asset.acquisition_date,
                    "note": note,
                }
            )
            asset.equipment_id = equipment
            rental = asset.rental_asset_id
            if rental and "equipment_id" in rental._fields and not rental.equipment_id:
                rental.equipment_id = equipment
            created |= equipment
        return created

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _open_lifecycle_wizard(self, model, name):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "custom.fixed.asset",
                "active_ids": self.ids,
                "default_asset_ids": [(6, 0, self.ids)],
            },
        }

    def action_open_report_damage_wizard(self):
        return self._open_lifecycle_wizard("custom.asset.report.damage.wizard", _("Report Damage"))

    def action_open_report_missing_wizard(self):
        return self._open_lifecycle_wizard("custom.asset.report.missing.wizard", _("Report Missing"))

    def action_open_replacement_wizard(self):
        self.ensure_one()
        if self.replaced_by_asset_id:
            raise UserError(
                _(
                    "Asset %(code)s has already been replaced by %(new)s.",
                    code=self.code,
                    new=self.replaced_by_asset_id.code,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Register Replacement Unit"),
            "res_model": "custom.asset.replacement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_replaced_asset_id": self.id},
        }

    def action_open_writeoff_wizard(self):
        """Derecognise a missing unit through the standard disposal wizard.

        Proceeds are zero, so the loss equals NBV. This is the only point in the
        lifecycle where depreciation actually stops.
        """
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("Only running assets can be written off."))
        company = self.company_id
        return {
            "type": "ir.actions.act_window",
            "name": _("Write Off %s", self.code),
            "res_model": "custom.fixed.asset.disposal.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_asset_id": self.id,
                "default_disposal_value": 0.0,
                "default_loss_account_id": company.asset_loss_account_id.id,
                "default_note": _(
                    "Write-off of missing asset %(code)s. Report ref: %(ref)s",
                    code=self.code,
                    ref=self.missing_reference or "-",
                ),
                "asset_lifecycle_writeoff": True,
            },
        }

    def action_return_to_service(self):
        """Bring a repaired unit home and clear its condition."""
        for asset in self:
            if asset.condition not in ("damaged", "in_repair", "repaired", "missing"):
                raise UserError(
                    _(
                        "Asset %(code)s is already serviceable - nothing to return.",
                        code=asset.code,
                    )
                )
            open_repair = asset.open_repair_id
            if open_repair:
                raise UserError(
                    _(
                        "Repair order %(name)s on asset %(code)s is still open. Close "
                        "or cancel it before returning the unit to service.",
                        name=open_repair.name,
                        code=asset.code,
                    )
                )
            event = "found" if asset.condition == "missing" else "return_service"
            home = asset._home_stock_location()
            if asset.lot_id and not home:
                raise UserError(
                    _(
                        "Nowhere to return asset %(code)s to: it has no recorded "
                        "origin, its asset location maps to no warehouse location, "
                        "and %(company)s has no warehouse. Map the asset location "
                        "or move the serial by hand.",
                        code=asset.code,
                        company=asset.company_id.name,
                    )
                )
            source = asset._resolve_serial_source_location()
            picking = asset._move_serial_to(home, reference=asset.code)
            asset._log_condition_event(
                event,
                condition_to="ok",
                description=_("Returned to service."),
                picking_id=picking.id if picking else None,
                location_id=home.id or None,
                from_location_id=source.id or None,
            )
            rental = asset.rental_asset_id
            if rental and rental.state == "maintenance":
                rental.state = "available"
        return True

    def action_view_repairs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Repairs of %s", self.display_name),
            "res_model": "repair.order",
            "view_mode": "list,form",
            "domain": [("x_fixed_asset_id", "=", self.id)],
            "context": {"default_x_fixed_asset_id": self.id},
        }

    def action_view_condition_log(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Condition History of %s", self.display_name),
            "res_model": "custom.asset.condition.log",
            "view_mode": "list,form",
            "domain": [("asset_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_open_equipment_provision_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Equipment Cards"),
            "res_model": "custom.asset.equipment.provision.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "custom.fixed.asset",
                "active_ids": self.ids,
                "default_asset_ids": [(6, 0, self.ids)],
            },
        }
