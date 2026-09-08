#!/usr/bin/env bash
# Copy the client-facing artefacts to the download share.
#
# Target is a subdirectory, not the share root: the root already holds ~40 loose
# files and adding three more makes it worse.
#
# Only the three deliverables go out. catalog.json, catalog.md, catalog-audit.md
# and gaps.yaml stay in git — they are working files, not deliverables.

set -euo pipefail
cd "$(dirname "$0")"

DEST=/srv/sftp-share/files/katalog-fitur-platform
OWNER=sftpshare
GROUP=sftpusers

FILES=(
  "dist/Katalog_Fitur_Platform_Odoo_Erajaya.pdf"
  "dist/Katalog_Fitur_Platform_Odoo_Erajaya.docx"
  "dist/Matriks_Fitur_Platform_Odoo_Erajaya.xlsx"
)

for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f — run ./build.sh first" >&2; exit 1; }
done

mkdir -p "$DEST"
chown "$OWNER:$GROUP" "$DEST" 2>/dev/null || true
chmod 0755 "$DEST"

for f in "${FILES[@]}"; do
  install -o "$OWNER" -g "$GROUP" -m 0644 "$f" "$DEST/"
  echo "  $(basename "$f")"
done

( cd "$DEST" && sha256sum ./*.pdf ./*.docx ./*.xlsx > SHA256SUMS.txt )
chown "$OWNER:$GROUP" "$DEST/SHA256SUMS.txt"
chmod 0644 "$DEST/SHA256SUMS.txt"

echo
echo "Published to $DEST"
ls -lh "$DEST"
