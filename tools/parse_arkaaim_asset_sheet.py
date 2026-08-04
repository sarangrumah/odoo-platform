#!/usr/bin/env python3
"""Parse the ``Aset Tetap`` sheet of the ARKA/AIM begbal template into register CSVs.

The sheet carries two column blocks per row: the client's own columns (A-K,
whose depreciation cells are all ``-``) and a computed block (M-Q: cost, accum.
depreciation to cutover, book value, remaining life, method) that the client
filled in on 4-Aug-2026. The computed block only covers ``Registered Asset``
rows -- those are the units behind the GL balances. ``Unregistered`` rows
(AIM spares + every ARKA item) are register-only: no GL, no depreciation.

Usage::

    python3 tools/parse_arkaaim_asset_sheet.py --check
    python3 tools/parse_arkaaim_asset_sheet.py --write

Output CSVs (consumed by scripts/tenants/arkaaim/rebuild_asset_register.py):
    addons/_tenants/custom_arka_aim_asset_register/data/asset_register_registered.csv
    addons/_tenants/custom_arka_aim_asset_register/data/asset_register_unregistered.csv
"""

import argparse
import csv
import datetime
import sys
from collections import Counter
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[1]
WORKBOOK = REPO / "imports/arka_aim/Template_Begbal_AIM_ARKA_0408261700.xlsx"
OUT_DIR = REPO / "addons/_tenants/custom_arka_aim_asset_register/data"
SHEET = "Aset Tetap"
CUTOVER = datetime.date(2026, 5, 31)

# Column indexes (0-based) -- the sheet's layout, header on row 6.
COL = {
    "code": 0,
    "name": 1,
    "owner": 2,
    "category": 3,
    "status": 4,
    "acq_date": 5,
    "cost_client": 6,
    "cost": 12,
    "accum": 13,
    "book_value": 14,
    "remaining_life": 15,
    "method": 16,
}

# What the register must tie to: the posted GL balances at cutover (also the TB).
GL_COST = 27_110_131_391.00  # account 1205104000
GL_ACCUM = 6_776_493_894.83  # account 1205203000
# The computed block is built from per-unit rounding, so it lands a rupiah above
# the GL. The sheet shows the same gap in its own control rows (1.00 / 0.04).
GL_TOLERANCE = 5.0

REGISTERED = "Registered Asset"


def _num(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "–", "—"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _text(value):
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    text = _text(value)
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def read_rows(worksheet):
    """Return the asset rows, skipping the header, TOTAL and note rows."""
    rows = []
    for row in worksheet.iter_rows(min_row=7, values_only=True):
        cells = list(row) + [None] * (20 - len(row))
        owner, status = _text(cells[COL["owner"]]), _text(cells[COL["status"]])
        if not owner or status not in (REGISTERED, "Unregistered Asset"):
            continue  # TOTAL / note / blank rows carry no owner+status pair
        rows.append(
            {
                "code": _text(cells[COL["code"]]),
                "name": _text(cells[COL["name"]]),
                "owner": owner,
                "category": _text(cells[COL["category"]]),
                "status": status,
                "acq_date": _date(cells[COL["acq_date"]]),
                "cost_client": round(_num(cells[COL["cost_client"]]), 2),
                "cost": round(_num(cells[COL["cost"]]), 2),
                "accum": round(_num(cells[COL["accum"]]), 2),
                "book_value": round(_num(cells[COL["book_value"]]), 2),
                "remaining_life": int(_num(cells[COL["remaining_life"]])),
                "method": _text(cells[COL["method"]]),
            }
        )
    return rows


def assign_codes(rows):
    """ARKA rows carry no asset code ('-'); give them a traceable generated one."""
    generated = 0
    counter = 0
    for row in rows:
        if row["code"] not in ("", "-"):
            continue
        counter += 1
        prefix = "ARKA" if row["owner"] == "ARKA" else "AIM"
        row["code"] = f"AS-{prefix}-{counter:04d}"
        row["code_generated"] = "1"
        generated += 1
    for row in rows:
        row.setdefault("code_generated", "0")
    return generated


def check(rows):
    """Reconcile the sheet against the GL; return (ok, report)."""
    report, ok = [], True
    registered = [row for row in rows if row["status"] == REGISTERED]
    unregistered = [row for row in rows if row["status"] != REGISTERED]

    report.append(f"  rows total              : {len(rows)}")
    for key, group in (("registered", registered), ("unregistered", unregistered)):
        breakdown = Counter((row["owner"], row["category"]) for row in group)
        report.append(f"  {key:<23}: {len(group)}")
        for (owner, category), count in sorted(breakdown.items()):
            report.append(f"      {owner} / {category}: {count}")

    cost = sum(row["cost"] for row in registered)
    accum = sum(row["accum"] for row in registered)
    book = sum(row["book_value"] for row in registered)
    report.append(f"  registered cost         : {cost:,.2f} (GL {GL_COST:,.2f}, diff {cost - GL_COST:,.2f})")
    report.append(f"  registered accum. depr. : {accum:,.2f} (GL {GL_ACCUM:,.2f}, diff {accum - GL_ACCUM:,.2f})")
    report.append(f"  registered book value   : {book:,.2f}")
    if abs(cost - GL_COST) > GL_TOLERANCE:
        ok = False
        report.append("  COST does not tie to GL 1205104000 -- do not load")
    if abs(accum - GL_ACCUM) > GL_TOLERANCE:
        ok = False
        report.append("  ACCUM does not tie to GL 1205203000 -- do not load")

    off_book = [row for row in registered if abs(row["cost"] - row["accum"] - row["book_value"]) > 0.01]
    if off_book:
        ok = False
        report.append(f"  {len(off_book)} registered rows where cost - accum != book value")

    lives = Counter(row["remaining_life"] for row in registered)
    methods = Counter(row["method"] for row in registered)
    report.append(f"  remaining life (months) : {dict(lives)}")
    report.append(f"  depreciation method     : {dict(methods)}")

    dated = [row for row in registered if not row["acq_date"]]
    if dated:
        ok = False
        report.append(f"  {len(dated)} registered rows without an acquisition date")

    codes = [row["code"] for row in registered]
    duplicates = [code for code, count in Counter(codes).items() if count > 1]
    if duplicates:
        ok = False
        report.append(f"  duplicate asset codes among registered rows: {duplicates[:5]}")

    unreg_cost = sum(row["cost_client"] for row in unregistered)
    report.append(f"  unregistered cost       : {unreg_cost:,.2f} (register only, no GL)")
    with_gl = [row for row in unregistered if row["cost"] or row["accum"]]
    if with_gl:
        ok = False
        report.append(f"  {len(with_gl)} unregistered rows unexpectedly carry computed values")

    report.append(f"  sheet grand total       : {sum(row['cost_client'] for row in rows):,.2f}")
    return ok, report


FIELDS = [
    "code",
    "code_generated",
    "name",
    "owner",
    "category",
    "status",
    "acq_date",
    "cost",
    "accum",
    "book_value",
    "remaining_life",
    "method",
]


def write_csv(path, rows, cost_field):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record["cost"] = row[cost_field]
            writer.writerow(record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="reconcile only (default)")
    parser.add_argument("--write", action="store_true", help="write the CSVs")
    parser.add_argument("--workbook", default=str(WORKBOOK))
    args = parser.parse_args()

    workbook = openpyxl.load_workbook(args.workbook, data_only=True, read_only=True)
    rows = read_rows(workbook[SHEET])
    generated = assign_codes(rows)
    ok, report = check(rows)

    print(f"== {SHEET} (cutover {CUTOVER.isoformat()}) ==")
    print("\n".join(report))
    if generated:
        print(f"  generated asset codes   : {generated} (rows whose 'Kode Aset' was '-')")
    print(f"  RESULT: {'OK' if ok else 'FAILED'}")

    if args.write:
        if not ok:
            print("  refusing to write CSVs while checks fail")
            return 1
        registered = [row for row in rows if row["status"] == REGISTERED]
        unregistered = [row for row in rows if row["status"] != REGISTERED]
        write_csv(OUT_DIR / "asset_register_registered.csv", registered, "cost")
        write_csv(OUT_DIR / "asset_register_unregistered.csv", unregistered, "cost_client")
        print(f"  wrote asset_register_registered.csv ({len(registered)} rows)")
        print(f"  wrote asset_register_unregistered.csv ({len(unregistered)} rows)")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
