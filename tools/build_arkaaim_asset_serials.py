#!/usr/bin/env python3
"""Map the begbal asset codes onto the physical serials from the old listing.

The register that ARKA-AIM runs on is built from the ``Aset Tetap`` sheet of the
begbal workbook, which carries a client asset code (``AS0000868545``) but **no**
serial column. The physical serials survive only in the superseded PO-derived
register ``data/aim_asset_register.csv`` (from ``Listing Asset - odoo.xlsx``):
1,600 batteries and 1,500 drones. The other 490 units genuinely carry no serial.

The two sources share no join key. Their per-product-group counts match exactly,
so this tool pairs them **positionally within a group**, in each file's own row
order -- which is deterministic and reproducible, but arbitrary per unit: the
population and the values are right, the code<->serial pairing is not evidence.
Replace ``data/asset_serials.csv`` wholesale the day the client supplies a real
``Kode Aset -> Serial`` mapping; nothing else has to change.

Usage::

    python3 tools/build_arkaaim_asset_serials.py --check
    python3 tools/build_arkaaim_asset_serials.py --write
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "addons/_tenants/custom_arka_aim_asset_register/data"
LISTING_CSV = DATA / "aim_asset_register.csv"
REGISTERED_CSV = DATA / "asset_register_registered.csv"
UNREGISTERED_CSV = DATA / "asset_register_unregistered.csv"
OUT_CSV = DATA / "asset_serials.csv"

# Begbal ``Nama Aset`` -> listing ``source_desc``. Only the two groups that
# actually carry serials are mapped; everything else stays blank on purpose.
GROUP_MAP = {
    "Damoda Drone Battery": "IT1 SP Damoda Drone Battery",
    "Damoda Drone DMD": "IT1 Damoda Drone DMD-M400W-V3",
}


def _rows(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def build():
    """Return ``(pairs, problems)`` -- ``pairs`` is a list of (code, serial)."""
    listing = _rows(LISTING_CSV)
    register = _rows(REGISTERED_CSV) + _rows(UNREGISTERED_CSV)

    serials_by_group = defaultdict(list)
    for row in listing:
        serial = (row["serial_number"] or "").strip()
        if serial:
            serials_by_group[row["source_desc"]].append(serial)

    codes_by_group = defaultdict(list)
    for row in register:
        source = GROUP_MAP.get(row["name"])
        if source:
            codes_by_group[source].append(row["code"])

    problems = []
    unmapped = set(serials_by_group) - set(GROUP_MAP.values())
    if unmapped:
        problems.append(f"listing groups carry serials but are not in GROUP_MAP: {sorted(unmapped)}")

    pairs = []
    for source in GROUP_MAP.values():
        codes, serials = codes_by_group[source], serials_by_group[source]
        if len(codes) != len(serials):
            problems.append(f"{source}: {len(codes)} register units vs {len(serials)} serials -- refusing to pair")
            continue
        pairs.extend(zip(codes, serials))

    duplicate_codes = [code for code, count in Counter(c for c, _ in pairs).items() if count > 1]
    if duplicate_codes:
        problems.append(f"duplicate asset codes in the pairing: {duplicate_codes[:5]}")
    return pairs, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the CSV (default: report only)")
    parser.add_argument("--check", action="store_true", help="report only")
    args = parser.parse_args()

    pairs, problems = build()
    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)

    # The client's own listing repeats 8 battery serials; that is their data, so
    # the register cannot treat the serial as unique. Reported, not rejected.
    repeated = [s for s, n in Counter(s for _, s in pairs).items() if n > 1]
    print(f"{len(pairs)} code -> serial pairs, {len(set(s for _, s in pairs))} distinct serials")
    if repeated:
        print(f"NOTE: {len(repeated)} serials repeat in the source listing: {sorted(repeated)}")
    for code, serial in pairs[:3]:
        print(f"  sample: {code} -> {serial}")

    if problems:
        return 1
    if args.write:
        with OUT_CSV.open("w", newline="") as handle:
            # LF, like every other data file here; csv defaults to CRLF.
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["code", "serial_number"])
            writer.writerows(pairs)
        print(f"wrote {OUT_CSV.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
