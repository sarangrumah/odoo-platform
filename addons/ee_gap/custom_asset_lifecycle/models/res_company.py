# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    asset_damage_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Asset Damage Location",
        domain="[('usage', '=', 'internal')]",
        help="Where a serial goes when its unit is reported damaged.",
    )
    asset_missing_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Asset Lost/Missing Location",
        domain="[('usage', '=', 'internal')]",
        help="Where a serial goes when its unit is reported missing, so it stops "
        "counting as available on-hand stock while the loss is investigated.",
    )
    asset_loss_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Asset Loss Account",
        help="Expense account debited for the net book value of a written-off unit.",
    )
    asset_compensation_income_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Asset Compensation Income Account",
        help="Income account credited at fair value when a client hands over a "
        "replacement unit that becomes company property.",
    )
    asset_replacement_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Asset Replacement Journal",
        domain="[('type', '=', 'general')]",
        help="Journal used for the acquisition entry of a replacement unit. "
        "Falls back to the asset's own depreciation journal.",
    )
    asset_equipment_category_id = fields.Many2one(
        comodel_name="maintenance.equipment.category",
        string="Asset Equipment Category",
        help="Default maintenance category for equipment cards created from the register.",
    )

    @api.constrains(
        "asset_damage_location_id",
        "asset_missing_location_id",
    )
    def _check_lifecycle_locations_company(self):
        """A location belonging to another company cannot receive these units.

        Odoo refuses the transfer at validation time with a company-inconsistency
        error, which is safe but arrives at the worst possible moment -- the
        operator is mid-report on a broken unit. Worse, it is easy to configure by
        accident: warehouse codes are unique across companies, so a setup script
        that resolves ``DMG`` by code happily hands company 1's damage warehouse
        to company 2. That is exactly what happened on prd_arkaaim.
        """
        for company in self:
            for field, label in (
                ("asset_damage_location_id", _("Asset Damage Location")),
                ("asset_missing_location_id", _("Asset Lost/Missing Location")),
            ):
                location = company[field]
                if location and location.company_id and location.company_id != company:
                    raise ValidationError(
                        _(
                            "%(label)s %(location)s belongs to %(owner)s, but you are "
                            "configuring %(company)s. Units cannot be transferred "
                            "across companies, so pick a location of "
                            "%(company)s -- or a shared one.",
                            label=label,
                            location=location.complete_name,
                            owner=location.company_id.name,
                            company=company.name,
                        )
                    )
