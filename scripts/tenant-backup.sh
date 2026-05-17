#!/usr/bin/env bash
# Trigger an on-demand backup for a tenant.
#
# Usage:
#   ./tenant-backup.sh <slug> [kind]
#
# kind ∈ manual (default) | daily | monthly | yearly

set -euo pipefail

slug="${1:?slug required}"
kind="${2:-manual}"

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

echo "→ Backing up tenant '$slug' (kind=$kind)..."
./scripts/orchestrator-call.sh POST "/v1/tenants/${slug}/backups" "{\"kind\":\"${kind}\"}" \
  | python3 -m json.tool
