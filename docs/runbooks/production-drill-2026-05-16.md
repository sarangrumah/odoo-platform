# Production-readiness drill — 2026-05-16

End-to-end validation of secrets management, observability, backup/restore, and alert pipeline on the dev stack before first production deployment. All steps executed against the live Docker Compose stack on Windows host (Docker Desktop + WSL2).

## Summary

| Area | Status | Detail |
|------|--------|--------|
| Dev cert bootstrap | ✓ PASS | Self-signed RSA-4096 (CN=localhost, 365d) at `nginx/certs/server.{crt,key}`. |
| Age keypair | ✓ PASS | `age-keygen` produced keypair; public `age1wdh3mpmewqdzp...` registered in `.sops.yaml`. |
| SOPS encryption | ✓ PASS | 10/64 keys encrypted, 5 critical secrets (POSTGRES_PASSWORD, REDIS_PASSWORD, GATEWAY_SHARED_SECRET, CORETAX_SERTEL_MASTER_KEY, ANTHROPIC_API_KEY) round-trip verified. |
| Observability stack | ⚠ PASS (1 known gap) | 14/15 services healthy. node-exporter unable to start on WSL2 (`path / is mounted on / but it is not a shared or slave mount`). 6/7 Prometheus targets `up`. |
| Backup → restore | ✓ PASS | pg_dump (Fc) `smoke_test` → 1.8 MB → restored to fresh DB `restore_test`. 15 cosmetic `IMMUTABLE` warnings on unaccent indexes (known PG behavior). Row counts: 85 modules, 5 audit, 7 classifications, 5 partners — match exactly. PDP hash chain verified clean post-restore. |
| Alert pipeline | ✓ PASS (after config fix) | 18 rules loaded. Synthetic + real alerts routed end-to-end: Alertmanager → predictor webhook → AI gateway call. Fixed routing matcher (was `component=capacity`, now `alertname=~"Capacity.*"`). |

## Findings worth fixing in code (already applied during drill)

1. **OpenSSL on Git-Bash inherits `OPENSSL_CONF` from PostgreSQL install** pointing to a missing `psqlODBC\etc\openssl.cnf`. Workaround: `OPENSSL_CONF= openssl ...`. Consider patching `scripts/dev-bootstrap.sh` to unset it.
2. **SOPS `encrypted_regex` too narrow** — original `^(password|secret|key|token|api).*$` missed `GATEWAY_SHARED_SECRET` (starts with `GATEWAY`). Updated to `(?i)(password|passwd|secret|key|token|api[_-]?key|credential|sertel|private|...)` with case-insensitive flag.
3. **Alertmanager route mismatch** — original matcher `component = capacity` never matched real alert labels (`component=disk|cpu|memory`). Updated to `alertname =~ "Capacity.*|DRILL_.*"`.
4. **Real OdooLongpollingDown alert firing** in dev mode — expected, because dev override sets `WORKERS=0` so Odoo doesn't spawn a gevent longpolling process. Not a bug. Document in dev runbook. Prod (`WORKERS≥4`) won't have this.
5. **dropdb against active DB needs explicit terminate** — `pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='X' AND pid<>pg_backend_pid()` first.

## Known limitations (not fixed; document & accept)

- **node-exporter cannot run on Docker Desktop / WSL2** (mount propagation limitation). Will work on real Linux hosts. Acceptable: dev gets pg/redis/odoo metrics, host metrics only in prod.
- **AI gateway returns 502** on real chat/predict calls because the smoke `.env` uses a stub ANTHROPIC_API_KEY. The HMAC + routing pipeline is verified, only the downstream LLM is stubbed. Replace with real key before prod use.
- **Coretax XSDs are placeholders** — drill does not validate against real DJP schemas. Tracked separately (see `addons/compliance/custom_coretax/data/xsd/SOURCES.md`).

## Repro procedure

```bash
cd E:\Projects\Odoo\platform
# 1. Bootstrap
OPENSSL_CONF= bash scripts/dev-bootstrap.sh
export PATH="$HOME/go/bin:$PATH"
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

# 2. Encrypt env
sops --encrypt --age age1wdh3mpmewqdzp... \
  --input-type=dotenv --output-type=yaml \
  --filename-override .secrets.enc.yaml .env > .secrets.enc.yaml

# 3. Bring stack up
make up-obs

# 4. Backup-restore drill
docker compose exec -T -e PGPASSWORD=$PASS postgres bash -c 'pg_dump -U odoo -Fc smoke_test' \
  | gzip > data/backups/drill-$(date +%Y%m%d).sql.gz
docker compose exec -T -e PGPASSWORD=$PASS postgres createdb -U odoo restore_test
gunzip -c data/backups/drill-*.sql.gz \
  | docker compose exec -T -e PGPASSWORD=$PASS postgres pg_restore -U odoo --no-owner --no-acl -d restore_test
# Verify row counts + chain
docker compose exec -T -e PGPASSWORD=$PASS postgres psql -U odoo -d restore_test \
  -c "SELECT * FROM pdp.verify_audit_chain();"

# 5. Alert pipeline
curl -X POST -H 'Content-Type: application/json' http://localhost:19093/api/v2/alerts \
  -d '[{"labels":{"alertname":"CapacitySaturationWarn","severity":"warning","component":"disk"},
       "startsAt":"'"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"'"}]'
# Wait 30s for group_wait, then:
docker compose logs --since 60s custom-predictor | grep '/run-now'
```

## Sign-off

- **Drill date:** 2026-05-16
- **Stack:** odoo:19.0, postgres:16-alpine, redis:7-alpine, ai-gateway 0.1.0, custom-predictor 0.1.0
- **Modules installed at drill time:** 13 (`queue_job` + 12 `custom_*`)
- **Backup file:** `data/backups/drill-20260516-132102.sql.gz` (1849700 bytes, sha256 `d7b84b38ce253c2871a588048ac051b7d38dca6938d772be0d5d9870a66da16e`)
- **Next required before prod deploy:**
  - [ ] Replace ANTHROPIC_API_KEY with real value
  - [ ] Replace self-signed cert with CA-issued (or use Caddy ACME via `make up-tls` + real DOMAIN)
  - [ ] Configure S3 backup env vars (S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET) and verify push from `pg-backup-s3` sidecar
  - [ ] Test backup restore from S3 in a true DR drill
  - [ ] Run `pre-commit install && pre-commit run --all-files` and fix any findings
