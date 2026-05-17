# SOP — Tenant Offboarding

Soft-delete (archive) flow for tenants leaving the platform. Tenant
data is **renamed but not destroyed** for 30 days; this allows
recovery if the request was made in error or if regulatory holds apply.

## Pre-conditions

- Tenant in state `active` or `suspended`.
- Tenant has been notified (legal / contractual obligation).
- Final backup has been confirmed (`make tenant-backup SLUG=...` returns
  `outcome=success`).

## Procedure

### 1. Final backup

```bash
make tenant-backup SLUG=acme KIND=manual
make tenant-list-backups SLUG=acme | head -20
```

Confirm the latest entry has `outcome: success` and note the `s3_key` —
this is the snapshot regulatory or legal teams can request later.

### 2. Suspend first (optional, cooling-off)

If you want a window where the tenant cannot log in but data is still
quickly recoverable:

```bash
make tenant-suspend SLUG=acme
```

Tenant URL returns 503; data is intact. Resume with `make tenant-resume`.

### 3. Archive

```bash
make tenant-archive SLUG=acme
```

What happens:

- All Postgres connections to the tenant DB are terminated.
- DB is renamed to `_archived_<unix_ts>_<slug>`.
- Registry state transitions to `archived`, `purge_after = now + 30 days`.
- Hosts entry `<slug>.platform.localhost` is **NOT removed** (manual step).

### 4. Manual hosts cleanup

Remove the line `127.0.0.1   <slug>.platform.localhost` from
`C:\Windows\System32\drivers\etc\hosts` once you no longer need ops
access.

### 5. Confirm in Super Admin

- Open `https://admin.platform.localhost` → **Tenants** filter by state
  `Archived` — `<slug>` should appear with `Purge after = <date>`.

### 6. Notify finance / billing

Send the final backup `s3_key` to billing so they can attach to the
closure ticket / contract artefact.

## Purge (automatic, day 30)

The orchestrator's hourly housekeeping job calls `provisioner.purge_due()`
which:

1. Drops the archived DB (irreversibly).
2. Deletes the registry row.
3. Writes a final `purge` action to `tenant_registry.action_log`
   (hash-chained, immutable).
4. Deletes still-valid backup objects per retention policy. Backups
   beyond their `expires_at` were already cleaned by the periodic prune.

After purge:

- Tenant slug becomes available for re-use.
- `tenant_registry.action_log` retains full history (slug + actions),
  but no tenant row exists.

## Early purge (legal hold lift / GDPR erasure)

If regulator / law requires immediate purge before the 30-day window:

```bash
# 1. Archive (or skip if already archived)
make tenant-archive SLUG=acme

# 2. Edit the registry row to expire purge immediately
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "UPDATE tenant_registry.tenants SET purge_after = now() WHERE slug = 'acme';"

# 3. Wait up to 1 hour for housekeeping, or trigger manually
docker compose exec tenant-orchestrator python -c \
  "from app.provisioner import purge_due; print(purge_due('manual:legal-hold-lift'))"
```

Document the legal reference (court order, regulator letter) in the
tenant's `notes` field BEFORE early purge — the audit log will record
the manual purge action with that context.

## Audit references

```bash
make tenant-verify-chain
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT ts, action, actor, outcome FROM tenant_registry.action_log
        WHERE tenant_slug = 'acme' ORDER BY id;"
```

Confirm the chain shows: `provision_started → provision_completed →
(optional suspend → resume)* → backup* → archive → purge`.
