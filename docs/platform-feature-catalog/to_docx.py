#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rewrite the print HTML into something pandoc turns into a sane DOCX.

Word ignores the print stylesheet entirely, so anything carried only by CSS is
lost. The transforms here re-express those things as structure:

* the callout `<div class="note">` becomes a labelled blockquote — otherwise it
  renders as an ordinary paragraph and the warning silently stops reading as one;
* the CSS-styled cover becomes a plain title block;
* the hand-built table of contents is dropped, because pandoc `--toc` builds a
  real, navigable one;
* the inline `<style>` is dropped so pandoc uses its own defaults rather than
  half-applying ours.

Figures are expected to already reference PNG — run `render_html.py --img png`.

Usage: python3 to_docx.py [in.html] [out.html]
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

NOTE_RE = re.compile(r'<div class="note">(.*?)</div>', re.S)
TOC_RE = re.compile(r'<section class="toc">.*?</section>', re.S)
COVER_RE = re.compile(r'<section class="cover">(.*?)</section>', re.S)
STYLE_RE = re.compile(r"<style>.*?</style>", re.S)
ENTRY_RE = re.compile(r'<div class="entry">|</div>')


def convert_cover(match: re.Match) -> str:
    body = match.group(1)
    title = " ".join(re.findall(r"<h1>(.*?)</h1>", body, re.S)).replace("<br>", " ")
    sub = " ".join(re.findall(r'<div class="sub">(.*?)</div>', body, re.S))
    pairs = re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", body, re.S)
    rows = "".join(f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>" for k, v in pairs)
    return (
        f"<h1>{' '.join(title.split())}</h1><p><em>{' '.join(sub.split())}</em></p><table><tbody>{rows}</tbody></table>"
    )


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "src", "catalog.html")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "src", "catalog-docx.html")

    with open(src, "r", encoding="utf-8") as fh:
        html = fh.read()

    html = STYLE_RE.sub("", html)
    html = TOC_RE.sub("", html)
    html = COVER_RE.sub(convert_cover, html)
    html = NOTE_RE.sub(
        lambda m: f"<blockquote><p><strong>CATATAN.</strong> {m.group(1).strip()}</p></blockquote>",
        html,
    )
    # The entry wrapper only existed to control page breaks.
    html = ENTRY_RE.sub("", html)

    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"{os.path.relpath(dst, HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
