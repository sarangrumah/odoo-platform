# Backup & Restore Runbook

Covers the production backup pipeline introduced in Phase 2D.3.

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

## Failure scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `pg-backup-s3` crashloops | empty/invalid `S3_*` creds | Re-check `.env`; `docker compose logs pg-backup-s3` |
| Backups stop appearing in S3 | bucket lifecycle policy expiring objects | Adjust `BACKUP_KEEP_DAYS` vs bucket policy |
| Local disk fills | `BACKUP_KEEP_DAYS` too high | Lower retention or move to S3-only |
| Restore hangs at `COPY` | role mismatch (user that owns DB ≠ restoring user) | Restore as superuser or grant ownership first |
| `pg_dump` version mismatch | client/server version skew | Sidecar image must match Postgres major; we pin `:16` |
