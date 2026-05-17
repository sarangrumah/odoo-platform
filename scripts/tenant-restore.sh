#!/usr/bin/env bash
# Restore a backup into a staging DB (non-destructive by default).
#
# Usage:
#   ./tenant-restore.sh <slug> <s3_key> [target_db]
#
# If target_db omitted, defaults to '<slug>_staging' on the server side.

set -euo pipefail

slug="${1:?slug required}"
s3_key="${2:?s3_key required (see ./tenant-list-backups.sh <slug>)}"
target_db="${3:-}"

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

body=$(python3 -c "
import json, sys
out = {'s3_key': sys.argv[1]}
if sys.argv[2]:
    out['target_db'] = sys.argv[2]
print(json.dumps(out))
" "$s3_key" "$target_db")

echo "→ Restoring '$slug' from $s3_key..."
./scripts/orchestrator-call.sh POST "/v1/tenants/${slug}/backups/restore" "$body" \
  | python3 -m json.tool
