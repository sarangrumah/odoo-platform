# Platform Architecture

This document is the operator's map of the Custom platform. It explains what each
service does, how they talk to each other, and which ports they expose. For the
full design rationale (trade-offs, alternatives considered, future direction),
see the master plan at `docs/plan.md`.

## Contents

- [Stack diagram](#stack-diagram)
- [Service responsibilities](#service-responsibilities)
- [Port map](#port-map)
- [Data flows](#data-flows)
  - [Odoo to ai-gateway (HMAC)](#odoo-to-ai-gateway-hmac)
  - [custom-predictor / Prometheus / ai-gateway](#custom-predictor--prometheus--ai-gateway)
  - [PDP audit insertion path](#pdp-audit-insertion-path)
- [Reference](#reference)

## Stack diagram

```
                       +-------------------+
                       |     Operators     |
                       |  (browser, CLI)   |
                       +---------+---------+
                                 |
                       https://erp.local (443)
                                 |
                     +-----------v-----------+
                     |      nginx / TLS      |
                     |   (reverse proxy)     |
                     +-----+-----------+-----+
                           |           |
              odoo:8069    |           |   ai-gw:8088
                           |           |
        +------------------v-+       +-v------------------+
        |   Odoo 19 (web)    |<----->|    ai-gateway     |
        | addons/{core,...}/ | HMAC  |  (FastAPI/Python) |
        +---+----------+-----+       +--------+----------+
            |          |                      |
   psql 5432|     amqp |9092                  | http 9090
            |          |                      |
     +------v--+   +---v------+         +-----v-----+
     |Postgres |   |Kafka/Red |         | Prometheus |
     | (main)  |   | (jobs)   |         |  (scrape)  |
     +---------+   +----------+         +-----+-----+
                                              |
                                       +------v------+
                                       |custom-predictor|
                                       | (Python ML) |
                                       +-------------+
```

ASCII only. The real network diagram with VLANs lives in `docs/plan.md`.

## Service responsibilities

| Service | Owner | Repo path | Purpose |
| --- | --- | --- | --- |
| `nginx` | Platform | `infra/nginx/` | TLS termination, HSTS, request log, IP allow-list for `/web/database`. |
| `odoo` | Platform | `addons/{core,compliance,ee_gap,verticals}/*` | ERP core, business logic, RBAC, ORM. |
| `postgres` | Platform | `infra/postgres/` | Primary OLTP store. Logical replication target for warm-standby. |
| `ai-gateway` | AI | `services/ai-gateway/` | Brokers LLM and ML calls. Validates HMAC from Odoo. Caches prompts. |
| `custom-predictor` | AI | `services/custom-predictor/` | Hosts forecasting models. Exposes `/predict` and `/metrics`. |
| `prometheus` | SRE | `infra/prometheus/` | Scrapes `custom-predictor`, `ai-gateway`, Odoo `/metrics`. |
| `grafana` | SRE | `infra/grafana/` | Dashboards on top of Prometheus. |
| `loki` / `promtail` | SRE | `infra/logging/` | Log aggregation. |

Each service has a `Dockerfile` and a `make` target in the top-level `Makefile`.

## Port map

| Port | Service | Bind | Notes |
| --- | --- | --- | --- |
| 443 | nginx | public | Only public port. |
| 80 | nginx | public | Redirects to 443. |
| 8069 | odoo (web) | localhost | Behind nginx. |
| 8072 | odoo (longpolling/gevent) | localhost | Behind nginx, `/longpolling/*`. |
| 5432 | postgres | localhost | Network ACL via `pg_hba.conf`. |
| 8088 | ai-gateway | localhost | HMAC-validated. |
| 8089 | custom-predictor | localhost | Internal only. |
| 9090 | prometheus | localhost | Behind VPN. |
| 3000 | grafana | localhost | Behind VPN. |
| 3100 | loki | localhost | Behind VPN. |

Authoritative source: `infra/compose/docker-compose.yml`.

## Data flows

### Odoo to ai-gateway (HMAC)

1. An Odoo addon (e.g. `custom_ai_bridge`) calls `services.ai_gateway.client.post()`.
2. The client builds a JSON body and computes
   `X-Custom-Signature = HMAC_SHA256(shared_secret, timestamp + "." + body)`.
3. nginx forwards `POST /v1/chat` to `ai-gateway:8088`.
4. `ai-gateway` rejects the request if:
   - Timestamp drift exceeds 300 s.
   - Signature mismatch.
   - `X-Era-Tenant` not in the allow-list.
5. On success `ai-gateway` calls the upstream model (OpenAI, local vLLM, or
   `custom-predictor` for tabular models).
6. Response is streamed back through nginx to Odoo.

Shared secret rotation is documented in `docs/runbooks/secret-rotation.md`.

### custom-predictor / Prometheus / ai-gateway

1. `custom-predictor` exposes `/metrics` (Prometheus text format) on port 8089.
2. `prometheus` scrapes every 15 s; alert rules in
   `infra/prometheus/rules/custom-predictor.yml`.
3. `ai-gateway` queries `custom-predictor` at `/predict` for tabular features.
4. `ai-gateway` also exposes its own `/metrics` for end-to-end latency.
5. Grafana dashboard `dashboards/predictor.json` joins both metric streams.

### PDP audit insertion path

Personal-data accesses must produce an immutable audit row. Path:

1. Any model that mixes in `pdp.audit.mixin` calls
   `self._pdp_log("read", record_id, fields)` from `read()`/`write()`.
2. The mixin inserts into `custom_pdp_audit_event` with:
   - `prev_hash` = sha256 of the previous row.
   - `row_hash` = sha256 of `(prev_hash || payload)`.
3. A postgres `BEFORE UPDATE OR DELETE` trigger on `custom_pdp_audit_event` raises
   `EXCEPTION 'audit log is append-only'`. See `custom_pdp_audit/data/pg_trigger.sql`.
4. Nightly cron `custom_pdp_audit.cron_verify_chain` walks the table and alerts on
   any broken hash link.

Full PDP mapping: `docs/pdp-compliance.md`.

## Reference

- Full plan and design rationale: `docs/plan.md`
- Adding a new vertical: `docs/adding-vertical.md`
- Runbooks: `docs/runbooks/`
- Compliance: `docs/pdp-compliance.md`, `docs/coretax.md`
