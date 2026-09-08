# -*- coding: utf-8 -*-
"""Keep the legacy analytic dimension in step with the new master.

After the migration the Operating Unit is the master and the analytic account
is one of its links. Everything Levi's already has still reads
``l10n_ou_analytic_id`` (it is what feeds ``analytic_distribution``, the P&L by
branch, the GL analysis view and the retail import), so picking a unit on a line
must fill that field — otherwise the ledger would quietly stop carrying the
dimension the reports are built on.

Only ever *fills* it: a line that already names an analytic keeps it, so
historical rows and the localization's own stamping are untouched. The arrow
never points the other way — this module does not write
``analytic_distribution``, `custom_levis_localization` still owns that.
"""

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Relabelled to keep the two dimensions apart on screen and in the logs:
    # the localization's field is the *analytic* leg of the same unit, and Odoo
    # warns loudly when two fields of a model share a label.
    l10n_ou_analytic_id = fields.Many2one(string="Operating Unit (Analytic)")

    @api.onchange("operating_unit_id")
    def _onchange_operating_unit_analytic(self):
        for line in self:
            analytic = line.operating_unit_id.analytic_account_id
            if analytic and not line.l10n_ou_analytic_id:
                line.l10n_ou_analytic_id = analytic.id

    @api.model_create_multi
    def create(self, vals_list):
        units = self.env["operating.unit"]
        for vals in vals_list:
            if vals.get("operating_unit_id") and not vals.get("l10n_ou_analytic_id"):
                unit = units.browse(vals["operating_unit_id"])
                if unit.analytic_account_id:
                    vals["l10n_ou_analytic_id"] = unit.analytic_account_id.id
        return super().create(vals_list)


class OperatingUnit(models.Model):
    _inherit = "operating.unit"

    l10n_levis_store_code = fields.Char(
        related="warehouse_id.code",
        string="Store Code (retail import)",
        readonly=True,
        help="The code X24 / X101 join on. Shown here so nobody is tempted to "
        "change it on the warehouse to match a renamed unit.",
    )


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    l10n_ou_analytic_display = fields.Char(string="Operating Unit (Analytic)")
