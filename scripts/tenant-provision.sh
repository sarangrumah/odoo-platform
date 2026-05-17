#!/usr/bin/env bash
# Provision a new tenant via the orchestrator API.
#
# Usage:
#   ./tenant-provision.sh <slug> "<display name>" [plan_tier] [contact_email]
#
# Example:
#   ./tenant-provision.sh acme "Acme Corporation" standard ops@acme.com

set -euo pipefail

slug="${1:?slug required}"
display_name="${2:?display name required}"
plan_tier="${3:-standard}"
contact_email="${4:-}"

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

body=$(python3 -c "
import json, sys
print(json.dumps({
    'slug': sys.argv[1],
    'display_name': sys.argv[2],
    'plan_tier': sys.argv[3],
    'contact_email': sys.argv[4] or None,
}))
" "$slug" "$display_name" "$plan_tier" "$contact_email")

echo "→ Provisioning tenant '$slug' ($display_name)..."
result=$(./scripts/orchestrator-call.sh POST /v1/tenants "$body")
echo "$result" | python3 -m json.tool

echo
echo "⚠ Capture the admin_password + fernet_key_dek above — they are not retrievable."
echo "Tenant URL: https://${slug}.platform.localhost"
echo "Hosts entry to add: 127.0.0.1   ${slug}.platform.localhost"
