# Secret Rotation Policy

| Secret | Rotation cadence | Method | Owner |
|--------|-----------------|--------|-------|
| `POSTGRES_PASSWORD` | Quarterly + on-suspect | `ALTER ROLE odoo WITH PASSWORD '...'` then update `.env` and roll Odoo | DBA |
| `ODOO_ADMIN_PASSWD` | Quarterly | Update `.env`, restart Odoo. Re-set via `odoo.conf` after rotation | Platform owner |
| `REDIS_PASSWORD` | Quarterly | `CONFIG SET requirepass`, update env, roll Redis + Odoo + ai-gateway | DBA |
| `GATEWAY_SHARED_SECRET` | Quarterly + on-suspect | Generate via `openssl rand -hex 32`. Update env on both Odoo & ai-gateway. **No graceful overlap** — schedule short window. | Platform owner |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | On-vendor-suspect or 6-month | Vendor portal → new key → `.env` → restart ai-gateway. Revoke old. | AI owner |
| `CORETAX_SERTEL_MASTER_KEY` | **Never rotate without migration plan** — encrypts all stored sertel. Rotation requires decrypt-all → re-encrypt batch job. | Finance + DBA |
| `GRAFANA_ADMIN_PASSWORD` | Quarterly | Update env, restart Grafana. | Ops |
| `PGADMIN_PASSWORD` | Quarterly | Update env, restart pgadmin. | Ops |
| TLS cert (`nginx/certs/`) | Per CA lifecycle (90d for LE) | Auto-renew via cert-manager or certbot. | Ops |

## Local dev bootstrap

For a fresh clone (or any host that lacks dev certs / SOPS key):

```bash
make dev-bootstrap
```

This script (`scripts/dev-bootstrap.sh`) is idempotent and:

1. Generates `nginx/certs/server.{crt,key}` (self-signed, CN=localhost, RSA-4096, 365d)
   only if they are absent. These are git-ignored.
2. Generates an age keypair at `~/.config/sops/age/keys.txt` (via `age-keygen`) only
   if absent. Mode is set to `600`.
3. Prints the resulting age **public key** with a copy-paste-ready snippet for
   `.sops.yaml`. Each operator must add their public key under
   `creation_rules[].age` so the team can decrypt the shared `.secrets.enc.yaml`.
4. Reminds you to export `SOPS_AGE_RECIPIENT` and `SOPS_AGE_KEY_FILE`, which the
   `make encrypt-env` / `make decrypt-env` targets depend on.

Re-running `make dev-bootstrap` after the first run is safe — it will detect
existing material and skip generation.

## Procedure for an emergency rotation (suspected leak)

1. Generate new secret using documented method.
2. Update `.env` and re-encrypt `.secrets.enc.yaml` (`make encrypt-env`).
3. `docker compose up -d --force-recreate <service>` for every consumer.
4. Verify with `make logs SERVICE=<service>` — fail-fast checks must pass.
5. Revoke old secret at issuer (DB ALTER ROLE, vendor portal).
6. Record incident in audit log via `make verify-audit-chain` snapshot + manual entry in `docs/runbooks/`.
