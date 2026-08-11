---
status: override
module: custom_wms_hht
source: manifest + controllers/ + static/
---

# custom_wms_hht

## Purpose
The **handheld warehouse application** that actually moves stock. It replaces
the demo shell in `custom_hht_bridge` — five flat tabs, empty stubs, and a scan
endpoint that only *logged* the scan — with a task-driven app wired into the
`custom_wms_*` modules.

It is deliberately a **separate module from `custom_hht_bridge`**: the bridge is
installed on ARKA production databases that have none of the WMS models, and it
must not be forced to upgrade for a WMS-only feature.

The module declares no Python model. Everything it does is controllers plus an
OWL front end over models owned by the WMS stack — which is why an automated
scan reports it as empty and why this entry exists.

## Business Flow
- **Sidebar shell** with a work-queue badge per module, instead of flat tabs, so
  a picker sees where the work is.
- **Receive** — open receipts, GS1/EAN scan, IMEI serial capture, expiry and
  supplier batch entry, QC pass/fail against the quarantine gate from
  `custom_wms_inbound_qc`.
- **Putaway** — the engine's ranked bin suggestion per line; accept it, or
  override by scanning a different bin.
- **Pick & Pack** — pick list grouped by source bin, scan-to-confirm, put in
  package, validate.
- **Package** — scan any package to see contents, location and history, and move
  it bin to bin.
- **Count** — cycle-count and spot-check sessions, line by line.
- **Bin-to-bin** — transfer-order proposals raised by the low-water engine in
  `custom_wms_to_engine`.
- **Stock check** — read-only: scan a product to see its details, the suggested
  bin, and on-hand versus reserved stock per bin.

## Key Models
None declared. The app operates on `stock.picking`, `stock.move.line`,
`stock.quant`, `custom.cycle.count.session`, `custom.wms.putaway.suggestion` and
`custom.transfer.order`, all owned by the modules it depends on.

## Important Fields
Not applicable — no fields are declared here. The device contract is the route
surface below, and the per-device HMAC credential held by `custom_hht_bridge`.

## Endpoints
`/hht/` serves the PWA shell. The WMS task routes sit under `/hht/wms/`:
`package`, `package/move`, `picking`, `pick/confirm`, `pick/pack`,
`pick/validate`, `count/sessions`, `count/lines`, `count/submit`,
`bin2bin/list`, `bin2bin/execute`, plus the receive and putaway routes. Each is
authenticated per device and the offline queue is idempotent on
`(device_id, client_id)`, so a re-sent scan cannot double-move stock.
