---
status: draft
generated_at: 2026-06-02T00:00:00Z
generator: claude-code-hand-authored-v1
module: custom_stock_delivery_report_fix
manifest_version: 19.0.1.0.0
---

# custom_stock_delivery_report_fix

## Status — RETIRED, but not automatically redundant
`installable: False` and every `data` entry commented out. Odoo 19's
`stock.stock_report_delivery_has_serial_move_line` now reads
`move_line.move_id.packaging_uom_id` itself, so this patch's `<xpath>` no longer matches and
breaks a fresh install.

**Retired upstream does not mean redundant on every tenant.** The patch stays load-bearing on
any database whose *own copy* of the parent view is still the old form — a tenant that has not
had `-u stock` since the upstream fix landed. Found exactly that on `gentlewoman` (2026-08-03):
module still `state='installed'`, its view still active and still needed, while `prd_wms`,
`rnd_wms` and `demo_wms` had already moved to the new form. Symptom on the shared instance is
one log line per registry load: `Some modules are not loaded ... ['custom_stock_delivery_report_fix']`.

**Do not uninstall it on its own.** Removing it from a tenant with the old parent view plants a
latent `AttributeError` that only fires on the first lot/serial-tracked delivery. Correct order:

1. Check the tenant's parent view — old form contains `move_line.packaging_uom_id !=`, new form
   contains `move_line.move_id.packaging_uom_id`.
2. `-u stock` on that database, which replaces the parent view with the new form.
3. Re-check the view, then uninstall this module. Its single `ir.ui.view` record and its
   `ir_model_data` row go with it.
4. Verify the slip still renders and the log line is gone.

## Purpose
Single-purpose compatibility patch for Odoo 19's stock delivery-slip report. Upstream's `stock.stock_report_delivery_has_serial_move_line` QWeb template reads `move_line.packaging_uom_id`, but `packaging_uom_id` is defined on `stock.move` (see `stock/models/stock_move.py`), **not** on `stock.move.line`. Rendering a delivery slip for a picking with serial/lot move lines therefore raises `AttributeError: 'stock.move.line' object has no attribute 'packaging_uom_id'`. This module replaces the broken template block to read the field from `move_line.move_id` and guards against an unset packaging.

## Business Flow
- A warehouse user prints / previews a delivery slip (`stock.report_deliveryslip`) for a picking that contains serial- or lot-tracked move lines.
- Without this module the report crashes on the packaging line. With it installed, the inherited template renders the packaging quantity + UoM from `move_line.move_id.packaging_uom_id`, only when that field is set and differs from `product_uom_id`, and only for users in `uom.group_uom`.

## Key Models
None. This module ships **no Python models** — `__init__.py` is empty. It is a pure QWeb view-inheritance patch.

## Important Fields
None added. References existing fields: `stock.move.packaging_uom_id`, `stock.move.line.product_uom_id`, `stock.move.line.quantity`, `stock.move.line.move_id`.

## Public Methods
None.

## Integration Points
- **Depends on:** `stock`.
- **Inherits from (QWeb):** `stock.stock_report_delivery_has_serial_move_line` — single `<xpath position="replace">` on the `t-if="move_line.packaging_uom_id != move_line.product_uom_id"` node.
- **External calls:** none.
- **auto_install:** `False` (was `True` while the module was live, which is why it is present on tenants nobody explicitly added it to). **installable:** `False` — see Status above.

## Gotchas
- **It was `auto_install=True` while live**, so it is present on tenants nobody explicitly selected it for; do not assume it is absent.
- **Tightly coupled to the upstream template's XPath.** This is exactly what happened: upstream fixed the bug, the `<xpath>` stopped matching, and the module was retired. Revisit on every Odoo version bump.
- **"The report renders fine" is not proof the patch is redundant.** The patched block lives in the serial/lot sub-template, so on a database with no lot-tracked move lines the branch is never reached and rendering with and without the patch gives byte-identical output. Decide from the data, not the render: `packaging_uom_id` exists only on `stock.move` — check `ir_model_fields` / `information_schema.columns` — and check which form the tenant's parent view carries.
- **`-u stock` leaves this module stuck in `to upgrade`.** Odoo cannot upgrade an `installable: False` module, and any module in a pending state makes `button_immediate_uninstall` raise `UserError: Odoo is currently processing another module operation`. Settle the pending rows first (`to upgrade`/`to remove` → `installed`, `to install` → `uninstalled`, then commit) and only then uninstall.
- The replacement keeps the original `groups="uom.group_uom"` gating and the `_compute_quantity` conversion semantics; it only re-sources `packaging_uom_id` from `move_id` and adds a truthiness guard.

## Out of Scope
- Any change to packaging logic on `stock.move` / `stock.move.line` themselves — this is a report-rendering fix only.
- Other stock reports (picking operations, internal transfer slips) — only the serial/lot delivery-slip packaging line is patched.
