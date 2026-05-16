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

SERVICE ?= odoo
MODULE  ?= custom_core
DB      ?= odoo_dev
FILE    ?=
IMAGE   ?=

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

down: ## Stop all (keep volumes)
	$(COMPOSE_DEV) $(COMPOSE_OBS) $(COMPOSE_LLM) $(COMPOSE_TLS) -f docker-compose.prod.yml down

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
	$(COMPOSE_DEV) exec odoo odoo -d $(DB) --without-demo=all --stop-after-init -i base

install: ## Install module: make install MODULE=custom_core DB=erp_dev
	$(COMPOSE_DEV) exec odoo odoo -d $(DB) -i $(MODULE) --stop-after-init

update: ## Update module: make update MODULE=custom_core DB=erp_dev
	$(COMPOSE_DEV) exec odoo odoo -d $(DB) -u $(MODULE) --stop-after-init

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
