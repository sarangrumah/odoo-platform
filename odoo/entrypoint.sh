#!/usr/bin/env bash
# ============================================================
# Odoo 19 Platform — entrypoint
# - Fail-fast on weak/missing secrets
# - Render odoo.conf from template via envsubst
# - Wait for postgres + redis
# - exec odoo (PID 1)
# ============================================================
set -euo pipefail

# Template lives in the read-only image at /usr/local/share/ so it stays
# accessible when /etc/odoo is mounted as a writable tmpfs in prod compose.
# Fallback to /etc/odoo for backward-compat with older images.
CONFIG_TMPL="/usr/local/share/odoo.conf.tmpl"
[ -r "$CONFIG_TMPL" ] || CONFIG_TMPL="/etc/odoo/odoo.conf.tmpl"
CONFIG_OUT="/etc/odoo/odoo.conf"

log() { echo "[entrypoint] $*" >&2; }
fail() { echo "[entrypoint] FATAL: $*" >&2; exit 1; }

# ----- Fail-fast on missing/weak secrets -----
require_var() {
  local name="$1"
  local val="${!name:-}"
  [[ -n "$val" ]] || fail "$name is empty — set it in .env"
  [[ "$val" == *"changeme"* ]] && fail "$name still contains 'changeme' — replace with real value"
  return 0
}

require_min_len() {
  local name="$1" minlen="$2"
  local val="${!name:-}"
  (( ${#val} >= minlen )) || fail "$name too short (need >= $minlen chars, got ${#val})"
}

require_var POSTGRES_PASSWORD
require_var ODOO_ADMIN_PASSWD
require_var REDIS_PASSWORD
require_var GATEWAY_SHARED_SECRET
require_min_len POSTGRES_PASSWORD 16
require_min_len ODOO_ADMIN_PASSWD 12
require_min_len REDIS_PASSWORD 16
require_min_len GATEWAY_SHARED_SECRET 32

# CORETAX_SERTEL_MASTER_KEY required only if compliance modules will be installed,
# but we still fail-fast since the env file always sets it.
if [[ -n "${CORETAX_SERTEL_MASTER_KEY:-}" ]]; then
  require_var CORETAX_SERTEL_MASTER_KEY
fi

# ----- Render odoo.conf from template -----
[[ -f "$CONFIG_TMPL" ]] || fail "Missing config template at $CONFIG_TMPL"

# Defaults if unset (compose passes explicit, but safe fallback)
export WORKERS="${WORKERS:-0}"
export MAX_CRON_THREADS="${MAX_CRON_THREADS:-2}"
export LIST_DB="${LIST_DB:-False}"
export WITHOUT_DEMO="${WITHOUT_DEMO:-all}"
export LIMIT_TIME_CPU="${LIMIT_TIME_CPU:-600}"
export LIMIT_TIME_REAL="${LIMIT_TIME_REAL:-1200}"
export LIMIT_MEMORY_SOFT="${LIMIT_MEMORY_SOFT:-2147483648}"
export LIMIT_MEMORY_HARD="${LIMIT_MEMORY_HARD:-2684354560}"
export LOG_LEVEL="${LOG_LEVEL:-info}"
export PROXY_MODE="${PROXY_MODE:-True}"
export DBFILTER="${DBFILTER:-^.*\$}"
export SERVER_WIDE_MODULES="${SERVER_WIDE_MODULES:-base,web}"
export HOST="${HOST:-postgres}"
export PORT="${PORT:-5432}"
export USER="${USER:-odoo}"
export PASSWORD="${PASSWORD:-${POSTGRES_PASSWORD}}"

# envsubst will replace ${VAR}; escape literal $ as $$ in template
envsubst < "$CONFIG_TMPL" > "$CONFIG_OUT"
chmod 0640 "$CONFIG_OUT" || true

log "Rendered config to $CONFIG_OUT"

# ----- Wait for postgres -----
log "Waiting for postgres at $HOST:$PORT ..."
for i in {1..60}; do
  if PGPASSWORD="$PASSWORD" psql -h "$HOST" -p "$PORT" -U "$USER" -d postgres -c 'SELECT 1' >/dev/null 2>&1; then
    log "postgres is ready"
    break
  fi
  sleep 2
  if (( i == 60 )); then fail "postgres not ready after 120s"; fi
done

# ----- Wait for redis (best-effort, non-fatal if redis-cli absent) -----
if command -v redis-cli >/dev/null 2>&1; then
  log "Pinging redis at ${REDIS_HOST:-redis}:${REDIS_PORT:-6379} ..."
  for i in {1..30}; do
    if redis-cli -h "${REDIS_HOST:-redis}" -p "${REDIS_PORT:-6379}" -a "${REDIS_PASSWORD}" --no-auth-warning ping 2>/dev/null | grep -q PONG; then
      log "redis is ready"
      break
    fi
    sleep 1
  done
fi

# ----- Verify addons paths readable -----
for path in /mnt/extra-addons/core /mnt/extra-addons/compliance /mnt/extra-addons/ee_gap /mnt/extra-addons/verticals; do
  [[ -d "$path" ]] || log "WARN: $path not present (may be intentional)"
done

# ----- Drop into odoo -----
log "Starting Odoo: $*"
exec "$@" --config="$CONFIG_OUT"
