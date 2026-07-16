# Platform Architecture

Operator's map of the Custom Odoo platform: what runs, where the code lives, how
modules are tiered, and how external systems connect.

Every claim here is labelled **NOW** (deployed today) or **TARGET** (planned, not
built). Nothing is described as existing until it does — the previous version of
this document drew Kafka, a warm-standby Postgres and an `infra/` tree that were
never built, and planning started from those assumptions.

Last verified against the repo: 2026-07-16.

## Contents

- [Stack (NOW)](#stack-now)
- [Services](#services)
- [Module tiers](#module-tiers)
- [External integrations](#external-integrations)
- [Deployment topology](#deployment-topology)
- [Data flows](#data-flows)
- [Reference](#reference)

## Stack (NOW)

One host, one Docker network (`odoo-net`), every data path a bind-mount under
`./data/`. Compose files live at the repo root: `docker-compose.yml` (base) plus
overlays.

```
                        Operators / tenants (browser, CLI)
                                     |
                        caddy (443) | nginx (18443)      <- TLS, one of the two
                                     |
      +-----------------+------------+-------------+------------------+
      |                 |                          |                  |
  odoo (8069)     hub-portal (18000)      tenant-orchestrator    storefront
  odoo-mgmt*      (Vite/React admin UI)       (18091, FastAPI)     (18100)
      |                                           |
      |  HMAC                                     | HMAC + docker.sock (ro)
      +--------------> ai-gateway (18080) ---> ollama* / OpenAI / Anthropic
      |
      +--------------> redis (16379)   nonce replay, cache — NOT a job broker
      |
      +--------------> postgres (15432)  single cluster, all tenant DBs
      |
      +--------------> minio (19000)  backups/objects — same host, same disk

  observability overlay*: prometheus, alertmanager, loki, promtail, grafana,
                          node/postgres/redis/odoo exporters, custom-predictor

  * = overlay-only (see table below)
```

Ports above are the host-published defaults from `.env.example`; in-container
ports differ (Odoo is 8069/8072 inside). Only Caddy/nginx should be public —
`docs/vps-demo-deploy.md` binds everything else to `127.0.0.1`.

## Services

| Service | Repo path | Compose file | Purpose |
| --- | --- | --- | --- |
| `postgres` | `postgres/` | base | Single Postgres 16 cluster; one DB per tenant. |
| `redis` | — (image) | base | Nonce replay store for HMAC, cache, rate-limit. |
| `odoo` | `odoo/`, `addons/*` | base | ERP core, business logic, RBAC, ORM. |
| `odoo-mgmt` | `odoo/` | multitenant | Second Odoo for DB management (`LIST_DB=True`). **Shares the same cluster and filestore as `odoo`** — see the constraint below. |
| `ai-gateway` | `ai-gateway/` | base | Brokers LLM calls (Anthropic/OpenAI/Ollama). Validates HMAC from Odoo. |
| `tenant-orchestrator` | `tenant-orchestrator/` | base | FastAPI: provision/suspend/backup/restore tenants; per-tenant backup scheduler. |
| `hub-portal` | `hub-portal/` | base | The single UI (Vite + React): landing, intake, admin, super-admin. |
| `storefront` (+`-tls`) | `storefront/` | base | Headless commerce front-end. |
| `minio` | — (image) | base | S3-compatible object store (backups, attachments). |
| `baileys` | `services/baileys/` | base | WhatsApp bridge (notifications). |
| `ftps` | — (image) | base | pure-ftpd drop folder; Levi's retail feed lands here. |
| `caddy` | `caddy/` | multitenant, tls-acme | Wildcard TLS / ACME reverse proxy. |
| `nginx` | `nginx/` | prod | TLS termination, request log. |
| `pg-backup-local` | — | prod | Daily/weekly/monthly `pg_dump` → `./data/backups`. |
| `pg-backup-s3` | — | prod | Offsite backup — **profile-gated `s3-backup`, off by default**. |
| `prometheus`, `alertmanager`, `loki`, `promtail`, `grafana`, `*-exporter` | `observability/` | observability | Ops metrics/logs. Not business BI. |
| `custom-predictor` | `custom-predictor/` | observability | Capacity forecasting. |
| `ollama` | — (image) | local-llm | Local LLM; `AI_PROVIDER=ollama`. |
| `finance-sap-bridge` | `services/finance-sap-bridge/` | **none** | SAP/HRIS ↔ Kafka bridge. **Not in any compose file**; runs separately. |

Overlays: `dev` (exposes pg/redis, mailpit, pgadmin, hot reload, `LIST_DB=True`),
`prod` (nginx, backups, `WORKERS=4`, read-only rootfs), `multitenant` (caddy +
odoo-mgmt, `DBFILTER=^%d$`), `observability`, `tls-acme`, `local-llm`.
Targets: see `make up-dev`, `up-prod`, `up-multitenant`, `up-obs`, `up-llm`, `up-tls`.

## Module tiers

Tier is decided **by the `addons/` group a module sits in** — nothing else
encodes it. In particular `category` in a manifest is *not* the tier: `ee_gap`
modules deliberately reuse stock Odoo categories (`Accounting/Accounting`, …) so
they appear next to the Enterprise apps they replace.

| Group | Count | Scope | Contents |
| --- | --- | --- | --- |
| `_vendor/` | 4 | third-party | Vendored OCA (`queue_job`, `auth_jwt`, …). Do not edit; `fetch_oca.sh`. |
| `core/` | 8 | all tenants | `custom_core` (HMAC `secure_endpoint`), `custom_adapter_framework`, `custom_ai_bridge`, `custom_hht_bridge`, … |
| `control_plane/` | 4 | platform | `custom_hub_console`, `custom_super_admin`, `custom_tenant_infra`, `custom_onboarding_journey`. |
| `compliance/` | 9 | all ID tenants | PDP (`custom_pdp_*`), Coretax, PPh withholding. |
| `ee_gap/` | 78 | all tenants | The CE→EE delta: accounting, payroll, WMS, finance portal, retail, e-commerce. |
| `verticals/` | 10 | one industry | `custom_ppob_*` + `_template/`. |
| `_tenants/` | 5 | one customer | `custom_levis_*`, `custom_arka_*`. |
| `operations/` | 3 | internal | `custom_brd_analyzer`, `custom_dev_cycle`, `custom_ops_monitor`. |

Rules:

- **A shared integration engine belongs in `ee_gap`/`core`, never `_tenants`.**
  The seed data may be customer-specific; the engine is not. Canonical example:
  `ee_gap/custom_retail_import` is generic, while its `levis_*` profiles in
  `data/retail_import_profiles.xml` are one tenant's.
- **Promotion:** a pattern that appears for a 2nd customer moves from `_tenants/`
  up to `ee_gap/`.
- **Which modules make up a vertical** is answered by
  `control_plane/custom_hub_console/models/industry_pack.py::_SEED_PACK_MODULES`,
  not by manifests.
- **Adding a group is not free.** `addons_path` is one literal line in
  `odoo/odoo.conf.tmpl` (baked into the image at build — a restart will *not*
  pick it up, rebuild), plus 7 other registration points: the catalog buckets,
  the BRD analyzer map + Selection, two search-view filter blocks,
  `hub-portal/src/pages/admin/ModuleDeployPage.tsx`, and
  `scripts/generate_module_knowledge.py`. Module **depth must stay
  `addons/<group>/<module>/`** — `module_catalog._addons_root()` counts `..`.
- **Do not rename `compliance/`**: `.gitignore` ignores Coretax `.p12`/`.pfx`
  private keys by that path.

## External integrations

One HMAC contract, both directions, identical canonical form
(`timestamp_bytes || raw_body`, ±300 s drift, Redis nonce replay, CIDR allow-list):

- **Inbound:** `@secure_endpoint('<scope>')` in
  `core/custom_core/controllers/secure_endpoint.py`. Scopes in use: `hht`,
  `finance_sap`, `storefront`, `ops_alertmanager`.
- **Outbound:** `core/custom_adapter_framework` — `BaseAdapter` (retry with
  backoff, circuit breaker, 4xx treated as permanent), `custom.adapter.config`
  (credentials via `credential_ref` → `ir.config_parameter`),
  `custom.adapter.call.log` (append-only, stores a request *hash*, not the body).

New outbound integrations must use the framework. `custom_ai_bridge`,
`custom_payment_id`, `custom_sms_id` and `custom_voip` hand-roll their own
adapters — that is debt, not precedent.

| System | State |
| --- | --- |
| **XStore** (Levi's POS) | **NOW:** no connector. XStore emits XLSX/CSV report exports (X101 master, X20 on-hand, X24 sales, X70/X70D tenders) consumed by `ee_gap/custom_retail_import`. Its SFTP poller (`retail.import.feed`) is **off by default**. X24/X70D are decision-gated — the parser runs but `run` raises until POS mapping is confirmed, so **POS data is not in Odoo yet**. |
| **SAP / HRIS** | **NOW:** Odoo never speaks RFC/IDoc/Kafka. `SAP <-> Kafka <-> finance-sap-bridge <-- REST+HMAC --> Odoo`. Both adapters ship `status=disabled`, so the portal deliberately works before SAP is ready. Contracts: `services/finance-sap-bridge/app/contracts.md`. |
| **Kafka** | **NOW: mock.** `confluent-kafka` is an optional import; without `KAFKA_BOOTSTRAP` it degrades to a mock producer. **No broker in any compose file.** Do not design an event bus on it yet. |
| **Async** | **NOW:** `queue_job` (OCA, DB-backed) in 6 modules, loaded via `SERVER_WIDE_MODULES`. Redis is *not* a job broker. No RabbitMQ/Celery. |
| **HHT** | **NOW:** inbound PWA `/hht/` + `/api/hht/*`, per-device HMAC, offline queue idempotent on `(device_id, client_id)`. |
| **BI (Tableau/Metabase/…)** | **NOW: none.** `odoo_readonly` exists in `postgres/init/03-roles.sql` but is `NOLOGIN` and only granted on the `pdp` schema. No replica, no ODBC surface, no warehouse, no ETL. Greenfield. |

## Deployment topology

**NOW:** a single VPS runs everything (~15 containers). `docs/vps-demo-deploy.md`
and `docs/prod-deploy-checklist.md` both describe one host.

**TARGET:** production + separate redundant / database / reporting / backup hosts.

| Role | Status | Blocker |
| --- | --- | --- |
| PROD | exists, runs everything | all data paths are `./data/*` bind-mounts on one filesystem |
| DB | **not built** | `HOST: postgres` is hardcoded in `docker-compose.yml` and `docker-compose.multitenant.yml`; no `PG_HOST` env for the odoo service. pgbouncer is aspirational only. |
| REDUNDANT | **not built** | replication line is commented out in `postgres/pg_hba.conf`; no shared-state design |
| REPORTING | **not built** | `odoo_readonly` is NOLOGIN and pdp-scoped; no replica to point it at |
| BACKUP | **half** | `pg-backup-s3` is off by default; MinIO is on the same host writing the same disk, so "offsite" is nominal. **WAL archiving is not wired, so the real RPO is 24 h**, not the 1 h claimed in `docs/runbooks/disaster-recovery.md`. |

Constraints to respect when splitting:

1. **`odoo` and `odoo-mgmt` must share one Postgres cluster *and* the same
   `./data/odoo-filestore` mount.** Split them and assets 404. This limits how
   PROD may be divided.
2. `tenant-orchestrator/app/routers/vps.py` + `provisioner_ssh.py` already
   implement remote-VPS bootstrap over SSH but are **intentionally not registered**
   in `app/main.py` and stubbed by `PLATFORM_DEMO_MODE`. They clone the monolith
   per tenant — they do not split tiers.
3. `HOST_CPU_CORES` / `HOST_RAM_GB` / `HOST_DISK_GB` in `.env.example` are
   singular: the capacity model assumes one box.
4. Tenant VPS addons_path is **flat** (`/mnt/extra-addons`) in
   `tenant-orchestrator/bootstrap_templates/deploy_odoo.sh.template`, unlike the
   per-group path on the main host.

## Data flows

### Odoo → ai-gateway (HMAC)

1. `custom_ai_bridge` calls the `custom.ai` service (`chat()` / `recommend()`).
2. It signs the request with `custom_core`'s HMAC helper (**not** the adapter
   framework — a known inconsistency).
3. `ai-gateway` rejects on signature mismatch or >300 s drift, then calls the
   upstream provider (`AI_PROVIDER`: anthropic / openai / ollama).

### Retail import (Levi's)

1. XStore exports land in the FTPS drop folder (`./data/data_levis`, mounted at
   `/mnt/data_levis`) or are uploaded through the wizard.
2. `retail.import.profile` declares format, header row, column map, namespace.
3. `retail.import.wizard` previews (dry-run) and de-dupes by SHA256;
   `retail.import.executor` loads idempotently via `ir.model.data` external IDs.

### PDP audit insertion path

1. A model mixing in `pdp.audit.mixin` calls `self._pdp_log(...)`.
2. The row stores `prev_hash` and `row_hash = sha256(prev_hash || payload)`.
3. A Postgres `BEFORE UPDATE OR DELETE` trigger makes the table append-only.
4. A nightly cron walks the chain and alerts on a broken link.

Full mapping: `docs/pdp-compliance.md`.

## Reference

- Adding a vertical: `docs/adding-vertical.md`
- Per-project docs: `docs/projects/`
- Runbooks: `docs/runbooks/` · SOPs: `docs/sops/`
- Compliance: `docs/pdp-compliance.md`, `docs/coretax.md`
- Deploy: `docs/vps-demo-deploy.md`, `docs/prod-deploy-checklist.md`
