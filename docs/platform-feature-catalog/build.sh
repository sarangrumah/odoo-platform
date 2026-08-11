#!/usr/bin/env bash
# Build every artefact of the Erajaya feature catalog from the repo itself.
#
#   ./build.sh            full build + verification
#   ./build.sh --no-pdf   skip Chromium (fast loop while editing prose)
#
# Order matters: catalog.json is the single source of truth, and everything
# downstream reads only that file.

set -euo pipefail
cd "$(dirname "$0")"

SKIP_PDF=0
[[ "${1:-}" == "--no-pdf" ]] && SKIP_PDF=1

DOCX_TITLE="Katalog Fitur Platform Odoo — Erajaya Group"

echo "==> 1/8  scan addons/ → catalog.json (+ audit)"
python3 build_catalog_json.py --audit

echo "==> 2/8  data-derived diagrams"
python3 build_diagrams.py

echo "==> 3/8  catalog.md"
python3 render_md.py

echo "==> 4/8  printable HTML"
python3 render_html.py

echo "==> 5/8  XLSX feature matrix"
python3 build_xlsx.py

if [[ $SKIP_PDF -eq 0 ]]; then
  echo "==> 6/8  PDF"
  node build_pdf.mjs

  echo "==> 7/8  DOCX"
  node rasterize_svg.mjs
  python3 render_html.py --img png --out src/catalog-png.html >/dev/null
  python3 to_docx.py src/catalog-png.html src/catalog-docx.html >/dev/null
  # Word cannot render SVG reliably, hence the PNG pass above.
  pandoc src/catalog-docx.html -f html -t docx \
    -o dist/Katalog_Fitur_Platform_Odoo_Erajaya.docx \
    --toc --toc-depth=2 --resource-path=src \
    --metadata title="$DOCX_TITLE"
  echo "    dist/Katalog_Fitur_Platform_Odoo_Erajaya.docx"
else
  echo "==> 6-7/8  PDF + DOCX skipped (--no-pdf)"
fi

echo "==> 8/8  verify"
python3 verify.py $([[ $SKIP_PDF -eq 1 ]] && echo --skip-pdf)
