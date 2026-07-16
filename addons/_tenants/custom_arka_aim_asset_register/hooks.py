"""Post-init hook: seed the AIM asset group/location and load the per-unit drone
fixed-asset register, reconciled to the 31-May-2026 opening-balance GL.

The drones already sit as a lump sum in the AIM opening-balance GL (module
``custom_arka_aim_opening_balance``): cost 27,110,131,391 (1205104000), accumulated
depreciation 6,776,493,895 (1205203000). So this loader posts NO acquisition
journal. For each unit it:

1. creates a ``custom.fixed.asset`` (draft) at PO unit cost (no GL impact on create);
2. confirms it -> the base model builds a 48-month straight-line schedule anchored
   on ``DEP_START`` (specific dates);
3. marks every schedule line dated <= ``OPEN_DATE`` (31-May-2026) as
   ``posted=True, move_id=False`` -- i.e. the 12 months of depreciation already
   embedded in the GL accumulated balance. These lines count into the asset's
   accumulated depreciation / NBV but are NEVER posted to the GL and are NEVER
   re-posted by the monthly cron (which only picks up unposted lines). The
   remaining 36 unposted lines are all dated AFTER the opening date, so the cron
   depreciates strictly forward.

Consistent-rate reconciliation (accum applied at the same 12/48 = 25% rate the GL
uses). Register is booked at PO cost, so all three variances trace to the single
+34,976,845 cost difference between the PO and the GL:

    register cost  27,145,108,236  vs GL 27,110,131,391  -> +34,976,845
    register accum  6,786,277,059  vs GL  6,776,493,895  -> + 9,783,164  (25%)
    register NBV   20,358,831,177  vs GL 20,333,637,496  -> +25,193,681  (75%)

Idempotent: skips entirely if any AIM ``custom.fixed.asset`` already exists.
Company is resolved by NAME so the module is portable across trn_arkaaim_begbal /
prd_arkaaim.
"""

import csv
import logging
from datetime import date

from odoo.exceptions import UserError
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

MODULE = "custom_arka_aim_asset_register"
CSV_PATH = "data/aim_asset_register.csv"

AIM_COMPANY = "PT Aero Inovasi Media"
GROUP_CODE = "AIM-FA-OFFC"
GROUP_NAME = "Office and outlet equipment"
LOCATION_NAME = "RUKO GUDANG PALEM"

# AIM chart codes (same numbering as the Erajaya chart).
COST_CODE = "1205104000"  # Fixed Assets - Cost - Office and outlet equipment
ACCUM_CODE = "1205203000"  # Fixed asset - Accum depre - Office and outlet equipment
EXPENSE_CODE = "7204103000"  # Depre Exp - Fixed Asset - Office and outlet equipment

# Depreciation policy for the drone fleet. The GL accumulated balance
# (6,776,493,895) is exactly 25% of the cost => 12 months of a 48-month life were
# depreciated by the opening date. DEP_START is set so the 12 already-elapsed
# monthly lines land on/just-before OPEN_DATE and the 13th (first forward) line
# falls in June 2026. CONFIRM WITH FINANCE (flagged in the plan).
ORIG_LIFE_MONTHS = 48
DEP_START = date(2025, 6, 30)  # depreciation start month (assumed from the 25% accum)
OPEN_DATE = date(2026, 5, 31)  # begbal cutover; lines <= this are seeded posted, not GL'd

BATCH = 250


def _company(env):
    return env["res.company"].search([("name", "=", AIM_COMPANY)], limit=1)


def _acc(env, company, code):
    return (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
    )


def seed_group_and_location(env):
    """Upsert the AIM 'Office and outlet equipment' asset group and the RUKO
    GUDANG PALEM location. Idempotent and non-destructive (only empty account /
    journal fields are filled). Returns ``(group, location)`` or ``(False, False)``
    when the AIM company is absent.
    """
    company = _company(env)
    if not company:
        _logger.warning("%s: company %r not found -> skip group/location seed", MODULE, AIM_COMPANY)
        return False, False

    Group = env["custom.fixed.asset.group"]
    Location = env["custom.fixed.asset.location"]

    cost = _acc(env, company, COST_CODE)
    accum = _acc(env, company, ACCUM_CODE)
    expense = _acc(env, company, EXPENSE_CODE)
    journal = env["account.journal"].search(
        [("type", "=", "general"), ("company_id", "=", company.id)], limit=1
    )
    account_vals = {
        "default_asset_account_id": cost.id or False,
        "default_depreciation_account_id": accum.id or False,
        "default_expense_account_id": expense.id or False,
        "default_journal_id": journal.id or False,
    }

    group = Group.with_context(active_test=False).search(
        [("code", "=", GROUP_CODE), ("company_id", "=", company.id)], limit=1
    )
    if group:
        fill = {f: v for f, v in account_vals.items() if v and not group[f]}
        if fill:
            group.write(fill)
    else:
        group = Group.create(
            {
                "name": GROUP_NAME,
                "code": GROUP_CODE,
                "company_id": company.id,
                "default_useful_life_months": ORIG_LIFE_MONTHS,
                **{f: v for f, v in account_vals.items() if v},
            }
        )

    location = Location.with_context(active_test=False).search(
        [("name", "=", LOCATION_NAME)], limit=1
    )
    if not location:
        location = Location.create({"name": LOCATION_NAME})

    _logger.info("%s: seeded group %s + location %s for %s", MODULE, GROUP_CODE, LOCATION_NAME, company.name)
    return group, location


def _read_csv():
    with file_open(f"{MODULE}/{CSV_PATH}", "r") as fh:
        return list(csv.DictReader(fh))


def post_init_hook(env):
    group, location = seed_group_and_location(env)
    company = _company(env)
    if not company or not group:
        _logger.warning("%s: AIM company/group missing -> skip register load", MODULE)
        return

    Asset = env["custom.fixed.asset"].with_company(company)
    if Asset.search_count([("company_id", "=", company.id)]):
        _logger.info("%s: AIM already has fixed assets -> skip register load (idempotent)", MODULE)
        return

    cost_acc = _acc(env, company, COST_CODE)
    accum_acc = _acc(env, company, ACCUM_CODE)
    exp_acc = _acc(env, company, EXPENSE_CODE)
    journal = env["account.journal"].search(
        [("type", "=", "general"), ("company_id", "=", company.id)], limit=1
    )
    missing = [
        name
        for name, rec in (("cost", cost_acc), ("accum", accum_acc), ("expense", exp_acc), ("journal", journal))
        if not rec
    ]
    if missing:
        raise UserError(f"{MODULE}: missing AIM account/journal for {missing} -> cannot load register")

    rows = _read_csv()
    base_vals = {
        "company_id": company.id,
        "group_id": group.id,
        "location_id": location.id if location else False,
        "posting_date": DEP_START,
        "depreciation_date_mode": "specific",
        "useful_life_months": ORIG_LIFE_MONTHS,
        "asset_account_id": cost_acc.id,
        "depreciation_account_id": accum_acc.id,
        "expense_account_id": exp_acc.id,
        "journal_id": journal.id,
    }
    vals_list = []
    for row in rows:
        unit_cost = float(row["unit_cost"] or 0)
        vals_list.append(
            {
                **base_vals,
                "name": row["name"],
                "serial_number": row["serial_number"] or False,
                "source_group": row["source_group"] or False,
                "source_desc": row["source_desc"] or False,
                "acquisition_date": row["acquisition_date"],
                "acquisition_value": unit_cost,
                # Zero-value listing-only units have no cost to depreciate.
                "depreciation_method": "straight_line" if unit_cost > 0 else "none",
            }
        )

    assets = Asset.create(vals_list)
    _logger.info("%s: created %s AIM fixed-asset records", MODULE, len(assets))

    # Confirm in batches; for depreciable assets seed the already-elapsed history
    # lines (date <= OPEN_DATE) as posted-but-un-GL'd so the cron only posts forward.
    seeded_lines = 0
    for start in range(0, len(assets), BATCH):
        chunk = assets[start : start + BATCH]
        chunk.action_confirm()
        history = chunk.depreciation_line_ids.filtered(lambda l: l.date <= OPEN_DATE)
        if history:
            history.write({"posted": True})
            seeded_lines += len(history)
        env.invalidate_all()

    _logger.info(
        "%s: confirmed %s assets, seeded %s opening-depreciation lines (posted, not GL'd)",
        MODULE,
        len(assets),
        seeded_lines,
    )
