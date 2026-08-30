# -*- coding: utf-8 -*-
"""Merge fixed assets that are really ONE purchase of N identical units.

WHY
---
Until ``custom_accounting_asset`` 19.0.0.6.0 the register only knew per-unit
assets, so a purchase of 5 identical waste bins was booked as 5 asset numbers.
Pooled assets now exist (one number, ``quantity = 5``), and this script folds the
historic per-unit records into one pool so the client can retire a broken unit
the new way instead of disposing of a whole asset number.

WHAT IT DOES NOT DO
-------------------
Nothing is posted to the GL. The cost is already in the asset account and the
depreciation is already in accumulated depreciation; merging only rearranges the
subledger. The absorbed records keep their posted depreciation lines (audit
trail), are flagged ``merged_into_id`` and cancelled, and their accumulated
depreciation is carried on the survivor as
``opening_accumulated_depreciation`` so the pooled NBV is unchanged to the cent.

GROUPING — deliberately strict
------------------------------
Two assets are only merged when EVERYTHING that drives their accounting matches:
company, asset group, location, custodian, source product, acquisition and
posting dates, depreciation date rule, method, declining factor, useful life,
the four accounts, the journal, the per-unit acquisition value, the name, and
the exact set of dates on which depreciation has been posted. Anything that has
been revalued, already pooled, already merged, or partially retired is skipped,
and so is anything carrying a serial number or a rental unit: those are tracked
per unit on purpose (the stock quant and the rental record hang off the lot).
Widen this only with an accountant in the room.

USAGE (odoo shell, inside a container that can reach the DB)::

    docker exec -i odoo19-platform-odoo sh -c \
        'odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 --shell-interface=python' \
        < scripts/consolidate_pooled_assets.py

Environment:
    ASSET_MERGE_APPLY=1        actually merge (default: dry run, nothing written)
    ASSET_MERGE_GROUP=EQ       only this asset-group code
    ASSET_MERGE_COMPANY=1      only this company id
    ASSET_MERGE_MIN=2          minimum units in a group before it is merged
    ASSET_MERGE_LIMIT=0        stop after N groups (0 = no limit)

Output goes to stderr, because ``odoo shell`` swallows stdout.
"""

import os
import sys
from collections import defaultdict

env = self.env  # noqa: F821  (provided by odoo shell)

APPLY = os.environ.get("ASSET_MERGE_APPLY") == "1"
ONLY_GROUP = os.environ.get("ASSET_MERGE_GROUP") or ""
ONLY_COMPANY = int(os.environ.get("ASSET_MERGE_COMPANY") or 0)
MIN_UNITS = int(os.environ.get("ASSET_MERGE_MIN") or 2)
LIMIT = int(os.environ.get("ASSET_MERGE_LIMIT") or 0)


def log(msg):
    print(msg, file=sys.stderr)


def signature(asset):
    """Everything that must match before two records can share one asset number."""
    return (
        asset.company_id.id,
        asset.group_id.id,
        asset.location_id.id,
        asset.custodian_id.id,
        # product_id only exists when custom_asset_from_receipt is installed
        getattr(asset, "product_id", False) and asset.product_id.id or 0,
        (asset.name or "").strip().lower(),
        asset.acquisition_date,
        asset.posting_date,
        asset.depreciation_date_mode,
        asset.depreciation_method,
        round(asset.declining_factor or 0.0, 4),
        asset.useful_life_months,
        asset.asset_account_id.id,
        asset.depreciation_account_id.id,
        asset.expense_account_id.id,
        asset.journal_id.id,
        round(asset.acquisition_value, 2),
        round(asset.salvage_value or 0.0, 2),
        # same depreciation history, or the pooled schedule would be a fiction
        tuple(sorted(line.date for line in asset.depreciation_line_ids.filtered("posted"))),
    )


domain = [
    ("state", "=", "running"),
    ("merged_into_id", "=", False),
    ("quantity", "=", 1.0),
    ("revaluation_value", "=", 0.0),
]
if ONLY_COMPANY:
    domain.append(("company_id", "=", ONLY_COMPANY))
if ONLY_GROUP:
    domain.append(("group_id.code", "=", ONLY_GROUP))

Asset = env["custom.fixed.asset"].with_context(active_test=False)
candidates = Asset.search(domain, order="code, id")
candidates = candidates.filtered(lambda a: not a.partial_disposal_ids and not a.revaluation_ids)
log("candidates: %s running single-unit assets" % len(candidates))

# A serial-linked asset IS the unit -- the stock quant and the rental unit hang
# off its lot. Those are per-unit on purpose and are never pooled. (On ARKA-AIM
# that is the entire register: 3,180 of 3,180.)
serialised = candidates.filtered(
    lambda a: ("lot_id" in a._fields and a.lot_id) or ("rental_asset_ids" in a._fields and a.rental_asset_ids)
)
if serialised:
    log("skipping %s serial-linked / rental asset(s) -- tracked per unit on purpose" % len(serialised))
    candidates -= serialised

buckets = defaultdict(lambda: env["custom.fixed.asset"])
for asset in candidates:
    buckets[signature(asset)] |= asset

groups = [assets for assets in buckets.values() if len(assets) >= MIN_UNITS]
groups.sort(key=lambda assets: (-len(assets), assets[0].code))
if LIMIT:
    groups = groups[:LIMIT]

if not groups:
    log("nothing to merge with the current filters")
else:
    log("")
    log("%-14s %-40s %5s %16s %16s" % ("survivor", "name", "units", "value", "accum"))
    log("-" * 96)

merged_assets = 0
for assets in groups:
    survivor = assets[0]
    others = assets[1:]
    value = sum(assets.mapped("acquisition_value"))
    accum = sum(assets.mapped("accumulated_depreciation"))
    log("%-14s %-40s %5s %16.2f %16.2f" % (survivor.code, (survivor.name or "")[:40], len(assets), value, accum))
    codes = others.mapped("code")
    # A 1,600-unit group would otherwise print a screenful of codes per line.
    shown = ", ".join(codes[:10])
    if len(codes) > 10:
        shown += ", ... (+%s more)" % (len(codes) - 10)
    log("               absorbs: %s" % shown)
    if APPLY:
        survivor._merge_assets_into_pool(others)
        merged_assets += len(others)

log("")
log(
    "summary: %s group(s), %s record(s) would remain, %s absorbed"
    % (len(groups), len(groups), sum(len(a) - 1 for a in groups))
)
log("")
if APPLY:
    log("MERGED %s group(s), %s asset record(s) absorbed" % (len(groups), merged_assets))
    env.cr.commit()
    log("committed")
else:
    log(
        "DRY RUN — %s group(s) would be merged, %s record(s) absorbed." % (len(groups), sum(len(a) - 1 for a in groups))
    )
    log("Re-run with ASSET_MERGE_APPLY=1 to write.")
