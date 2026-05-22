# ============================================================
# Odoo 19 Platform — operational shortcuts
# ============================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE_BASE := docker compose -f docker-compose.yml
COMPOSE_DEV  := $(COMPOSE_BASE) -f docker-compose.dev.yml
COMPOSE_PROD := $(COMPOSE_BASE) -f docker-compose.prod.yml
COMPOSE_OBS  := -f docker-compose.observability.yml
COMPOSE_LLM  := -f docker-compose.local-llm.yml
COMPOSE_TLS  := -f docker-compose.tls-acme.yml
COMPOSE_MT   := -f docker-compose.multitenant.yml

SERVICE ?= odoo
MODULE  ?= custom_core
DB      ?= odoo_dev
FILE    ?=
IMAGE   ?=
SLUG    ?=
NAME    ?=
PLAN    ?= standard
EMAIL   ?=
KIND    ?= manual
S3_KEY  ?=
TARGET_DB ?=

# ----- Help -----
.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n",$$1,$$2}'

# ----- Bring up / down -----
.PHONY: up up-dev up-prod up-obs up-all up-llm up-tls down stop restart
up: up-dev ## Alias for up-dev

up-dev: ## Start base + dev override (hot reload, pgadmin, mailpit)
	$(COMPOSE_DEV) up -d --build

up-prod: ## Start base + prod override (nginx, hardened, multi-worker)
	$(COMPOSE_PROD) up -d --build

up-obs: ## Start base + observability (prometheus, grafana, loki, alertmanager, exporters, predictor)
	$(COMPOSE_DEV) $(COMPOSE_OBS) up -d --build

up-all: ## Start base + dev + observability + local LLM
	$(COMPOSE_DEV) $(COMPOSE_OBS) $(COMPOSE_LLM) up -d --build

up-llm: ## Start with local Ollama (profile local-llm)
	$(COMPOSE_DEV) $(COMPOSE_LLM) up -d --build

up-tls: ## Start with Caddy ACME (set DOMAIN+ACME_EMAIL in .env first)
	$(COMPOSE_PROD) $(COMPOSE_TLS) up -d --build

up-multitenant: ## Start multi-tenant stack (Caddy wildcard + orchestrator + MinIO)
	$(COMPOSE_BASE) $(COMPOSE_MT) $(COMPOSE_OBS) up -d --build

down: ## Stop all (keep volumes)
	$(COMPOSE_DEV) $(COMPOSE_OBS) $(COMPOSE_LLM) $(COMPOSE_TLS) $(COMPOSE_MT) -f docker-compose.prod.yml down

stop: ## Stop services
	$(COMPOSE_DEV) stop

restart: ## Restart a service: make restart SERVICE=odoo
	$(COMPOSE_DEV) restart $(SERVICE)

# ----- Logs / shell -----
.PHONY: logs shell-odoo shell-pg psql shell-ai
logs: ## Tail logs: make logs SERVICE=odoo
	$(COMPOSE_DEV) logs -f --tail=200 $(SERVICE)

shell-odoo: ## Bash into Odoo container
	$(COMPOSE_DEV) exec odoo bash

shell-pg: ## Bash into Postgres container
	$(COMPOSE_DEV) exec postgres bash

psql: ## psql as POSTGRES_USER
	$(COMPOSE_DEV) exec postgres psql -U $${POSTGRES_USER:-odoo}

shell-ai: ## Bash into AI gateway container
	$(COMPOSE_DEV) exec ai-gateway bash

# ----- Odoo lifecycle -----
.PHONY: init-db update install drop-db
init-db: ## Initialize DB: make init-db DB=erp_dev
	$(COMPOSE_DEV) exec odoo odoo -d $(DB) --without-demo=all --stop-after-init --no-http -i base

install: ## Install module: make install MODULE=custom_core DB=erp_dev
	$(COMPOSE_DEV) exec odoo odoo -d $(DB) -i $(MODULE) --stop-after-init --no-http

update: ## Update module: make update MODULE=custom_core DB=erp_dev
	$(COMPOSE_DEV) exec odoo odoo -d $(DB) -u $(MODULE) --stop-after-init --no-http

drop-db: ## Drop DB (careful): make drop-db DB=erp_dev
	$(COMPOSE_DEV) exec postgres dropdb -U $${POSTGRES_USER:-odoo} --if-exists $(DB)

# ----- DevSecOps -----
.PHONY: pre-commit scan scan-secret scan-image scan-fs sast sbom
pre-commit: ## Run all pre-commit hooks
	pre-commit run --all-files

scan: scan-fs scan-image scan-secret ## Run all scans (fs + image + secret)

scan-fs: ## Trivy filesystem scan
	trivy fs --severity HIGH,CRITICAL --exit-code 0 .

scan-image: ## Trivy image scan on built images
	@for img in odoo19-platform-odoo odoo19-platform-ai-gateway odoo19-platform-custom-predictor; do \
	  echo "=== Scanning $$img ==="; \
	  trivy image --severity HIGH,CRITICAL --exit-code 0 $$img:latest; \
	done

scan-secret: ## Gitleaks secret scan
	gitleaks detect --redact --verbose --no-banner

sast: ## Semgrep SAST with custom Odoo rules
	semgrep --config .semgrep/odoo-rules.yml --config p/python --config p/owasp-top-ten --error .

sbom: ## Generate SBOM (CycloneDX) for python services
	cyclonedx-py environment -o sbom-odoo.json --of JSON odoo/ || true
	cyclonedx-py environment -o sbom-ai-gateway.json --of JSON ai-gateway/ || true

# ----- Secrets (SOPS) -----
.PHONY: encrypt-env decrypt-env dev-bootstrap
encrypt-env: ## Encrypt .env to .secrets.enc.yaml (requires age key in SOPS_AGE_KEY_FILE)
	sops --encrypt --age $${SOPS_AGE_RECIPIENT} .env > .secrets.enc.yaml

decrypt-env: ## Decrypt .secrets.enc.yaml to .secrets.dec.yaml (gitignored)
	sops --decrypt .secrets.enc.yaml > .secrets.dec.yaml

dev-bootstrap: ## Generate dev certs + age keypair
	bash scripts/dev-bootstrap.sh

# ----- Backup / restore -----
.PHONY: backup restore backup-now
backup: ## pg_dump all DBs to data/backups/
	@mkdir -p data/backups
	$(COMPOSE_DEV) exec postgres bash -c 'pg_dumpall -U $${POSTGRES_USER:-odoo} | gzip' > data/backups/dumpall-$$(date +%Y%m%d-%H%M%S).sql.gz
	@echo "Backup written to data/backups/"

restore: ## Restore: make restore FILE=data/backups/dumpall-xxx.sql.gz
	@test -n "$(FILE)" || (echo "FILE= required" && exit 1)
	gunzip -c $(FILE) | $(COMPOSE_DEV) exec -T postgres psql -U $${POSTGRES_USER:-odoo} postgres

backup-now: ## Trigger immediate backup (requires backup sidecar running)
	@echo "Triggering immediate S3 backup via pg-backup-s3 sidecar..."
	$(COMPOSE_PROD) exec pg-backup-s3 sh -c '/backup.sh' || \
	  $(COMPOSE_PROD) exec pg-backup-s3 sh -c '/scripts/backup.sh' || \
	  (echo "Falling back to local backup container..." && $(COMPOSE_PROD) exec pg-backup-local sh -c '/backup.sh')
	@echo "Backup complete. Verify with: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50 pg-backup-s3"

# ----- Image signing -----
.PHONY: sign
sign: ## Sign an image with cosign keyless OIDC: make sign IMAGE=ghcr.io/.../odoo:tag
	@test -n "$(IMAGE)" || (echo "IMAGE= required" && exit 1)
	cosign sign --yes $(IMAGE)

# ----- Verification -----
.PHONY: verify-audit-chain test-gateway
verify-audit-chain: ## Verify PDP audit log hash chain integrity
	$(COMPOSE_DEV) exec postgres psql -U $${POSTGRES_USER:-odoo} -d $(DB) -f /docker-entrypoint-initdb.d/../verify_audit_chain.sql

test-gateway: ## Run AI gateway tests
	$(COMPOSE_DEV) exec ai-gateway pytest -v

test-orchestrator: ## Run tenant-orchestrator tests
	$(COMPOSE_BASE) exec tenant-orchestrator python -m pytest -v

# ============================================================
# Multi-tenant operations (P0)
# ============================================================
.PHONY: tenant-list tenant-provision tenant-suspend tenant-resume tenant-archive \
        tenant-backup tenant-list-backups tenant-restore tenant-verify-chain \
        init-master-admin rotate-orchestrator-pwd

tenant-list: ## List all tenants
	./scripts/orchestrator-call.sh GET /v1/tenants | python3 -m json.tool

tenant-provision: ## Provision tenant: make tenant-provision SLUG=acme NAME="Acme Corp" [PLAN=standard] [EMAIL=...]
	@test -n "$(SLUG)" || (echo "SLUG= required" && exit 1)
	@test -n "$(NAME)" || (echo "NAME= required" && exit 1)
	./scripts/tenant-provision.sh "$(SLUG)" "$(NAME)" "$(PLAN)" "$(EMAIL)"

tenant-suspend: ## Suspend tenant: make tenant-suspend SLUG=acme
	@test -n "$(SLUG)" || (echo "SLUG= required" && exit 1)
	./scripts/orchestrator-call.sh POST /v1/tenants/$(SLUG)/suspend '{}' | python3 -m json.tool

tenant-resume: ## Resume tenant: make tenant-resume SLUG=acme
	@test -n "$(SLUG)" || (echo "SLUG= required" && exit 1)
	./scripts/orchestrator-call.sh POST /v1/tenants/$(SLUG)/resume '{}' | python3 -m json.tool

tenant-archive: ## Archive tenant (30d purge window): make tenant-archive SLUG=acme
	@test -n "$(SLUG)" || (echo "SLUG= required" && exit 1)
	./scripts/orchestrator-call.sh DELETE /v1/tenants/$(SLUG) '{"retention_days":30}' | python3 -m json.tool

tenant-backup: ## Manual backup: make tenant-backup SLUG=acme [KIND=manual]
	@test -n "$(SLUG)" || (echo "SLUG= required" && exit 1)
	./scripts/tenant-backup.sh "$(SLUG)" "$(KIND)"

tenant-list-backups: ## List a tenant's backups: make tenant-list-backups SLUG=acme
	@test -n "$(SLUG)" || (echo "SLUG= required" && exit 1)
	./scripts/tenant-list-backups.sh "$(SLUG)"

tenant-restore: ## Restore a backup to staging: make tenant-restore SLUG=acme S3_KEY=acme/2026/05/17/... [TARGET_DB=acme_staging]
	@test -n "$(SLUG)" || (echo "SLUG= required" && exit 1)
	@test -n "$(S3_KEY)" || (echo "S3_KEY= required" && exit 1)
	./scripts/tenant-restore.sh "$(SLUG)" "$(S3_KEY)" "$(TARGET_DB)"

tenant-verify-chain: ## Verify tenant_registry.action_log hash chain
	./scripts/verify-tenant-chain.sh && echo "✓ Chain intact" || echo "✗ Chain has breaks"

init-master-admin: ## Bootstrap master_admin DB (run once after first `make up-multitenant`)
	$(COMPOSE_BASE) exec odoo odoo -d master_admin --without-demo=all --stop-after-init -i custom_super_admin

rotate-orchestrator-pwd: ## Rotate tenant_orchestrator role password to current env value
	@test -n "$$PG_ORCHESTRATOR_PASSWORD" || (echo "Set PG_ORCHESTRATOR_PASSWORD in .env" && exit 1)
	$(COMPOSE_BASE) exec -T postgres psql -U $${POSTGRES_USER:-odoo} -d $${POSTGRES_DB:-postgres} \
	  -c "ALTER ROLE tenant_orchestrator WITH LOGIN PASSWORD '$$PG_ORCHESTRATOR_PASSWORD';"
	@echo "✓ Password rotated. Restart orchestrator: docker compose restart tenant-orchestrator"

# ============================================================
# P4 — Production hardening (load, chaos, compliance)
# ============================================================
.PHONY: load-smoke load-mixed load-provisioning \
        chaos-postgres chaos-redis chaos-ai-gateway chaos-orchestrator \
        chaos-fill-disk chaos-pajakku \
        compliance-verify capacity-tune dr-drill-snapshot

load-smoke: ## k6 read-only smoke (5 VUs / 30s)
	k6 run --vus 5 --duration 30s tests/load/k6/read_only.js

load-mixed: ## k6 full mixed scenario (500 VUs / 30 min, 60/30/10 read/write/report)
	k6 run tests/load/k6/mixed_scenario.js

load-provisioning: ## k6 parallel tenant provisioning (10 VUs)
	k6 run tests/load/k6/provisioning.js

chaos-postgres: ## Drill: kill postgres, verify Odoo reconnect + no data loss
	./scripts/chaos/kill-postgres.sh

chaos-redis: ## Drill: kill redis, verify ai-gateway rate-limit fails open
	./scripts/chaos/kill-redis.sh

chaos-ai-gateway: ## Drill: kill ai-gateway, verify Odoo degrades gracefully
	./scripts/chaos/kill-ai-gateway.sh

chaos-orchestrator: ## Drill: kill tenant-orchestrator, verify tenants stay up
	./scripts/chaos/kill-orchestrator.sh

chaos-fill-disk: ## Drill: fill disk briefly, verify era-predictor alert
	./scripts/chaos/fill-disk.sh

chaos-pajakku: ## Drill: block Pajakku network, verify circuit breaker opens
	./scripts/chaos/kill-pajakku-network.sh

compliance-verify: ## Run all SOC2-style automated checks; report at docs/compliance/_last_verify.json
	./scripts/compliance/verify_all.sh

capacity-tune: ## Snapshot capacity prediction accuracy; weekly cron helper
	./scripts/capacity/tune_predictor.sh

dr-drill-snapshot: ## Take a forensic snapshot before running a DR drill
	@mkdir -p data/forensic
	$(COMPOSE_BASE) exec -T postgres pg_dumpall -U $${POSTGRES_USER:-odoo} | gzip > \
	  data/forensic/dumpall-$$(date +%Y%m%dT%H%M%SZ).sql.gz
	@echo "Snapshot saved. Run drills, then compare via 'gunzip -c data/forensic/<latest>.sql.gz | head'"
