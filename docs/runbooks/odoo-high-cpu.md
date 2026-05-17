# Runbook — Odoo High CPU

## Symptoms

- Grafana → Odoo dashboard shows worker CPU sustained > 80%
- Alertmanager: `odoo_request_latency_p95 > 3000`
- User reports "everything is slow"

## Triage (5 min)

```bash
# 1. Per-worker CPU snapshot
docker compose exec odoo top -bn1 | head -20

# 2. Worker count + tuning
docker compose exec odoo cat /etc/odoo/odoo.conf | grep -E "^(workers|limit_)"
# WORKERS env in .env determines this; recommended: 2 * CPU + 1

# 3. Cron stuck?
docker compose exec odoo odoo --help | head -2  # noop check that container is responsive
docker compose exec postgres psql -U "$POSTGRES_USER" -d <tenant_db> -c \
  "SELECT * FROM ir_cron WHERE active AND lastcall < now() - interval '1 hour';"

# 4. Long requests in flight (last 5 min)
docker compose logs --tail=2000 odoo | grep -E "limit_time_real|werkzeug.*[0-9]{4} ms"
```

## Likely Causes + Fixes

### A. Insufficient workers

Symptom: requests queued, all workers busy. Fix: edit `.env` and bump:

```
WORKERS=8           # was 4
MAX_CRON_THREADS=2
```

Then `docker compose restart odoo`. Each worker uses ~250 MB; size
against host RAM.

### B. Long-running report rendering

QWeb PDF generation (wkhtmltopdf) is CPU-heavy and bypasses normal
request timeouts. Symptom: one worker stuck on a report endpoint.

Fix:

- Increase `LIMIT_TIME_REAL` in `.env` from default 1200 to 2400 for
  heavy consolidation reports.
- Move the report to async (XLSX export with apscheduler) — Phase 3 work.

### C. Inefficient compute field firing on bulk write

A frequent pattern: a recursive compute (e.g. `branch_root_id` on the
analytic extension) recomputes for every write. If a downstream module
does a bulk `write({...})` on many records, this cascades.

Fix:

- Identify the offending compute via Odoo log `INFO odoo.models.dependents`
- Add `recursive=True` if missing (already done for `branch_root_id`)
- Batch the upstream write with `prefetch_fields=False` to short-circuit
  unrelated compute chains

### D. PDP audit log write storm

Every business write triggers `_pdp_audit_write`. Under bulk import
(e.g. CSV partner import), this multiplies. Symptom: many `INSERT INTO
pdp.audit_log` lines in PG log; high CPU on postgres rather than odoo.

Fix (temporary):

- Run the bulk job with `context = {"no_pdp_audit": True}` (mixin
  must respect this — add if missing).
- Plan: batched audit-log inserts (Phase 3).

## Escalation

- If CPU stays > 90% for > 15 min and worker bump doesn't help →
  declare **S2** and move bulk import jobs to off-hours.
- Check era-predictor's capacity dashboard — if RAM saturation ETA
  is < 7 days, **add headroom now** (scale up VPS).
