"""Rebuild the ARKA/AIM fixed-asset register from the client's begbal sheet.

Tenant: PT Aero Inovasi Media (company 1) + PT Aero Reksa Kreasi Angkasa
(company 2). DBs: ``trn_arkaaim_begbal`` (test) then ``prd_arkaaim`` (prod).

The register that shipped in Jul-2026 was derived from the purchase order: one
uniform acquisition date (30-Jan-2025), one asset group, and unit costs that
miss the later additions and the 31-May-2026 reclass to Office Supplies. The
client's ``Aset Tetap`` sheet now carries per-unit acquisition dates and a
computed depreciation block that ties to the GL, so the register is rebuilt from
it.

All the loading rules live in the module
(``custom_arka_aim_asset_register.hooks``) so a fresh install and this rebuild
cannot drift apart. What only this script does is DELETE the existing register
first -- an install hook must never do that.

Run inside the Odoo container (stdin, so no file needs to exist in the image)::

    docker exec -i odoo19-platform-odoo sh -c 'odoo shell -d prd_arkaaim --no-http' \
        < scripts/tenants/arkaaim/rebuild_asset_register.py

Environment:
    ASSET_REBUILD=1           actually delete + reload (default: dry run)
    ASSET_POSTED_THROUGH=...  last month already charged to the GL. Defaults to
                              the cutover 2026-05-31; on prd_arkaaim, where
                              Depre-0626 is posted, use 2026-06-30 so the cron
                              does not charge June twice.
"""

import logging
import os
from datetime import date

from odoo.addons.custom_arka_aim_asset_register.hooks import (
    OPEN_DATE,
    load_register,
    read_register_rows,
)

_logger = logging.getLogger(__name__)

REBUILD = os.environ.get("ASSET_REBUILD") == "1"
POSTED_THROUGH = date.fromisoformat(os.environ.get("ASSET_POSTED_THROUGH", OPEN_DATE.isoformat()))
BATCH = 250


def drop_old_register(env):
    """Delete the existing register. Returns the number of assets removed."""
    assets = env["custom.fixed.asset"].with_context(active_test=False).search([])
    if not assets:
        return 0
    lines = env["custom.fixed.asset.depreciation.line"].search([("asset_id", "in", assets.ids)])
    # Lines carrying a move_id were actually journalised. Deleting the line
    # leaves that journal entry untouched -- only the link back to the asset
    # goes away, which is unavoidable when the register is rebuilt.
    journalised = len(lines.filtered(lambda line: line.move_id))
    _logger.info(
        "asset_rebuild: deleting %s assets, %s depreciation lines (%s journalised)",
        len(assets),
        len(lines),
        journalised,
    )
    if not REBUILD:
        return len(assets)
    # action_reset_draft refuses assets with posted lines, so drop the schedule
    # first and then the assets themselves.
    for start in range(0, len(lines), 5000):
        lines[start : start + 5000].unlink()
        env.cr.flush()
    for start in range(0, len(assets), BATCH):
        assets[start : start + BATCH].unlink()
        env.cr.flush()
    return len(assets)


def main(env):
    rows = read_register_rows()
    _logger.info(
        "asset_rebuild: %s rows from the sheet (cutover %s, posted through %s)",
        len(rows),
        OPEN_DATE,
        POSTED_THROUGH,
    )
    drop_old_register(env)
    if not REBUILD:
        env.cr.rollback()
        _logger.info("asset_rebuild: dry run, set ASSET_REBUILD=1 to apply")
        return True

    created, seeded_lines = load_register(env, rows, posted_through=POSTED_THROUGH)
    env.cr.commit()
    _logger.info(
        "asset_rebuild: created %s assets, seeded %s already-charged lines; committed",
        created,
        seeded_lines,
    )
    return True


main(env)  # noqa: F821 -- `env` is provided by `odoo shell`
