# Runbook — Single-Tenant Data Recovery

Use when **one tenant's** data is corrupt / lost while the rest of the
platform is healthy (S3 severity per DR runbook). Do NOT confuse with
full DR — this is the single-DB restore flow.

## When to Use

- Tenant admin reports "all my data is gone"
- `make verify-audit-chain DB=<tenant>` returns broken rows
- A bad import / migration overwrote production data
- A tenant accidentally hit "Erase all data" via DSAR

## Pre-flight

```bash
# Confirm scope — only ONE tenant affected
make tenant-list | jq '[.[] | select(.state=="active")] | .[].slug'

# Capture current state for forensic comparison
docker compose exec postgres pg_dump -U "$POSTGRES_USER" \
  -d <slug> -Fc -f /tmp/<slug>-pre-recovery.dump
docker cp ${COMPOSE_PROJECT_NAME:-odoo19-platform}-postgres:/tmp/<slug>-pre-recovery.dump \
  ./data/forensic/
```

## Step-by-step

### 1. Suspend the tenant (prevents further damage)

```bash
make tenant-suspend SLUG=<slug>
```

### 2. Identify the right backup

```bash
make tenant-list-backups SLUG=<slug>
# Pick the latest s3_key BEFORE the corrupting event.
# Common heuristics:
#   - "before the bad import" → check incident timeline
#   - "yesterday's daily" → previous 02:00 UTC backup
#   - "last week's monthly" → first-of-month snapshot
```

### 3. Restore to staging (non-destructive)

```bash
make tenant-restore SLUG=<slug> S3_KEY=<slug>/YYYY/MM/DD/<file>.dump
# Restores to <slug>_staging (default target)
```

### 4. Validate the staging DB

```bash
SLUG_STG=<slug>_staging
PGE="docker compose exec postgres psql -U $POSTGRES_USER -d $SLUG_STG -tAc"

# Sanity counts
$PGE "SELECT 'partners:'   || COUNT(*) FROM res_partner WHERE active;"
$PGE "SELECT 'invoices:'   || COUNT(*) FROM account_move WHERE state='posted';"
$PGE "SELECT 'employees:'  || COUNT(*) FROM hr_employee WHERE active;"
$PGE "SELECT 'audit rows:' || COUNT(*) FROM pdp.audit_log;"
$PGE "SELECT 'audit chain broken:' || COUNT(*) FROM pdp.verify_audit_chain();"

# Spot check: latest 5 invoices match what user expects
$PGE "SELECT name, partner_id, amount_total, state, invoice_date
        FROM account_move
       ORDER BY id DESC LIMIT 5;"
```

CSM should confirm with the tenant via screenshot that the counts +
recent records look right.

### 5. Cut over (live swap)

**Only after the tenant confirms staging is correct.**

```bash
TS=$(date +%s)
docker compose exec postgres psql -U "$POSTGRES_USER" -c "
  -- Atomic swap, no race window
  BEGIN;
  ALTER DATABASE $SLUG RENAME TO ${SLUG}_corrupt_${TS};
  ALTER DATABASE ${SLUG}_staging RENAME TO $SLUG;
  COMMIT;
"

# Cycle Odoo workers so they pick up the new DB
docker compose restart odoo

# Resume the tenant
make tenant-resume SLUG=<slug>
```

### 6. Notify + audit

```bash
# Tenant audit chain integrity (must be 0)
make verify-audit-chain DB=<slug>

# Master action_log entry
docker compose exec postgres psql -U "$POSTGRES_USER" -c \
  "INSERT INTO tenant_registry.action_log
     (tenant_slug, action, actor, detail, outcome)
   VALUES ('<slug>', 'manual_recovery',
           '<ops_user>',
           '{\"from_s3_key\": \"...\", \"corrupted_db_renamed_to\": \"${SLUG}_corrupt_${TS}\"}'::jsonb,
           'success');"
```

Email the tenant admin with:
- The recovery time + data point restored from (e.g. "01:30 WIB today")
- Any data that was lost between the backup point and the incident
- The forensic dump path (if they ever need to inspect the corrupt
  state again)

### 7. Cleanup (after 7 days)

If no rollback is requested:

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -c \
  "DROP DATABASE ${SLUG}_corrupt_${TS};"
rm -f ./data/forensic/<slug>-pre-recovery.dump
```

## Lessons-Learned Loop

After every single-tenant recovery, add a row to the DR runbook
appendix even though it's S3. Patterns from S3 incidents often
predict S1 failures.
