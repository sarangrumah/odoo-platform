# Finance Portal (SAP) — module suite

Odoo as a **system of engagement** in front of SAP S/4HANA (system of record).
Implements the "Finance Portal - Integration.xlsx" requirement: Cash Advance,
Reimbursement & Expenses, Vendor Invoice (PO / Non-PO Non-Trade), Perjalanan
Dinas settlement — each with **Tax → Finance** approval, budget/PR validation,
SAP push + status mirror, master-data sync, and SSO.

## Modules

| Module | Role |
|--------|------|
| `custom_finance_portal` | Engagement domain: documents + `finance.document.mixin` (no GL posting), master data, Tax→Finance approval (via `custom_approval_engine`), dashboards, vendor record rule |
| `custom_finance_budget` | Cost budget per division/year + `_check_document_budget` (soft enforce) |
| `custom_finance_portal_sap` | SAP/HRIS edge: `finance_sap_bridge`/`finance_hris_bridge` adapters, async push (`queue_job`), daily master sync cron, inbound `secure_endpoint('finance_sap')` webhook, `finance.sync.log` + Sync menu |
| `custom_finance_portal_sso` | Keycloak SSO (`auth_oauth`) + role→group mapping (employee vs vendor) |
| `services/finance-sap-bridge` | **Non-Odoo** sidecar: Kafka ⇄ HMAC-REST bridge (mock mode without Kafka) |

Install order is handled by `depends`; installing `custom_finance_portal_sap`
and `custom_finance_portal_sso` pulls the rest.

## Engagement lifecycle

`draft → submitted → (Tax review → Finance review) → approved → pushed → posted → paid`
(+ `rejected`/`cancelled`). Odoo **never posts a journal**; `_finance_push_to_sap`
sends the approved document to the bridge; the bridge mirrors SAP's payment-plan
date + status back via the webhook (`_finance_apply_sap_status`).

## Deploy (per tenant)

```bash
make install MODULE=custom_finance_portal_sap DB=<tenant>
make install MODULE=custom_finance_portal_sso DB=<tenant>
# restart the Odoo container (new Python is not re-imported by `make update` alone)
```

Then configure:

1. **Bridge**: deploy `services/finance-sap-bridge`; in Odoo set
   `custom.adapter.config` `finance_sap_bridge` `base_url` + the HMAC secret under
   `custom_finance_portal_sap.sap_bridge_secret`, flip status to *active*.
   Set the inbound webhook secret `custom_core.secure_endpoint.finance_sap.secret`
   (= bridge `BRIDGE_OUTBOUND_SECRET`). Enable the two sync crons.
2. **SSO**: enable the `Keycloak SSO` OAuth provider, set realm endpoints +
   client id (see `custom_finance_portal_sso/MODULE_KNOWLEDGE.md`).
3. **Approval**: create a `approval.matrix` on each document model with tier 1
   = Tax group, tier 2 = Finance group (no matrix ⇒ documents approve directly).

## External dependencies / gaps (client SAP & Kafka team)

These are flagged "Not Ready" in the spreadsheet and are **not** our Odoo build —
the suite is contract-first and runs in stub/mock until they land:

- SAP to expose **non-trade PR/PO/GR** with value + status (currently trade only).
- Kafka/SAP connectors for **GL posting, journal, MIRO, payment list, GL account/
  budget, master feeds** (item category, COA, cost budget, approval matrix).
- **Attachment** addon to SAP Basis; **PO/invoice approval status** from SAP.
- **HRIS** travel + employee-master API contract.

See `services/finance-sap-bridge/app/contracts.md` for the agreed JSON shapes and
topic map to build against.

## Industry pack (optional packaging)

To ship as a one-click bundle, add a `custom.hub.industry.pack` "Finance Portal
(SAP)" in `custom_hub_console` (`_SEED_PACK_MODULES` + `industry_pack_seed.xml`)
listing: `custom_finance_portal`, `custom_finance_budget`,
`custom_finance_portal_sap`, `custom_finance_portal_sso`, `custom_approval_engine`,
`custom_adapter_framework`, `queue_job`, `hr`, `account`, `auth_oauth`.
