---
status: override
module: custom_finance_portal
source: manifest + models/*.py
---

# custom_finance_portal

## Purpose
Makes Odoo a **system of engagement in front of SAP S/4HANA**, which stays the
system of record. Odoo runs the submission forms, the two-stage Tax Review →
Finance Review approval, and budget/PR validation. The approved document is
pushed to SAP by `custom_finance_portal_sap`; SAP posts the GL or MIRO and pays.

The design decision that matters to Finance: **Odoo never posts its own journal
entries here.** It mirrors SAP status back. Nothing in this module can create a
second version of the truth in the ledger.

## Business Flow
- A requester opens one of four document types, all built on `approval.mixin`
  and `pdp.audited.mixin`: Cash Advance (with its own realization document),
  Reimbursement, Vendor Invoice (PO Non-Trade and Non-PO Non-Trade, with a
  vendor portal), and Travel Settlement — the last being a read-only mirror of
  HRIS travel data, settled against the cash advance.
- On submission the document checks its division budget through
  `custom_finance_budget._check_document_budget` and the PR-required threshold
  held in `finance.limitation`.
- Approval runs Tax Review, then Finance Review, through the shared approval
  engine — the same delegation, out-of-office and SLA escalation rules the rest
  of the platform uses.
- On final approval the mixin calls `_finance_push_to_sap`. Out of the box that
  hook runs a **local stub**, so the portal is fully usable before the SAP and
  Kafka connectors exist. `custom_finance_portal_sap` overrides the hook to
  enqueue a real async push.
- SAP status flows back through `_finance_apply_sap_status`, again stubbed until
  the bridge is live.

## Key Models
- `finance.document.mixin` — the shared spine: state, approval wiring, the
  `_finance_push_to_sap` / `_finance_apply_sap_status` hooks, PDP audit.
- `finance.cash.advance` + `finance.cash.advance.line`, and
  `finance.cash.advance.realization` + its line — request and settlement.
- `finance.reimbursement` + `finance.reimbursement.line` — reimbursement and
  expense claims.
- `finance.vendor.invoice` + `finance.vendor.invoice.line` — vendor-submitted
  invoices for MIRO.
- `finance.travel.settlement` — HRIS travel mirror settled against a cash advance.
- `finance.synced.mixin` — records that carry an SAP external identifier.
- Master data: `finance.submission.type`, `finance.invoice.type`,
  `finance.invoice.routine.type`, `finance.item.submission`, `finance.vertical`
  (division), `finance.limitation` (per-type thresholds incl. PR-required).

## Important Fields
- `finance.limitation` thresholds — decide when a purchase requisition becomes
  mandatory; the single most commonly reconfigured record in the module.
- `finance.vertical` — the division axis every budget check and approval matrix
  resolves against.
- `x_sap_external_id` (via `finance.synced.mixin`) — the idempotency key for
  every push and pull against SAP.
