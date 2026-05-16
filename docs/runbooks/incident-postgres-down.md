# Runbook: Postgres Down

Severity: **SEV-1**. Without Postgres, Odoo cannot serve any request.

## Contents

- [Detect](#detect)
- [Diagnose](#diagnose)
- [Mitigate](#mitigate)
- [Recover](#recover)
- [Postmortem template](#postmortem-template)

## Detect

You may be paged via:

- Prometheus alert `PostgresDown` (no scrape from `pg_exporter` for 2 min).
- Prometheus alert `OdooDbErrorBurst` (HTTP 500 rate from Odoo > 5/s).
- Synthetic check at `https://erp.local/web/health` returning 5xx.
- User reports in the on-call channel.

Quick triage from the bastion:

```bash
# Is the container running?
docker ps --filter name=postgres --format '{{.Status}}'

# Is the port open?
nc -zv postgres-host 5432

# Can Odoo reach it?
docker exec odoo-web psql "$ODOO_DB_DSN" -c '\l' | head
```

Alert routing config: `infra/prometheus/alerts/postgres.yml`.

## Diagnose

Work top-down:

1. **Process / container**:
   ```bash
   docker logs --tail=200 postgres
   systemctl status postgresql      # if bare-metal
   ```
   Look for: `FATAL`, `out of memory`, `could not write to file`, `panic`.

2. **Disk**:
   ```bash
   df -h /var/lib/postgresql
   du -sh /var/lib/postgresql/data/pg_wal
   ```
   PG halts writes when `pg_wal` partition is full.

3. **Replication lag** (if streaming standby exists):
   ```bash
   psql -h primary -c "SELECT * FROM pg_stat_replication;"
   ```

4. **Connections**:
   ```bash
   psql -c "SELECT count(*) FROM pg_stat_activity;"
   ```
   Compare to `max_connections` in `postgresql.conf`.

5. **System**:
   ```bash
   dmesg | tail -50           # OOM kill?
   journalctl -u docker -n 100
   uptime
   ```

Common root causes:

| Symptom | Likely cause | Next step |
| --- | --- | --- |
| `out of memory` in dmesg | Linux OOM killer killed postgres | See [Mitigate](#mitigate) -> bring up + raise limits |
| `No space left on device` | `pg_wal` full | Free disk, enable archive_command |
| `database system is in recovery mode` | Crashed; auto-recovery in progress | Wait, do not interrupt |
| `too many connections` | Connection leak (Odoo workers stuck) | Restart Odoo workers |
| Container missing | docker daemon restarted, container not autostart | `docker start postgres` |

## Mitigate

Goal: restore service quickly, even if root cause is not fully understood.

1. **Stop write amplification** by pausing Odoo workers:
   ```bash
   docker compose stop odoo-web odoo-cron
   ```
2. **Free disk** if applicable:
   ```bash
   # Archive old WAL files only after confirming a base backup exists
   ls -lh /var/lib/postgresql/data/pg_wal | head
   ```
3. **Raise memory limits** if OOM-killed (edit
   `infra/compose/docker-compose.yml`, `mem_limit`).
4. **Bring postgres back**:
   ```bash
   docker compose up -d postgres
   docker logs -f postgres
   ```
   Wait for `database system is ready to accept connections`.
5. **Bring Odoo back gradually**:
   ```bash
   docker compose up -d odoo-web
   # watch error rate before starting cron
   docker compose up -d odoo-cron
   ```

Communicate in the incident channel after each step.

## Recover

After service is stable:

1. **Confirm data integrity**:
   ```bash
   psql -c "SELECT pg_is_in_recovery();"
   psql -d erp_prod -c "SELECT count(*) FROM custom_pdp_audit_event;"
   ```
   The PDP audit count should be monotonically non-decreasing vs the last
   nightly metric.
2. **Verify the audit hash chain** manually:
   ```bash
   docker exec odoo-web odoo shell -d erp_prod \
     -c "env['pdp.audit.event'].verify_chain()"
   ```
3. **Re-enable scheduled jobs** that were paused.
4. **Run a fresh `pg_basebackup`** to a new file before the next business day.
5. **Update monitoring**:
   - Confirm `PostgresDown` alert resolved.
   - Confirm replication catching up if applicable.

Backup / restore reference: `docs/runbooks/backup-restore.md` (TBD).

## Postmortem template

Open within 24 hours of resolution. Save as
`docs/postmortems/YYYY-MM-DD-postgres-down.md`.

```markdown
# Postmortem: Postgres Down (YYYY-MM-DD)

## Summary
One-paragraph plain-language summary.

## Impact
- Duration: HH:MM to HH:MM (UTC+7), total Xh Ym.
- Users affected: ~N concurrent sessions, M tenants.
- Data loss: yes/no. If yes, scope.
- PDP audit chain: intact / broken (link verifier output).

## Timeline
- HH:MM Detected by ...
- HH:MM On-call acknowledged
- HH:MM Mitigation started
- HH:MM Service restored
- HH:MM All-clear

## Root cause
Why it happened. Five whys.

## What went well
- ...

## What went poorly
- ...

## Action items
- [ ] Owner: short description (due date)
- [ ] ...

## Appendix
- Logs:
- Dashboards:
- Related alerts:
```
