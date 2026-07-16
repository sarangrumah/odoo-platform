#!/usr/bin/env python3
"""Generate the l10n_erajaya localization module data files.

One-time generator. Reads:
  - imports/arka_aim_coa.csv          (master COA, 548 rows)
  - /tmp/prd_aim_taxes.json           (live prd_arkaaim company-1 active taxes dump)
Writes the CSV template files + nothing else (Python/manifest are hand-maintained).

Run from repo root:  python3 tools/gen_l10n_erajaya.py
"""

import csv
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COA = os.path.join(REPO, "imports", "arka_aim_coa.csv")
TAXES = "/tmp/prd_aim_taxes.json"
OUT = os.path.join(REPO, "addons", "ee_gap", "l10n_erajaya", "data", "template")

# --- exclusion filter ---------------------------------------------------------
EXCL_TYPES = {"asset_cash", "liability_credit_card"}
BRANDS = [
    "PT Bank",
    "BCA",
    "BRI",
    "BNI",
    "Mandiri",
    "CIMB",
    "Permata",
    "Danamon",
    "Maybank",
    "OCBC",
    "Panin",
    "HSBC",
    "Citibank",
    "Time Deposit",
    "Time Loan",
]

# --- account type / reconcile coercions (data fixes) --------------------------
COERCE_TYPE = {"2103100001": "liability_payable", "6199000000": "expense_direct_cost"}
COERCE_RECONCILE = {"2103100001": True}

# accounts that MUST survive the filter (referenced by taxes / company defaults)
REQUIRED = [
    "1117200001",
    "2104300001",
    "2104100004",
    "2104100005",
    "1106000001",
    "2103100001",
    "5199000000",
    "6199000000",
    "7607000000",
    "7704000000",
]


def axid(code):
    return "erajaya_" + code


def slug(s):
    return re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z]+", "_", s.lower())).strip("_")


def write_csv(name, header, rows):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        w.writerows(rows)
    print("wrote %-40s %d data rows" % (name, len(rows)))


def main():
    # ---- accounts ----
    src = list(csv.DictReader(open(COA)))
    kept, dropped = [], []
    for r in src:
        why = None
        if r["account_type"] in EXCL_TYPES:
            why = "type:" + r["account_type"]
        else:
            for b in BRANDS:
                if b.lower() in r["name"].lower():
                    why = "brand:" + b
                    break
        (dropped if why else kept).append((r, why))
    keptcodes = {r["code"] for r, _ in kept}
    missing = [c for c in REQUIRED if c not in keptcodes]
    if missing:
        raise SystemExit("ABORT: required accounts dropped/missing: %s" % missing)

    acc_rows = []
    for r, _ in kept:
        code = r["code"]
        atype = COERCE_TYPE.get(code, r["account_type"])
        recon = COERCE_RECONCILE.get(code, r["reconcile"] in ("True", "1", True))
        acc_rows.append([axid(code), code, r["name"], atype, "True" if recon else "False"])
    write_csv("account.account-erajaya.csv", ["id", "code", "name", "account_type", "reconcile"], acc_rows)
    print("  dropped %d accounts:" % len(dropped))
    for r, why in dropped:
        print("    %-12s %-50s [%s]" % (r["code"], r["name"][:50], why))

    # ---- account groups (1- and 2-digit prefixes) ----
    NAMES1 = {
        "1": "Aset",
        "2": "Kewajiban",
        "3": "Ekuitas",
        "4": "Pendapatan",
        "5": "Pendapatan",
        "6": "Beban Pokok",
        "7": "Beban",
        "8": "Lain-lain",
    }
    pref1 = sorted({c[0] for c in keptcodes})
    pref2 = sorted({c[:2] for c in keptcodes})
    grp_rows = []
    for p in pref1:
        grp_rows.append(["erajaya_group_%s" % p, p, p, NAMES1.get(p, "Group %s" % p)])
    for p in pref2:
        grp_rows.append(["erajaya_group_%s" % p, p, p, "%s %s" % (NAMES1.get(p[0], "Group"), p)])
    write_csv("account.group-erajaya.csv", ["id", "code_prefix_start", "code_prefix_end", "name"], grp_rows)

    # ---- taxes + tax groups ----
    taxes = json.load(open(TAXES))
    groups = {}
    for t in taxes:
        if t["group_name"]:
            groups.setdefault(t["group_name"], "erajaya_tg_" + slug(t["group_name"]))
    tg_rows = [[xid, "base.id", name, "", ""] for name, xid in sorted(groups.items())]
    write_csv(
        "account.tax.group-erajaya.csv",
        ["id", "country_id", "name", "tax_payable_account_id", "tax_receivable_account_id"],
        tg_rows,
    )

    TAX_HDR = [
        "id",
        "active",
        "description",
        "is_base_affected",
        "invoice_label",
        "type_tax_use",
        "tax_group_id",
        "name",
        "amount_type",
        "amount",
        "repartition_line_ids/repartition_type",
        "repartition_line_ids/tag_ids",
        "repartition_line_ids/factor_percent",
        "repartition_line_ids/document_type",
        "repartition_line_ids/account_id",
    ]

    def fact(f):
        return "" if abs(f - 100.0) < 1e-9 else (str(int(f)) if f == int(f) else str(f))

    def acct(code):
        return axid(code) if code else ""

    seen = set()
    tax_rows = []
    for t in taxes:
        xid = "erajaya_tax_%s_%s" % (slug(t["name"]), t["type_tax_use"])
        n = xid
        i = 1
        while n in seen:
            i += 1
            n = "%s_%d" % (xid, i)
        seen.add(n)
        gxid = groups.get(t["group_name"], "")
        rep = t["repartition"]
        r0 = rep[0]
        tax_rows.append(
            [
                n,
                "",
                t["description"] or "",
                "" if t["is_base_affected"] else "False",
                t["invoice_label"] or "",
                t["type_tax_use"],
                gxid,
                t["name"],
                t["amount_type"],
                str(t["amount"]),
                r0["rep_type"],
                "",
                fact(r0["factor"]),
                r0["doc_type"],
                acct(r0["account_code"]),
            ]
        )
        for r in rep[1:]:
            tax_rows.append(
                [
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    r["rep_type"],
                    "",
                    fact(r["factor"]),
                    r["doc_type"],
                    acct(r["account_code"]),
                ]
            )
    write_csv("account.tax-erajaya.csv", TAX_HDR, tax_rows)

    # default sale/purchase tax xml_ids (active "12% (Non-Luxury Good)")
    def find(name, use):
        for t in taxes:
            if t["name"] == name and t["type_tax_use"] == use:
                return "erajaya_tax_%s_%s" % (slug(t["name"]), use)
        return None

    print("\nDEFAULT sale tax xmlid:", find("12% (Non-Luxury Good)", "sale"))
    print("DEFAULT purchase tax xmlid:", find("12% (Non-Luxury Good)", "purchase"))
    print("\nKEPT %d accounts, %d taxes, %d groups" % (len(acc_rows), len(taxes), len(tg_rows)))


if __name__ == "__main__":
    main()
