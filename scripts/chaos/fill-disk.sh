#!/usr/bin/env bash
# Drill: fill the bind-mounted data volume to simulate disk pressure.
# Safe by default — caps fill at 200 MB and auto-deletes after 60s.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
. ./scripts/chaos/lib/_common.sh

SIZE_MB="${SIZE_MB:-200}"
HOLD_SECONDS="${HOLD_SECONDS:-60}"
TARGET_DIR="${TARGET_DIR:-./data/_chaos_fill}"

START=$(now_iso)
color_yellow "[$(now_iso)] DRILL: fill-disk (${SIZE_MB} MB for ${HOLD_SECONDS}s)"
mkdir -p "$TARGET_DIR"

color_red "Allocating ${SIZE_MB} MB at ${TARGET_DIR}/blob.bin..."
if command -v fallocate >/dev/null 2>&1; then
  fallocate -l "${SIZE_MB}M" "${TARGET_DIR}/blob.bin"
else
  dd if=/dev/zero of="${TARGET_DIR}/blob.bin" bs=1M count="${SIZE_MB}" status=none
fi

color_cyan "Disk usage now:"
df -h "$TARGET_DIR" | tail -n 1

color_cyan "Sleeping ${HOLD_SECONDS}s while era-predictor next tick fires..."
echo "(Watch http://localhost:${GRAFANA_PORT:-13000} → Capacity dashboard)"
sleep "$HOLD_SECONDS"

color_green "Cleaning up..."
rm -f "${TARGET_DIR}/blob.bin"
rmdir "$TARGET_DIR" 2>/dev/null || true

drill_report "fill-disk" "$START" "$(now_iso)" \
  "Verify Alertmanager fired host-disk warning + era-predictor surfaced shortened ETA."
