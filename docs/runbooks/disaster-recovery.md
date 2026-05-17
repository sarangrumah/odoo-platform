# Disaster Recovery Runbook

**Tier**: 99.5% SLA (Phase 2 locked decision)
**RPO**: 1 hour (daily full backup + WAL archiving 1h)
**RTO**: 4 hours (matches monthly downtime budget)

> Read this top-to-bottom before declaring DR. Skipping the
> "DETECT → DECLARE → COMMS" steps to jump straight to RESTORE is
> the single most common cause of botched recoveries (we restore
> stale data because the failure was actually still recoverable from
> the primary).

---

## Severity Classification

| Severity | Definition | Action |
|----------|------------|--------|
| **S1 — Total outage** | All tenants down OR data corruption confirmed on > 50% of tenants | Declare DR immediately. Full team page-out. |
| **S2 — Major outage** | One service tier degraded (e.g. ai-gateway down, Pajakku adapter circuit open for > 30min) but tenants can still operate core workflows | Mitigate without declaring DR. Open incident ticket. |
| **S3 — Single-tenant outage** | One tenant's DB corrupted / inaccessible; others healthy | Restore that tenant from backup (no platform-wide DR). |
| **S4 — Performance degradation** | All tenants up but latency > 2× normal | Diagnose, no DR. |

Only **S1** triggers this runbook in full.

---

## Phase 1: DETECT (target: < 5 min from incident)

Detection sources, in order of priority:

1. **Alertmanager** — webhook to ops Slack/email when:
   - All Odoo containers unhealthy for > 2 min
   - Postgres `service_healthy` flipping repeatedly
   - era-predictor `saturation_eta_days < 1`
2. **Synthetic check** — external uptime monitor (Uptime Kuma /
   Pingdom) hitting `https://platform.localhost/healthz`
3. **User reports** — escalations from CSMs

Pull baseline before acting:

```bash
docker compose ps                          # service-by-service health
make tenant-list                           # registry state
make tenant-verify-chain                   # detect log corruption
docker compose logs --tail=200 postgres    # primary suspect
```

If `tenant-verify-chain` returns rows, **data integrity is compromised** —
escalate to S1 even if services look healthy.

---

## Phase 2: DECLARE + COMMS (target: < 15 min from detection)

1. **Open the incident channel**:
   - Slack `#incident-active`
   - Set topic: `S1 DR — <one-line summary> — IC: <oncall>`
2. **Page the team**:
   - Oncall engineer (technical IC)
   - CSM lead (customer comms)
   - Engineering manager (status updates to stakeholders)
3. **Status page**: post initial "Investigating service disruption"
   message to `status.platform.id` (or comms equivalent).
4. **Freeze writes** (defensive — prevents downstream divergence):

   ```bash
   make tenant-suspend SLUG=<each_active_slug>
   # OR (preferred, faster):
   docker compose exec postgres psql -U "$POSTGRES_USER" -c \
     "UPDATE tenant_registry.tenants SET state='suspended' WHERE state='active';"
   ```

---

## Phase 3: RESTORE (target: < 3 hours from declaration)

### 3a. Decide between IN-PLACE RECOVERY vs RESTORE-FROM-BACKUP

| Symptom | Action |
|---------|--------|
| Container crashed but data dir intact | IN-PLACE: `docker compose up -d <svc>` + verify |
| Data dir corrupted (PG won't start) | RESTORE: bring stack to baseline, restore from MinIO/S3 |
| Disk full | IN-PLACE: free space, restart svc |
| Network partition | IN-PLACE: fix network, services self-heal |
| Audit chain broken | RESTORE: roll back to last known-good backup |

### 3b. In-Place Recovery

```bash
# Bring up only postgres first to validate
docker compose up -d postgres
docker compose exec postgres pg_isready -U "$POSTGRES_USER"

# Then everything else
docker compose up -d
watch -n 5 'docker compose ps'
```

Resume tenants once all services healthy:

```bash
for slug in <slugs>; do make tenant-resume SLUG=$slug; done
```

### 3c. Restore From Backup

For **each affected tenant**, identify the latest pre-incident backup:

```bash
make tenant-list-backups SLUG=acme | jq '[.[] | select(.outcome=="success")] | .[0]'
```

Restore to a staging DB first (non-destructive), validate, then cut over:

```bash
# 1. Restore to staging
make tenant-restore SLUG=acme S3_KEY=acme/2026/05/17/acme-013000Z.dump

# 2. Validate staging DB
docker compose exec postgres psql -U "$POSTGRES_USER" -d acme_staging -c \
  "SELECT count(*) FROM res_partner;
   SELECT count(*) FROM account_move WHERE state='posted';
   SELECT count(*) FROM tenant_registry.action_log;"  # last one runs against master DB only

# 3. Compare counts with pre-incident expected (CSM should have rough numbers)

# 4. If staging passes, swap DB names atomically:
docker compose exec postgres psql -U "$POSTGRES_USER" -c \
  "ALTER DATABASE acme RENAME TO acme_corrupt_$(date +%s);
   ALTER DATABASE acme_staging RENAME TO acme;"

# 5. Recompute Odoo registry + Caddy routing (auto-picks new DB)
docker compose restart odoo caddy

# 6. Per-tenant audit chain sanity
make verify-audit-chain DB=acme
```

### 3d. WAL Replay (closes the 1h RPO gap)

If the last successful backup is < 24h old AND the postgres WAL
archive is reachable, replay incremental WAL to recover closer to
the failure moment:

```bash
docker compose exec postgres bash -c \
  "pg_waldump --start=<lsn_at_backup> /var/lib/postgresql/data/pg_wal/ > /tmp/wal.txt"
# Inspect; apply via point-in-time recovery if needed (see Postgres docs)
```

> Note: WAL archiving to MinIO is **not yet wired** in this iteration
> — the planned 1h RPO assumes daily backups + future WAL streaming.
> Current effective RPO is 24h until WAL archiving lands in Phase 3.

---

## Phase 4: VERIFY (target: < 30 min after restore)

Mandatory checklist before resuming:

```bash
# 1. Chain integrity per tenant
for slug in <slugs>; do make verify-audit-chain DB=$slug; done
make tenant-verify-chain

# 2. Smoke test critical workflows per tenant (manual)
#    - Login + dashboard loads
#    - Vendor bill post succeeds
#    - Payslip compute returns
#    - Faktur generation succeeds

# 3. Pajakku adapter healthy (if used)
# Visit Coretax Config → Pajakku tab → "Test Connection"

# 4. Audit log tail shows recent activity
docker compose exec postgres psql -U "$POSTGRES_USER" -d acme -c \
  "SELECT ts, action, classification FROM pdp.audit_log ORDER BY id DESC LIMIT 20;"
```

---

## Phase 5: CUTOVER + RESUME

```bash
for slug in <slugs>; do make tenant-resume SLUG=$slug; done
```

Update status page: "Service restored. Monitoring."

---

## Phase 6: POST-MORTEM (within 5 business days)

Use this template (copy into `docs/runbooks/postmortems/YYYY-MM-DD-<incident>.md`):

```markdown
# Incident YYYY-MM-DD: <title>

## Summary
- **Severity**: S1
- **Duration**: HH:MM detection → HH:MM resolution = <duration>
- **Affected**: <tenant slugs>
- **Data loss**: <none | n records>

## Timeline (UTC)
| Time | Event |
|------|-------|
| HH:MM | First Alertmanager fire |
| HH:MM | Declared S1 |
| ...   | ... |
| HH:MM | All tenants resumed |

## Root Cause
<single-paragraph explanation>

## Impact
- Customer-facing: <X requests served 5xx; Y tenants offline for Zmin>
- Data: <integrity verified via verify-audit-chain | rows lost: ...>
- Financial: <SLA credits owed: $...>

## What Went Well
- ...

## What Went Wrong
- ...

## Action Items
| # | Action | Owner | Due |
|---|--------|-------|-----|
| 1 | ... | ... | YYYY-MM-DD |
```

---

## Monthly DR Drill

Run on the first business Wednesday of each month. Cadence per
`scripts/chaos/README.md`:

| Quarter Month | Drill |
|---|---|
| Month 1 (Jan, Apr, Jul, Oct) | `kill-postgres.sh` + full restore-to-staging cycle |
| Month 2 (Feb, May, Aug, Nov) | `kill-ai-gateway.sh` + `kill-redis.sh` |
| Month 3 (Mar, Jun, Sep, Dec) | `fill-disk.sh` + `kill-pajakku-network.sh` |

For the restore drill specifically, target RTO ≤ 4 hours. Record
actual time-to-restore in the appendix below.

---

## Appendix: Drill Log

| Date | Drill | RTO Target | RTO Actual | Outcome | Notes |
|------|-------|------------|------------|---------|-------|
| _example_ | kill-postgres | 4h | 12 min | PASS | clean shutdown + restart, 0 data loss |

---

## Appendix: Key Contacts

- **Pajakku support** — when adapter is enabled and submissions are
  failing: contact info per active contract.
- **Postgres consultant** — for WAL replay scenarios beyond runbook
  scope. Stored in 1Password vault.
- **DPO** — `dpo@<company>` for PDP-related incidents (data loss
  involving PII triggers UU 27/2022 notification obligations within
  72 hours).
