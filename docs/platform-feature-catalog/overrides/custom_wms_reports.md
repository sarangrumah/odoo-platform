---
status: override
module: custom_wms_reports
source: manifest + models/*.py + report/
---

# custom_wms_reports

## Purpose
The **warehouse reporting pack** — six analyses plus printable documents,
covering the reporting requirements the WMS stack did not answer. Every analysis
model is a **read-only SQL view**, not a stored table, so nothing here can drift
from the operational data it summarises.

## Business Flow
- **Purchase Return Report** — done moves to supplier locations, grouped per
  supplier and per SKU (list and pivot).
- **Stock Summary Report** — on-hand per SKU, warehouse and location with unit
  cost and stock value.
- **Stock Take Report** — cycle-count lines with expected, counted and variance
  quantity plus variance value, and a printable PDF sheet per session.
- **Spot Check** — a `spot_check` sampling method added to cycle-count plans
  (small random sample) with a report view filtered to it.
- **Transfer Report** — stock moves by operation type with demand and done
  quantity.
- **Scrap Report** — write-offs per bin, SKU and lot with scrap value and the
  replenish flag, plus a printable Scrap Note PDF.
- Every analysis exports to **XLSX with embedded Code128 barcodes** at two
  levels: one column for the transaction (picking, scrap order, count session or
  bin) and one for the line item (the lot when tracked, otherwise the product
  EAN). The sheet stays scannable outside Odoo. The PDFs carry the same two
  barcode levels.

## Key Models
- `custom.wms.purchase.return.report`, `custom.wms.stock.summary.report`,
  `custom.wms.stock.take.report`, `custom.wms.transfer.report`,
  `custom.wms.scrap.report` — the five SQL-view analysis models.
- `custom.wms.xlsx.report` — the shared XLSX writer with the Code128 embedding.
- `custom.cycle.count.plan` / `custom.cycle.count.session` (inherited) — where
  the `spot_check` sampling method is added.
- `stock.scrap` (inherited) — extended for the Scrap Note.

## Important Fields
- `custom.cycle.count.plan.method` — extended by `selection_add` with
  `spot_check` alongside the existing sampling methods, and
  `ondelete={"spot_check": "set default"}` so uninstalling does not orphan plans.
- Stock value columns on the summary and take reports read from the move value,
  not from a valuation layer: Odoo 19 has no `stock.valuation.layer` in this
  configuration, and reading one would silently return nothing.

## Deployment note
This module is not installed everywhere its reports are wanted. On
`prd_levis_begbal` the On-Hand and Purchase Return reports were requested by the
client and exist here, but installing the pack pulls in the WMS dependency
chain — a decision that was taken explicitly rather than by porting the reports
into the accounting engine.
