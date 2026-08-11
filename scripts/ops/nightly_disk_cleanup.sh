#!/usr/bin/env bash
# Nightly disk reclamation for the platform host.
#
# Three things pile up unattended: buildkit cache, journald, and the filestore
# directories of databases that were dropped without anyone deleting their
# attachments. On 11-Aug-2026 that came to 36.5 GB / 0.9 GB / 1.0 GB -- the host
# was at 84% full.
#
#   nightly_disk_cleanup.sh [--dry-run]
#
# Runs from /etc/cron.d/odoo-platform-disk-cleanup at 03:30, after the 02:30
# pg_dump has finished. Logs to /var/log/odoo-platform-cleanup.log.
set -euo pipefail

PLATFORM=/opt/odoo-platform
FILESTORE=$PLATFORM/data/odoo-filestore/filestore
PG_CONTAINER=odoo19-platform-postgres
BUILD_CACHE_KEEP=168h   # a week, so an ordinary rebuild still hits cache
JOURNAL_KEEP=200M
ORPHAN_MIN_AGE_DAYS=7   # never touch a filestore younger than this
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then log "DRY-RUN: $*"; else "$@"; fi; }

free_mb() { df -Pm / | awk 'NR==2 {print $4}'; }
before=$(free_mb)
log "start (dry_run=$DRY_RUN, free ${before} MB)"

# 1. buildkit cache ---------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
    log "DRY-RUN: docker builder prune -af --filter until=$BUILD_CACHE_KEEP"
    docker builder prune -af --filter "until=$BUILD_CACHE_KEEP" --dry-run 2>/dev/null | tail -1 || true
else
    docker builder prune -af --filter "until=$BUILD_CACHE_KEEP" 2>&1 | tail -1 | sed 's/^/  /'
fi

# 2. journald ---------------------------------------------------------------
run journalctl --vacuum-size="$JOURNAL_KEEP" 2>&1 | tail -1 | sed 's/^/  /' || true

# 3. orphan filestores ------------------------------------------------------
# Guarded hard: this deletes attachments, and a filestore whose database is
# merely unreachable looks exactly like one whose database is gone. If the list
# cannot be read, or comes back implausibly short, do nothing at all.
pgpass=$(grep -m1 '^POSTGRES_PASSWORD=' "$PLATFORM/.env" 2>/dev/null | cut -d= -f2- || true)
dbs=$(docker exec -e PGPASSWORD="$pgpass" "$PG_CONTAINER" psql -U odoo -d postgres -tAc \
    "select datname from pg_database where datistemplate = false" 2>/dev/null || true)
db_count=$(printf '%s\n' "$dbs" | grep -c . || true)

if [ "$db_count" -lt 5 ]; then
    log "SKIP filestore sweep: database list returned $db_count entries (need >= 5)"
elif [ ! -d "$FILESTORE" ]; then
    log "SKIP filestore sweep: $FILESTORE does not exist"
else
    removed=0
    freed=0
    while IFS= read -r dir; do
        name=$(basename "$dir")
        printf '%s\n' "$dbs" | grep -qxF "$name" && continue
        # A filestore created minutes ago may belong to a database still being
        # restored, so age is the second guard behind the name check.
        if [ -n "$(find "$dir" -maxdepth 0 -mtime -"$ORPHAN_MIN_AGE_DAYS")" ]; then
            log "  keep $name (younger than $ORPHAN_MIN_AGE_DAYS days)"
            continue
        fi
        size=$(du -sm "$dir" | cut -f1)
        log "  orphan $name (${size} MB)"
        run rm -rf -- "$dir"
        removed=$((removed + 1))
        freed=$((freed + size))
    done < <(find "$FILESTORE" -mindepth 1 -maxdepth 1 -type d)
    log "filestore sweep: $removed orphan(s), ${freed} MB"
fi

after=$(free_mb)
log "done (free ${after} MB, reclaimed $((after - before)) MB)"
