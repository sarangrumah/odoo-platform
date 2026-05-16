# Runbook: Odoo OOM Kills

Severity: **SEV-2** by default, escalates to **SEV-1** if more than one worker
is killed within 5 minutes or longpolling is also down.

The Linux kernel kills Odoo workers when they exceed cgroup memory limits or
trigger global OOM. Symptoms: HTTP 502 from nginx, abrupt session loss,
`Out of memory: Killed process ... odoo` in `dmesg`.

## Contents

- [Detect](#detect)
- [Diagnose](#diagnose)
- [Mitigate](#mitigate)
- [Recover](#recover)
- [Postmortem template](#postmortem-template)

## Detect

Page sources:

- Prometheus alert `OdooWorkerOOM` (kernel OOM counter increment for odoo
  cgroup).
- Prometheus alert `Odoo5xxBurst` (nginx 502 rate > 2/s).
- Grafana panel "Odoo worker memory" (worker > 90% of `--limit-memory-hard`).
- User reports of "the page just reloaded and I got logged out".

Quick triage:

```bash
# Kernel kills in last hour
dmesg -T | grep -iE 'killed process .* (odoo|python3)' | tail -20

# Container memory pressure
docker stats --no-stream odoo-web odoo-cron

# Current worker count
docker exec odoo-web pgrep -af odoo | wc -l
```

## Diagnose

1. **Identify which worker type** was killed:
   - HTTP workers (`--workers=N`)
   - Cron workers (`--max-cron-threads`)
   - Longpolling / gevent (`odoo-gevent`)
2. **Check `--limit-memory-soft` and `--limit-memory-hard`** in
   `infra/compose/odoo.env`:
   - soft: worker self-recycles after request completes (graceful).
   - hard: worker killed immediately (this is what causes the 502).
3. **Find the offending request**:
   ```bash
   docker logs odoo-web --since 30m | \
     grep -E 'memory|werkzeug|long' | tail -50
   ```
   Look for `Memory limit (...) exceeded` log lines, then nearby request URL.
4. **Common culprits**:
   - Large XLSX export from a list view without pagination.
   - Report PDF rendering with huge dataset (wkhtmltopdf in-process).
   - ORM `read()` returning all rows from a large table due to missing
     domain.
   - Custom code holding refs in module-level caches.
5. **Cluster-wide signals**:
   - Postgres `pg_stat_activity` showing a single very long query - usually
     correlates.
   - `custom_pdp_audit_event` growth spike (someone enumerated PII).

## Mitigate

Pick the lightest action that restores service:

1. **Workers auto-respawn**; verify count returns to configured value:
   ```bash
   docker exec odoo-web pgrep -af odoo | wc -l
   ```
   If not, restart:
   ```bash
   docker compose restart odoo-web
   ```
2. **Throttle the offending endpoint** (if identified) via nginx
   `limit_req_zone` in `infra/nginx/odoo.conf`.
3. **Bump `--limit-memory-hard`** temporarily (e.g. from 2 GiB to 3 GiB) and
   restart workers. Track this as a deliberate over-ride to be revisited in
   the postmortem.
4. **Reduce worker count** if total RAM is the constraint (e.g. workers 8 ->
   6) to lower the OOM-killer pressure on the host.
5. **Kill the runaway query** in postgres if a specific PID is identified:
   ```bash
   psql -c "SELECT pg_cancel_backend(<pid>);"
   ```

Announce each mitigation in the incident channel.

## Recover

1. Verify error rate back to baseline in Grafana.
2. Verify queue jobs (`queue.job` model) have caught up.
3. Verify the PDP audit chain is intact:
   ```bash
   docker exec odoo-web odoo shell -d erp_prod \
     -c "env['pdp.audit.event'].verify_chain()"
   ```
   (Workers crashing mid-write should be fine because audit inserts are
   transactional, but verify to be safe.)
4. Re-enable any disabled scheduled actions.
5. Restore default `--limit-memory-hard` if temporarily bumped, only after
   the root cause is fixed.

## Postmortem template

Save as `docs/postmortems/YYYY-MM-DD-odoo-oom.md`.

```markdown
# Postmortem: Odoo Workers OOM-Killed (YYYY-MM-DD)

## Summary
One-paragraph plain-language summary, including which worker type and what
the user-visible impact was.

## Impact
- Duration: HH:MM to HH:MM (UTC+7), total Xh Ym.
- Workers killed: N (HTTP) / M (cron) / K (gevent).
- Failed requests: ~N (5xx).
- Tenants affected:
- PDP audit chain: intact / broken.

## Timeline
- HH:MM First OOM kill in dmesg
- HH:MM Page fired
- HH:MM On-call acknowledged
- HH:MM Offending request identified
- HH:MM Mitigation applied
- HH:MM Service restored
- HH:MM All-clear

## Root cause
Five whys. Identify whether it was code (unbounded read), data (table grew),
config (limits too low), or capacity (host RAM).

## What went well
- ...

## What went poorly
- ...

## Action items
- [ ] Add server-side pagination to <view> (owner, due date)
- [ ] Add Prometheus alert on <metric>
- [ ] Raise <limit> permanently after load test
- [ ] ...

## Appendix
- dmesg excerpt:
- Slow query log:
- Grafana snapshot URL:
```
