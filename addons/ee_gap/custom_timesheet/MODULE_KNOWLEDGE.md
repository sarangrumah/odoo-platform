---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_timesheet
manifest_version: 19.0.0.2.0
---

# custom_timesheet

## Purpose
EE-equivalent extensions on top of CE `hr_timesheet` + `project` + `sale_timesheet`: per-line billable flag with per-line billing rate, draft→submitted→validated workflow gated by `custom_approval_engine`, overtime hours computation (anything above 8h/day), OT-to-payroll bridge via `hr.work.entry`, customer-invoice wizard that bulk-creates a draft `account.move` from selected validated billable lines, and an AI weekly summary per project (`custom.timesheet.weekly.summary`) bridged to `custom.ai`.

## Business Flow
- Employee logs hours by creating `account.analytic.line` (CE timesheet entry) with `unit_amount` (hours), `project_id`, `task_id`. New fields default: `x_billable=False`, `x_validation_state='draft'`.
- `_compute_overtime_hours` derives `x_overtime_hours = max(0, unit_amount - 8.0)` (constant `STANDARD_DAILY_HOURS=8.0`).
- Validation workflow on the line:
  - `action_submit_validation()` — draft → submitted; calls `action_request_approval()` from `approval.mixin`. If no approval matrix matches (UserError), auto-validates → `validated`.
  - `action_validate()` — gates via `_approval_check_required()` (engine-side); on pass → `validated`.
  - `action_reset_to_draft()` — back to draft; **blocks if `x_billed_invoice_line_id` is set** (already invoiced).
- OT → payroll: `action_create_overtime_work_entry()` on a validated line with `x_overtime_hours > 0`:
  - Ensures `hr.work.entry.type` code='OT' exists (creates `display_code='OT'` too).
  - Cancels previous work entry if re-run (idempotent).
  - Creates `hr.work.entry` (`state='draft'`, `duration=x_overtime_hours`, `date_start = date 17:00`, `date_stop = date_start + OT hours`).
  - Stores back-link on `x_overtime_work_entry_id`; optional `x_source_timesheet_id` on work entry if field exists.
- Billable invoicing: user opens `sale.order` form; `x_billable_timesheet_pending_count` is computed by counting analytic lines with `x_billable=True`, `x_validation_state='validated'`, no `x_billed_invoice_line_id`, on the SO's order_line.
- `action_open_invoice_timesheet_wizard()` launches `custom.timesheet.invoice.wizard` (Transient): user picks date range; `_onchange_filters` populates `line_ids` from domain (billable, validated, not billed, in range, matching `so_line` or partner). User toggles `selected` per line and clicks `action_create_invoice()`:
  - Builds invoice line vals using `billing_rate || aal.x_billing_rate` as `price_unit`, `unit_amount` as `quantity`.
  - Resolves `product_id` from `aal.so_line.product_id` if present.
  - Creates an `account.move` (`move_type='out_invoice'`, draft) and links each analytic line's `x_billed_invoice_line_id` to its invoice line.
- AI weekly summary: HR/PM creates a `custom.timesheet.weekly.summary` per (project, week_start) — unique constraint. `_compute_aggregates` populates `total_hours`, `billable_hours`, `overtime_hours`, `line_count` from analytic lines in `[week_start, week_end]`. `action_ai_summarize()` collects payload (project metadata + up to 200 line `_custom_ai_payload()` dicts) and calls `custom.ai._recommend(model, res_id, payload)`; the response's `summary`/`response`/`text` is stored in `summary_html` and chatter-posted. State → `summarized`.
- `unlink` on analytic line cancels the linked OT work entry first.

## Key Models
- `account.analytic.line` (inherited) — Adds billable flag, billing rate/currency, OT hours, billed-invoice link, OT work entry link, validation state. Mixes in `mail.thread` + `approval.mixin`.
- `custom.timesheet.weekly.summary` — Per (project, week) AI summary row; unique `(project_id, week_start, company_id)`.
- `custom.timesheet.invoice.wizard` (Transient) + `custom.timesheet.invoice.wizard.line` (Transient).
- `sale.order` (inherited) — Adds `x_billable_timesheet_pending_count` and the invoice-wizard launcher action.

## Important Fields
- `account.analytic.line.x_billable` (Boolean, default False, tracked).
- `account.analytic.line.x_billing_rate` (Monetary, currency_field=`x_billing_currency_id`) — per-line override.
- `account.analytic.line.x_billing_currency_id` (M2o `res.currency`, default company currency).
- `account.analytic.line.x_overtime_hours` (Float, computed, stored) — `max(0, unit_amount - 8.0)`.
- `account.analytic.line.x_validation_state` (Selection: draft/submitted/validated, tracked) — only validated lines may be invoiced or fed to payroll.
- `account.analytic.line.x_billed_invoice_line_id` (M2o `account.move.line`, readonly) — set by the invoice wizard.
- `account.analytic.line.x_overtime_work_entry_id` (M2o `hr.work.entry`, readonly) — set by OT bridge.
- `custom.timesheet.weekly.summary.week_start` (Date, required) — ISO Monday; `week_end = week_start + 6 days`.
- `custom.timesheet.weekly.summary.summary_html` (Html, sanitised, tracked) — AI output wrapped in `<div class='o_ai_summary'>`.
- `custom.timesheet.weekly.summary.state` (Selection: draft/summarized).

## Public Methods
- `account.analytic.line.action_submit_validation()` — draft → submitted (auto-validates on no matrix).
- `account.analytic.line.action_validate()` — Engine-gated → validated.
- `account.analytic.line.action_reset_to_draft()` — Blocks if already invoiced.
- `account.analytic.line.action_create_overtime_work_entry()` — OT → `hr.work.entry`; idempotent.
- `account.analytic.line._custom_ai_payload()` — Per-line dict (date, employee, project, task, hours, OT, billable, description) for AI summary.
- `custom.timesheet.weekly.summary.action_ai_summarize()` — Call `custom.ai`, fill summary_html, set state.
- `custom.timesheet.weekly.summary._build_for_project_week(project_id, week_start)` (`@api.model`) — Get-or-create + refresh.
- `custom.timesheet.invoice.wizard.action_preview()` / `action_create_invoice()` — Wizard actions.
- `sale.order.action_open_invoice_timesheet_wizard()` — Open wizard pre-filled with SO + partner.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `custom_approval_engine`, `custom_ai_bridge`, `hr_timesheet`, `project`, `account`, `sale_management`, `sale_timesheet`, `hr_work_entry`, `custom_hr_payroll_id`, `mail`.
- **Inherits from:** `account.analytic.line` (+ `mail.thread`, `approval.mixin`), `sale.order`.
- **Extended by:** none in-tree.
- **External calls:** `custom.ai._recommend` for weekly summaries.
- **Cross-vertical:** generic professional-services capability; not Indonesia-specific.

## Gotchas
- **`STANDARD_DAILY_HOURS=8.0` is module-level constant** — not configurable per company / role / employee. A part-time employee with a 4h day will not see "OT above 4h".
- **OT work entry `date_start` is hardcoded to 17:00** — irrespective of actual check-in/clock-out; this is a synthetic time window. Real overtime timing comes from `custom_attendance` if used.
- **Validation auto-bypass on missing matrix** — `action_submit_validation` swallows the engine's UserError and auto-promotes to validated. If the approval matrix is misconfigured (no rows at all), all timesheets self-validate.
- **`_compute_overtime_hours` triggers only on `unit_amount`** — splitting a 10h day into two 5h lines yields zero OT each.
- **Invoice wizard uses `zip(analytic_lines, inv_lines)`** to link back — relies on ordering being preserved through `account.move.create`. Risky if Odoo re-orders.
- **`partner_id` filter in wizard domain** uses `aal.partner_id OR aal.so_line.order_partner_id` (OR'd via prefix domain operator) — analytic lines without either field set won't match by partner.
- **Cross-line OT work entry has no awareness of attendance** — if both `custom_attendance` and this module create OT work entries for the same day, duplicates can result.
- **`approval.mixin._approval_check_required()` raises UserError** if the matrix gates it; `action_validate` re-raises (intentional). Operators must clear approval before forced validation.
- **Currency on the analytic line is `x_billing_currency_id`** but the company's currency is used for the invoice; FX conversion is not handled.
- **Weekly summary payload truncated at 200 lines** (`lines[:200]`) — long-running projects with > 200 entries/week get partial input to AI.
- **`summary_html` is wrapped in a div but otherwise raw** — relies on the AI returning safe HTML; field is `sanitize=True` so most tags get stripped.
- **`hr.work.entry.type` get-or-create writes `display_code='OT'` unconditionally** (no `_fields` guard) — fails if `display_code` isn't on the model in some installations.

## Out of Scope
- **Approval matrix definition** — provided by `custom_approval_engine`.
- **Indonesian regulatory OT compliance** — module is generic; Indonesian-specific OT rules (200% weekend, Kepmenaker 102/2004) live in `custom_attendance` or downstream.
- **Multi-currency invoice** — wizard creates invoices in company currency.
- **Project budget vs actuals** — no margin/cost analysis.
- **Forecast / planning** — see `custom_planning`.
