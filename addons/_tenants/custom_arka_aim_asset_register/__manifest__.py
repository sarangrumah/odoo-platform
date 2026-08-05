# -*- coding: utf-8 -*-
{
    "name": "ARKA-AIM Drone Fixed-Asset Register",
    "version": "19.0.2.0.0",
    "summary": "Per-unit fixed-asset subledger for ARKA/AIM, built from the client's "
    "begbal sheet and reconciled to the 31-May-2026 opening-balance GL.",
    "description": """
ARKA-AIM Fixed-Asset Register
=============================

Builds the ``custom.fixed.asset`` subledger for both ARKA/AIM companies from the
``Aset Tetap`` sheet of the client's begbal workbook (4-Aug-2026), parsed by
``tools/parse_arkaaim_asset_sheet.py``.

* 3,180 AIM ``Registered Asset`` units -- per-unit acquisition date and cost,
  48-month straight line. These are the units behind the AIM opening balance:
  cost 27,110,131,391 (``1205104000``), accumulated depreciation 6,776,493,895
  (``1205203000``), NBV 20,333,637,497.
* 410 ``Unregistered`` units -- 144 AIM spares (reclassed to Office Supplies on
  31-May-2026) and 266 ARKA support items. Absent from every GL balance, so they
  are register-only: no depreciation, no journal.

The module posts **no** acquisition journal. Depreciation already charged to the
GL is seeded as ``posted=True, move_id=False`` so it counts towards accumulated
depreciation without ever reaching the GL again, and the monthly cron only posts
forward. Three asset groups (Device / Komponen Drone / Alat Pendukung) are
seeded on every upgrade so their account wiring self-heals.

Idempotent: skips the load if any ``custom.fixed.asset`` already exists. To
rebuild a database that already has a register, run
``scripts/tenants/arkaaim/rebuild_asset_register.py`` (deletes the old register
first -- deliberate and backed up, never done by the install hook).

Superseded source: the PO-derived register (``data/aim_asset_register.csv``,
uniform 30-Jan-2025 acquisition date) is kept for reference only.

TENANT-SCOPED: install only on the ARKA-AIM databases.
""",
    "author": "Platform",
    "category": "Tenants/ARKA-AIM",
    "license": "LGPL-3",
    "depends": [
        "custom_accounting_asset",
    ],
    "data": [
        "views/fixed_asset_views.xml",
        "data/seed_functions.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
}
