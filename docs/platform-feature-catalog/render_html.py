#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render ``catalog.json`` + ``narrative/`` into printable HTML.

Feeds both outputs: Chromium print-to-PDF, and pandoc → DOCX (via to_docx.py).
Same block list as ``render_md.py``, so the three formats cannot disagree about
content.

Usage: python3 render_html.py [--out src/catalog.html] [--img svg|png]
  --img svg  inline the SVG (crisp in PDF)
  --img png  reference the rasterised PNG (Word does not render SVG reliably)
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re

import render_common as rc

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")

INLINE_MD = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+?`)")


def inline(text: str) -> str:
    """Escape, then re-apply the three inline marks the narrative uses."""
    out = []
    for part in INLINE_MD.split(str(text)):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<strong>{html.escape(part[2:-2])}</strong>")
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<em>{html.escape(part[1:-1])}</em>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def slug(text: str, seen: dict) -> str:
    """Stable anchor, de-duplicated.

    Thirteen chapters end with the same "Yang bersifat khusus per-brand"
    heading, so the raw slug collides. Duplicate ids are invalid HTML and make
    pandoc warn on every one of them.
    """
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "bagian"
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}-{seen[base]}"


def render_figure(b, mode: str) -> str:
    name = os.path.basename(b["src"])
    caption = f"<figcaption>{inline(b['alt'])}</figcaption>" if b["alt"] else ""
    if mode == "svg":
        path = os.path.join(SRC, "svg", name)
        with open(path, "r", encoding="utf-8") as fh:
            svg = fh.read()
        # Strip the XML prolog if present; an inline <svg> must not carry one.
        svg = re.sub(r"^<\?xml[^>]*\?>\s*", "", svg)
        return f"<figure>{svg}{caption}</figure>"
    png = f"png/{os.path.splitext(name)[0]}.png"
    return f'<figure><img src="{png}" alt="{html.escape(b["alt"])}">{caption}</figure>'


def render_blocks(blocks, mode: str) -> str:
    out: list[str] = []
    in_entry = False
    seen_anchors: dict[str, int] = {}

    def close_entry():
        nonlocal in_entry
        if in_entry:
            out.append("</div>")
            in_entry = False

    for b in blocks:
        kind = b["kind"]
        if kind == "heading":
            lvl = b["level"]
            if lvl <= 2:
                close_entry()
            if lvl == 3 and " — " in b["text"] and b["text"].split(" — ")[0].islower():
                # An appendix entry: keep the whole block on one page.
                close_entry()
                out.append('<div class="entry">')
                in_entry = True
            anchor = slug(b["text"], seen_anchors)
            out.append(f'<h{lvl} id="{anchor}">{inline(b["text"])}</h{lvl}>')
        elif kind == "para":
            out.append(f"<p>{inline(b['text'])}</p>")
        elif kind == "note":
            out.append(f'<div class="note">{inline(b["text"])}</div>')
        elif kind == "list":
            items = "".join(f"<li>{inline(i)}</li>" for i in b["items"])
            out.append(f"<ul>{items}</ul>")
        elif kind == "figure":
            out.append(render_figure(b, mode))
        elif kind == "table":
            out.append(render_table(b))
        else:
            raise KeyError(f"unknown block kind {kind}")
    close_entry()
    return "\n".join(out)


def render_table(b) -> str:
    classes = " ".join(c for c in ("compact" if b.get("compact") else "", "headless" if b.get("headless") else "") if c)
    cls = f' class="{classes}"' if classes else ""
    cols = ""
    if b.get("widths"):
        cols = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in b["widths"]) + "</colgroup>"
    head = "".join(f"<th>{inline(h)}</th>" for h in b["head"])
    body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in b["rows"])
    return f"<table{cls}>{cols}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_toc(blocks) -> str:
    out = ['<section class="toc"><h1 class="first">Daftar Isi</h1><ol>']
    open_sub = False
    for b in blocks:
        if b["kind"] != "heading" or b["level"] > 2:
            continue
        if b["level"] == 1:
            if open_sub:
                out.append("</ol></li>")
                open_sub = False
            out.append(f"<li>{html.escape(b['text'])}<ol>")
            open_sub = True
        else:
            if not open_sub:
                out.append("<li><ol>")
                open_sub = True
            out.append(f"<li>{html.escape(b['text'])}</li>")
    if open_sub:
        out.append("</ol></li>")
    out.append("</ol></section>")
    return "".join(out)


def render_cover(cat) -> str:
    meta, counts = cat["meta"], cat["meta"]["counts"]
    dirty = " (ada perubahan belum ter-commit)" if meta["git_dirty"] else ""
    return f"""<section class="cover">
  <div class="eyebrow">Erajaya Group · Platform Odoo</div>
  <h1>Katalog Fitur<br>Platform Odoo</h1>
  <div class="sub">Seluruh kapabilitas yang sudah dibangun, dikelompokkan per domain,
    dengan pemisahan antara yang berlaku umum dan yang khusus satu brand —
    ditambah analisis kesenjangan administrasi platform.</div>
  <dl>
    <dt>Modul custom</dt><dd>{counts["modules_total"]}</dd>
    <dt>Domain fungsional</dt><dd>{len(cat["domains"])}</dd>
    <dt>Brand terdaftar</dt><dd>{len(cat["tenants"])}</dd>
    <dt>Versi</dt><dd>v{meta["generated_at"][:10]}</dd>
    <dt>Sumber</dt><dd>commit <code>{meta["git_commit"]}</code>{dirty}</dd>
    <dt>Platform</dt><dd>Odoo {meta["odoo_series"]} Community</dd>
  </dl>
</section>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=os.path.join(HERE, "catalog.json"))
    ap.add_argument("--out", default=os.path.join(SRC, "catalog.html"))
    ap.add_argument("--img", choices=("svg", "png"), default="svg")
    ap.add_argument("--no-cover", action="store_true")
    args = ap.parse_args()

    with open(args.catalog, "r", encoding="utf-8") as fh:
        cat = json.load(fh)
    blocks = rc.build_document(cat)

    with open(os.path.join(SRC, "style.css"), "r", encoding="utf-8") as fh:
        css = fh.read()

    parts = [
        "<!doctype html>",
        '<html lang="id"><head><meta charset="utf-8">',
        "<title>Katalog Fitur Platform Odoo — Erajaya Group</title>",
        f"<style>{css}</style>",
        "</head><body>",
    ]
    if not args.no_cover:
        parts.append(render_cover(cat))
    parts.append(render_toc(blocks))
    parts.append(render_blocks(blocks, args.img))
    parts.append("</body></html>")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"{len(blocks)} blocks → {os.path.relpath(args.out, HERE)} (img={args.img})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
