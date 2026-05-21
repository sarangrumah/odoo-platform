---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_repairs
manifest_version: 19.0.0.1.0
---

# custom_repairs

## Purpose
Extends CE `repair.order` for Indonesian SMB tenants with **warranty matrix lookup, turnaround SLA, WhatsApp customer status updates (Bahasa Indonesia), labour + material cost analysis, optional MRP work-order link, optional quality check on completion, and a customer-returns flag**. All extra fields are namespaced `x_*` so the module composes cleanly with other repair extensions.

## Business Flow
- A `custom.repairs.warranty.matrix` row defines `(product_id, warranty_months, warranty_terms)`. `_compute_warranty_status` reads it: given `x_serial_number` + `x_purchase_date` + `product_id`, it computes `x_warranty_until = purchase_date + warranty_months` and `x_warranty_status` (in_warranty / out_of_warranty / extended / na).
- Operator sets `x_promised_completion_date`; `_compute_sla_status` returns on_track / at_risk (≤ 1 day) / breached / done.
- On `write({'state':'confirmed'})`, `_maybe_create_mrp_workorder` best-effort creates an `mrp.production` stub when material lines exist and `mrp` is installed (no BoM, just origin). Stored on `x_mrp_production_id`.
- On `write({'state':'done'})`, `x_actual_completion_date` is auto-stamped, then `_maybe_launch_quality_check` best-effort creates a `quality.check` against the first matching `quality.point` (by `product_id` when present, else any).
- Cost compute (`_compute_total_repair_cost`): material cost iterates `move_ids` (Odoo 19) / `operations` / `parts_lines` (older), preferring `product.standard_price * qty`, falling back to `price_subtotal` / `price_total` / `price_unit`. Labour cost = `x_labor_hours * x_labor_rate` (default rate from ICP `custom_repairs.labor_rate`, default 100 000 IDR/hour).
- `action_send_status_whatsapp()` queues a `whatsapp.message` per repair: looks up the first active `whatsapp.account`, drafts an Indonesian-language body (`"Halo {nama}, status perbaikan {ref}: {state}. Estimasi selesai: {tanggal}"`) and flags `x_customer_notified=True`. Silently skips if no phone, no account, or no partner.
- `action_set_returned()` flags `x_returned=True` + stamps `x_return_date`; chatter post.

## Key Models
- `repair.order` (inherited) — Adds ~20 `x_*` fields covering warranty / SLA / WhatsApp / cost / returns / MRP / quality.
- `custom.repairs.warranty.matrix` — Per-product warranty term (months + terms text + active).

## Important Fields
- `repair.order.x_warranty_status` (in_warranty/out_of_warranty/extended/na, computed/stored, **writable** — allows manual override after compute).
- `repair.order.x_warranty_until` (Date, computed/stored, writable) — `purchase_date + warranty_months`.
- `repair.order.x_serial_number` / `x_purchase_date` (tracking).
- `repair.order.x_promised_completion_date` (Date, tracking).
- `repair.order.x_actual_completion_date` (Datetime, readonly) — auto-stamped on done.
- `repair.order.x_sla_status` (on_track/at_risk/breached/done, computed/stored).
- `repair.order.x_id_complaint` (Text) — Indonesian-language complaint capture.
- `repair.order.x_labor_hours` / `x_labor_rate` / `x_material_cost` / `x_labor_cost` / `x_total_repair_cost`.
- `repair.order.x_returned` (Boolean, readonly, copy=False) + `x_return_date` (Datetime, readonly).
- `repair.order.x_mrp_production_id` (M2o `mrp.production`, readonly).
- `repair.order.x_quality_check_ids` (O2m `quality.check`, computed) + `x_quality_check_count`.
- `repair.order.x_customer_notified` (Boolean, tracking).
- `custom.repairs.warranty.matrix.warranty_months` (Integer, default 12, CHECK >= 0).

## Public Methods
- `repair.order.action_send_status_whatsapp()` — Queue Indonesian status message per repair.
- `repair.order.action_set_returned()` — Mark customer-returned + stamp date + chatter.
- `repair.order._maybe_create_mrp_workorder()` — Best-effort `mrp.production` stub on confirm.
- `repair.order._maybe_launch_quality_check()` — Best-effort `quality.check` on done.
- `repair.order._material_line_records()` — Probe move_ids/operations/parts_lines for version-portable line access.
- `repair.order._material_cost_field_candidates()` — Field-name fallback chain for material cost.
- `repair.order._default_labor_rate()` (`@api.model`) — Read `custom_repairs.labor_rate` ir.config_parameter (default 100 000 IDR).

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `repair`, `custom_whatsapp`, `mail`.
- **Inherits from:** `repair.order`.
- **Extended by:** Indonesian vertical retail / electronics repair modules.
- **External calls:** Creates `whatsapp.message` rows for `custom_whatsapp` to dispatch; optional `mrp.production` + `quality.check` records when those modules are installed.
- **Cross-vertical:** generic repair workflow; Indonesian-language message body is hardcoded.

## Gotchas
- **WhatsApp body is hardcoded Bahasa Indonesia** (`"Halo …, status perbaikan …"`) — no translation; wrong for multi-locale tenants.
- **`_compute_warranty_status` preserves manual values when prereqs are missing** — only sets `na`/`False` if values are currently blank. Repeatedly clearing `x_serial_number` won't reset a manually-overridden warranty.
- **`_maybe_create_mrp_workorder` creates an `mrp.production` with NO BoM** — just product + qty=1 + origin. Useful as a placeholder; not a real manufacturing routing.
- **`_maybe_launch_quality_check` matches `quality.point` by `product_id`** then falls back to *any* point — can launch unrelated checks if no product-specific point exists.
- **`x_quality_check_ids` compute matches by `name like rec.name`** — non-relational, brittle if check names don't contain the repair name.
- **`x_warranty_status='extended'` is never set by compute** — only via manual override (the matrix has no extended-warranty flag).
- **`extended` value semantics** depend on operator discipline; no expiry tracking for extensions.
- **Cost compute material-line walking has a quirky `price_unit` vs `price_subtotal` branch** — when `price_subtotal` is found, it's added to `material` directly and `unit_cost` is cleared; the qty-multiplication branch only fires for `price_unit`.
- **Default labour rate is 100 000 IDR/hour** (Indonesian assumption); override via `ir.config_parameter('custom_repairs.labor_rate')`.
- **`action_send_status_whatsapp` silently skips** records with no phone / no account — only logs at INFO level.

## Out of Scope
- Two-way WhatsApp conversation (only outbound).
- Warranty claim / chargeback to vendor.
- Repair routing with multi-station BoM.
- Photo evidence of damage / repair.
- Customer portal for repair status — uses WhatsApp instead.
- Multi-currency (cost fields are Float, not Monetary).
- Extended warranty tracking with separate expiry.
