# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# IAS 16 revaluation role -> Erajaya chart account code.
ERAJAYA_REVALUATION_CODE_MAP = {
    "default_revaluation_surplus_account_id": "3005200004",  # OCI Current - Fixed Assets
    "default_revaluation_loss_account_id": "7706000000",  # Loss on impairment of Fixed Assets
    "default_revaluation_income_account_id": "8300000004",  # OCI - Fixed assets (income_other)
    "default_retained_earnings_account_id": "3006100001",  # Retained earnings - beginning
}

# The EBR asset categories -> Erajaya chart codes: 6 owned fixed assets plus the
# 6 right-of-use (PSAK 73) counterparts. Codes verified against
# ``l10n_erajaya/data/template/account.account-erajaya.csv``.
#
# Notes:
#  * Land is non-depreciable, so it carries only a cost account (no accumulated
#    depreciation / no depreciation-expense account).
#  * 1205202000 "Accum depre - Vehicles" was missing from the chart when this
#    seed was first written; it exists now and FA-VEH resolves it. Resolution
#    stays defensive: any code that does not resolve in a company is simply
#    skipped, leaving the field empty (non-destructive).
#  * ``useful_life`` values are provisional PSAK-style defaults for *new* assets
#    only (they do not post anything); confirm/adjust with Finance.
ERAJAYA_ASSET_GROUP_SEED = [
    # (code, name, cost_code, accum_code, expense_code, useful_life_months)
    ("FA-LAND", "Land", "1205101000", None, None, 0),
    ("FA-BLDG", "Building and improvements", "1205102000", "1205201000", "7204101000", 240),
    ("FA-VEH", "Vehicles", "1205103000", "1205202000", "7204102000", 96),
    ("FA-OFFC", "Office and outlet equipment", "1205104000", "1205203000", "7204103000", 48),
    ("FA-MACH", "Machinery", "1205105000", "1205204000", "7204105000", 96),
    ("FA-FURN", "Furniture and fixtures", "1205106000", "1205205000", "7204104000", 48),
    # Right-of-Use assets (PSAK 73). Same six sub-categories as the owned
    # fixed assets, on the 1206xxxxxx / 7205xxxxxx branch of the chart.
    #
    #  * ROU Land is seeded cost-only: the chart carries no accumulated
    #    depreciation and no depreciation-expense account for it (accum starts
    #    at 1206201000 = Building). If Finance leases land on a term that has
    #    to be amortised, those two accounts must be added to the chart first.
    #  * The expense account is the G&A line ``7205xxxxxx`` ("Depreciation -
    #    Right of Use Asset - X"), mirroring how the owned groups point at
    #    7204xxxxxx. The chart also carries a *selling* variant
    #    (7110001000 / 7110002000 / 7110099000); an asset booked against a store
    #    cost centre should have its expense account overridden on the asset
    #    itself, which is why only one of the two can be a group default.
    #  * ``useful_life`` is provisional at 60 months. A ROU asset is amortised
    #    over its own lease term, so this default exists only to keep the form
    #    valid -- it must be set per lease.
    ("ROU-LAND", "Right of Use Asset - Land", "1206101000", None, None, 0),
    ("ROU-BLDG", "Right of Use Asset - Building and improvements", "1206102000", "1206201000", "7205001000", 60),
    ("ROU-VEH", "Right of Use Asset - Vehicles", "1206103000", "1206202000", "7205002000", 60),
    ("ROU-OFFC", "Right of Use Asset - Office and outlet equipment", "1206104000", "1206203000", "7205003000", 60),
    ("ROU-MACH", "Right of Use Asset - Machinery", "1206105000", "1206204000", "7205005000", 60),
    ("ROU-FURN", "Right of Use Asset - Furniture and fixtures", "1206106000", "1206205000", "7205004000", 60),
]

# Journal every depreciating group posts its depreciation to. A group created
# without one raises on ``action_confirm()`` -- the defect that took all six
# owned categories down before it was wired by hand.
ERAJAYA_DEPRECIATION_JOURNAL_CODE = "DEPRE"


class CustomFixedAssetGroup(models.Model):
    _inherit = "custom.fixed.asset.group"

    @api.model
    def _seed_erajaya_asset_groups(self):
        """Upsert the EBR asset categories (owned + right-of-use) as
        ``custom.fixed.asset.group`` records for every company that carries the
        Erajaya chart.

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
          company; an accum/expense account that does not resolve is left empty;
        * a depreciating category (one with an expense account) is pointed at the
          company's ``DEPRE`` journal, without which ``action_confirm()`` raises.
          Land carries no expense account and so is left without a journal.
        """
        Account = self.env["account.account"]
        Journal = self.env["account.journal"]
        seeded = 0
        for company in self.env["res.company"].search([]):

            def _acc(code):
                if not code:
                    return False
                account = Account.with_company(company).search([("code", "=", code)], limit=1)
                return account.id or False

            journal_id = Journal.search(
                [
                    ("code", "=", ERAJAYA_DEPRECIATION_JOURNAL_CODE),
                    ("type", "=", "general"),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            ).id

            for code, name, cost_code, accum_code, expense_code, useful_life in ERAJAYA_ASSET_GROUP_SEED:
                cost_id = _acc(cost_code)
                if not cost_id:
                    # Not an Erajaya-chart company for this category -> skip.
                    continue
                expense_id = _acc(expense_code)
                account_vals = {
                    "default_asset_account_id": cost_id,
                    "default_depreciation_account_id": _acc(accum_code),
                    "default_expense_account_id": expense_id,
                }
                if expense_id and journal_id:
                    account_vals["default_journal_id"] = journal_id
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
