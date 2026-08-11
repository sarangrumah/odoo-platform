#!/usr/bin/env bash
# Verify that last night's pg_backup_all.sh run actually produced a usable
# backup set, and shout on WhatsApp if it did not.
#
# Why a separate checker: pg_backup_all.sh exiting non-zero only helps if
# somebody reads the log. The failure mode that matters is the SILENT one --
# cron not firing at all, the disk filling, a dump truncated mid-write. Those
# leave a green-looking tree and no error anywhere. This job asserts the
# properties a restore actually needs, from outside the backup script.
#
# Checks, in order of how badly they bite:
#   1. last-run.status is from today and says OK
#   2. today's daily directory exists
#   3. no *.part files (a .part is a dump that was cut off)
#   4. every live database has a dump -- catches a tenant provisioned into a
#      blind spot, which is exactly how the old container failed
#   5. globals.sql is non-empty (no roles = no usable restore)
#   6. one dump passes `pg_restore -l` (catches truncation/corruption)
#
# Alerting is deliberately noisy-on-failure and silent-on-success, with one
# exception: on HEARTBEAT_DOM it sends an OK message too, so that silence
# stays meaningful. An alert channel nobody ever hears from is indistinguishable
# from a broken one.

set -uo pipefail

ENV_FILE="${ENV_FILE:-/opt/odoo-platform/.env}"
DEST="${DEST:-/opt/db-backups/auto}"
PG_CONTAINER="${PG_CONTAINER:-odoo19-platform-postgres}"
BAILEYS_URL="${BAILEYS_URL:-http://127.0.0.1:18088}"
ALERT_FILE="$DEST/ALERT"
HEARTBEAT_DOM="${HEARTBEAT_DOM:-01}"
PROBE_DB="${PROBE_DB:-prd_levis_begbal}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

today="$(date +%Y%m%d)"
day_dir="$DEST/daily/$today"
problems=()

# ---- checks -----------------------------------------------------------------

status_line="$(cat "$DEST/last-run.status" 2>/dev/null)"
if [ -z "$status_line" ]; then
  problems+=("last-run.status tidak ada — cron backup sepertinya tidak jalan sama sekali")
else
  case "$status_line" in
    "$(date +%Y-%m-%d)"*) ;;
    *) problems+=("last-run.status masih bertanggal lama: ${status_line:0:40}") ;;
  esac
  case "$status_line" in
    *" OK "*) ;;
    *) problems+=("status bukan OK: ${status_line:0:120}") ;;
  esac
fi

if [ ! -d "$day_dir" ]; then
  problems+=("direktori $day_dir tidak ada")
else
  parts="$(find "$day_dir" -name '*.part' | wc -l)"
  [ "$parts" -eq 0 ] || problems+=("$parts dump terputus (file .part)")

  if [ ! -s "$day_dir/globals.sql" ]; then
    problems+=("globals.sql kosong/tidak ada — restore akan kehilangan semua role")
  fi

  # Every live database must have a dump. Compare sets, not counts: an extra
  # dump for a dropped DB is harmless, a missing one is not.
  PGPASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  PGUSER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  PGUSER="${PGUSER:-odoo}"
  # A database created after the run began cannot have a dump, and saying so every
  # morning is how an alert stops being read: scratch databases are routine here
  # (`scratch_clearing` on 11-Aug, `tst_rolemgr` the same afternoon, both gone
  # within hours). The age comes from base/<oid>/PG_VERSION, which is written once
  # at CREATE DATABASE and never touched again -- so this needs no naming
  # convention and cannot be fooled by a tenant that happens to be called scratch.
  #
  # Run start = the oldest dump in today's set. Anything newer than that is
  # excluded; anything older is a real miss.
  if [ -n "$PGPASSWORD" ]; then
    live="$(docker exec -i -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
      psql -U "$PGUSER" -d postgres -At -F'|' -c \
      "select datname, extract(epoch from (pg_stat_file('base/'||oid||'/PG_VERSION')).modification)::bigint
         from pg_database where not datistemplate and datallowconn order by 1;" 2>/dev/null)"
    if [ -z "$live" ]; then
      # pg_stat_file needs superuser; fall back to the plain list rather than
      # skipping the check, and accept that new databases will be reported.
      live="$(docker exec -i -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
        psql -U "$PGUSER" -d postgres -At -c \
        "select datname||'|0' from pg_database where not datistemplate and datallowconn order by 1;" 2>/dev/null)"
    fi
    if [ -z "$live" ]; then
      problems+=("tidak bisa membaca daftar database dari $PG_CONTAINER")
    else
      run_start="$(find "$day_dir" -name '*.dump' -printf '%T@\n' 2>/dev/null \
                   | sort -n | head -1 | cut -d. -f1)"
      run_start="${run_start:-0}"
      missing=()
      skipped=()
      while IFS='|' read -r db born; do
        [ -n "$db" ] || continue
        [ -s "$day_dir/$db.dump" ] && continue
        if [ "${born:-0}" -gt "$run_start" ] && [ "$run_start" -gt 0 ]; then
          skipped+=("$db")
        else
          missing+=("$db")
        fi
      done <<< "$live"
      # Never silent: an exclusion nobody can see is how a real gap hides.
      [ "${#skipped[@]}" -eq 0 ] || log "abaikan (dibuat setelah backup jalan): ${skipped[*]}"
      [ "${#missing[@]}" -eq 0 ] || problems+=("DB tanpa dump: ${missing[*]}")
    fi
  else
    problems+=("tidak bisa membaca POSTGRES_PASSWORD dari $ENV_FILE")
  fi

  # Integrity probe on one large dump. pg_restore -l reads the whole TOC, so a
  # truncated or corrupt archive fails here rather than during a real restore.
  #
  # It must run in a throwaway container with the directory BIND-MOUNTED. The
  # host has no pg_restore, and piping the archive into `docker exec` does not
  # work: a custom-format archive needs to seek, and on a pipe pg_restore
  # silently lists nothing -- which would read as "corrupt" on every good dump.
  if [ -s "$day_dir/$PROBE_DB.dump" ]; then
    pg_image="$(docker inspect "$PG_CONTAINER" -f '{{.Config.Image}}' 2>/dev/null)"
    pg_image="${pg_image:-postgres:16-alpine}"
    n="$(docker run --rm -v "$day_dir:/b:ro" "$pg_image" \
           pg_restore -l "/b/$PROBE_DB.dump" 2>/dev/null | grep -c 'TABLE DATA')"
    if [ "${n:-0}" -lt 1 ]; then
      problems+=("$PROBE_DB.dump gagal dibaca pg_restore — arsip rusak")
    fi
  fi
fi

# ---- alerting ---------------------------------------------------------------

# Never raises: a delivery problem must not hide the verdict, which is why the
# verdict is also written to disk and to the log unconditionally.
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
  code="$(curl -s -m 20 -o /tmp/pg_backup_check_wa.$$ -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $secret" -H 'Content-Type: application/json' \
    --data-raw "$(printf '{"to":"%s","type":"text","text":%s}' "$to" \
                  "$(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")" \
    "$BAILEYS_URL/sessions/$session/messages")"
  if [ "$code" = "200" ]; then
    log "WA: terkirim ke $to"
    rm -f /tmp/pg_backup_check_wa.$$
    return 0
  fi
  log "WA: GAGAL http=$code body=$(head -c 200 /tmp/pg_backup_check_wa.$$ 2>/dev/null)"
  rm -f /tmp/pg_backup_check_wa.$$
  return 1
}

# WhatsApp is one channel, and it has already failed silently: the session was
# logged out on 4-Aug-2026, so the 11-Aug alert reached nobody and sat unread in
# $ALERT_FILE. Every verdict now also goes to syslog, and a failing verdict leaves
# the ALERT file that /etc/update-motd.d/99-odoo-backup-alert prints on each SSH
# login. Delivery stays best-effort; the record does not.
notify() {
  local level="$1" text="$2"
  logger -t odoo-backup -p "daemon.$level" -- "$(printf '%s' "$text" | tr '\n' ' ')" 2>/dev/null || true
  send_wa "$text"
}

host="$(hostname -s)"
if [ "${#problems[@]}" -eq 0 ]; then
  size="$(du -sh "$day_dir" 2>/dev/null | cut -f1)"
  ndumps="$(find "$day_dir" -name '*.dump' | wc -l)"
  log "OK — $ndumps dump, $size, $day_dir"
  rm -f "$ALERT_FILE"
  logger -t odoo-backup -p daemon.info -- "OK $ndumps dump, $size, $day_dir" 2>/dev/null || true
  if [ "$(date +%d)" = "$HEARTBEAT_DOM" ]; then
    send_wa "✅ Backup Odoo ($host) sehat.
$ndumps database, $size, $(date '+%d-%b-%Y').
Pesan bulanan — kalau tanggal 1 berikutnya tidak ada kabar, kanal alert-nya yang mati."
  fi
  exit 0
fi

msg="⚠️ BACKUP ODOO BERMASALAH ($host)
$(date '+%d-%b-%Y %H:%M')

$(printf '• %s\n' "${problems[@]}")

Cek: /var/log/odoo-pg-backup.log"

log "MASALAH:"
printf '  - %s\n' "${problems[@]}"
printf '%s\n' "$msg" > "$ALERT_FILE"

if ! notify err "$msg"; then
  # WhatsApp is down too. syslog and the ALERT file already carry the verdict, and
  # the login banner reads that file -- so record that nobody was messaged, and
  # say where the alert did land.
  log "PERINGATAN: WhatsApp GAGAL — alert ada di syslog (odoo-backup), $ALERT_FILE, dan banner login"
  printf '\n[alert WhatsApp GAGAL terkirim %s — dibaca lewat banner login / journalctl -t odoo-backup]\n' \
    "$(date -Is)" >> "$ALERT_FILE"
fi
exit 1
