#!/usr/bin/env bash
# ============================================================
# dev-bootstrap.sh
# Idempotent local-dev bootstrap:
#   1. Generates self-signed TLS cert for nginx if missing.
#   2. Generates an age keypair for SOPS if missing.
#   3. Prints the age public key and instructions for .sops.yaml.
#
# Usage:  bash scripts/dev-bootstrap.sh
# Or via: make dev-bootstrap
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CERT_DIR="${REPO_ROOT}/nginx/certs"
CERT_FILE="${CERT_DIR}/server.crt"
KEY_FILE="${CERT_DIR}/server.key"

# Age key path: respect XDG, fallback to $HOME/.config
AGE_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/sops/age"
AGE_KEY_FILE="${AGE_DIR}/keys.txt"

color() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
info()  { color "1;34" "[INFO ] $*"; }
ok()    { color "1;32" "[ OK  ] $*"; }
warn()  { color "1;33" "[WARN ] $*"; }
err()   { color "1;31" "[ERR  ] $*" >&2; }

require_bin() {
  local bin="$1" hint="$2"
  if ! command -v "${bin}" >/dev/null 2>&1; then
    err "Required binary '${bin}' not found in PATH."
    err "  Hint: ${hint}"
    exit 1
  fi
}

# ----------------------------------------------------------------
# Step 1 — self-signed nginx cert
# ----------------------------------------------------------------
bootstrap_cert() {
  info "Checking nginx self-signed TLS cert..."
  mkdir -p "${CERT_DIR}"

  if [[ -s "${CERT_FILE}" && -s "${KEY_FILE}" ]]; then
    ok "TLS cert already exists at ${CERT_FILE} (skipping)."
    return 0
  fi

  require_bin openssl "Install OpenSSL (apt install openssl / brew install openssl / Git-Bash bundles it)."

  info "Generating self-signed cert (CN=localhost, 4096-bit RSA, 365 days)..."
  openssl req -x509 -nodes -days 365 -newkey rsa:4096 \
    -subj "/CN=localhost" \
    -keyout "${KEY_FILE}" \
    -out "${CERT_FILE}" \
    >/dev/null 2>&1

  chmod 600 "${KEY_FILE}"
  chmod 644 "${CERT_FILE}"
  ok "Wrote ${CERT_FILE} and ${KEY_FILE}."
}

# ----------------------------------------------------------------
# Step 2 — age keypair for SOPS
# ----------------------------------------------------------------
bootstrap_age() {
  info "Checking age keypair for SOPS..."
  mkdir -p "${AGE_DIR}"

  if [[ -s "${AGE_KEY_FILE}" ]]; then
    ok "Age key already exists at ${AGE_KEY_FILE} (skipping)."
  else
    require_bin age-keygen "Install age (apt install age / brew install age / https://github.com/FiloSottile/age/releases)."
    info "Generating age keypair at ${AGE_KEY_FILE}..."
    age-keygen -o "${AGE_KEY_FILE}" 2>/dev/null
    chmod 600 "${AGE_KEY_FILE}"
    ok "Wrote ${AGE_KEY_FILE}."
  fi

  # Always extract & display public key (idempotent — no file mutation).
  local pubkey
  pubkey="$(grep -E '^# public key:' "${AGE_KEY_FILE}" | head -n1 | sed 's/^# public key: //')"
  if [[ -z "${pubkey}" ]]; then
    warn "Could not parse public key from ${AGE_KEY_FILE}."
    warn "Inspect the file manually; the public key line starts with '# public key:'."
    return 0
  fi

  cat <<EOF

================================================================
  Age public key (paste this into .sops.yaml):

    ${pubkey}

  Edit ${REPO_ROOT}/.sops.yaml and set the 'age:' field under
  creation_rules to this value (replace the placeholder).

  Example:
    creation_rules:
      - path_regex: \\.secrets\\.enc\\.yaml\$
        age: >-
          ${pubkey}

  Then export the env vars for the Makefile helpers:
    export SOPS_AGE_RECIPIENT='${pubkey}'
    export SOPS_AGE_KEY_FILE='${AGE_KEY_FILE}'
================================================================

EOF
}

main() {
  info "Running dev-bootstrap (repo: ${REPO_ROOT})"
  bootstrap_cert
  bootstrap_age
  ok "dev-bootstrap complete."
}

main "$@"
