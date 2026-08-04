#!/usr/bin/env bash
# Daily pg_dump of every database on the platform, with daily/weekly/monthly
# rotation.
#
# Why this exists rather than the pg-backup-local container: that image loops a
# STATIC list from POSTGRES_DB, so a tenant provisioned tomorrow is silently
# absent from every backup taken after it. This enumerates the databases at run
# time, so new tenants are covered the first night they exist.
#
# Layout under $DEST:
#   daily/<YYYYMMDD>/<db>.dump      custom-format, restore with pg_restore
#   daily/<YYYYMMDD>/globals.sql    roles + tablespaces (pg_dumpall --globals-only)
#   weekly/<YYYY-Www>/              hardlinks to the Sunday run
#   monthly/<YYYY-MM>/              hardlinks to the 1st-of-month run
#   last-run.status                 one line per run, for monitoring
#
# Weekly/monthly are hardlinks into the daily tree on the same filesystem, so a
# retained week costs no extra space until its daily copy is pruned.
#
# Exits non-zero if any single database fails, after attempting all the others.

set -uo pipefail

ENV_FILE="${ENV_FILE:-/opt/odoo-platform/.env}"
DEST="${DEST:-/opt/db-backups/auto}"
PG_CONTAINER="${PG_CONTAINER:-odoo19-platform-postgres}"
KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_WEEKLY="${KEEP_WEEKLY:-8}"
KEEP_MONTHLY="${KEEP_MONTHLY:-6}"
MIN_FREE_MB="${MIN_FREE_MB:-5120}"
LOCK="/var/lock/odoo-pg-backup.lock"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "FATAL: $*"; exit 1; }

# Serialise runs: a slow night must not overlap the next one.
exec 9>"$LOCK" || die "cannot open $LOCK"
flock -n 9 || die "another run holds $LOCK — skipping"

[ -r "$ENV_FILE" ] || die "cannot read $ENV_FILE"
PGPASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
PGUSER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
PGUSER="${PGUSER:-odoo}"
[ -n "$PGPASSWORD" ] || die "POSTGRES_PASSWORD not found in $ENV_FILE"

docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true \
  || die "container $PG_CONTAINER is not running"

# Refuse to start a run we cannot finish; a half-written dump set is worse than
# a missed night, because it looks like a backup.
free_mb=$(df -Pm "$DEST" 2>/dev/null | awk 'NR==2{print $4}')
[ -z "$free_mb" ] && free_mb=$(df -Pm "$(dirname "$DEST")" | awk 'NR==2{print $4}')
[ "$free_mb" -ge "$MIN_FREE_MB" ] \
  || die "only ${free_mb}MB free under $DEST, need ${MIN_FREE_MB}MB"

psql_q() {
  docker exec -i -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
    psql -U "$PGUSER" -d postgres -At -c "$1"
}

stamp="$(date +%Y%m%d)"
day_dir="$DEST/daily/$stamp"
mkdir -p "$day_dir" || die "cannot create $day_dir"

mapfile -t dbs < <(psql_q "
  select datname from pg_database
  where not datistemplate and datallowconn
  order by datname;")
[ "${#dbs[@]}" -gt 0 ] || die "no databases returned"

log "backing up ${#dbs[@]} databases into $day_dir"

failed=()
for db in "${dbs[@]}"; do
  out="$day_dir/${db}.dump"
  if docker exec -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
       pg_dump -U "$PGUSER" -Fc -d "$db" > "$out.part" 2>/dev/null; then
    mv "$out.part" "$out"
    log "  ok   $db ($(du -h "$out" | cut -f1))"
  else
    rm -f "$out.part"
    failed+=("$db")
    log "  FAIL $db"
  fi
done

# Roles and tablespaces live outside any single database; without them a
# restore comes up with no owners.
if docker exec -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
     pg_dumpall -U "$PGUSER" --globals-only > "$day_dir/globals.sql.part" 2>/dev/null; then
  mv "$day_dir/globals.sql.part" "$day_dir/globals.sql"
else
  rm -f "$day_dir/globals.sql.part"
  failed+=("globals")
  log "  FAIL globals"
fi

# Promote to weekly / monthly by hardlink (same filesystem, so near-free).
promote() {
  local target="$1"
  mkdir -p "$target"
  cp -al "$day_dir/." "$target/" 2>/dev/null || cp -a "$day_dir/." "$target/"
  log "promoted to $target"
}
[ "$(date +%u)" = "7" ] && promote "$DEST/weekly/$(date +%G-W%V)"
[ "$(date +%d)" = "01" ] && promote "$DEST/monthly/$(date +%Y-%m)"

# Prune: keep the newest N directories in each tier (names sort chronologically).
prune() {
  local dir="$1" keep="$2" n
  [ -d "$dir" ] || return 0
  n=0
  while IFS= read -r d; do
    n=$((n + 1))
    if [ "$n" -gt "$keep" ]; then
      rm -rf "$d"
      log "pruned $d"
    fi
  done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d | sort -r)
}
prune "$DEST/daily"   "$KEEP_DAILY"
prune "$DEST/weekly"  "$KEEP_WEEKLY"
prune "$DEST/monthly" "$KEEP_MONTHLY"

total="$(du -sh "$DEST" 2>/dev/null | cut -f1)"
if [ "${#failed[@]}" -eq 0 ]; then
  log "OK ${#dbs[@]} databases, store now $total"
  echo "$(date -Is) OK dbs=${#dbs[@]} size=$total" > "$DEST/last-run.status"
  exit 0
fi
log "FAILED for: ${failed[*]}"
echo "$(date -Is) FAILED dbs=${#dbs[@]} failed=${failed[*]} size=$total" > "$DEST/last-run.status"
exit 1
