# Runbook — Postgres Slow / High Latency

## Symptoms

- Grafana → Postgres dashboard shows query p99 > 5s
- Odoo log `WARNING ... slow query` lines accumulating
- User reports "list views taking 10+ seconds"
- Alertmanager: `postgres_query_p99_seconds > 5`

## Triage (5 min)

```bash
# 1. Are connections saturated?
docker compose exec postgres psql -U "$POSTGRES_USER" -c \
  "SELECT state, COUNT(*) FROM pg_stat_activity GROUP BY state;"
# Healthy: most rows in 'idle' or 'active' < 50; > 80 = pool exhaustion

# 2. Long-running queries?
docker compose exec postgres psql -U "$POSTGRES_USER" -c \
  "SELECT pid, now()-query_start AS duration, state, query
   FROM pg_stat_activity
   WHERE state='active' AND now()-query_start > interval '30 seconds'
   ORDER BY duration DESC LIMIT 10;"

# 3. Locks held > 30s?
docker compose exec postgres psql -U "$POSTGRES_USER" -c \
  "SELECT blocked.pid, blocked.query AS blocked_query,
          blocking.pid AS blocker, blocking.query AS blocker_query
   FROM pg_stat_activity blocked
   JOIN pg_locks bl ON bl.pid = blocked.pid AND NOT bl.granted
   JOIN pg_locks bg ON bg.locktype = bl.locktype AND bg.granted
   JOIN pg_stat_activity blocking ON blocking.pid = bg.pid
   WHERE blocked.pid <> blocking.pid;"

# 4. Cache hit ratio (target > 99%)
docker compose exec postgres psql -U "$POSTGRES_USER" -c \
  "SELECT sum(heap_blks_hit)::float / NULLIF(sum(heap_blks_hit + heap_blks_read), 0) AS cache_hit_ratio
   FROM pg_statio_user_tables;"
```

## Likely Causes + Fixes

### A. Audit log trigger contention

`pdp._audit_log_before_insert` re-reads the prior row + recomputes the
hash on every insert. Under heavy concurrent write load on the same
schema, this serialises inserts.

**Fix**: confirm with `pg_stat_activity` that the blocker is an INSERT
on `pdp.audit_log`. If so:

- Short term: increase Odoo workers (more parallelism) but be aware
  the bottleneck shifts to chain contention.
- Long term: migrate to a per-tenant chain rather than per-DB single
  chain (planned Phase 3 work).

### B. Missing index on a custom field

```sql
-- Find seq scans on large tables
SELECT relname, seq_scan, idx_scan, n_live_tup
  FROM pg_stat_user_tables
 WHERE seq_scan > idx_scan * 10
   AND n_live_tup > 10000
 ORDER BY seq_scan DESC;
```

Add an index via a small migration in the relevant module.

### C. Bloat after large delete/anonymise

```sql
-- Bloat estimate
SELECT schemaname, relname, n_dead_tup, n_live_tup,
       round(n_dead_tup::numeric / NULLIF(n_live_tup, 0), 2) AS dead_ratio
  FROM pg_stat_user_tables
 WHERE n_dead_tup > 10000
 ORDER BY dead_ratio DESC;
```

If dead ratio > 0.2 on a hot table, run `VACUUM (ANALYZE, VERBOSE) <table>`
in a low-traffic window.

### D. Connection pool exhaustion

If `pg_stat_activity` shows > 80% of `max_connections` busy, raise the
limit (`max_connections = 300` in postgres command override) and/or
add pgbouncer (planned).

## Escalation

- > 30 min sustained p99 > 5s on multiple tenants → declare **S2** per
  DR runbook and start incident channel.
- If query plan looks wrong on a recently-updated module → roll back
  the module: `make update MODULE=<broken_module> DB=<db>` with the
  previous commit checked out.
