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

# 3. Copy the filestore.
echo ">>> copy filestore"
docker exec "$ODOO" sh -c "rm -rf /var/lib/odoo/filestore/${DST}; if [ -d /var/lib/odoo/filestore/${SRC} ]; then cp -a /var/lib/odoo/filestore/${SRC} /var/lib/odoo/filestore/${DST}; fi"

# 4. Report size.
docker exec "$PG" sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -tAc \"SELECT 'size: '||pg_size_pretty(pg_database_size('${DST}'));\""
echo ">>> Done: ${DST}"
