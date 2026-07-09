# -*- coding: utf-8 -*-
"""Operating-Unit stamping on the POS session closing entry (feature #9).

A POS session belongs to exactly one store (``config_id.warehouse_id``), so every
P&L line of its closing entry belongs to that store's Operating Unit. Core builds
those lines in ``_get_sale_vals`` without any analytic distribution, which left
the whole POS revenue stream outside the per-OU P&L.

Only the *sale* lines are stamped: tax, receivable and bank lines are balance
sheet and carry no OU. The distribution is merged through the same helper the
purchase side uses, so the OU is appended to its own analytic plan rather than
replacing any distribution core may have derived from the product.
"""

from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _levis_ou_analytic(self):
        """Operating-Unit analytic of this session's store, if any."""
        self.ensure_one()
        return self.config_id.warehouse_id.l10n_ou_analytic_id

    def _get_sale_vals(self, key, sale_vals):
        vals = super()._get_sale_vals(key, sale_vals)
        ou = self._levis_ou_analytic()
        if not ou:
            return vals
        vals["l10n_ou_analytic_id"] = ou.id
        # Set the distribution explicitly rather than leaning on the
        # ``l10n_ou_analytic_id`` trigger: ``analytic_distribution`` is a stored
        # computed field with readonly=False, so a value supplied at create time
        # wins and the result stays deterministic.
        vals["analytic_distribution"] = self.env[
            "purchase.order.line"
        ]._levis_merge_ou_distribution(vals.get("analytic_distribution"), ou.id)
        return vals
