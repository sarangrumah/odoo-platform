---
status: override
module: custom_finance_portal_sap
source: manifest + models/*.py + controllers/
---

# custom_finance_portal_sap

## Purpose
The Odoo side of the SAP/HRIS edge. **Odoo never speaks Kafka directly.** It
speaks HMAC-signed REST to a bridge microservice
(`services/finance-sap-bridge/`) that consumes and produces Kafka on its behalf.
That indirection is what lets the Finance Portal ship and be used before SAP
integration exists.

## Business Flow
- The module registers two adapters — `finance_sap_bridge` and
  `finance_hris_bridge` — on `custom_adapter_framework`, inheriting its circuit
  breaker, HMAC signing, retry with backoff, and append-only call log.
- It overrides `finance.document.mixin._finance_push_to_sap` to enqueue a
  `queue_job` that pushes an approved document: cash-advance GL posting, journal
  posting, reimbursement GL posting, or invoice-for-MIRO depending on the type.
- A daily scheduler pulls master data — chart of accounts, cost budget,
  supplier, item category, division/vertical — and upserts idempotently keyed on
  `x_sap_external_id`.
- An inbound `@secure_endpoint('finance_sap')` webhook lets the bridge mirror
  the planned payment date and payment status back in near-real time.
- Every push and pull is written to `finance.sync.log`, which drives a Sync menu
  operators can read without database access.
- **Degradation is deliberate:** with no enabled `custom.adapter.config` the
  push falls back to the local stub and the crons no-op. Both adapters ship
  `status=disabled`.

## Key Models
- `finance.sync.log` — append-only record of every push and pull, with payload
  reference, direction, state and error text.
- `finance.document.mixin` (inherited) — the push hook is replaced here.

Adapter registration (`models/finance_sap_adapter.py`) and the per-document SAP
field extension (`models/finance_document_sap.py`) add behaviour to existing
models rather than declaring new ones.

## Important Fields
- `custom.adapter.config.status` — the master switch. While `disabled`, the
  portal runs standalone and nothing leaves the database.
- `finance.sync.log.state` — the field operators watch when a document appears
  approved in Odoo but unpaid in SAP.
- `x_sap_external_id` — the upsert key on every synced master-data record.

## Endpoints
- `POST /finance/sap/master` — master-data delivery from the bridge.
- `POST /finance/sap/status` — payment/posting status mirror.
Both sit behind the platform HMAC contract: timestamp plus raw body, ±300 s
drift, Redis-backed nonce replay guard, CIDR allow-list.
