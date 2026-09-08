---
status: override
module: custom_wms_sap_slotting
source: manifest + models/*.py
---

# custom_wms_sap_slotting

## Purpose
Adds the two **SAP WM slotting dimensions** that `custom_wms_putaway` does not
model: Storage Type (SAP *Lagertyp*) and Storage Section (SAP *Lagerbereich*).
Warehouses migrating off SAP WM expect putaway to search in that order; without
these dimensions the generic engine cannot reproduce their slotting rules.

Everything is added by **inheritance**. `custom_wms_putaway` is untouched, so
tenant databases that do not use SAP slotting never need to upgrade the shared
putaway addon.

## Business Flow
- Storage Types and Storage Sections become first-class records, each carrying
  an ordered **search sequence**. The reference configuration ships
  AC1/AC2/AP1/AP2/FO1/FO2/FL1 as types and
  BB1/GF1/GO1/LS1/OD1/RU1/SL1/SS1/TR1/GA2 as sections.
- A new putaway rule kind, `sap_storage_search`, walks the two sequences —
  storage type on the outer loop, storage section on the inner — and slots into
  the first bin with free volume.
- The resulting suggestion is **scored by how far down each sequence** the search
  had to go, so the ranked list the handheld shows reflects how good a fit the
  bin actually is, not just that it fits.
- Products and locations carry their type and section, which is what the search
  matches against.

## Key Models
- `custom.wms.storage.type` + `custom.wms.storage.type.search.line` — the
  Lagertyp dimension and its ordered search sequence.
- `custom.wms.storage.section` + `custom.wms.storage.section.search.line` — the
  Lagerbereich dimension and its sequence.
- `custom.putaway.engine`, `custom.wms.putaway.rule` (inherited) — the
  `sap_storage_search` rule kind.
- `stock.location`, `product.template`, `product.product` (inherited) — carry the
  type/section assignment.

## Important Fields
- The `sequence` on each search line — the ordering is the rule. Reordering these
  changes slotting behaviour with no code change, which is the point.
- `custom.wms.putaway.rule.kind` = `sap_storage_search` — selects the 2-D search
  instead of the generic multi-tier strategy.
