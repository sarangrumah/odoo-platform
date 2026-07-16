"""Render the GentleWoman spec documents (TSD, Blueprint, FSD) markdown -> styled PDF.

Pipeline: pandoc (markdown -> standalone HTML with inlined Erajaya VAS CSS via -H header)
          -> headless Chrome (HTML -> PDF, no header/footer).

Run : python tools/build_gentlewoman_docs.py
Out : docs/projects/gentlewoman/GentleWoman-{TSD,Blueprint,FSD}-v1.0.pdf
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "gentlewoman"
STYLE = ROOT / "tools" / "gentlewoman-doc-style.html"

DOCUMENTS = [
    ("11-TSD-v1.0.md", "GentleWoman-TSD-v1.0", "GentleWoman TSD v1.0 — Technical Specification"),
    ("12-Blueprint-v1.0.md", "GentleWoman-Blueprint-v1.0", "GentleWoman Blueprint v1.0 — Solution Blueprint"),
    ("13-FSD-v1.0.md", "GentleWoman-FSD-v1.0", "GentleWoman FSD v1.0 — Functional Specification"),
]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "google-chrome",
    "chromium",
    "chromium-browser",
]


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists() or shutil.which(c):
            return c
    raise SystemExit("Chrome/Chromium not found — install it or edit CHROME_CANDIDATES.")


def find_pandoc() -> str:
    p = shutil.which("pandoc") or r"C:\Users\amade\AppData\Local\Pandoc\pandoc.exe"
    if not Path(p).exists() and not shutil.which("pandoc"):
        raise SystemExit("pandoc not found — install it (https://pandoc.org/installing.html).")
    return p


def main() -> None:
    pandoc = find_pandoc()
    chrome = find_chrome()
    profile = Path(tempfile.mkdtemp(prefix="gw-chrome-"))

    for md_name, out_stem, title in DOCUMENTS:
        md = DOCS / md_name
        if not md.exists():
            print(f"  SKIP {md_name} (missing)")
            continue
        html = DOCS / f"{out_stem}.html"
        pdf = DOCS / f"{out_stem}.pdf"

        print(f"pandoc  {md_name} -> {html.name}")
        subprocess.run(
            [pandoc, str(md), "-o", str(html), "--standalone",
             "--metadata", f"title={title}", "-H", str(STYLE)],
            check=True,
        )

        print(f"chrome  {html.name} -> {pdf.name}")
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={profile}", "--virtual-time-budget=10000",
             f"--print-to-pdf={pdf}", html.as_uri()],
            check=True,
        )
        size = pdf.stat().st_size if pdf.exists() else 0
        print(f"  OK {pdf.name}  {size:,} bytes")

    shutil.rmtree(profile, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
