#!/usr/bin/env bash
# Break duplicate queue_job UUIDs across databases before they stop the job
# runner for every tenant.
#
# WHY THIS EXISTS
# ---------------
# The queue_job runner registers ChannelJobs keyed by UUID across ALL databases
# at once. Two databases holding the same not-done UUID trip
#
#   File ".../queue_job/jobrunner/channels.py", line 1030, in notify
#     assert job.db_name == db_name  -> AssertionError
#
# and the runner then loops initialize_databases() forever: no background job
# runs in ANY database. It is silent — the assert is the only trace, the UI
# shows nothing, and healthchecks stay green. Diagnose by absence.
#
# The source is always the same: a database cloned with `CREATE DATABASE ...
# TEMPLATE` or the Odoo UI duplicate copies the queue verbatim, UUIDs included.
# `scripts/tenants/levis/clone_db.sh` and the orchestrator's restore path both
# truncate queue_job for exactly this reason, but a human cloning by hand
# bypasses both — which is how it recurred on 26-Jun, 06-Jul, 03-Aug and again
# on 10-Aug-2026. This job is the guard that does not depend on remembering.
#
# WHAT IT DOES
# ------------
# Regenerates the UUID on all but one holder of each duplicate, so every UUID
# survives in exactly one database. It never deletes a row and never touches
# job payloads: a queue_job UUID is an internal identity, not a reference —
# provided nothing else points at it, which is checked below.
#
# Which holder keeps the original is decided by RANK (production first), then
# by database name, so the run is deterministic and re-runnable.
#
# SAFETY RAILS
# ------------
# * Only NOT_DONE rows are rewritten. Those are the ones the runner loads and
#   therefore the only ones that can crash it. Duplicates among done/cancelled
#   rows are reported, not touched: they are harmless where they sit, and
#   rewriting thousands of historical rows nightly buys nothing. Set
#   FIX_DONE=1 to include them (the 03-Aug cleanup did this once, by hand).
# * A row whose UUID is referenced by another row — as `graph_uuid`, or inside
#   any `dependencies` payload — is SKIPPED and reported. Renaming it would
#   break the job graph. Every payload observed on this platform is
#   `{"depends_on": [], "reverse_depends_on": []}`, so this should never fire;
#   if it does, it wants a human.
# * Databases with no `queue_job` table (non-Odoo, or Odoo without the module)
#   are skipped silently.
# * Read-only unless it finds something. A clean platform writes one OK line.
#
# The runner needs no restart: it retries every 5s and self-heals within one
# cycle, logging "database connections ready".
#
# USAGE
#   scripts/ops/queue_job_uuid_guard.sh            # scan + fix
#   QJ_DRY=1 scripts/ops/queue_job_uuid_guard.sh   # scan only, change nothing
#
# Installed by scripts/ops/odoo-queue-job-guard.cron.

set -uo pipefail

ENV_FILE="${ENV_FILE:-/opt/odoo-platform/.env}"
PG_CONTAINER="${PG_CONTAINER:-odoo19-platform-postgres}"
STATUS_FILE="${STATUS_FILE:-/var/lib/odoo-ops/queue-job-uuid.status}"
JOURNAL="${JOURNAL:-/var/lib/odoo-ops/queue-job-uuid-changes.log}"
LOCK="/var/lock/odoo-queue-job-uuid.lock"
DRY="${QJ_DRY:-0}"
FIX_DONE="${FIX_DONE:-0}"
# Higher rank keeps the original UUID. Everything unmatched sorts last, so a
# scratch clone always yields to the database it was cloned from.
rank_of() {
  case "$1" in
    prd_*) echo 40 ;;
    trn_*) echo 30 ;;
    rnd_*) echo 20 ;;
    demo*) echo 10 ;;
    *)     echo 0  ;;
  esac
}

NOT_DONE_STATES="'wait_dependencies','pending','enqueued','started','failed'"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "FATAL: $*"; echo "$(date -Is) FAILED $*" > "$STATUS_FILE" 2>/dev/null; exit 1; }

mkdir -p "$(dirname "$STATUS_FILE")" 2>/dev/null

# Serialise: two runs rewriting the same collision would fight each other.
exec 9>"$LOCK" || die "cannot open $LOCK"
flock -n 9 || die "another run holds $LOCK — skipping"

[ -r "$ENV_FILE" ] || die "cannot read $ENV_FILE"
PGPASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
PGUSER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
PGUSER="${PGUSER:-odoo}"
[ -n "$PGPASSWORD" ] || die "POSTGRES_PASSWORD not found in $ENV_FILE"

psql_db() {  # psql_db <db> <sql>
  docker exec -i -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
    psql -U "$PGUSER" -d "$1" -At -c "$2" 2>/dev/null
}

docker inspect "$PG_CONTAINER" >/dev/null 2>&1 || die "container $PG_CONTAINER not running"

mapfile -t dbs < <(psql_db postgres "
  select datname from pg_database
   where datallowconn and not datistemplate and datname <> 'postgres'
   order by datname;")
[ "${#dbs[@]}" -gt 0 ] || die "no databases found"

# FIX_DONE widens the scan to every row; the default is the crash surface only.
if [ "$FIX_DONE" = "1" ]; then
  WHERE=""
else
  WHERE="where state in ($NOT_DONE_STATES)"
fi

# ---- collect ---------------------------------------------------------------
# One line per row: "<uuid> <db> <state>". Databases without queue_job produce
# nothing, which is what we want.
tmp="$(mktemp)"; trap 'rm -f "$tmp" "$tmp.dups"' EXIT
scanned=0
for db in "${dbs[@]}"; do
  has="$(psql_db "$db" "select to_regclass('public.queue_job') is not null")"
  [ "$has" = "t" ] || continue
  scanned=$((scanned + 1))
  psql_db "$db" "select uuid||' '||state from queue_job $WHERE" \
    | awk -v d="$db" 'NF {print $1, d, $2}' >> "$tmp"
done

awk '{print $1}' "$tmp" | sort | uniq -d > "$tmp.dups"
ndup="$(wc -l < "$tmp.dups" | tr -d ' ')"

if [ "$ndup" = "0" ]; then
  log "OK — no duplicate UUIDs across $scanned database(s) carrying queue_job"
  echo "$(date -Is) OK dbs=$scanned duplicates=0" > "$STATUS_FILE"
  exit 0
fi

log "found $ndup duplicated UUID(s) across $scanned database(s)"

# ---- fix -------------------------------------------------------------------
fixed=0; skipped=0
while read -r uuid; do
  [ -n "$uuid" ] || continue
  # Holders, best-ranked first; the head keeps the original.
  mapfile -t holders < <(grep -E "^$uuid " "$tmp" | awk '{print $2}' \
    | while read -r d; do printf '%s %s\n' "$(rank_of "$d")" "$d"; done \
    | sort -k1,1nr -k2,2 | awk '{print $2}')
  keep="${holders[0]}"
  log "  $uuid — holders: ${holders[*]}  (keeping it in $keep)"

  for db in "${holders[@]:1}"; do
    # Refuse to rename a UUID something else points at.
    refs="$(psql_db "$db" "
      select count(*) from queue_job
       where graph_uuid = '$uuid'
          or coalesce(dependencies::text,'') like '%$uuid%'")"
    if [ "${refs:-0}" != "0" ]; then
      log "    SKIP $db — $refs row(s) reference this uuid (graph/dependencies); needs a human"
      skipped=$((skipped + 1))
      continue
    fi
    if [ "$DRY" = "1" ]; then
      log "    DRY  $db — would regenerate"
      continue
    fi
    # head -1: psql prints the returned value AND the "UPDATE 1" command tag.
    newid="$(psql_db "$db" "
      update queue_job set uuid = gen_random_uuid()
       where uuid = '$uuid' returning uuid" | head -1)"
    if [ -n "$newid" ]; then
      log "    FIX  $db — $uuid -> $newid"
      printf '%s %s %s -> %s\n' "$(date -Is)" "$db" "$uuid" "$newid" >> "$JOURNAL"
      fixed=$((fixed + 1))
    else
      log "    WARN $db — update matched nothing (row changed under us?)"
      skipped=$((skipped + 1))
    fi
  done
done < "$tmp.dups"

# ---- report ----------------------------------------------------------------
if [ "$FIX_DONE" != "1" ]; then
  # Duplicates among done/cancelled cannot crash the runner today, but they are
  # a loaded gun: requeue one in two databases and the platform stops.
  # `x | read var` would set the variable in a subshell and lose it.
  done_dups="$(for db in "${dbs[@]}"; do
    has="$(psql_db "$db" "select to_regclass('public.queue_job') is not null")"
    [ "$has" = "t" ] || continue
    psql_db "$db" "select uuid from queue_job where state not in ($NOT_DONE_STATES)"
  done | sort | uniq -d | wc -l | tr -d ' ')"
  [ "${done_dups:-0}" != "0" ] && \
    log "note: $done_dups duplicate uuid(s) among done/cancelled rows — harmless now, rerun with FIX_DONE=1 to clear"
fi

if [ "$DRY" = "1" ]; then
  log "DRY RUN — nothing written"
  echo "$(date -Is) DRY duplicates=$ndup" > "$STATUS_FILE"
  exit 0
fi

log "done — $fixed row(s) re-uuided, $skipped skipped"
echo "$(date -Is) FIXED duplicates=$ndup fixed=$fixed skipped=$skipped" > "$STATUS_FILE"

# A fix is routine and stays in the log. A SKIP is not: it means a collision is
# still live, the runner is still looping, and no script can clear it. Say so
# out loud — copied from pg_backup_check.sh, same env keys.
if [ "$skipped" != "0" ]; then
  secret="$(grep -E '^BAILEYS_SHARED_SECRET=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  to="$(grep -E '^ALERT_WHATSAPP_TO=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="$(grep -E '^ALERT_WHATSAPP_SESSION=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="${session:-acct-2}"
  msg="⚠️ queue_job UUID bentrok dan TIDAK bisa diperbaiki otomatis ($(hostname -s))
$(date '+%d-%b-%Y %H:%M')

$skipped baris dilewati karena uuid-nya direferensi baris lain.
Selama ini belum dibereskan, job background berhenti untuk SEMUA tenant.

Cek: $JOURNAL dan /var/log/odoo-queue-job-guard.log"
  if [ -n "$secret" ] && [ -n "$to" ]; then
    code="$(curl -s -m 20 -o /dev/null -w '%{http_code}' \
      -X POST -H "Authorization: Bearer $secret" -H 'Content-Type: application/json' \
      --data-raw "$(printf '{"to":"%s","type":"text","text":%s}' "$to" \
        "$(printf '%s' "$msg" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")" \
      "${BAILEYS_URL:-http://127.0.0.1:18088}/sessions/$session/messages")"
    log "WA: http=$code"
  else
    log "WA: dilewati — BAILEYS_SHARED_SECRET atau ALERT_WHATSAPP_TO kosong"
  fi
  exit 1
fi
exit 0
