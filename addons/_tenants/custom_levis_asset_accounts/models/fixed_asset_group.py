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

# The 6 EBR fixed-asset categories -> Erajaya chart codes. Codes verified against
# ``l10n_erajaya/data/template/account.account-erajaya.csv``.
#
# Notes:
#  * Land is non-depreciable, so it carries only a cost account (no accumulated
#    depreciation / no depreciation-expense account).
#  * The chart ships NO "Accum depre - Vehicles" account (there is a gap at
#    1205202000), so the Vehicles group is seeded without an accumulated
#    depreciation account and that field must be wired manually once the account
#    exists. Resolution is defensive: any code that does not resolve in a company
#    is simply skipped, leaving the field empty (non-destructive).
#  * ``useful_life`` values are provisional PSAK-style defaults for *new* assets
#    only (they do not post anything); confirm/adjust with Finance.
ERAJAYA_ASSET_GROUP_SEED = [
    # (code, name, cost_code, accum_code, expense_code, useful_life_months)
    ("FA-LAND", "Land", "1205101000", None, None, 0),
    ("FA-BLDG", "Building and improvements", "1205102000", "1205201000", "7204101000", 240),
    ("FA-VEH", "Vehicles", "1205103000", None, "7204102000", 96),
    ("FA-OFFC", "Office and outlet equipment", "1205104000", "1205203000", "7204103000", 48),
    ("FA-MACH", "Machinery", "1205105000", "1205204000", "7204105000", 96),
    ("FA-FURN", "Furniture and fixtures", "1205106000", "1205205000", "7204104000", 48),
]


class CustomFixedAssetGroup(models.Model):
    _inherit = "custom.fixed.asset.group"

    @api.model
    def _seed_erajaya_asset_groups(self):
        """Upsert the 6 EBR fixed-asset categories as ``custom.fixed.asset.group``
        records for every company that carries the Erajaya chart.

        Runs from a ``<function>`` data record so it re-applies idempotently on
        every module update. Behaviour:

        * keyed by ``(code, company_id)`` -> an existing group is updated
          non-destructively (only empty account fields are filled), a missing one
          is created;
        * accounts are resolved **by code within each company** (``code`` is
          company-dependent in Odoo 19);
        * a company without the Erajaya cost accounts (e.g. an id_psak company) is
          skipped automatically;
        * a category whose cost account is absent in a company is skipped for that
          company; an accum/expense account that does not resolve is left empty.
        """
        Account = self.env["account.account"]
        seeded = 0
        for company in self.env["res.company"].search([]):
            def _acc(code):
                if not code:
                    return False
                account = Account.with_company(company).search([("code", "=", code)], limit=1)
                return account.id or False

            for code, name, cost_code, accum_code, expense_code, useful_life in ERAJAYA_ASSET_GROUP_SEED:
                cost_id = _acc(cost_code)
                if not cost_id:
                    # Not an Erajaya-chart company for this category -> skip.
                    continue
                account_vals = {
                    "default_asset_account_id": cost_id,
                    "default_depreciation_account_id": _acc(accum_code),
                    "default_expense_account_id": _acc(expense_code),
                }
                group = self.with_context(active_test=False).search(
                    [("code", "=", code), ("company_id", "=", company.id)], limit=1
                )
                if group:
                    # Non-destructive: only fill empty account fields.
                    vals = {f: v for f, v in account_vals.items() if v and not group[f]}
                    if vals:
                        group.write(vals)
                        seeded += 1
                else:
                    self.create(
                        {
                            "name": name,
                            "code": code,
                            "company_id": company.id,
                            "default_useful_life_months": useful_life,
                            **{f: v for f, v in account_vals.items() if v},
                        }
                    )
                    seeded += 1

        _logger.info(
            "custom_levis_asset_accounts: seeded/updated %s Erajaya asset group(s).",
            seeded,
        )
        return seeded

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
