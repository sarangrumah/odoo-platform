# Load Tests (k6)

k6 scenarios validating the platform under the **P4 production-grade
acceptance targets** (Phase 2 plan, SLA tier 99.5%):

| Metric | Threshold |
|--------|-----------|
| p95 latency (HTTP) | < 3000 ms |
| p99 latency (HTTP) | < 5000 ms |
| Error rate | < 0.1% |
| Concurrent users | 10 tenants × 50 = 500 |
| Duration | 30 min ramped |

## Files

| File | Purpose |
|------|---------|
| `mixed_scenario.js` | Main suite — 60% read / 30% write / 10% report. Hits one tenant per VU. |
| `read_only.js` | Smoke test variant: list views + dashboard only (no DB writes). Useful for first-touch validation. |
| `provisioning.js` | Stresses `tenant-orchestrator` `POST /v1/tenants` with parallel provisioning (separate from end-user load). |
| `lib/auth.js` | Odoo session login helper (cookies). |
| `lib/hmac.js` | HMAC signer mirroring `app.security` in ai-gateway / tenant-orchestrator. |
| `lib/tenants.js` | Tenant slug pool + per-VU pinning. |

## Install k6

Local install (no Docker needed):

- macOS: `brew install k6`
- Windows: `choco install k6` or download from <https://k6.io/docs/get-started/installation/>
- Linux: `sudo apt install k6` (or use the official repo)

## Run

Set the target stack URL + tenant pool via env:

```bash
export PLATFORM_BASE=https://platform.localhost
export TENANT_SLUGS=acme,widgetco,studio   # comma-separated
export TENANT_LOGIN=admin
export TENANT_PASSWORD=...                   # captured at provision time
export ORCHESTRATOR_SHARED_SECRET=...        # from .env

# Smoke (~30s, 5 VUs)
k6 run --vus 5 --duration 30s read_only.js

# Mixed (defaults to the production-grade thresholds above)
k6 run mixed_scenario.js

# Provisioning stress (5 parallel tenant creations)
k6 run provisioning.js
```

Results are written to `summary.json` (k6 default) plus k6's stdout.

## Interpreting Failures

- **p95 > 3s** on read endpoints → check Odoo worker count
  (`docker compose exec odoo cat /etc/odoo/odoo.conf | grep workers`)
  and Postgres slow query log.
- **p95 > 3s** on write endpoints → check redis health + PDP audit
  trigger cost (`pdp._audit_log_before_insert` recomputes hash on
  every insert; high write volume may need batching).
- **Error rate > 0.1%** → drill into the per-status histogram in
  k6 output; 502/504 = upstream timeout (raise Odoo `limit_time_real`),
  401 = HMAC drift (clock skew between client + ai-gateway).

## CI Integration (planned)

Quarterly load test runs from a scheduled GitHub Actions workflow
against a staging stack. Not yet activated — when staging environment
is provisioned, uncomment `.github/workflows/load.yml.disabled`.
