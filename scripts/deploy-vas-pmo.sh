#!/usr/bin/env bash
# =============================================================================
# VAS PMO deploy — run this ON THE VPS, from the repo root.
#
# Deliberately NOT fully automatic. Two steps in this deploy touch things that are
# shared with other tenants, and both are gated behind an explicit flag:
#
#   * restarting the `odoo` container (required for new Python modules to register
#     their controllers) briefly interrupts EVERY tenant on that container,
#     including live ones. --restart-odoo, in a maintenance window.
#   * changing DBFILTER affects how every tenant resolves. This script only tells
#     you what to change; it never edits it for you.
#
# Usage:
#   scripts/deploy-vas-pmo.sh --db rnd_vas_pmo --host vaspmo.example.com [flags]
#
# Flags:
#   --db NAME            target database (default: $VAS_PMO_TENANT_DB or rnd_vas_pmo)
#   --host FQDN          public hostname; also the value for ODOO_TENANT_HOST
#   --restart-odoo       allow restarting the shared odoo container (needs a window)
#   --with-tests         run the vaspmo test suite after install (recommended)
#   --rotate-secrets     generate fresh HMAC + JWT secrets and write them to .env
#   --dry-run            print what would happen, change nothing
# =============================================================================
set -euo pipefail

DB="${VAS_PMO_TENANT_DB:-rnd_vas_pmo}"
PUBLIC_HOST=""
RESTART_ODOO=0
WITH_TESTS=0
ROTATE=0
DRY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB="$2"; shift 2 ;;
    --host) PUBLIC_HOST="$2"; shift 2 ;;
    --restart-odoo) RESTART_ODOO=1; shift ;;
    --with-tests) WITH_TESTS=1; shift ;;
    --rotate-secrets) ROTATE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; exit 1; }
run()  { if [[ $DRY -eq 1 ]]; then printf '   (dry-run) %s\n' "$*"; else eval "$@"; fi; }

# ---------------------------------------------------------------- preflight
[[ -f docker-compose.yml && -d addons/ee_gap ]] || die "Run this from the platform repo root."
[[ -f .env ]] || die ".env is missing. Copy .env.example and fill it in first."
command -v docker >/dev/null || die "docker not found."

COMPOSE="docker compose"
$COMPOSE config --quiet >/dev/null 2>&1 || die "docker-compose.yml does not parse."

say "Target: db=$DB host=${PUBLIC_HOST:-<not set>} restart_odoo=$RESTART_ODOO dry_run=$DRY"

# Refuse the obvious foot-gun: deploying onto a database that is not ours.
case "$DB" in
  *vas_pmo*) : ;;
  *) die "Refusing: '$DB' does not look like a VAS PMO database. Pass --db explicitly if you are sure." ;;
esac

# ---------------------------------------------------------------- secrets
ensure_env() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" .env; then
    if [[ -n "$value" ]]; then
      run "python3 - <<'PY'
import pathlib, re
p = pathlib.Path('.env'); t = p.read_text(encoding='utf-8')
t = re.sub(r'^${key}=.*$', '${key}=${value}', t, flags=re.M)
p.write_text(t, encoding='utf-8')
PY"
    fi
  else
    run "printf '%s=%s\n' '${key}' '${value}' >> .env"
  fi
}

read_env() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//'; }

if [[ $ROTATE -eq 1 ]]; then
  say "Rotating VAS PMO secrets"
  NEW_HMAC=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
  NEW_JWT=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
  ensure_env VAS_PMO_HMAC_SECRET "$NEW_HMAC"
  ensure_env VAS_PMO_JWT_SECRET "$NEW_JWT"
  warn "Secrets rotated. Every logged-in session is invalidated once Odoo picks the new JWT key up."
fi

HMAC_SECRET="$(read_env VAS_PMO_HMAC_SECRET)"
JWT_SECRET="$(read_env VAS_PMO_JWT_SECRET)"
[[ -n "$HMAC_SECRET" ]] || die "VAS_PMO_HMAC_SECRET is empty. Re-run with --rotate-secrets."
[[ -n "$JWT_SECRET" ]] || die "VAS_PMO_JWT_SECRET is empty. Re-run with --rotate-secrets."

ensure_env VAS_PMO_TENANT_DB "$DB"
[[ -n "$PUBLIC_HOST" ]] && ensure_env VAS_PMO_TENANT_HOST "$PUBLIC_HOST"

# The BFF -> Odoo hop must ride the internal TLS terminator in production.
CURRENT_BASE="$(read_env VAS_PMO_ODOO_BASE_URL)"
if [[ "$CURRENT_BASE" != https://* ]]; then
  warn "VAS_PMO_ODOO_BASE_URL is '$CURRENT_BASE' — that is the local dev value."
  warn "Production should be https://nginx so the JWT never crosses the network in clear text."
  ensure_env VAS_PMO_ODOO_BASE_URL "https://nginx"
fi

# ---------------------------------------------------------------- database
say "Checking database $DB"
PGPW="$(read_env POSTGRES_PASSWORD)"
PGUSER="$(read_env POSTGRES_USER)"; PGUSER="${PGUSER:-odoo}"
DB_EXISTS=$($COMPOSE exec -T -e PGPASSWORD="$PGPW" postgres \
  psql -U "$PGUSER" -d postgres -tAc "select 1 from pg_database where datname='$DB'" 2>/dev/null || true)

if [[ "$DB_EXISTS" != "1" ]]; then
  say "Creating $DB and installing base"
  run "$COMPOSE exec -T odoo odoo -d '$DB' --without-demo=all --stop-after-init --no-http -i base"
else
  say "$DB already exists — will upgrade in place"
fi

# ---------------------------------------------------------------- modules
say "Installing / upgrading the VAS PMO module stack"
# custom_project_api pulls portfolio + cr + notify + auth_jwt through its dependencies.
if [[ "$DB_EXISTS" != "1" ]]; then
  run "$COMPOSE exec -T odoo odoo -d '$DB' --stop-after-init --no-http -i custom_project_api"
else
  run "$COMPOSE exec -T odoo odoo -d '$DB' --stop-after-init --no-http -u custom_project_api"
fi

if [[ $WITH_TESTS -eq 1 ]]; then
  say "Running the vaspmo test suite (44 tests)"
  # Two flags that are not optional here:
  #   --http-port  the shared 8069 is in use by the live server
  #   --db-filter  the HttpCase tests call auth='public' routes, and Odoo answers 404
  #                on those whenever more than one database matches the filter
  run "$COMPOSE exec -T odoo odoo -d '$DB' --db-filter='^${DB}\$' --stop-after-init \
        --http-port 18169 --test-enable --test-tags vaspmo \
        -u custom_project_portfolio,custom_project_cr,custom_project_notify,custom_project_api 2>&1 \
        | tail -5"
  warn "Read the tail above: it must say '0 failed, 0 error(s)'."
fi

# ---------------------------------------------------------------- wire secrets into Odoo
say "Wiring secrets and the BFF URL into $DB"
WIRE_PY=$(mktemp)
cat > "$WIRE_PY" <<'PY'
import os
env = self.env
p = env["ir.config_parameter"].sudo()
p.set_param("custom_core.secure_endpoint.vaspmo.secret", os.environ["HMAC_IN"])
env.ref("custom_project_api.jwt_validator_vaspmo").secret_key = os.environ["JWT_IN"]
p.set_param("custom_project_notify.bff_url", "http://vas-pmo:8080")
base = os.environ.get("PUBLIC_BASE", "")
if base:
    p.set_param("custom_project_notify.public_base_url", base)
env.cr.commit()
print("WIRED ok")
PY
PUBLIC_BASE=""
[[ -n "$PUBLIC_HOST" ]] && PUBLIC_BASE="https://$PUBLIC_HOST"
if [[ $DRY -eq 1 ]]; then
  printf '   (dry-run) would set HMAC secret, JWT key, bff_url and public_base_url in %s\n' "$DB"
else
  $COMPOSE exec -T -e HMAC_IN="$HMAC_SECRET" -e JWT_IN="$JWT_SECRET" -e PUBLIC_BASE="$PUBLIC_BASE" \
    odoo odoo shell -d "$DB" --no-http < "$WIRE_PY" 2>&1 | grep -E "WIRED|Error|Traceback" || true
fi
rm -f "$WIRE_PY"

# ---------------------------------------------------------------- front end
say "Building and starting the vas-pmo container"
run "$COMPOSE build vas-pmo"
run "$COMPOSE up -d vas-pmo"

# ---------------------------------------------------------------- odoo restart
if [[ $RESTART_ODOO -eq 1 ]]; then
  warn "Restarting the SHARED odoo container. Every tenant on it is interrupted for ~30s."
  run "$COMPOSE restart odoo"
else
  warn "Odoo was NOT restarted."
  warn "New Python modules only register their HTTP controllers after a restart, so"
  warn "/vaspmo/api/* will keep answering 404 until you run, in a maintenance window:"
  warn "    docker compose restart odoo"
fi

# ---------------------------------------------------------------- verify
say "Verifying"
sleep 8
if [[ $DRY -eq 0 ]]; then
  echo -n "  vas-pmo health: "
  $COMPOSE exec -T vas-pmo wget -qO- http://127.0.0.1:8080/api/health 2>&1 || echo "FAILED"
  echo
  echo -n "  unsigned /api/notify must be 401: "
  $COMPOSE exec -T vas-pmo wget -S -qO- --post-data '{}' \
    --header='Content-Type: application/json' http://127.0.0.1:8080/api/notify 2>&1 \
    | grep -o "HTTP/1.1 [0-9]*" | head -1 || true
fi

# ---------------------------------------------------------------- what's left
say "Remaining manual steps"
cat <<EOF
  1. DBFILTER — this script does not touch it. /vaspmo/api/* routes are auth='public',
     and Odoo answers 404 whenever more than one database matches the filter.
     Point the filter at the host, e.g. in .env:
         DBFILTER=^%h\$        (with PROXY_MODE=true and the proxy passing Host)
     and make ${PUBLIC_HOST:-<your host>} resolve to $DB.

  2. Reverse proxy — publish the app on 443. Caddy/nginx -> vas-pmo:8080.
     Do NOT expose 18110 to the public internet directly.

  3. WhatsApp — fill WAHUB_API_URL / WAHUB_APP_ID / WAHUB_APP_SECRET in .env, then
     test with NOTIFICATION_TEST_MODE=true and NOTIFICATION_TEST_PHONE set to one
     tester's number before letting it reach the team.

  4. Give the team access — each Odoo user needs a 'VAS PMO / *' group.
     Brand-side contacts get 'VAS PMO / Brand PIC' only; they will see just their
     own vertical's work.

  5. Verticals — fill legal_entity for the brands where it is still blank. Those
     blanks are deliberate, not missing data.
EOF

say "Done."
