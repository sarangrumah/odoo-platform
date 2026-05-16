# Odoo 19 Platform

A Docker-based foundation for Odoo Community Edition 19 with five additional layers on top of vanilla Odoo:

1. **EE-Gap modules** — custom modules that close the feature gap between Odoo CE and Enterprise (Accounting full, HR Payroll/Appraisal/Referral, Marketing Automation, Studio-lite, Helpdesk, Field Service, Documents, Sign, Subscription, Rental, MRP PLM, Quality, IoT, VoIP, Appointments, Social, Planning).
2. **AI Intelligence** — sidecar `ai-gateway` (FastAPI) providing chat / embedding / workflow-recommendation / capacity-prediction across Claude, OpenAI, and local Ollama via env switch.
3. **Indonesian compliance** — UU 27/2022 (PDP): classification, consent, DSAR, masking, audit log immutable, retention. Coretax DJP: XML export per 31 official templates, bukti potong import, NSFP 17-digit (per PER-11/PJ/2025), sertel encrypted storage.
4. **DevSecOps active day-1** — pre-commit (gitleaks/ruff/bandit/hadolint), GitHub Actions (Semgrep/pip-audit/Trivy/cosign), SOPS-encrypted secrets, CIS-hardened containers.
5. **Observability + predictive** — Prometheus + Grafana + Loki + Alertmanager + exporters, plus `custom-predictor` sidecar that uses the AI gateway to recommend hardware upgrades from 7-day metric trends.

## Quickstart (dev)

```bash
cp .env.example .env
# edit .env — replace every `changeme` value
make up
```

Then:

- Odoo: http://localhost:18069
- AI gateway health: http://localhost:18080/health
- Grafana: http://localhost:13000 (after `make up-obs`)
- pgAdmin: http://localhost:15050
- Mailpit: http://localhost:18025

## Common commands

```bash
make help              # list all targets
make up-prod           # start prod stack (nginx, multi-worker)
make up-obs            # start with observability
make up-all            # base + dev + observability + local LLM
make scan              # trivy + gitleaks
make pre-commit        # run all pre-commit hooks
make backup            # pg_dumpall to data/backups/
make logs SERVICE=odoo
make update MODULE=custom_core DB=erp_dev
```

## Project layout

See [docs/architecture.md](docs/architecture.md).

## Adding a vertical

See [docs/adding-vertical.md](docs/adding-vertical.md). Fork `addons/verticals/_template/`.

## Compliance

- [docs/pdp-compliance.md](docs/pdp-compliance.md) — UU PDP implementation
- [docs/coretax.md](docs/coretax.md) — Coretax XML export/import

## Ports (default — override in `.env`)

| Service        | Host  |
|----------------|-------|
| Odoo HTTP      | 18069 |
| Odoo longpoll  | 18072 |
| PostgreSQL     | 15432 |
| Redis          | 16379 |
| AI Gateway     | 18080 |
| custom-predictor  | 18090 |
| Prometheus     | 19090 |
| Grafana        | 13000 |
| Loki           | 13100 |
| Alertmanager   | 19093 |
| pgAdmin (dev)  | 15050 |
| Mailpit (dev)  | 18025 / 11025 |
| Nginx (prod)   | 18000 / 18443 |
| Ollama (opt)   | 11434 |

## License

LGPL-3 (matches Odoo CE).
