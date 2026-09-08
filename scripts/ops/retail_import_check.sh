#!/usr/bin/env bash
# Verify that the retail import pipeline actually moved data last night, and shout
# on WhatsApp if it did not.
#
# Why a separate checker: every surface the pipeline owns can look healthy while it
# is dead. On 10-Aug-2026 one POS session left open in the UI made every X24 sales
# import raise; the log rows stayed 'running' (the state is committed BEFORE the
# handler runs), the next hourly poll saw a duplicate hash and archived the file,
# and the feed reported last_status=ok. Files kept arriving, the archive kept
# filling, cron stayed green -- and prd_levis_begbal did not book a single sale for
# eight days. Nobody noticed until somebody asked.
#
# So this asserts the properties that matter from OUTSIDE Odoo, in the order they
# bite:
#   1. no import stuck in 'running' (a dead run that also blocks re-import)
#   2. no import that ended 'failed' in the last day
#   3. no active feed reporting last_status=error
#   4. the daily feeds (X24/X70D/X31) actually imported something in the last 26h
#   5. POS sales are not stale: a database that sold in the last 30 days must have
#      sold in the last 48h
#
# Check 5 is the one that would have caught August on day one: it measures the
# OUTCOME (rows in pos_order), not the machinery's opinion of itself. Its blind
# spot is deliberate -- a database with no sales at all for 30 days is treated as
# dormant rather than broken, otherwise every frozen demo tenant alerts forever.
#
# Read-only: it opens no transaction that writes, and touches no file but its own
# ALERT marker.

set -uo pipefail

ENV_FILE="${ENV_FILE:-/opt/odoo-platform/.env}"
PG_CONTAINER="${PG_CONTAINER:-odoo19-platform-postgres}"
BAILEYS_URL="${BAILEYS_URL:-http://127.0.0.1:18088}"
ALERT_FILE="${ALERT_FILE:-/opt/db-backups/auto/ALERT-retail-import}"
STUCK_HOURS="${STUCK_HOURS:-6}"
FEED_SILENT_HOURS="${FEED_SILENT_HOURS:-26}"
SALES_STALE_HOURS="${SALES_STALE_HOURS:-48}"
# Feeds expected to deliver EVERY night. Matched against retail_import_feed.file_glob;
# the occasional feeds (X101 master, CoA, X20) must not alert when they stay quiet.
DAILY_GLOBS="${DAILY_GLOBS:-X24%,X70D%,X31%}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

PGPASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
PGUSER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
PGUSER="${PGUSER:-odoo}"

problems=()

psql_q() { # db, sql -> tab-separated rows on stdout
  docker exec -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
    psql -U "$PGUSER" -d "$1" -Atq -c "$2" 2>/dev/null
}

if [ -z "$PGPASSWORD" ]; then
  problems+=("tidak bisa membaca POSTGRES_PASSWORD dari $ENV_FILE")
else
  dbs="$(psql_q postgres "SELECT datname FROM pg_database WHERE NOT datistemplate AND datallowconn ORDER BY 1")"
  for db in $dbs; do
    has="$(psql_q "$db" "SELECT to_regclass('public.retail_import_feed') IS NOT NULL")"
    [ "$has" = "t" ] || continue

    # Only databases that actually RUN the pipeline, not the many clones that merely
    # carry its configuration. Every restored copy of a tenant keeps the feeds, the
    # profiles and x24_post_enabled, so those are useless as a discriminator -- an
    # alert that lists rnd_/tst_/demo_ every morning is an alert nobody reads.
    #
    # Two signals, either one qualifies:
    #   - an ACTIVE mailbox: the nightly mail ingest runs here (prd_levis_begbal)
    #   - a feed that imported something in the last 7 days: covers SFTP-only tenants
    #     and lets a new tenant enrol itself simply by working
    # The 7-day clause means a database broken for longer drops out of monitoring --
    # acceptable, because it can only get there after alerting every day for a week.
    monitored="$(psql_q "$db" "
      SELECT (SELECT count(*) FROM retail_import_mailbox WHERE active) > 0
          OR (SELECT count(*) FROM retail_import_log
               WHERE imported_at > now() - interval '7 days') > 0")"
    [ "$monitored" = "t" ] || continue

    globs="$(printf "'%s'," ${DAILY_GLOBS//,/ })"; globs="${globs%,}"

    while IFS= read -r line; do
      [ -n "$line" ] && problems+=("[$db] $line")
    done < <(psql_q "$db" "
      SELECT 'impor MACET: log ' || id || ' ' || coalesce(filename, '?')
             || ' masih running sejak ' || to_char(coalesce(started_at, imported_at), 'DD-Mon HH24:MI')
        FROM retail_import_log
       WHERE state = 'running'
         AND coalesce(started_at, imported_at) < now() - interval '${STUCK_HOURS} hours'
      UNION ALL
      SELECT 'impor GAGAL: log ' || id || ' ' || coalesce(filename, '?')
             || ' — ' || left(coalesce(error_message, ''), 100)
        FROM retail_import_log
       WHERE state = 'failed'
         AND coalesce(finished_at, imported_at) > now() - interval '24 hours'
      UNION ALL
      SELECT 'feed ERROR: ' || name || ' — ' || left(coalesce(last_message, ''), 100)
        FROM retail_import_feed
       WHERE active AND last_status = 'error'
      UNION ALL
      SELECT 'feed DIAM: ' || f.name || ' — impor terakhir '
             || coalesce(to_char(max(l.imported_at), 'DD-Mon HH24:MI'), 'tidak pernah')
        FROM retail_import_feed f
        LEFT JOIN retail_import_log l ON l.profile_id = f.profile_id
       WHERE f.active AND f.file_glob LIKE ANY (ARRAY[${globs}])
       GROUP BY f.id, f.name
      HAVING coalesce(max(l.imported_at), timestamp '1970-01-01')
             < now() - interval '${FEED_SILENT_HOURS} hours'
    ")

    # Outcome check: sales themselves, not the importer's opinion of them.
    if [ "$(psql_q "$db" "SELECT to_regclass('public.pos_order') IS NOT NULL")" = "t" ]; then
      stale="$(psql_q "$db" "
        SELECT 'PENJUALAN BASI: pos_order terakhir ' || to_char(max(date_order), 'DD-Mon-YYYY')
               || ' (' || count(*) || ' order dalam 30 hari)'
          FROM pos_order
         WHERE date_order > now() - interval '30 days'
        HAVING max(date_order) < now() - interval '${SALES_STALE_HOURS} hours'
      ")"
      [ -n "$stale" ] && problems+=("[$db] $stale")
    fi
  done
fi

# ---- alerting ---------------------------------------------------------------
# Same plumbing as pg_backup_check.sh: WhatsApp is best-effort (that session has
# gone logged-out before and the alert reached nobody), the RECORD is not -- every
# verdict goes to syslog, and a failing one leaves $ALERT_FILE behind.

send_wa() {
  local text="$1" secret to session code
  secret="$(grep -E '^BAILEYS_SHARED_SECRET=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  to="$(grep -E '^ALERT_WHATSAPP_TO=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="$(grep -E '^ALERT_WHATSAPP_SESSION=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="${session:-acct-2}"
  if [ -z "$secret" ] || [ -z "$to" ]; then
    log "WA: dilewati — BAILEYS_SHARED_SECRET atau ALERT_WHATSAPP_TO kosong"
    return 1
  fi
  code="$(curl -s -m 20 -o /tmp/retail_import_check_wa.$$ -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $secret" -H 'Content-Type: application/json' \
    --data-raw "$(printf '{"to":"%s","type":"text","text":%s}' "$to" \
                  "$(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")" \
    "$BAILEYS_URL/sessions/$session/messages")"
  if [ "$code" = "200" ]; then
    log "WA: terkirim ke $to"
    rm -f /tmp/retail_import_check_wa.$$
    return 0
  fi
  log "WA: GAGAL http=$code body=$(head -c 200 /tmp/retail_import_check_wa.$$ 2>/dev/null)"
  rm -f /tmp/retail_import_check_wa.$$
  return 1
}

host="$(hostname -s)"
if [ "${#problems[@]}" -eq 0 ]; then
  log "OK — tidak ada impor macet/gagal, feed harian jalan, penjualan segar"
  rm -f "$ALERT_FILE"
  logger -t odoo-retail-import -p daemon.info -- "OK retail import sehat" 2>/dev/null || true
  exit 0
fi

msg="⚠️ IMPOR RETAIL BERMASALAH ($host)
$(date '+%d-%b-%Y %H:%M')

$(printf '• %s\n' "${problems[@]}")

Cek: /var/log/odoo-retail-import-check.log
Session POS yang terbuka memblokir impor X24 — cek dulu:
  SELECT id, state FROM pos_session WHERE state <> 'closed';"

log "MASALAH:"
printf '  - %s\n' "${problems[@]}"
printf '%s\n' "$msg" > "$ALERT_FILE"
logger -t odoo-retail-import -p daemon.err -- "$(printf '%s' "$msg" | tr '\n' ' ')" 2>/dev/null || true
send_wa "$msg"
exit 1
