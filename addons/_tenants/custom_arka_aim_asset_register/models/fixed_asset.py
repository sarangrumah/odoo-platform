# -*- coding: utf-8 -*-
"""Serial-tracking extension of ``custom.fixed.asset``.

The base model has no serial or source-listing fields (one record = one asset).
The AIM drone register is loaded per unit/serial, so we add a small set of
identity fields to hold the physical listing's serial number, asset group and
description. These are informational only -- they do not affect depreciation.
"""

from odoo import api, fields, models


class CustomFixedAssetGroup(models.Model):
    _inherit = "custom.fixed.asset.group"

    @api.model
    def _seed_aim_asset_register(self):
        """Data-hook entry point: upsert the AIM asset group + location.

        Delegates to ``hooks.seed_group_and_location`` (lazy import to avoid a
        circular import at module load). Idempotent -> safe to re-run on every
        module upgrade.
        """
        from ..hooks import seed_group_and_location

        seed_group_and_location(self.env)
        return True


class CustomFixedAsset(models.Model):
    _inherit = "custom.fixed.asset"

    # The register is looked up by serial on the floor, so the serial has to be
    # reachable from the plain search box and from any m2o picker -- not only
    # from the "Search Serial Number for:" dropdown entry.
    _rec_names_search = ["name", "code", "serial_number"]

    serial_number = fields.Char(
        index=True,
        copy=False,
        help="Physical serial number from the asset listing (blank for spares/consumables that carry no serial). "
        "Not unique: the client's own listing repeats eight battery serials.",
    )
    source_group = fields.Char(
        string="Source Asset Group",
        help="Asset Group as it appears in the source listing (provenance).",
    )
    source_desc = fields.Char(
        string="Source Description",
        help="Asset Description as it appears in the source listing (provenance).",
    )

    @api.model
    def _seed_aim_asset_serials(self):
        """Data-hook entry point: (re)write the physical serials on every upgrade.

        Delegates to ``hooks.load_serial_numbers`` (lazy import, as above). It
        only touches a serial that is blank or a copy of the asset code, so it is
        idempotent and never clobbers a serial a human corrected by hand.
        """
        from ..hooks import load_serial_numbers

        load_serial_numbers(self.env)
        return True
