# -*- coding: utf-8 -*-
"""Operating Unit on a fixed asset, as a field people can actually fill in.

Sheet item #24 (remark 07/09) asks for "field OPERATING UNIT ketika akuisisi",
and #57 for the analytic distribution to reach the depreciation journal. The
base module answers the second half: ``custom.fixed.asset`` now carries
``analytic_distribution`` and stamps it on every entry it writes.

But an analytic *distribution* is a percentage map across every analytic plan,
edited through a popover. Accounting here does not think in distributions —
they think "this laptop belongs to PIM2". So this module puts a plain
many2one on top, restricted to the Operating Unit plan, that writes the
distribution underneath it.

The distribution stays the source of truth: setting the OU writes
``{ou_id: 100}`` and clearing it clears the distribution, while an asset whose
distribution was set some other way (an import, a second plan, two stores
splitting one asset) still reads back whichever OU holds 100 % — and reads
back empty, rather than lying, when no single account does.
"""

from odoo import api, fields, models

# The analytic plan the Operating Unit accounts live under. Matched on name so
# this survives a tenant whose plan was created by hand rather than by seed;
# resolution is defensive everywhere, because a company that has no such plan
# must still be able to open an asset form.
OU_PLAN_NAME = "Operating Unit"


class CustomFixedAsset(models.Model):
    _inherit = "custom.fixed.asset"

    l10n_ou_analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        compute="_compute_l10n_ou_analytic_id",
        inverse="_inverse_l10n_ou_analytic_id",
        store=True,
        readonly=False,
        domain="[('plan_id.name', '=', 'Operating Unit')]",
        help="The store this asset belongs to. Writes the analytic "
        "distribution that every depreciation, disposal and revaluation entry "
        "for this asset will carry, so Accounting can read the store off the "
        "journal entry instead of off the asset register.",
    )

    @api.model
    def _l10n_ou_plan(self):
        """The Operating Unit analytic plan, or an empty recordset."""
        # ``order="id"`` so the choice is stable if a tenant ever ends up with
        # two plans of this name — better a consistently wrong plan that shows
        # up in testing than one that changes between calls.
        return self.env["account.analytic.plan"].search([("name", "=", OU_PLAN_NAME)], limit=1, order="id")

    @api.depends("analytic_distribution")
    def _compute_l10n_ou_analytic_id(self):
        """Read the OU back out of the distribution.

        Only a single account carrying the whole 100 % is reported. An asset
        split across two stores has no one Operating Unit, and showing either
        of them would be a lie the user would then save back.
        """
        Analytic = self.env["account.analytic.account"]
        plan = self._l10n_ou_plan()
        for asset in self:
            account = Analytic.browse()
            distribution = asset.analytic_distribution or {}
            if plan:
                whole = [key for key, pct in distribution.items() if pct == 100]
                # A key may be a comma-joined set of accounts (one per plan);
                # take the one that belongs to the Operating Unit plan.
                ids = [int(part) for key in whole for part in str(key).split(",") if part.isdigit()]
                candidates = Analytic.browse(ids).exists().filtered(lambda a: a.plan_id == plan)
                if len(candidates) == 1:
                    account = candidates
            asset.l10n_ou_analytic_id = account

    def _inverse_l10n_ou_analytic_id(self):
        """Write the OU into the distribution, leaving other plans alone."""
        plan = self._l10n_ou_plan()
        for asset in self:
            distribution = dict(asset.analytic_distribution or {})
            # Drop whatever this plan had before, keep every other plan's share.
            for key in list(distribution):
                ids = [int(part) for part in str(key).split(",") if part.isdigit()]
                accounts = self.env["account.analytic.account"].browse(ids).exists()
                if plan and accounts.filtered(lambda a: a.plan_id == plan):
                    del distribution[key]
            if asset.l10n_ou_analytic_id:
                distribution[str(asset.l10n_ou_analytic_id.id)] = 100.0
            asset.analytic_distribution = distribution or False
