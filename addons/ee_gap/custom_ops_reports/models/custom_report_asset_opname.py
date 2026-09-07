# -*- coding: utf-8 -*-
"""#15 General Report Aset — monthly stock-opname of the fleet.

One row per fixed-asset unit (``custom.fixed.asset``), enriched best-effort with:

* **Operational state** — ``rental.asset.state`` (available / on_rent /
  maintenance / retired) of the rental unit linked to this asset.
* **Condition** — the ``condition`` (good / damaged / partial) on the most
  recent ``custom.bast.line`` for the asset's serial/lot.

Both enrichments follow the hard FKs contributed by ``custom_asset_from_receipt``
(``custom.fixed.asset.lot_id`` and ``.rental_asset_ids``) when they are present.
They used to be matched on the ``serial_number`` *string* instead, which only
worked while every unit's serial was a copy of its asset code; once the register
carries real physical serials — many units have none at all — a string join
silently drops rows. The string match survives only as a fallback for a database
that has no link module installed. Units with no match show a blank operational
state / condition. This is a snapshot (no period).

``custom.fixed.asset.serial_number`` is contributed by the ARKA tenant module
``custom_arka_aim_asset_register``, not by the generic asset app. This report
does not depend on that tenant module — depending on it would drag ARKA's
3,329-unit data seed into any database that merely wanted the report — so the
serial is displayed only when the field is present, and the column is blank when
it is not.
"""

from odoo import models


class CustomReportAssetOpname(models.AbstractModel):
    _name = "custom.report.asset.opname"
    _inherit = "custom.report.engine"
    _description = "Asset Opname Report"

    _report_code = "asset_opname"
    _report_title = "General Report Aset (Opname)"

    def _xlsx_columns(self):
        return [
            {"header": "No", "field": "seq", "kind": "number", "width": 6},
            {"header": "Code", "field": "code", "kind": "text", "width": 16},
            {"header": "Unit", "field": "name", "kind": "text", "width": 32},
            {"header": "Serial", "field": "serial", "kind": "text", "width": 22},
            {"header": "Group", "field": "group", "kind": "text", "width": 22},
            {"header": "Location", "field": "location", "kind": "text", "width": 22},
            {"header": "Asset State", "field": "state", "kind": "text", "width": 14},
            {"header": "Operational", "field": "op_state", "kind": "text", "width": 14},
            {"header": "Condition", "field": "condition", "kind": "text", "width": 12},
        ]

    def _asset_to_op_state(self, assets, company_ids):
        """{fixed asset id: rental.asset.state}, followed through the FK.

        Falls back to matching ``rental.asset.serial_number`` against the
        register's serial when the linking module is not installed.
        """
        Rental = self.env["rental.asset"]
        if "fixed_asset_id" in Rental._fields:
            rentals = Rental.search(
                [
                    ("fixed_asset_id", "in", assets.ids),
                    ("company_id", "in", company_ids + [False]),
                ]
            )
            return {rental.fixed_asset_id.id: rental.state for rental in rentals}

        if "serial_number" not in assets._fields:
            return {}
        by_serial = {}
        for rental in Rental.search([("serial_number", "!=", False), ("company_id", "in", company_ids + [False])]):
            by_serial.setdefault(rental.serial_number, rental.state)
        return {
            asset.id: by_serial[asset.serial_number]
            for asset in assets
            if asset.serial_number and asset.serial_number in by_serial
        }

    def _asset_to_condition(self, assets):
        """{fixed asset id: latest custom.bast.line.condition}, via the lot FK.

        The newest BAST line (highest id) for a lot wins. Without the lot FK the
        register cannot be tied to a BAST at all, so the column stays blank.
        """
        if "lot_id" not in assets._fields:
            return {}
        lot_ids = [asset.lot_id.id for asset in assets if asset.lot_id]
        if not lot_ids:
            return {}
        by_lot = {}
        # Newest first so the first write per lot is the latest condition.
        for line in self.env["custom.bast.line"].search([("lot_id", "in", lot_ids)], order="id desc"):
            by_lot.setdefault(line.lot_id.id, line.condition)
        return {asset.id: by_lot[asset.lot_id.id] for asset in assets if asset.lot_id and asset.lot_id.id in by_lot}

    def _has_serial(self):
        """The serial lives on a tenant module; it may simply not be there."""
        return "serial_number" in self.env["custom.fixed.asset"]._fields

    def _build_lines(self, filters):
        company_ids = filters["company_ids"]
        domain = [("company_id", "in", company_ids)]
        if filters.get("group_ids"):
            domain.append(("group_id", "in", filters["group_ids"]))
        if filters.get("location_ids"):
            domain.append(("location_id", "in", filters["location_ids"]))
        if filters.get("state"):
            domain.append(("state", "=", filters["state"]))

        has_serial = self._has_serial()

        state_labels = dict(self.env["custom.fixed.asset"]._fields["state"]._description_selection(self.env))

        assets = self.env["custom.fixed.asset"].search(domain, order="code")
        op_by_asset = self._asset_to_op_state(assets, company_ids)
        cond_by_asset = self._asset_to_condition(assets)
        lines = []
        n_good = n_damaged = n_on_rent = 0
        for idx, asset in enumerate(assets, start=1):
            serial = (asset.serial_number or "") if has_serial else ""
            op_state = op_by_asset.get(asset.id, "")
            condition = cond_by_asset.get(asset.id, "")
            if condition == "good":
                n_good += 1
            elif condition == "damaged":
                n_damaged += 1
            if op_state == "on_rent":
                n_on_rent += 1
            lines.append(
                {
                    "seq": idx,
                    "code": asset.code or "",
                    "name": asset.name or "",
                    "serial": serial,
                    "group": asset.group_id.name or "",
                    "location": asset.location_id.name or "",
                    "state": state_labels.get(asset.state, asset.state or ""),
                    "op_state": op_state,
                    "condition": condition,
                }
            )

        lines.append(
            {
                "type": "grand_total",
                "name": "Total units: %d | Good: %d | Damaged: %d | On rent: %d"
                % (len(assets), n_good, n_damaged, n_on_rent),
            }
        )
        return lines
