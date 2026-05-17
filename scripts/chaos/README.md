# Chaos Drills

Manual + scripted failure-injection sequences used in the **monthly DR
drill** and ad-hoc resilience verification. Each script:

1. **Pre-flight**: snapshot the current state (running containers,
   pending transactions, recent error count) so the post-mortem can
   compare to baseline.
2. **Inject**: kill the target component or fill a resource.
3. **Observe**: poll dependent services + log Grafana panels for
   anomalies.
4. **Recover**: restart and verify the system self-heals within the
   declared RTO budget (4 hours for SLA tier 99.5%).
5. **Report**: print a structured summary the operator can paste into
   the DR drill log.

## Drills

| Script | Target | Expected behaviour |
|--------|--------|--------------------|
| `kill-postgres.sh` | Postgres primary | Odoo workers re-connect within ~30s; in-flight HTTP requests fail with 500 + retry on client. |
| `kill-redis.sh` | Redis | `ai-gateway` rate limiter fails open with a warning log; no user-facing impact. |
| `kill-ai-gateway.sh` | ai-gateway | Odoo "Ask AI" features show a friendly error; core workflows unaffected. |
| `fill-disk.sh` | Host filesystem | `era-predictor` issues a capacity warning within one tick; Alertmanager fires. |
| `kill-orchestrator.sh` | tenant-orchestrator | Tenant lifecycle ops fail with 503 from Caddy; super-admin UI surfaces the error; no tenant data impacted. |
| `kill-pajakku-network.sh` | Outbound HTTPS to Pajakku (iptables) | Pajakku adapter circuit breaker opens after 10 failures; submissions queue. |

## Usage

```bash
# From the platform root
./scripts/chaos/kill-postgres.sh
# Wait until you see "Recovered" + the post-action snapshot

./scripts/chaos/fill-disk.sh
# Press Ctrl-C to release the fill before the disk actually fills
```

All drills **default to safe mode** (small windows, easy cleanup).
Production-targeting variants require explicit `CONFIRM=yes` env.

## DR Drill Cadence

Per `docs/runbooks/disaster-recovery.md` §"Monthly DR Drill":

| Month | Target |
|-------|--------|
| Jan, Apr, Jul, Oct | `kill-postgres.sh` + full restore-to-staging |
| Feb, May, Aug, Nov | `kill-ai-gateway.sh` + `kill-redis.sh` |
| Mar, Jun, Sep, Dec | `fill-disk.sh` + `kill-pajakku-network.sh` |

Document each drill in the runbook's appendix with date, duration,
recovery time, and observations.
