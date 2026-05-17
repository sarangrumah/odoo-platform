# Tenant Orchestrator

Multi-tenant lifecycle service for the Odoo 19 Platform. Owns:

- **Provisioning**: create per-tenant Odoo DB via Odoo's create-DB endpoint,
  install the `custom_*` module set, generate + wrap a per-tenant Fernet DEK.
- **Lifecycle**: suspend / resume / archive / purge — with append-only,
  hash-chained `tenant_registry.action_log`.
- **Backups**: scheduled pg_dump → MinIO/S3 with retention (daily/monthly/yearly),
  on-demand backup, point-in-time restore to a staging DB.
- **Key management**: master KMS wrapping key (env), per-tenant DEK
  envelope-encrypted at rest, surfaced via `GET /v1/tenants/{slug}/dek` to
  Odoo over the internal trusted network for in-memory caching.

## API

All `/v1/*` endpoints require HMAC: header `X-Custom-Signature: t=<unix>,v1=<hex>`
computed as `HMAC-SHA256(ORCHESTRATOR_SHARED_SECRET, f"{ts}.{raw_body}")`.
Replay window 5 minutes. Same scheme as `ai-gateway` so Odoo can re-use a
single signer helper from `custom.security`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/v1/tenants` | List tenants (filter by `state`) |
| `POST` | `/v1/tenants` | Provision tenant (returns admin pwd + DEK ONCE) |
| `GET`  | `/v1/tenants/{slug}` | Read tenant |
| `POST` | `/v1/tenants/{slug}/suspend` | Suspend |
| `POST` | `/v1/tenants/{slug}/resume` | Resume |
| `DELETE`| `/v1/tenants/{slug}` | Archive (rename DB, schedule purge) |
| `GET`  | `/v1/tenants/{slug}/dek` | Return unwrapped DEK to Odoo (internal use) |
| `GET`  | `/v1/tenants/{slug}/backups` | List backups |
| `POST` | `/v1/tenants/{slug}/backups` | Trigger a backup |
| `POST` | `/v1/tenants/{slug}/backups/restore` | Restore from S3 key |
| `GET`  | `/health` | Liveness (no auth) |
| `GET`  | `/metrics` | Prometheus (no auth) |

## Required env

See `app/config.py`. Minimum set:

```
PG_SUPER_PASSWORD=...                    # POSTGRES_PASSWORD
PG_ORCHESTRATOR_PASSWORD=...             # rotate from default via ALTER ROLE
MASTER_WRAPPING_KEY=...                  # 44-char base64 Fernet key
ORCHESTRATOR_SHARED_SECRET=...           # 32+ char HMAC secret
S3_SECRET_KEY=...                        # MinIO password
ODOO_ADMIN_PASSWD=...                    # Odoo master_pwd for DB creation
```

## Run locally

The service runs as part of `docker compose up`. Test endpoints with HMAC:

```bash
TS=$(date +%s)
BODY='{}'
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$ORCHESTRATOR_SHARED_SECRET" -hex | awk '{print $2}')
curl -X GET http://localhost:18091/v1/tenants \
  -H "X-Custom-Signature: t=$TS,v1=$SIG"
```

## Tests

```bash
cd tenant-orchestrator
python -m pytest tests/ -q
```

Tests cover: HMAC gate, validators, DEK roundtrip. Integration tests against
real Postgres / MinIO live in `tests/integration/` and run via
`make test-orchestrator-integration` (requires `docker compose up postgres minio`).
