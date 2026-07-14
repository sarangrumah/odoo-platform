#!/usr/bin/env bash
# Clone an Odoo database (schema+data) and its filestore on the odoo19-platform stack.
# Usage: clone_db.sh <source_db> <dest_db>
# Uses CREATE DATABASE ... TEMPLATE (binary copy, like Odoo's own db duplicate) which
# avoids the unaccent/IMMUTABLE index errors that pg_dump|psql hits on Odoo schemas.
# Terminates the source DB's leftover idle connections first (Odoo workers only
# reconnect on a new request for that DB, so the clone window is safe).
set -euo pipefail

SRC="${1:?source db required}"
DST="${2:?dest db required}"

PG=odoo19-platform-postgres
ODOO=odoo19-platform-odoo

echo ">>> Cloning ${SRC} -> ${DST}"

# 1. Drop dest if present, terminate connections to BOTH dbs, create dest from SRC template.
docker exec "$PG" sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('${SRC}','${DST}') AND pid<>pg_backend_pid();
DROP DATABASE IF EXISTS \"${DST}\";
CREATE DATABASE \"${DST}\" TEMPLATE \"${SRC}\" OWNER \"\$POSTGRES_USER\";
SQL"

# 2. Clear the cloned queue_job rows. The TEMPLATE copy carries the source DB's
#    queue_job rows verbatim, so the clone shares their UUIDs. The queue_job
#    jobrunner keys pending jobs by UUID across ALL databases in one process; a
#    duplicate UUID trips `assert job.db_name == db_name` in channels.py and the
#    runner crash-loops, so background jobs never drain for ANY tenant. Wiping the
#    clone's queue (CASCADE also clears queue_job_lock + wizard rel tables) is the
#    permanent fix. Guarded so it is a no-op when queue_job is not installed.
echo ">>> clear cloned queue_job (prevents duplicate-UUID jobrunner crash-loop)"
docker exec "$PG" sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d \"${DST}\" -v ON_ERROR_STOP=1 -tAc \"DO \\\$\\\$ BEGIN IF to_regclass('public.queue_job') IS NOT NULL THEN TRUNCATE TABLE queue_job CASCADE; END IF; END \\\$\\\$;\""

# 3. Copy the filestore.
echo ">>> copy filestore"
docker exec "$ODOO" sh -c "rm -rf /var/lib/odoo/filestore/${DST}; if [ -d /var/lib/odoo/filestore/${SRC} ]; then cp -a /var/lib/odoo/filestore/${SRC} /var/lib/odoo/filestore/${DST}; fi"

# 4. Report size.
docker exec "$PG" sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -tAc \"SELECT 'size: '||pg_size_pretty(pg_database_size('${DST}'));\""
echo ">>> Done: ${DST}"
