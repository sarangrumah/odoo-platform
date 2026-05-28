"""Extract X101 Material Master to clean CSVs ready for Odoo import.

Decisions applied (documented in docs/Master data-.../Review Result.xlsx sheet 7):
- Dedup: keep most recent row per PROD SKU by PRICE EFFECTIVE FROM (descending).
- Encoding: replace U+FFFD (replacement char) with '(R)' marker, then back to '(R)' literal
  (we use '(R)' because openpyxl source already lost the original encoding — using '(R)' is
  safe ASCII and recognizable; user can mass-replace to '®' later if desired).
  UPDATE per user: keep '®' (R-in-circle). We restore U+FFFD -> '®'.
- Variants: only combinations (SIZE, INSEAM) that appear in source.
- INSEAM '-' = no inseam (non-bottoms) -> single Size axis only.
- Currency: integer IDR, decimal=2 default Odoo IDR config (no scaling).

Outputs (CSV files in same directory):
  out_templates.csv          (14,885 templates) -> product.template
  out_attributes.csv         (Size + Inseam attribute values)
  out_template_attrlines.csv (template_id, attribute, value_id) -> product.template.attribute.line
  out_variants.csv           (~159,658 variants) -> product.product mapping with barcode + sku
  out_categories.csv         (CATEGORY/CLASS/SUBCLASS 3-level tree)
"""
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = r"E:\Projects\Odoo\platform\docs\Master data-20260528T090510Z-3-001\Master data\X101_Material_Master.xlsx"

# Encoding cleanup: source XLSX has U+FFFD where original was U+00AE (R)
REPL = {"�": "®"}


def clean(s):
    if s is None:
        return ""
    s = str(s)
    for k, v in REPL.items():
        s = s.replace(k, v)
    return s.strip()


def main():
    print(f"Reading {SRC} ...", flush=True)
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb.active

    # Buffers
    # by PROD SKU -> (price_eff_date, row_dict) keep max date
    sku_best = {}
    # template aggregation by PRODUCT CODE
    tmpl_meta = {}  # code -> dict(name, brand, cat, cls, subcls, retail_price, price_eff)
    # attribute values seen
    sizes = set()
    inseams = set()
    # per template, set of variant tuples
    tmpl_variants = defaultdict(set)  # code -> {(size, inseam), ...}

    total = 0
    skipped_blank = 0
    for i, row in enumerate(ws.iter_rows(min_row=3, values_only=True)):
        # row indices per header: 0=None,1=PRODUCT CODE,2=DESC,3=BRAND,4=CAT,5=CLASS,
        # 6=SUBCLASS,7=PRICE LEVEL,8=LEVEL VALUE,9=PROD SKU,10=ITEM SIZE,11=INSEAM,
        # 12=PROD GTIN,13=PROD JAN,14=ITEM RETAIL PRICE,15=PRICE EFFECTIVE FROM
        pc = row[1]
        sku = row[9]
        if not pc or not sku:
            skipped_blank += 1
            continue
        total += 1
        name = clean(row[2])
        brand = clean(row[3])
        cat = clean(row[4])
        cls = clean(row[5])
        subcls = clean(row[6])
        size = clean(row[10])
        inseam_raw = row[11]
        inseam = clean(inseam_raw) if inseam_raw not in (None, "-") else ""
        gtin = clean(row[12]) if row[12] else ""
        retail = float(row[14]) if row[14] is not None else 0.0
        eff = row[15] if isinstance(row[15], datetime) else None

        # Dedup by SKU keeping latest eff date
        prev = sku_best.get(sku)
        prev_eff = prev[0] if prev else None
        if prev is None or (eff and (prev_eff is None or eff > prev_eff)):
            sku_best[sku] = (
                eff,
                {
                    "sku": sku,
                    "tmpl_code": pc,
                    "size": size,
                    "inseam": inseam,
                    "gtin": gtin,
                },
            )

        # Template meta (use latest by eff date too)
        m = tmpl_meta.get(pc)
        if m is None or (eff and (m.get("eff") is None or eff > m["eff"])):
            tmpl_meta[pc] = {
                "code": pc,
                "name": name,
                "brand": brand,
                "cat": cat,
                "cls": cls,
                "subcls": subcls,
                "retail": retail,
                "eff": eff,
            }

        tmpl_variants[pc].add((size, inseam))
        if size:
            sizes.add(size)
        if inseam:
            inseams.add(inseam)

        if (i + 1) % 50000 == 0:
            print(f"  scanned {i + 1} rows...", flush=True)

    wb.close()
    print(f"Scan done. total={total}, skipped_blank={skipped_blank}", flush=True)
    print(f"Unique templates: {len(tmpl_meta)}", flush=True)
    print(f"Unique SKUs (post-dedup): {len(sku_best)}", flush=True)
    print(f"Distinct sizes: {len(sizes)}, distinct inseams: {len(inseams)}", flush=True)

    # ---- Write categories (CATEGORY > CLASS > SUBCLASS) ----
    cats_seen = set()
    cls_seen = set()
    subcls_seen = set()
    for m in tmpl_meta.values():
        if m["cat"]:
            cats_seen.add(m["cat"])
        if m["cat"] and m["cls"]:
            cls_seen.add((m["cat"], m["cls"]))
        if m["cat"] and m["cls"] and m["subcls"]:
            subcls_seen.add((m["cat"], m["cls"], m["subcls"]))

    def cat_xid(name):
        safe = name.replace(" ", "_").replace("/", "_").replace("-", "_").upper()
        return f"cat_l1_{safe}"

    def cls_xid(cat, cls):
        safe = (cat + "_" + cls).replace(" ", "_").replace("/", "_").replace("-", "_").upper()
        return f"cat_l2_{safe}"

    def sub_xid(cat, cls, sub):
        safe = (
            (cat + "_" + cls + "_" + sub)
            .replace(" ", "_")
            .replace("/", "_")
            .replace("-", "_")
            .upper()
        )
        return f"cat_l3_{safe}"

    with open(os.path.join(HERE, "out_categories.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["xid", "name", "parent_xid"])
        for c in sorted(cats_seen):
            w.writerow([cat_xid(c), c, ""])
        for cat, cls in sorted(cls_seen):
            w.writerow([cls_xid(cat, cls), cls, cat_xid(cat)])
        for cat, cls, sub in sorted(subcls_seen):
            w.writerow([sub_xid(cat, cls, sub), sub, cls_xid(cat, cls)])

    # ---- Write attributes ----
    with open(os.path.join(HERE, "out_attributes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["attribute", "value", "xid"])
        for s in sorted(sizes):
            w.writerow(["Size", s, f"attr_size_{s.replace(' ', '_').replace('/', '_')}"])
        for ins in sorted(inseams):
            w.writerow(["Inseam", ins, f"attr_inseam_{ins.replace(' ', '_').replace('/', '_')}"])

    # ---- Write templates ----
    with open(os.path.join(HERE, "out_templates.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tmpl_xid", "default_code", "name", "list_price", "categ_xid"])
        for pc, m in sorted(tmpl_meta.items()):
            tmpl_xid = "tmpl_" + pc.replace("-", "_").replace(" ", "_")
            categ_xid = (
                sub_xid(m["cat"], m["cls"], m["subcls"])
                if m["cat"] and m["cls"] and m["subcls"]
                else (cls_xid(m["cat"], m["cls"]) if m["cat"] and m["cls"] else (cat_xid(m["cat"]) if m["cat"] else ""))
            )
            w.writerow([tmpl_xid, pc, m["name"], f"{m['retail']:.2f}", categ_xid])

    # ---- Write template-attribute lines (which attributes each template uses) ----
    with open(
        os.path.join(HERE, "out_template_attrlines.csv"), "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f)
        w.writerow(["tmpl_xid", "attribute", "value"])
        for pc, vset in sorted(tmpl_variants.items()):
            tmpl_xid = "tmpl_" + pc.replace("-", "_").replace(" ", "_")
            t_sizes = sorted({s for s, _ in vset if s})
            t_inseams = sorted({i for _, i in vset if i})
            for s in t_sizes:
                w.writerow([tmpl_xid, "Size", s])
            for ins in t_inseams:
                w.writerow([tmpl_xid, "Inseam", ins])

    # ---- Write variants (one row per PROD SKU) ----
    with open(os.path.join(HERE, "out_variants.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "tmpl_xid", "size", "inseam", "gtin"])
        for sku, (_, v) in sorted(sku_best.items()):
            tmpl_xid = "tmpl_" + v["tmpl_code"].replace("-", "_").replace(" ", "_")
            w.writerow([sku, tmpl_xid, v["size"], v["inseam"], v["gtin"]])

    print(f"Wrote CSVs to {HERE}", flush=True)
    print(
        f"  categories={len(cats_seen)}+{len(cls_seen)}+{len(subcls_seen)} "
        f"templates={len(tmpl_meta)} variants={len(sku_best)} "
        f"sizes={len(sizes)} inseams={len(inseams)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
