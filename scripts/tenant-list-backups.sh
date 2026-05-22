#!/usr/bin/env bash
set -euo pipefail
slug="${1:?slug required}"
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
./scripts/orchestrator-call.sh GET "/v1/tenants/${slug}/backups" | python3 -m json.tool
