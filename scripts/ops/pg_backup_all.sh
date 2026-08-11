#!/usr/bin/env bash
# Daily pg_dump of every database on the platform, with daily/weekly/monthly
# rotation.
#
# Why this exists rather than the pg-backup-local container: that image loops a
# STATIC list from POSTGRES_DB, so a tenant provisioned tomorrow is silently
# absent from every backup taken after it. This enumerates the databases at run
# time, so new tenants are covered the first night they exist.
#
# A pg_dump is SQL only. Odoo keeps attachments as FILES on disk, so a database
# restored from a dump alone comes back attachment-blind: the ir.attachment rows
# are there, the bytes are not, and every download 404s. This script therefore
# also tars each database's filestore alongside its dump — a restore needs both
# halves. Verified 11-Aug-2026 after seven databases were dropped with dumps but
# no filestore: the data was recoverable, the attachments were not.
#
# Layout under $DEST:
#   daily/<YYYYMMDD>/<db>.dump            custom-format, restore with pg_restore
#   daily/<YYYYMMDD>/<db>-filestore.tgz   attachments; extract into the filestore root
#   daily/<YYYYMMDD>/globals.sql          roles + tablespaces (pg_dumpall --globals-only)
#   weekly/<YYYY-Www>/                    hardlinks to the Sunday run
#   monthly/<YYYY-MM>/                    hardlinks to the 1st-of-month run
#   last-run.status                       one line per run, for monitoring
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

# Filestore. The host directory is Odoo's data_dir; the per-database attachment
# trees live one level down, in its `filestore/` subdirectory — hence the word
# twice. Pointing one level too high tars sessions/ and addons/ and produces an
# archive that restores nothing useful.
FILESTORE_ROOT="${FILESTORE_ROOT:-/opt/odoo-platform/data/odoo-filestore/filestore}"
BACKUP_FILESTORE="${BACKUP_FILESTORE:-1}"
# Kept shorter than the dumps on purpose: attachments are ~1.1 GB per night
# against ~4 GB for the whole dump set, and they are far less likely to be
# wanted from an old night. Weekly/monthly promotions are hardlinks taken before
# this prune runs, so a promoted Sunday keeps its filestore for the full weekly
# retention even after the daily copy is trimmed.
KEEP_FILESTORE_DAILY="${KEEP_FILESTORE_DAILY:-7}"
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
need_mb="$MIN_FREE_MB"
# The filestore copy is a real, measurable addition to the night's write, so
# make the precheck account for it rather than discovering it half way through.
if [ "$BACKUP_FILESTORE" = "1" ] && [ -d "$FILESTORE_ROOT" ]; then
  fs_mb=$(du -sm "$FILESTORE_ROOT" 2>/dev/null | awk '{print $1}')
  [ -n "$fs_mb" ] && need_mb=$((need_mb + fs_mb))
fi
[ "$free_mb" -ge "$need_mb" ] \
  || die "only ${free_mb}MB free under $DEST, need ${need_mb}MB"

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

# Attachments. Without this the dumps above restore a database whose every
# attachment download 404s.
fs_done=0
fs_skipped=0
if [ "$BACKUP_FILESTORE" = "1" ]; then
  if [ -d "$FILESTORE_ROOT" ]; then
    log "archiving filestores from $FILESTORE_ROOT"
    for db in "${dbs[@]}"; do
      src="$FILESTORE_ROOT/$db"
      # A database with no attachments yet has no directory. That is normal, not
      # a failure — but count it, so "0 archived" cannot pass for success.
      if [ ! -d "$src" ]; then
        fs_skipped=$((fs_skipped + 1))
        continue
      fi
      out="$day_dir/${db}-filestore.tgz"
      rc=0
      # Odoo may write into the filestore while we read it. tar exits 1 for
      # "file changed as we read it" or a file vanishing mid-read, which for a
      # backup is a warning, not a failure: the archive is still valid and the
      # next run picks the file up. Only exit >= 2 is a real error.
      tar czf "$out.part" --warning=no-file-changed \
          -C "$FILESTORE_ROOT" "$db" 2>/dev/null || rc=$?
      if [ "$rc" -le 1 ] && [ -s "$out.part" ]; then
        mv "$out.part" "$out"
        fs_done=$((fs_done + 1))
        [ "$rc" -eq 1 ] && log "  ok   $db filestore ($(du -h "$out" | cut -f1)) — files changed during read"
        [ "$rc" -eq 0 ] && log "  ok   $db filestore ($(du -h "$out" | cut -f1))"
      else
        rm -f "$out.part"
        failed+=("$db:filestore")
        log "  FAIL $db filestore (tar rc=$rc)"
      fi
    done
    log "filestores: $fs_done archived, $fs_skipped without a directory"
  else
    # Misconfiguration, not an empty platform: fail loudly rather than write a
    # dump set that silently has no attachments in it.
    failed+=("filestore-root-missing")
    log "  FAIL filestore root $FILESTORE_ROOT does not exist"
  fi
fi

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

# Filestores age out of the daily tier earlier than the dumps do. This deletes
# only the *-filestore.tgz inside older daily directories; the dumps in them are
# untouched, and any weekly/monthly promotion still holds a hardlink to the
# archive, so the bytes survive there for that tier's full retention.
prune_filestore() {
  local dir="$DEST/daily" keep="$KEEP_FILESTORE_DAILY" n=0 removed=0 d found
  [ -d "$dir" ] || return 0
  while IFS= read -r d; do
    n=$((n + 1))
    [ "$n" -le "$keep" ] && continue
    found=$(find "$d" -maxdepth 1 -name '*-filestore.tgz' | wc -l)
    [ "$found" -eq 0 ] && continue
    find "$d" -maxdepth 1 -name '*-filestore.tgz' -delete 2>/dev/null
    removed=$((removed + found))
    log "pruned $found filestore archive(s) from $d"
  done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d | sort -r)
  [ "$removed" -gt 0 ] && log "filestore prune: $removed archive(s) removed beyond $keep day(s)"
  return 0
}
prune_filestore

total="$(du -sh "$DEST" 2>/dev/null | cut -f1)"
if [ "${#failed[@]}" -eq 0 ]; then
  log "OK ${#dbs[@]} databases, $fs_done filestores, store now $total"
  echo "$(date -Is) OK dbs=${#dbs[@]} filestores=$fs_done size=$total" > "$DEST/last-run.status"
  exit 0
fi
log "FAILED for: ${failed[*]}"
echo "$(date -Is) FAILED dbs=${#dbs[@]} filestores=$fs_done failed=${failed[*]} size=$total" > "$DEST/last-run.status"
exit 1
