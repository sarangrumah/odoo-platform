#!/usr/bin/env bash
# ============================================================
# OCA module vendor fetcher
# Downloads selected OCA modules from GitHub release tarballs
# and unpacks them into this directory.
# Usage: bash addons/_vendor/fetch_oca.sh
# ============================================================
set -euo pipefail

PRIMARY_BRANCH="${OCA_BRANCH:-19.0}"
FALLBACK_BRANCH="${OCA_FALLBACK_BRANCH:-18.0}"
DEST_DIR="$(cd "$(dirname "$0")" && pwd)"
TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

# repo => space-separated module names
declare -A REPOS=(
  [queue]="queue_job"
  [server-auth]="auth_jwt"
  [rest-framework]="base_rest base_rest_auth_jwt"
  [social]="mail_tracking"
  [partner-contact]="partner_firstname"
)

VENDORED_19=()
VENDORED_18=()
NOT_FOUND=()

fetch_repo() {
  local repo="$1"
  local branch="$2"
  local out="$TMP/$repo-$branch.tar.gz"
  local url="https://github.com/OCA/$repo/archive/refs/heads/$branch.tar.gz"
  echo ">>> Fetching $repo @ $branch"
  if curl -fsSL -o "$out" "$url"; then
    tar -xzf "$out" -C "$TMP"
    return 0
  fi
  return 1
}

vendor_module() {
  local repo="$1"
  local branch="$2"
  local mod="$3"
  local src="$TMP/$repo-$branch/$mod"
  if [ -d "$src" ]; then
    rm -rf "$DEST_DIR/$mod"
    cp -r "$src" "$DEST_DIR/"
    if [ "$branch" != "$PRIMARY_BRANCH" ]; then
      cat > "$DEST_DIR/$mod/NEEDS_19_PORT.md" <<EOF
# Needs Odoo 19 port

This module was vendored from OCA repository \`$repo\` branch **$branch** because
the \`$PRIMARY_BRANCH\` branch did not contain it (or the branch did not exist)
at the time of fetching.

Action required: review for Odoo 19 compatibility (manifest version, ORM API
changes, deprecated fields, security ir.model.access csv format, etc.) and
re-vendor from $PRIMARY_BRANCH once OCA publishes the port.

Source: https://github.com/OCA/$repo/tree/$branch/$mod
EOF
    fi
    return 0
  fi
  return 1
}

for repo in "${!REPOS[@]}"; do
  primary_ok=0
  fallback_ok=0

  if fetch_repo "$repo" "$PRIMARY_BRANCH"; then
    primary_ok=1
  fi

  for mod in ${REPOS[$repo]}; do
    if [ "$primary_ok" = "1" ] && vendor_module "$repo" "$PRIMARY_BRANCH" "$mod"; then
      echo "vendored ($PRIMARY_BRANCH): $mod"
      VENDORED_19+=("$mod")
      continue
    fi
    # Need fallback
    if [ "$fallback_ok" = "0" ]; then
      if fetch_repo "$repo" "$FALLBACK_BRANCH"; then
        fallback_ok=1
      fi
    fi
    if [ "$fallback_ok" = "1" ] && vendor_module "$repo" "$FALLBACK_BRANCH" "$mod"; then
      echo "vendored ($FALLBACK_BRANCH, NEEDS PORT): $mod"
      VENDORED_18+=("$mod")
    else
      echo "NOT FOUND: $mod (tried $PRIMARY_BRANCH and $FALLBACK_BRANCH)"
      NOT_FOUND+=("$mod")
    fi
  done
done

echo ""
echo "============================================================"
echo "Summary:"
echo "  Vendored from $PRIMARY_BRANCH : ${VENDORED_19[*]:-(none)}"
echo "  Vendored from $FALLBACK_BRANCH (needs port): ${VENDORED_18[*]:-(none)}"
echo "  Not found anywhere            : ${NOT_FOUND[*]:-(none)}"
echo "============================================================"
