# finance-sap-bridge

The Kafka ⇄ Odoo bridge for the Finance Portal. Odoo never speaks Kafka; it
speaks **HMAC-signed REST** to this sidecar, which consumes/produces the SAP and
HRIS Kafka topics. Mirrors the WhatappHub/orchestrator microservice pattern.

```
SAP S/4HANA  <->  Kafka  <->  [ finance-sap-bridge ]  <--HMAC REST-->  Odoo
HRIS         <->  Kafka  <->        (this service)
```

## Responsibilities

- **Portal → SAP**: receive `POST /from-odoo/push` (the approved document
  payload from `custom_finance_portal_sap`), validate HMAC, produce to the
  `portal.to-sap.<doctype>` topic. On SAP ack (consumed from `sap.to-portal.ack`)
  call Odoo `POST /finance/sap/status`.
- **SAP → Portal**: consume `sap.to-portal.status` / `sap.to-portal.master.*`,
  translate and call Odoo `POST /finance/sap/status` or `/finance/sap/master`.
- **HRIS → Portal**: consume `hris.to-portal.travel`, call Odoo `/finance/sap/master`
  (`kind=travel`).
- **Master pull (request/reply)**: serve `POST /from-odoo/finance/master/<kind>`
  and `/from-odoo/finance/pr/lookup` by querying SAP (Kafka request/reply or SAP
  OData) and returning the records inline.
- Cross-cutting: **idempotency** (dedup by message key), **dead-letter queue**,
  **replay**, schema mapping, structured logging, `/health`.

## HMAC contract (symmetric with Odoo)

Canonical string = `f"{timestamp}".encode() + raw_body_bytes`; signature =
`HMAC_SHA256(secret, canonical).hexdigest()`. Headers `X-Timestamp` (unix secs),
`X-Signature` (hex). Drift tolerance ±300s. This is byte-identical to
`custom_core.controllers.secure_endpoint` (inbound to Odoo) and
`custom_adapter_framework.BaseAdapter._build_headers` (outbound from Odoo), so
both directions share one secret per scope.

- Odoo → bridge secret: `custom_finance_portal_sap.sap_bridge_secret` (Odoo side)
  must equal `BRIDGE_INBOUND_SECRET` (bridge side).
- bridge → Odoo secret: `BRIDGE_OUTBOUND_SECRET` (bridge) must equal
  `custom_core.secure_endpoint.finance_sap.secret` (Odoo side).

## Run

```bash
pip install -r requirements.txt
cp .env.example .env   # set ODOO_BASE_URL, secrets, KAFKA_BOOTSTRAP
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Without `confluent-kafka` installed (or `KAFKA_BOOTSTRAP` unset) the Kafka layer
runs in **mock mode**: `/from-odoo/*` still validates HMAC and echoes, so the
Odoo↔bridge contract can be tested end-to-end before the real bus exists.

See `app/contracts.md` for the topic map and JSON payload shapes.
