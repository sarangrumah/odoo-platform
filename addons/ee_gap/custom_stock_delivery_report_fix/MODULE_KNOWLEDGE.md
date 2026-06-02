---
status: draft
generated_at: 2026-06-02T00:00:00Z
generator: claude-code-hand-authored-v1
module: custom_stock_delivery_report_fix
manifest_version: 19.0.1.0.0
---

# custom_stock_delivery_report_fix

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
- **auto_install:** `True` — installs automatically whenever `stock` is present, so the upstream bug is patched on every tenant without an explicit add.

## Gotchas
- **`auto_install=True`** means this is pulled in implicitly with `stock`; do not assume it is absent just because no one selected it.
- **Tightly coupled to the upstream template's XPath.** If a future Odoo point release renames or restructures `stock_report_delivery_has_serial_move_line` (or fixes the bug itself), the `<xpath>` will fail to match and the module will error on upgrade — revisit on every Odoo version bump and remove once upstream ships the fix.
- The replacement keeps the original `groups="uom.group_uom"` gating and the `_compute_quantity` conversion semantics; it only re-sources `packaging_uom_id` from `move_id` and adds a truthiness guard.

## Out of Scope
- Any change to packaging logic on `stock.move` / `stock.move.line` themselves — this is a report-rendering fix only.
- Other stock reports (picking operations, internal transfer slips) — only the serial/lot delivery-slip packaging line is patched.
