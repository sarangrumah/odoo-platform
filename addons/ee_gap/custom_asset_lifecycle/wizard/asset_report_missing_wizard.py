# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class AssetReportMissingWizard(models.TransientModel):
    _name = "custom.asset.report.missing.wizard"
    _description = "Report Asset Missing"
    _inherit = ["custom.asset.condition.wizard.mixin"]

    missing_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Lost/Missing Location",
        domain="[('usage', '=', 'internal')]",
        default=lambda self: self.env.company.asset_missing_location_id,
        help="Leave empty to use the company's configured lost/missing location.",
    )
    reference = fields.Char(
        string="Report Reference (BAP)",
        required=True,
        help="Incident report / BAP number. Required: a missing unit eventually "
        "becomes a write-off, and the write-off needs a document behind it.",
    )
    open_writeoff = fields.Boolean(
        string="Write Off Immediately",
        default=False,
        help="Only when the loss is already confirmed and Finance is ready to "
        "derecognise. Otherwise leave unticked: the unit stays running and keeps "
        "depreciating while the loss is investigated, which is what IAS 16 requires.",
    )

    def _destination_location(self, asset):
        location = self.missing_location_id or asset.company_id.asset_missing_location_id
        if self.move_serial and asset.lot_id and not location:
            raise UserError(
                _(
                    "No lost/missing location set. Configure it under Accounting "
                    "Settings > Asset Lifecycle, or untick Move Serial."
                )
            )
        return location

    def action_report_missing(self):
        self.ensure_one()
        self._validate_assets(("missing", "written_off"))
        logs = self._apply(
            "missing",
            "missing",
            extra_asset_vals={
                "missing_reported_on": self.event_date,
                "missing_reference": self.reference,
            },
        )
        if self.open_writeoff:
            if len(self.asset_ids) != 1:
                raise UserError(_("Write off one asset at a time -- each disposal entry is posted individually."))
            return self.asset_ids.action_open_writeoff_wizard()
        return self._open_logs(logs)
