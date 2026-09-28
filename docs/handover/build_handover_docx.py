# -*- coding: utf-8 -*-
"""Render the handover markdown sources in this directory as styled DOCX.

The markdown files are the source of truth — they are diffable in git and readable
without Word. This script only lays them out.

Usage:
    python docs/handover/build_handover_docx.py                 # all documents
    python docs/handover/build_handover_docx.py --doc levis     # one document
    python docs/handover/build_handover_docx.py --list

Supported markdown subset (the sources are written to stay inside it):
    #/##/###          headings
    paragraphs        with **bold** and `code` inline
    - item            bullets, one level of nesting via two leading spaces
    1. item           numbered lists — numbers are taken verbatim from the source,
                      because other documents cite them ("daftar JANGAN butir 28-32")
    | a | b |         pipe tables with a `| --- |` separator row
    > text            call-outs
    ```              fenced code blocks
"""

import argparse
import os
import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))

# ── Palette ─────────────────────────────────────────────────────────────────
# Navy is the shared Erajaya/EAL colour (see docs/awards/eaa-ealhub).
C_INK = RGBColor(0x1A, 0x23, 0x32)
C_NAVY = RGBColor(0x23, 0x30, 0x8F)
C_MUTED = RGBColor(0x5A, 0x64, 0x72)
C_CODE = RGBColor(0x1F, 0x2D, 0x3D)
HEAD_BG = "23308F"
QUOTE_BG = "FFF4E5"
CODE_BG = "F4F5F7"
ROW_BG = "F7F8FA"

MONO = "Consolas"
BODY = "Calibri"

# ── Documents ───────────────────────────────────────────────────────────────
DOCS = {
    "master": {
        "src": "00-master.md",
        "out": "Handover-EAL-Hub-Master.docx",
        "subtitle": "Dokumen master lintas vertikal",
    },
    "levis": {
        "src": "10-levis.md",
        "out": "Handover-Levis.docx",
        "subtitle": "PT ERA Busana Retailindo (Levi's) — retail, produksi",
    },
    "arkaaim": {
        "src": "20-arkaaim.md",
        "out": "Handover-ARKA-AIM.docx",
        "subtitle": "ARKA-AIM — drone rental & drone show, produksi",
    },
    "wms": {
        "src": "30-wms.md",
        "out": "Handover-WMS.docx",
        "subtitle": "Warehouse Management — rnd/demo, belum produksi",
    },
    "integrasi": {
        "src": "40-integrasi.md",
        "out": "Handover-Integrasi-PPOB-VAS-ESB.docx",
        "subtitle": "PPOB/PPS, VAS PMO, ESB/EFN, Denso",
    },
    "prospek": {
        "src": "50-prospek.md",
        "out": "Handover-Pipeline-Prospek.docx",
        "subtitle": "GentleWoman, Finance Portal, JDS, PPS/Odoo-Hub, EAA",
    },
}

INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")
NUM_RE = re.compile(r"^(\d+)\.\s+(.*)$")


# ── Low-level helpers ───────────────────────────────────────────────────────


def _shade(el, hexcolor):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hexcolor)
    el.append(shd)


def _left_bar(paragraph, hexcolor):
    pPr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "6")
    left.set(qn("w:color"), hexcolor)
    borders.append(left)
    pPr.append(borders)


def _field(paragraph, instr):
    """Insert a Word field (used for PAGE and TOC)."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    itxt = OxmlElement("w:instrText")
    itxt.set(qn("xml:space"), "preserve")
    itxt.text = instr
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, itxt, sep, end):
        run._r.append(node)
    return run


def _emit_runs(paragraph, text, base_size=10.5, color=C_INK):
    """Write text into a paragraph, honouring **bold** and `code`."""
    for chunk in INLINE_RE.split(text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**") and len(chunk) > 4:
            run = paragraph.add_run(chunk[2:-2])
            run.bold = True
        elif chunk.startswith("`") and chunk.endswith("`") and len(chunk) > 2:
            run = paragraph.add_run(chunk[1:-1])
            run.font.name = MONO
            run.font.size = Pt(base_size - 1)
            run.font.color.rgb = C_CODE
            continue
        else:
            run = paragraph.add_run(chunk)
        run.font.size = Pt(base_size)
        run.font.color.rgb = color
    return paragraph


# ── Document furniture ──────────────────────────────────────────────────────


def _styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = BODY
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12

    for name, size, color, before, after in (
        ("Heading 1", 16, C_NAVY, 18, 8),
        ("Heading 2", 12.5, C_INK, 12, 5),
        ("Heading 3", 11, C_INK, 10, 4),
    ):
        st = doc.styles[name]
        st.font.name = BODY
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = color
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True


def _page_setup(doc):
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.0)
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(1.8)


def _footer(doc, label):
    footer = doc.sections[-1].footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"{label}  ·  hal. ")
    run.font.size = Pt(8)
    run.font.color.rgb = C_MUTED
    _field(p, "PAGE")
    for run in p.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = C_MUTED


def _cover(doc, title, subtitle, asof):
    for _ in range(4):
        doc.add_paragraph()

    p = doc.add_paragraph()
    run = p.add_run("HANDOVER")
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = C_NAVY
    run.font.name = BODY

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(title)
    run.font.size = Pt(28)
    run.font.bold = True
    run.font.color.rgb = C_INK
    run.font.name = BODY

    p = doc.add_paragraph()
    run = p.add_run(subtitle)
    run.font.size = Pt(12.5)
    run.font.color.rgb = C_MUTED
    run.font.name = BODY

    doc.add_paragraph()
    p = doc.add_paragraph()
    _left_bar(p, HEAD_BG)
    p.paragraph_format.left_indent = Cm(0.35)
    _emit_runs(
        p,
        f"EAL-Hub · platform Odoo 19 multi-tenant Erajaya Active Lifestyle\nBerlaku per: **{asof}**",
        base_size=10.5,
        color=C_MUTED,
    )

    for _ in range(2):
        doc.add_paragraph()

    p = doc.add_paragraph()
    _emit_runs(
        p,
        "Daftar isi di halaman berikut kosong sampai Word memperbaruinya: buka dokumen, "
        "tekan `Ctrl+A` lalu `F9`, atau klik kanan daftar isi → *Update Field*.",
        base_size=9,
        color=C_MUTED,
    )

    doc.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)

    p = doc.add_paragraph()
    run = p.add_run("Daftar Isi")
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = C_NAVY
    run.font.name = BODY
    _field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
    doc.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)


# ── Block renderers ─────────────────────────────────────────────────────────


def _add_table(doc, rows):
    header, body = rows[0], rows[1:]
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    for idx, text in enumerate(header):
        cell = table.rows[0].cells[idx]
        cell.text = ""
        _shade(cell._tc.get_or_add_tcPr(), HEAD_BG)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(2)
        run = p.add_run(text.replace("**", ""))
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for r, row in enumerate(body):
        cells = table.add_row().cells
        for idx in range(len(header)):
            cell = cells[idx]
            cell.text = ""
            if r % 2 == 1:
                _shade(cell._tc.get_or_add_tcPr(), ROW_BG)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.space_before = Pt(2)
            _emit_runs(p, row[idx] if idx < len(row) else "", base_size=9)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def _add_code(doc, lines):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.4)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    _shade(p._p.get_or_add_pPr(), CODE_BG)
    for i, line in enumerate(lines):
        run = p.add_run(line)
        run.font.name = MONO
        run.font.size = Pt(8.5)
        run.font.color.rgb = C_CODE
        if i != len(lines) - 1:
            run.add_break()


def _add_quote(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.4)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(8)
    _shade(p._p.get_or_add_pPr(), QUOTE_BG)
    _left_bar(p, "F79009")
    _emit_runs(p, text)


def _add_bullet(doc, text, nested):
    p = doc.add_paragraph(style="List Bullet 2" if nested else "List Bullet")
    p.paragraph_format.space_after = Pt(2)
    _emit_runs(p, text)


def _add_numbered(doc, number, text, nested):
    """Numbers are literal so cross-document references stay true."""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(1.5 if nested else 1.0)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(f"{number}. ")
    run.bold = True
    run.font.size = Pt(10.5)
    run.font.color.rgb = C_INK
    _emit_runs(p, text)


# ── Markdown walk ───────────────────────────────────────────────────────────


def render(md_path, out_path, subtitle):
    with open(md_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    # The H1 and the "Berlaku per" line feed the cover, then are dropped.
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "Handover")
    asof = "28 September 2026"
    for line in lines[:12]:
        m = re.match(r"\*\*Berlaku per:\*\*\s*(.+)", line.strip())
        if m:
            asof = m.group(1).strip()

    doc = Document()
    _styles(doc)
    _page_setup(doc)
    _cover(doc, title, subtitle, asof)
    _footer(doc, title)

    i = 0
    seen_h1 = False
    n = len(lines)
    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # horizontal rule -> section break in the flow
        if re.fullmatch(r"-{3,}", stripped):
            i += 1
            continue

        # fenced code
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            if buf:
                _add_code(doc, buf)
            continue

        # headings
        if stripped.startswith("# "):
            if not seen_h1:
                seen_h1 = True  # already on the cover
                i += 1
                continue
            doc.add_heading(stripped[2:].strip(), level=1)
            i += 1
            continue
        if stripped.startswith("## "):
            doc.add_heading(stripped[3:].strip(), level=1)
            i += 1
            continue
        if stripped.startswith("### "):
            doc.add_heading(stripped[4:].strip(), level=2)
            i += 1
            continue

        # tables
        if stripped.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [""] * (width - len(r)) for r in rows]
                _add_table(doc, rows)
            continue

        # call-outs (consecutive > lines join into one paragraph)
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            _add_quote(doc, " ".join(b for b in buf if b))
            continue

        indent = len(raw) - len(raw.lstrip())
        nested = indent >= 2

        # bullets
        if stripped.startswith("- "):
            buf = [stripped[2:].strip()]
            i += 1
            while i < n and lines[i].strip() and not _is_block_start(lines[i]):
                buf.append(lines[i].strip())
                i += 1
            _add_bullet(doc, " ".join(buf), nested)
            continue

        # numbered
        m = NUM_RE.match(stripped)
        if m:
            buf = [m.group(2).strip()]
            i += 1
            while i < n and lines[i].strip() and not _is_block_start(lines[i]):
                buf.append(lines[i].strip())
                i += 1
            _add_numbered(doc, m.group(1), " ".join(buf), nested)
            continue

        # plain paragraph — join wrapped lines
        buf = [stripped]
        i += 1
        while i < n and lines[i].strip() and not _is_block_start(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        _emit_runs(p, " ".join(buf))

    doc.save(out_path)
    return out_path


def _is_block_start(line):
    s = line.strip()
    return bool(s.startswith(("#", "|", ">", "- ", "```")) or NUM_RE.match(s) or re.fullmatch(r"-{3,}", s))


# ── CLI ─────────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc", default="all", help="master|levis|arkaaim|wms|integrasi|prospek|all")
    ap.add_argument("--list", action="store_true", help="list the documents and exit")
    args = ap.parse_args()

    if args.list:
        for key, meta in DOCS.items():
            print(f"{key:10s} {meta['src']:16s} -> {meta['out']}")
        return 0

    keys = list(DOCS) if args.doc == "all" else [args.doc]
    unknown = [k for k in keys if k not in DOCS]
    if unknown:
        print(f"unknown document(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    failures = 0
    for key in keys:
        meta = DOCS[key]
        src = os.path.join(HERE, meta["src"])
        if not os.path.exists(src):
            print(f"SKIP  {key:10s} {meta['src']} belum ada", file=sys.stderr)
            failures += 1
            continue
        out = render(src, os.path.join(HERE, meta["out"]), meta["subtitle"])
        size = os.path.getsize(out) / 1024
        with open(src, encoding="utf-8") as fh:
            nlines = sum(1 for _ in fh)
        print(f"OK    {key:10s} {nlines:5d} baris md -> {os.path.basename(out)} ({size:.0f} KB)")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
