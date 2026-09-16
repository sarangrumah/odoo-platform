# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AssetRegisterWizard(models.TransientModel):
    _name = "custom.report.asset.register.wizard"
    _description = "Asset Register Wizard"

    # Sheet row #60: "penarikan Asset Register Report bisa mendetail sampai ke
    # level tanggal, jangan hanya di level tahun". ``date_to`` is the as-of
    # date -- accumulation and book value are stated at it. Defaults reproduce
    # the old year-to-date behaviour, so nobody's saved habit changes.
    date_from = fields.Date(
        string="From",
        required=True,
        default=lambda self: date(fields.Date.context_today(self).year, 1, 1),
    )
    date_to = fields.Date(
        string="As Of",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    basis = fields.Selection(
        [
            ("posted", "Posted only (ledger)"),
            ("schedule", "Full schedule (incl. unposted)"),
        ],
        string="Basis",
        default="posted",
        required=True,
        help="Posted only: accumulation matches what the general ledger carries "
        "— use this for asset opname and monthly review. Full schedule: every "
        "planned depreciation line whether booked or not, which is the "
        "depreciation schedule rather than the register.",
    )
    company_ids = fields.Many2many(
        "res.company",
        default=lambda self: self.env.companies,
    )
    # Explicit short relation names: the auto-generated names
    # (custom_fixed_asset_group_custom_report_asset_register_wizard_rel, etc.)
    # exceed PostgreSQL's 63-char identifier limit and break registry load on Odoo 19.
    group_ids = fields.Many2many(
        "custom.fixed.asset.group",
        relation="asset_reg_wiz_group_rel",
        string="Groups",
    )
    location_ids = fields.Many2many(
        "custom.fixed.asset.location",
        relation="asset_reg_wiz_location_rel",
        string="Locations",
    )
    asset_states = fields.Selection(
        [
            ("running", "Running only"),
            ("all", "All (incl. draft/disposed)"),
        ],
        string="Assets",
        default="running",
        required=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("'From' cannot be later than 'As Of'."))

    def _build_filters(self):
        self.ensure_one()
        states = ["running"] if self.asset_states == "running" else []
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "group_ids": self.group_ids.ids,
            "location_ids": self.location_ids.ids,
            "asset_states": states,
            # The month columns span one calendar year; the closing year is the
            # one the reader is asking about.
            "year": self.date_to.year,
            "basis": self.basis,
        }

    def _options(self):
        filters = self._build_filters()
        return {
            **filters,
            "date_from": filters["date_from"].isoformat(),
            "date_to": filters["date_to"].isoformat(),
        }

    def action_print(self):
        self.ensure_one()
        data = {
            "doc_model": self._name,
            "options": self._options(),
        }
        return self.env.ref("custom_accounting_asset.action_report_asset_register").report_action(self, data=data)

    def action_export_xlsx(self):
        self.ensure_one()
        filename = "Asset_Register_%s.xlsx" % self.date_to
        return self.env["custom.report.asset.register"]._xlsx_action(self._options(), filename)
