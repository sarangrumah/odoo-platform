#!/usr/bin/env python3
"""Prepare the print-HTML for pandoc -> docx.

Word ignores our stylesheet, so anything the CSS was carrying (callout boxes,
menu-path chips, figure captions) has to be re-expressed as structure pandoc
understands: blockquotes, bold runs, italic paragraphs. Also swaps the Mermaid
SVGs for PNGs, which Word renders reliably.
"""

import re
import sys
from html.parser import HTMLParser  # noqa: F401  (kept for future use)

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()

# --- stylesheet links are meaningless in docx
s = re.sub(r"<link[^>]*>", "", s)

# --- Word can't be trusted with SVG; use the PNG renders
s = s.replace('src="svg/', 'src="png/').replace('.svg"', '.png"')


# --- the gradient cover becomes a plain title block
def cover(m):
    body = m.group(1)
    kicker = re.search(r'class="kicker">(.*?)</div>', body, re.S)
    h1 = re.search(r"<h1>(.*?)</h1>", body, re.S)
    h2 = re.search(r"<h2>(.*?)</h2>", body, re.S)
    lead = re.search(r'class="lead">(.*?)</div>', body, re.S)
    meta = re.findall(r"<div><b>(.*?)</b>(.*?)</div>", body, re.S)

    def clean(x):
        return re.sub(r"<[^>]+>", " ", x or "").replace("\n", " ").strip()

    out = []
    if kicker:
        out.append(f"<p><strong>{clean(kicker.group(1))}</strong></p>")
    if h1:
        out.append(f"<h1>{clean(h1.group(1))}</h1>")
    if h2:
        out.append(f"<p><strong>{clean(h2.group(1))}</strong></p>")
    if lead:
        out.append(f"<p><em>{clean(lead.group(1))}</em></p>")
    if meta:
        rows = "".join(f"<tr><td><strong>{clean(k)}</strong></td><td>{clean(v)}</td></tr>" for k, v in meta)
        out.append(f"<table><tbody>{rows}</tbody></table>")
    return "\n".join(out) + "\n<hr/>\n"


s = re.sub(r'<div class="cover[^"]*">(.*?)</div>\s*(?=<!-- =)', cover, s, flags=re.S)

# --- drop the hand-written TOC; pandoc generates a real, navigable one
s = re.sub(r'<div class="toc">.*?</div>\s*(?=<!-- =)', "", s, flags=re.S)

# --- callout boxes -> blockquotes (the only visually distinct block Word gives us)
LABEL = {"warn": "PERHATIAN", "danger": "PENTING", "ok": "CATATAN"}


def box(m):
    kind = (m.group(1) or "").strip()
    body = m.group(2)
    tag = next((LABEL[k] for k in LABEL if k in kind), "INFO")
    body = re.sub(
        r'<span class="t">(.*?)</span>',
        lambda t: f"<p><strong>{tag} — {t.group(1)}</strong></p>",
        body,
        flags=re.S,
    )
    if tag not in body:
        body = f"<p><strong>{tag}</strong></p>" + body
    return f"<blockquote>{body}</blockquote>"


s = re.sub(r'<div class="box([^"]*)">(.*?)</div>(?=\s*(?:<(?!/div)|$))', box, s, flags=re.S)

# --- menu paths and role chips: keep them legible without CSS
s = re.sub(r'<span class="path">(.*?)</span>', r"<code>\1</code>", s, flags=re.S)
s = re.sub(r'<span class="chip[^"]*">(.*?)</span>', r"<strong>[\1]</strong> ", s, flags=re.S)

# --- figure captions -> italic paragraph under the image
s = re.sub(r"<figcaption>(.*?)</figcaption>", r"<p><em>\1</em></p>", s, flags=re.S)
s = re.sub(r"</?figure[^>]*>", "", s)

# --- chapter subtitle line
s = re.sub(r'<div class="sub">(.*?)</div>', r"<p><em>\1</em></p>", s, flags=re.S)

# --- strip the numbering span so headings read "1. Pendahuluan"
s = re.sub(r'<span class="num">(.*?)</span>', r"\1", s, flags=re.S)

open(dst, "w", encoding="utf-8").write(s)
print(f"{dst}: {len(s)} bytes")
