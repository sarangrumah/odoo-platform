---
status: override
module: custom_wms_receiving_ext
source: manifest + models/*.py + wizards/
---

# custom_wms_receiving_ext

## Purpose
Closes the goods-receipt gaps in the WMS stack **without touching the shared
`custom_barcode` addon** — which matters because `custom_barcode` is installed
on tenant databases that have no interest in these behaviours, and every shared
addon version bump forces an upgrade run across all of them.

## Business Flow
- **GS1 expiry write-through.** AI 17 (expiration date) was already parsed into
  the scan line's `x_gs1_parsed` JSON but never applied anywhere. It now lands on
  `stock.lot.expiration_date` when the scan is applied to the picking.
- **Supplier batch reference.** A new field on both `stock.lot` and the scan
  line, filled manually or from the GS1 lot (AI 10) when the scan is applied — so
  a recall can be traced to the supplier's own batch number, not just ours.
- **Serial / IMEI capture.** GS1 AI 21 becomes the `stock.lot` name for
  serial-tracked products. A bare 14–16 digit IMEI scan, which previously fell
  through as "not found", is attributed to the picking's sole serial-tracked
  product.
- **Receipt template import.** A wizard on incoming pickings uploads a CSV or
  XLSX template (barcode or SKU, serial or lot, quantity, expiry date, supplier
  batch) and creates move lines and lots in bulk. A blank template is
  downloadable from the same wizard, so the format is never guessed.

## Key Models
- `custom.wms.receipt.import.wizard` — the CSV/XLSX bulk receipt loader.
- `stock.lot` (inherited) — gains the supplier batch reference and receives the
  GS1 expiry.
- `stock.move.line` (inherited) — carries the scanned lot/serial through to the
  picking.
- `custom.barcode.scan.line` / `custom.barcode.scan.session` (inherited) — where
  the GS1 write-through and IMEI attribution hook in.

## Important Fields
- `stock.lot.supplier_batch_ref` — the supplier's own batch number, the field
  that makes a supplier-side recall traceable. Declared here.
- The scan line's `x_gs1_parsed` JSON — the raw parse result, kept so a mapping
  bug can be diagnosed after the fact.
- The expiry target is `expiration_date`, which belongs to upstream
  `product_expiry`. This module does not declare it; it finally *writes* it,
  from GS1 AI 17, at the moment the scan is applied to the picking.
