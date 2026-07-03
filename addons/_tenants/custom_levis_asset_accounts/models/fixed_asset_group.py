# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# IAS 16 revaluation role -> Erajaya chart account code.
ERAJAYA_REVALUATION_CODE_MAP = {
    "default_revaluation_surplus_account_id": "3005200004",   # OCI Current - Fixed Assets
    "default_revaluation_loss_account_id": "7706000000",      # Loss on impairment of Fixed Assets
    "default_revaluation_income_account_id": "8300000004",    # OCI - Fixed assets (income_other)
    "default_retained_earnings_account_id": "3006100001",     # Retained earnings - beginning
}


class CustomFixedAssetGroup(models.Model):
    _inherit = "custom.fixed.asset.group"

    @api.model
    def _apply_erajaya_revaluation_defaults(self):
        """Resolve the Erajaya revaluation accounts by code within each company and
        fill them onto that company's asset groups.

        Non-destructive (only empty fields are set) and self-scoping (companies
        without the Erajaya codes are skipped). Invoked from a ``<function>`` data
        record so it re-runs idempotently on every module update.
        """
        Account = self.env["account.account"]
        wired_groups = 0
        for company in self.env["res.company"].search([]):
            # ``code`` is company-dependent in Odoo 19 -> resolve in company context.
            account_by_field = {}
            for field, code in ERAJAYA_REVALUATION_CODE_MAP.items():
                account = Account.with_company(company).search([("code", "=", code)], limit=1)
                if account:
                    account_by_field[field] = account.id
            if not account_by_field:
                # Not an Erajaya-chart company (e.g. id_psak) -> nothing to wire.
                continue

            groups = self.with_context(active_test=False).search([("company_id", "=", company.id)])
            if not groups:
                groups = self.create(
                    {
                        "name": "General",
                        "code": "GEN",
                        "company_id": company.id,
                    }
                )
            for group in groups:
                vals = {field: acc_id for field, acc_id in account_by_field.items() if not group[field]}
                if vals:
                    group.write(vals)
                    wired_groups += 1

        _logger.info(
            "custom_levis_asset_accounts: applied revaluation defaults to %s asset group(s).",
            wired_groups,
        )
        return wired_groups
