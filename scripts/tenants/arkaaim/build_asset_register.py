#!/usr/bin/env python3
"""Build the AIM drone fixed-asset register CSV from the two source files.

Sources (committed under ``docs/skenario-arka-aim/`` for provenance):

* ``Listing Asset - odoo.xlsx`` sheet ``Listing Asset-1 AIM`` -- the physical /
  serial listing (3,196 units at RUKO GUDANG PALEM). Provides the serial number,
  asset group and description per unit.
* ``PO Drone 1500unit.pdf`` -- PO 001/AIM-SES/01/25 (30-Jan-2025). Provides the
  per-unit acquisition cost. The PDF is a scan, so its 14 lines are transcribed
  into ``PO_LINES`` below (totals verified against the document footer).

The two files reconcile to 3,187 matched units + 133 PO-only spares (no serial in
the listing) + 9 listing-only units (no PO price). See the plan / MODULE_KNOWLEDGE
for the reconciliation baseline.

Output: ``addons/_tenants/custom_arka_aim_asset_register/data/aim_asset_register.csv``
one row per unit:

    serial_number, name, source_group, source_desc, unit_cost, acquisition_date

Run from the repo root (needs ``openpyxl``):

    python3 scripts/tenants/arkaaim/build_asset_register.py
"""

import csv
import os
from collections import Counter

import openpyxl

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LISTING_XLSX = os.path.join(REPO, "docs", "skenario-arka-aim", "Listing Asset - odoo.xlsx")
OUT_CSV = os.path.join(
    REPO,
    "addons",
    "_tenants",
    "custom_arka_aim_asset_register",
    "data",
    "aim_asset_register.csv",
)
ACQ_DATE = "2025-01-30"

# --- PO 001/AIM-SES/01/25 lines: (description, qty, unit_price, amount). --------
# Transcribed from PO Drone 1500unit.pdf; subtotal 27,145,108,661 verified.
PO_LINES = [
    ("IT1 SP Damoda Drone Battery", 1600, 1655220, 2648352704),
    ("IT1 SP Damoda Drone Remote Control", 3, 27381645, 82144935),
    ("IT1 SP Damoda Drone Base Battery", 12, 456361, 5476329),
    ("IT1 SP Drone Anemometer", 3, 632060, 1896179),
    ("IT1 SP Drone Spectrum Analyzer", 3, 12093560, 36280680),
    ("IT1 Damoda SP Adapter for Drone AP", 11, 159726, 1756989),
    ("IT1 Damoda SP Tripod for Drone AP", 11, 2868227, 31550500),
    ("IT1 Damoda SP Bttry measuremnt device", 32, 684541, 21905316),
    ("IT1 Damoda SP Base-Radio-PC Connector", 11, 228180, 2509984),
    ("IT1 Damoda SP Drone Propeller", 75, 114090, 8556765),
    ("IT1 Damoda SP Drone Bttry Chrging Dock", 53, 14466636, 766731696),
    ("IT1 Damoda Drone DMD-M400W-V3", 1500, 15094132, 22641197709),
    ("IT1 Damoda Drone Base Station", 3, 159726263, 479178788),
    ("IT1 Damoda Drone Radio Transmitter RT01", 3, 139190029, 417570086),
]
PO_UNIT = {desc: unit for desc, qty, unit, amt in PO_LINES}
PO_QTY = {desc: qty for desc, qty, unit, amt in PO_LINES}

# --- Listing "Asset Name" / "Asset Group" -> PO description (unit-price source).
# Keyed on the listing's *Asset Name* (col C); the DMD groups share one PO line.
NAME_TO_PO = {
    "Drone Battery": "IT1 SP Damoda Drone Battery",
    "Drone Remote Control": "IT1 SP Damoda Drone Remote Control",
    "Drone Spectrum Analyzer": "IT1 SP Drone Spectrum Analyzer",
    "Drone AP": "IT1 Damoda SP Adapter for Drone AP",
    "Drone Tripod AP": "IT1 Damoda SP Tripod for Drone AP",
    "Drone Battery Charging": "IT1 Damoda SP Drone Bttry Chrging Dock",
    "Drone DMD": "IT1 Damoda Drone DMD-M400W-V3",
    "Drone Base Station": "IT1 Damoda Drone Base Station",
    "Drone Radio Transmitter": "IT1 Damoda Drone Radio Transmitter RT01",
    # Listing-only items (no PO line) -> no price. Left unmapped on purpose.
    #   "Drone Hub Transmitter", "Drone Swarm GPS", "Drone Tripod GPS & RTK"
}
# PO lines that carry no physical serial in the listing (spares/consumables).
# Emitted as unit rows with a blank serial so the register still ties to PO cost.
PO_ONLY = [
    "IT1 SP Damoda Drone Base Battery",
    "IT1 SP Drone Anemometer",
    "IT1 Damoda SP Bttry measuremnt device",
    "IT1 Damoda SP Base-Radio-PC Connector",
    "IT1 Damoda SP Drone Propeller",
]


def _read_listing():
    wb = openpyxl.load_workbook(LISTING_XLSX, read_only=True, data_only=True)
    ws = wb["Listing Asset-1 AIM"]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not r[0]:
            continue
        # Company, Location, Asset Name, Asset Group, Asset Description, Serial, Qty, No
        _, location, name, group, desc, serial, qty, _no = (list(r) + [None] * 8)[:8]
        rows.append(
            {
                "location": location,
                "name": name,
                "group": group,
                "desc": desc,
                "serial": "" if serial in (None, "") else str(serial),
            }
        )
    return rows


def build():
    listing = _read_listing()
    out = []
    unmatched_names = Counter()

    # 1) One register row per physical listing unit.
    for row in listing:
        po_desc = NAME_TO_PO.get(row["name"])
        unit_cost = PO_UNIT.get(po_desc, 0) if po_desc else 0
        if not po_desc:
            unmatched_names[row["name"]] += 1
        out.append(
            {
                "serial_number": row["serial"],
                "name": f"{row['name']} {row['serial']}".strip() if row["serial"] else row["name"],
                "source_group": row["group"],
                "source_desc": row["desc"],
                "unit_cost": unit_cost,
                "acquisition_date": ACQ_DATE,
            }
        )

    # 2) PO-only spares (no serial in the listing) -> one row per unit, blank serial.
    for po_desc in PO_ONLY:
        for i in range(1, PO_QTY[po_desc] + 1):
            out.append(
                {
                    "serial_number": "",
                    "name": f"{po_desc} #{i}",
                    "source_group": "PO-ONLY (spare/consumable)",
                    "source_desc": po_desc,
                    "unit_cost": PO_UNIT[po_desc],
                    "acquisition_date": ACQ_DATE,
                }
            )

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["serial_number", "name", "source_group", "source_desc", "unit_cost", "acquisition_date"],
        )
        w.writeheader()
        w.writerows(out)

    # --- reconciliation summary -------------------------------------------------
    total_cost = sum(r["unit_cost"] for r in out)
    valued = [r for r in out if r["unit_cost"]]
    zero = [r for r in out if not r["unit_cost"]]
    po_subtotal = sum(amt for _d, _q, _u, amt in PO_LINES)
    print(f"listing units        : {len(listing)}")
    print(f"PO-only spare units  : {len(out) - len(listing)}")
    print(f"register rows total  : {len(out)}")
    print(f"valued rows          : {len(valued)}   zero-value rows: {len(zero)}")
    print(f"register cost (PO)    : {total_cost:,}")
    print(f"PO subtotal (doc)     : {po_subtotal:,}")
    print(f"GL cost 1205104000    : 27,110,131,391   variance: {total_cost - 27110131391:,}")
    if unmatched_names:
        print("listing-only names (no PO price):")
        for n, c in unmatched_names.items():
            print(f"    {n}: {c}")
    print(f"wrote {OUT_CSV}")


if __name__ == "__main__":
    build()
