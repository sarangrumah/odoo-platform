# Backup & Restore Runbook

Covers the production backup pipeline introduced in Phase 2D.3.

> **Read [Filestore is in no pg_dump](#filestore-is-in-no-pg_dump) before you drop
> or restore any database.** Every dump described in this runbook is SQL only. The
> attachments live somewhere else entirely and are not in any of them.

> **What actually runs on this host, measured 11-Aug-2026.** The two sidecars in
> the Topology table below are **not running** and `data/backups/` does not exist.
> The live nightly job is `scripts/ops/pg_backup_all.sh` at 02:30 (`/etc/cron.d/
> odoo-pg-backup`), writing `/opt/db-backups/auto/daily/<YYYYMMDD>/<db>.dump` in
> pg_dump custom format with 14/8/6 daily/weekly/monthly rotation, verified each
> morning at 07:05 by `pg_backup_check.sh`. It enumerates databases at run time,
> which is why it replaced the sidecar — that image loops a static list, so a
> tenant provisioned tomorrow is silently absent from every later backup. The rest
> of this runbook (restore drill, integrity checks, failure table) still applies;
> only the paths differ.

## Topology

Two sidecars run side-by-side in prod (both defined in `docker-compose.prod.yml`):

| Service | Image | Target | Purpose |
|---|---|---|---|
| `pg-backup-local` | `prodrigestivill/postgres-backup-local:16` | `./data/backups/` (host bind-mount) | Fast on-box restore; never leaves the host |
| `pg-backup-s3` | `eeshugerman/postgres-backup-s3:16` | S3 / S3-compatible bucket (`${S3_BUCKET}/${S3_PREFIX}/`) | Offsite, disaster-recovery |

Both run on the same `SCHEDULE` cron (default `@daily`). The local copy is a
safety net so you can restore even if S3 credentials or connectivity break.

## Where backups land

### Local
* Host: `./data/backups/`
* Layout (managed by the prodrigestivill image):
  ```
  data/backups/daily/<dbname>/<dbname>-YYYYMMDD-HHMMSS.sql.gz
  data/backups/weekly/...
  data/backups/monthly/...
  data/backups/last/<dbname>/<dbname>-latest.sql.gz
  ```

### S3
* Bucket / prefix: `s3://${S3_BUCKET}/${S3_PREFIX}/`
* Object name: `<timestamp>.sql.gz` (one rolled dump per scheduled run; older
  than `BACKUP_KEEP_DAYS` are pruned by the sidecar).
* Endpoint: `${S3_ENDPOINT}` (empty = real AWS; set for R2/MinIO/Wasabi).

## RTO / RPO assumptions

| Metric | Target | Notes |
|---|---|---|
| RPO (data loss tolerance) | 24h | With default `SCHEDULE=@daily`. Lower by tightening cron (e.g. `0 */6 * * *` for 6h) |
| RTO from local backup | ~15 min for a single DB ≤ 10 GB | Limited by `gunzip + psql` throughput |
| RTO from S3 | local time + S3 fetch time | Add bandwidth for object size; budget +15 min for ≤ 10 GB on a 100 Mbps link |
| Backup window | ~`pg_dumpall` runtime, single connection, `-Z9` gzip CPU-bound | Schedule during low traffic |

These are **assumptions** — measure them in your real environment and update
this table after each DR drill.

## Triggering an immediate backup

```bash
make backup-now
```

This shells into the running `pg-backup-s3` container and invokes its
backup script directly. Falls back to `pg-backup-local` if the S3 sidecar
is not running.

For a manual host-side dump (independent of the sidecars):

```bash
make backup            # writes data/backups/dumpall-<ts>.sql.gz
```

## Testing restore (dev / pre-prod drill)

Always restore into a **temp DB**, never directly over the live one.

```bash
# 1. Pick a backup file
ls -1 data/backups/daily/postgres/ | tail

# 2. Spin up a throwaway DB in the running postgres container
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres \
  psql -U "${POSTGRES_USER}" -c 'CREATE DATABASE restore_test;'

# 3. Restore the chosen dump into it
gunzip -c data/backups/daily/postgres/postgres-20260516-020000.sql.gz \
  | docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
      psql -U "${POSTGRES_USER}" -d restore_test

# 4. Smoke-test (row counts, last update timestamp, your critical tables)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres \
  psql -U "${POSTGRES_USER}" -d restore_test \
  -c "SELECT count(*) FROM res_users; SELECT max(create_date) FROM res_users;"

# 5. Drop the temp DB
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres \
  psql -U "${POSTGRES_USER}" -c 'DROP DATABASE restore_test;'
```

To restore an **S3** object first pull it down:

```bash
aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}/2026-05-16T02:00:00.sql.gz" \
  data/backups/restore-from-s3.sql.gz \
  --endpoint-url "${S3_ENDPOINT:-https://s3.${S3_REGION}.amazonaws.com}"
```

Then continue from step 3 above.

## Cron tuning

`SCHEDULE` uses Go-style cron (the underlying image supports both standard
5-field and `@daily` / `@hourly` shortcuts):

| Goal | `SCHEDULE` |
|---|---|
| Daily 02:00 (default) | `@daily` |
| Every 6 hours | `0 */6 * * *` |
| Hourly | `@hourly` |
| Workdays 22:00 | `0 22 * * 1-5` |

Tighter cadence reduces RPO but raises CPU/IO load during the dump. Run a
trial during peak hours before committing.

## Verifying backup integrity

### sha256 quick-check (catches truncation / silent corruption)

```bash
# Compute hash at backup time (one-shot, can be added to a wrapper)
for f in data/backups/daily/*/*.sql.gz; do
  sha256sum "$f" >> data/backups/sha256sums.txt
done

# Later, re-verify
sha256sum -c data/backups/sha256sums.txt
```

### gzip / format integrity

```bash
gunzip -t data/backups/daily/postgres/postgres-20260516-020000.sql.gz \
  && echo "gzip OK"
```

### Restore-to-temp-DB (the only real proof)

Schedule a monthly drill that performs the steps under "Testing restore"
end-to-end on the most recent backup. Capture row counts of your top-5
business tables and diff against the live DB.

## Filestore is in no pg_dump

`pg_dump` dumps the database. Odoo keeps every attachment as a **file on disk**,
outside Postgres: PDFs, product images, e-Faktur evidence, imported workbooks,
anything a user ever uploaded. None of it is in any dump this runbook describes.

Restore a database from a dump alone and it comes back structurally complete and
attachment-blind: the `ir.attachment` rows are there, the bytes they point at are
not, and every download 404s.

**The path, including the trap:**

```
/opt/odoo-platform/data/odoo-filestore/filestore/<db>/
```

Note the doubled `filestore`. The host directory `data/odoo-filestore` is mounted
at `/var/lib/odoo` in the containers, and Odoo puts its filestore in a `filestore`
subdirectory of that — so `data/odoo-filestore/<db>` (the path you would guess)
does not exist for any database, and a `tar` or an `ls` against it reports nothing
rather than failing. Check inside the container if you want the unambiguous
answer: `docker exec odoo19-platform-odoo-mgmt ls /var/lib/odoo/filestore`.

### Two ways to capture it

**Odoo's own backup** — the database manager's Backup produces a zip containing
`dump.sql` *and* the filestore, and its Restore puts both back. This is the only
one-step round trip. It is reached over an SSH tunnel, not from the domain:
`docs/runbooks/database-manager-access.md`.

**Or archive it alongside the dump**, which is what to do when you are dumping
from the CLI anyway:

```bash
db=prd_levis_AP
pg_dump -Fc -d "$db" -f "${db}_pre_drop_$(date +%Y%m%d).dump"
tar czf "${db}-filestore_$(date +%Y%m%d).tgz" \
  -C /opt/odoo-platform/data/odoo-filestore/filestore "$db"
```

Verify the archive is not empty before you rely on it — count real files, not tar
entries, or directory placeholders will flatter the number:

```bash
tar tzf <archive>.tgz | grep -v '/$' | wc -l
```

### Dropping a database gives you a 7-day window, not forever

Since 11-Aug-2026 a cron at 03:30 (`/etc/cron.d/odoo-platform-disk-cleanup`,
`/usr/local/sbin/odoo-platform-disk-cleanup.sh`) sweeps **orphan filestores** —
directories whose database no longer exists. Its first run reclaimed 60 folders
and 1.0 GB left by long-gone databases.

So a dropped database's attachments survive on disk for a while, but not
indefinitely. Its guards, read from the script:

| guard | effect |
|---|---|
| `ORPHAN_MIN_AGE_DAYS=7` | a filestore directory with mtime under 7 days is skipped |
| database list < 5 entries | sweep aborts entirely — a failed `psql` must never read as "everything is orphaned" |
| filestore path missing | sweep skipped |

**Archive at the moment you drop, not afterwards.** The seven days are a safety
margin against a race, not a retention policy to plan around. Dropping through
Odoo's database manager removes the filestore immediately anyway — that path does
not wait for the sweep at all.

Worked example, 11-Aug-2026: seven databases were dropped deliberately
(`prd_detail_levis`, `prd_levis_AP`, `trn_arkaaim_begbal`, `demo`, three `tst_*`).
Their dumps *and* a single 93 MB filestore archive were taken first, into
`/opt/odoo-platform/backups/dropped-20260811/`, so all seven can come back whole.
The nightly dumps in `/opt/db-backups/auto/daily/20260811` also exist and would
have restored the data — but not one attachment.

## Failure scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `pg-backup-s3` crashloops | empty/invalid `S3_*` creds | Re-check `.env`; `docker compose logs pg-backup-s3` |
| Backups stop appearing in S3 | bucket lifecycle policy expiring objects | Adjust `BACKUP_KEEP_DAYS` vs bucket policy |
| Local disk fills | `BACKUP_KEEP_DAYS` too high | Lower retention or move to S3-only |
| Restore hangs at `COPY` | role mismatch (user that owns DB ≠ restoring user) | Restore as superuser or grant ownership first |
| `pg_dump` version mismatch | client/server version skew | Sidecar image must match Postgres major; we pin `:16` |
| Restored DB works but every attachment 404s | filestore was never captured — it is in no dump | See [Filestore is in no pg_dump](#filestore-is-in-no-pg_dump); recover the directory or re-restore from an Odoo-format zip |
| `pg_restore: command not found` on the host | it is only inside the postgres container | `docker exec odoo19-platform-postgres pg_restore -l <file>` (bind-mount or copy the dump in first) |
