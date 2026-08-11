#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the two data-derived diagrams from ``catalog.json``.

D01 and D03 are hand-authored SVGs describing architecture that does not change
per build. D02, D04 and D05 count modules, so drawing them by hand would
reintroduce exactly the manual-number drift this catalog exists to remove —
they are regenerated on every build instead.

Usage: python3 build_diagrams.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "src", "svg")

STYLE = """<style>
 .lbl{font-size:13.5px;fill:#1A2332}
 .hd{font-size:12px;fill:#1A2332;font-weight:bold}
 .num{font-size:13px;fill:#714B67;font-weight:bold}
 .sm{font-size:11px;fill:#4A5568}
 .cap{font-size:11.5px;fill:#714B67;font-weight:bold;letter-spacing:.05em}
 .bar{fill:#714B67}
 .bar2{fill:#C9B8C6}
 .cell{fill:#FFFFFF;stroke:#E0D6DE;stroke-width:1}
 .alt{fill:#F5F2F4;stroke:#E0D6DE;stroke-width:1}
 .own{font-size:14px;fill:#714B67;font-weight:bold}
 .cfg{font-size:14px;fill:#9AA5B1}
</style>"""


# Layer order for the tier diagram: fewest tenants touched at the top.
TIER_ROWS = [
    ("_tenants", "_tenants/ — satu pelanggan", "saldo awal · penomoran · aturan satu entitas", 250, 400, "plum"),
    ("verticals", "verticals/ — satu industri", "PPOB / VAS · F&B ESB · template", 190, 520, "lila"),
    (
        "ee_gap",
        "ee_gap/ — semua tenant",
        "selisih Community → Enterprise: akuntansi · payroll · gudang · retail · portal keuangan",
        90,
        720,
        "box",
    ),
    ("compliance", "compliance/ — semua tenant ID", "UU PDP 27/2022 · Coretax · PPh", 90, 350, "box"),
    ("control_plane", "control_plane/ + operations/", "lapisan kendali — melayani operator", 460, 350, "box"),
    ("core", "core/ — fondasi", "HMAC · adapter · BAST · HHT · barcode", 90, 350, "box"),
    ("_vendor", "_vendor/ — pihak ketiga", "OCA: queue_job · auth_jwt · lainnya", 460, 350, "box"),
]


def tier_chart(cat) -> str:
    """The module-tier diagram.

    Generated rather than hand-drawn because it states a count per tier. The
    hand-authored version silently kept saying 105 ee_gap modules after the
    branch was rebased onto a main that had 103 — exactly the drift this
    catalog exists to remove.
    """
    counts = dict(cat["meta"]["counts"]["by_group"])
    # control_plane and operations share one row.
    counts["control_plane"] = counts.get("control_plane", 0) + counts.pop("operations", 0)
    width, height = 900, 430
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Calibri, Carlito, sans-serif">',
        """<style>
 .lbl{font-size:14px;fill:#1A2332;font-weight:bold}
 .sm{font-size:11.5px;fill:#4A5568}
 .num{font-size:22px;fill:#714B67;font-weight:bold}
 .numw{font-size:22px;fill:#FFFFFF;font-weight:bold}
 .lblw{font-size:14px;fill:#FFFFFF;font-weight:bold}
 .smw{font-size:11.5px;fill:#E8E0E7}
 .cap{font-size:12px;fill:#714B67;font-weight:bold;letter-spacing:.04em}
 .box{fill:#FFFFFF;stroke:#C9B8C6;stroke-width:1.4}
 .lila{fill:#E8E0E7;stroke:#C9B8C6;stroke-width:1.4}
 .plum{fill:#714B67;stroke:#714B67}
 .arrow{stroke:#714B67;stroke-width:2;fill:none;marker-end:url(#b)}
</style>
<defs><marker id="b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6"
 orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#714B67"/></marker></defs>""",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#FFFFFF"/>',
        '<text class="cap" x="40" y="28">SEMAKIN KE ATAS, SEMAKIN SEDIKIT TENANT YANG TERSENTUH</text>',
    ]

    y = 44
    prev_style = None
    for group, title, sub, x, w, style in TIER_ROWS:
        h = 60 if group == "ee_gap" else 52
        # New band starts a new row unless it sits beside the previous one.
        if prev_style == "pair":
            y -= 62
        p.append(f'<rect class="{style}" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        num_cls = "numw" if style == "plum" else "num"
        lbl_cls = "lblw" if style == "plum" else "lbl"
        sub_cls = "smw" if style == "plum" else "sm"
        p.append(
            f'<text class="{num_cls}" x="{x + 28}" y="{y + h / 2 + 10}" '
            f'text-anchor="middle">{counts.get(group, 0)}</text>'
        )
        p.append(f'<text class="{lbl_cls}" x="{x + 60}" y="{y + h / 2 - 2}">{title}</text>')
        p.append(f'<text class="{sub_cls}" x="{x + 60}" y="{y + h / 2 + 16}">{sub}</text>')
        prev_style = "pair" if (x == 90 and group in ("compliance", "core")) else None
        y += h + 10

    p.append('<path class="arrow" d="M868 330 L868 80"/>')
    p.append(
        '<text class="sm" x="856" y="210" text-anchor="middle" '
        'transform="rotate(-90 856 210)">promosi bila muncul untuk pelanggan kedua</text>'
    )
    p.append(
        '<text class="sm" x="40" y="392">Tingkat ditentukan semata-mata oleh direktori '
        "tempat modul berada. Kategori di dalam manifest bukan penentu tingkat.</text>"
    )
    p.append(
        f'<text class="sm" x="40" y="410">Total {cat["meta"]["counts"]["modules_total"]} '
        "modul. Mesin bersama tidak boleh masuk _tenants/, seberapa pun jelas ia diminta "
        "satu pelanggan.</text>"
    )
    p.append("</svg>")
    return "\n".join(p)


def domain_chart(cat) -> str:
    doms = sorted(cat["domains"], key=lambda d: -d["module_count"])
    # barmax leaves room for the longest label ("29 (22 umum · 7 lainnya)") to
    # the right of the widest bar without running past the viewBox.
    width, barmax, rowh = 900, 300, 34
    height = 90 + rowh * len(doms) + 30
    mx = max(d["module_count"] for d in doms)

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Calibri, Carlito, sans-serif">',
        STYLE,
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#FFFFFF"/>',
        '<text class="cap" x="40" y="30">MODUL PER DOMAIN FUNGSIONAL</text>',
        '<text class="sm" x="40" y="52">Batang penuh = modul berlaku umum. '
        "Batang muda = khusus brand, platform, atau pihak ketiga.</text>",
    ]
    y = 78
    for d in doms:
        mods = [m for m in cat["modules"] if m["domain"] == d["id"]]
        gen = sum(1 for m in mods if m["scope"] == "general")
        oth = len(mods) - gen
        wg, wo = round(barmax * gen / mx), round(barmax * oth / mx)
        p.append(f'<text class="lbl" x="40" y="{y + 15}">{d["title_id"]}</text>')
        p.append(f'<rect class="bar" x="330" y="{y + 3}" width="{wg}" height="16" rx="2"/>')
        if wo:
            p.append(f'<rect class="bar2" x="{330 + wg}" y="{y + 3}" width="{wo}" height="16" rx="2"/>')
        label = str(d["module_count"]) + (f"  ({gen} umum · {oth} lainnya)" if oth else "")
        p.append(f'<text class="num" x="{330 + wg + wo + 10}" y="{y + 16}">{label}</text>')
        y += rowh
    p.append(
        f'<text class="sm" x="40" y="{y + 18}">Total {cat["meta"]["counts"]["modules_total"]} '
        "modul. Dihasilkan otomatis dari repositori — angka pada diagram ini tidak "
        "dipelihara manual.</text>"
    )
    p.append("</svg>")
    return "\n".join(p)


def brand_matrix(cat) -> str:
    tenants, doms = cat["tenants"], cat["domains"]
    # `left` has to clear the longest domain title
    # ("Administrasi Platform & Odoo-as-a-Service") or the labels clip.
    colw, rowh, left = 82, 30, 340
    width = left + colw * len(tenants) + 40
    height = 130 + rowh * len(doms) + 60

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Calibri, Carlito, sans-serif">',
        STYLE,
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#FFFFFF"/>',
        '<text class="cap" x="30" y="26">DOMAIN × BRAND — DI MANA DATA ATAU KONFIGURASI BRAND SUDAH ADA</text>',
    ]
    for i, t in enumerate(tenants):
        x = left + i * colw + colw / 2
        p.append(
            f'<text class="hd" x="{x}" y="118" text-anchor="start" transform="rotate(-55 {x} 118)">{t["brand"]}</text>'
        )
    y = 126
    for r, d in enumerate(doms):
        mods = [m for m in cat["modules"] if m["domain"] == d["id"]]
        cls = "alt" if r % 2 else "cell"
        p.append(f'<rect class="{cls}" x="30" y="{y}" width="{left - 30}" height="{rowh}"/>')
        p.append(f'<text class="lbl" x="40" y="{y + 20}">{d["title_id"]}</text>')
        for i, t in enumerate(tenants):
            x = left + i * colw
            p.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{colw}" height="{rowh}"/>')
            own = sum(1 for m in mods if t["id"] in m["tenants"] and m["scope"] == "tenant")
            cfg = sum(1 for m in mods if t["id"] in m["tenants"] and m["scope"] != "tenant")
            txt = (f"●{own} " if own else "") + (f"○{cfg}" if cfg else "")
            if txt.strip():
                p.append(
                    f'<text class="{"own" if own else "cfg"}" x="{x + colw / 2}" '
                    f'y="{y + 20}" text-anchor="middle">{txt.strip()}</text>'
                )
        y += rowh
    p.append(
        f'<text class="sm" x="30" y="{y + 24}">● modul khusus brand (addons/_tenants/)   '
        "○ modul umum yang sudah membawa profil atau data brand tersebut</text>"
    )
    p.append(
        f'<text class="sm" x="30" y="{y + 42}">Sel kosong berarti domain itu tersedia untuk '
        "brand tersebut tetapi belum membawa data khusus — bukan berarti tidak "
        "tersedia.</text>"
    )
    p.append("</svg>")
    return "\n".join(p)


def main() -> int:
    with open(os.path.join(HERE, "catalog.json"), "r", encoding="utf-8") as fh:
        cat = json.load(fh)
    os.makedirs(SVG, exist_ok=True)
    for name, svg in (
        ("D02-tingkatan-modul.svg", tier_chart(cat)),
        ("D04-peta-domain.svg", domain_chart(cat)),
        ("D05-peta-brand.svg", brand_matrix(cat)),
    ):
        with open(os.path.join(SVG, name), "w", encoding="utf-8") as fh:
            fh.write(svg + "\n")
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
