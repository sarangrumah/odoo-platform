---
status: override
module: custom_finance_budget
source: manifest + models/finance_budget.py
---

# custom_finance_budget

## Purpose
A read-only **cost budget reference per division, cost centre and period**,
synced from SAP by `custom_finance_portal_sap`. Its whole job is to answer one
question at submission time: would this Finance Portal document overspend its
division's remaining budget?

## Business Flow
- `custom_finance_portal_sap`'s daily master-data pull writes `finance.budget`
  rows. Nothing in Odoo edits them by hand — SAP owns the number.
- `finance.document.mixin` calls `_check_document_budget` when a document is
  submitted. The check resolves the document's division and period, sums what is
  already committed, and compares against the budget row.
- **Enforcement is soft by design.** When no matching budget row exists — the
  usual state before the SAP feed goes live for a division — the check passes.
  The portal stays usable rather than blocking every submission on missing
  reference data.
- Hard blocking is a switch: `ir.config_parameter` `custom_finance_budget.enforce`,
  default `1`.
- `custom_approval_engine_budget` builds on the same check to block a **non-PO
  vendor bill** that would overspend its division budget — the one place the
  budget reaches outside the Finance Portal.

## Key Models
- `finance.budget` — one row per division / cost centre / period, holding the
  budgeted amount and the SAP identifier it came from.

## Important Fields
- `finance.budget.vertical_id` — the division the budget belongs to; the join
  key for every check.
- Config parameter `custom_finance_budget.enforce` — `1` blocks, `0` warns. The
  single most consequential setting in the module.
