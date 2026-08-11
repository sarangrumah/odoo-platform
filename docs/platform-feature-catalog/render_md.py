#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render ``catalog.json`` + ``narrative/`` into ``catalog.md``.

This is the version that lives in git and gets reviewed in a pull request. The
PDF and DOCX are built from the same block list via ``render_html.py``, so a
difference between them is a formatting difference, never a content one.

Usage: python3 render_md.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import os

import render_common as rc

HERE = os.path.dirname(os.path.abspath(__file__))


def _escape_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def format_blocks(blocks) -> str:
    out: list[str] = []
    for b in blocks:
        kind = b["kind"]
        if kind == "heading":
            out.append(f"{'#' * b['level']} {b['text']}\n")
        elif kind == "para":
            out.append(f"{b['text']}\n")
        elif kind == "note":
            out.append(f"> {b['text']}\n")
        elif kind == "figure":
            out.append(f"![{b['alt']}]({b['src']})\n")
        elif kind == "list":
            out.append("\n".join(f"- {i}" for i in b["items"]) + "\n")
        elif kind == "table":
            head = b["head"]
            if b.get("headless"):
                head = ["" for _ in head]
            out.append("| " + " | ".join(_escape_cell(h) for h in head) + " |")
            out.append("|" + "|".join(" --- " for _ in head) + "|")
            for row in b["rows"]:
                out.append("| " + " | ".join(_escape_cell(c) for c in row) + " |")
            out.append("")
        else:
            raise KeyError(f"unknown block kind {kind}")
    return "\n".join(out)


def header(cat) -> str:
    meta = cat["meta"]
    return (
        "<!-- GENERATED FILE — do not edit by hand.\n"
        "     Source: catalog.json + narrative/*.md\n"
        "     Rebuild: python3 docs/platform-feature-catalog/build.sh -->\n\n"
        "# Katalog Fitur Platform Odoo — Erajaya Group\n\n"
        f"Dihasilkan {meta['generated_at'][:10]} dari commit `{meta['git_commit']}`"
        f"{' (ada perubahan belum ter-commit)' if meta['git_dirty'] else ''} "
        f"pada branch `{meta['git_branch']}`. "
        f"Odoo {meta['odoo_series']}, {meta['counts']['modules_total']} modul custom.\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=os.path.join(HERE, "catalog.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "catalog.md"))
    args = ap.parse_args()

    with open(args.catalog, "r", encoding="utf-8") as fh:
        cat = json.load(fh)

    body = format_blocks(rc.build_document(cat))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(header(cat) + "\n" + body)

    lines = (header(cat) + body).count("\n")
    print(f"{lines} lines → {os.path.relpath(args.out, os.path.dirname(HERE))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
