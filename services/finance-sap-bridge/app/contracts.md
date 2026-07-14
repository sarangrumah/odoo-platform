# Bridge contracts — topic map & payload shapes

Contract-first: Odoo + bridge are built against these shapes so work proceeds
before the SAP/Kafka connectors are "Ready" (see the spreadsheet readiness flags).

## Kafka topics

| Direction | Topic | Producer | Consumer |
|-----------|-------|----------|----------|
| Portal → SAP | `portal.to-sap.cash_advance` | bridge | SAP connector |
| Portal → SAP | `portal.to-sap.cash_advance_realization` | bridge | SAP connector |
| Portal → SAP | `portal.to-sap.reimbursement` | bridge | SAP connector |
| Portal → SAP | `portal.to-sap.vendor_invoice` (→ MIRO) | bridge | SAP connector |
| SAP → Portal | `sap.to-portal.status` (payment plan + status) | SAP connector | bridge |
| SAP → Portal | `sap.to-portal.master.<kind>` | SAP connector | bridge |
| HRIS → Portal | `hris.to-portal.travel` | HRIS connector | bridge |

`<kind>` ∈ `division, item_category, supplier, budget, coa, cost_center, bank,
approval_matrix, finance_approval_matrix, business_plant, user, user_role`.

## Document push (Odoo → bridge → SAP)

`POST /from-odoo/finance/push` — body is `finance.document.mixin._finance_sap_payload()`:

```json
{
  "doc_type": "finance.cash.advance",
  "reference": "CA/2026/00001",
  "company": "PT Example",
  "requester": "Budi",
  "division": "FIN",
  "amount": 5000000,
  "currency": "IDR",
  "pr_number": "PR-001",
  "po_number": "",
  "lines": [
    {"item": "MEAL", "gl_account": "6101", "cost_center": "CC10",
     "amount": 5000000, "description": "Meal allowance"}
  ]
}
```

## Status mirror (SAP → bridge → Odoo)

`POST /finance/sap/status` — consumed by `finance.sync.log._apply_status_in`:

```json
{
  "doc_model": "finance.cash.advance",
  "doc_ref": "CA/2026/00001",
  "sap_document_no": "4900012345",
  "sap_payment_plan_date": "2026-07-01",
  "sap_payment_status": "scheduled"
}
```

`sap_payment_status` ∈ `pending | scheduled | paid | failed`.

## Master delta (SAP/HRIS → bridge → Odoo)

`POST /finance/sap/master` — handled by `finance.sync.log._upsert_<kind>`:

```json
{ "kind": "supplier",
  "records": [ {"id": "SAP-VEND-1", "code": "V001", "name": "Vendor A"} ] }
```

Every record MUST carry a stable `id` → stored as `x_sap_external_id` for
idempotent upsert.
