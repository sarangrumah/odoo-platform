---
status: override
module: custom_retail_import_api
source: manifest + models/*.py + controllers/mdm_api.py
---

# custom_retail_import_api

## Purpose
Receives **product master data pushed by an upstream MDM hub** instead of pulling
the same data from a scheduled report. Built for Levi's, whose XStore MDM HUB
feeds Odoo through SAP PO → IBM MQ → Mulesoft: running the SSRS X101 report often
enough to stay current was loading their XCenter database.

**Why it is a separate module from `custom_retail_import`.** Odoo builds
`ir.http.routing_map` per database from the modules installed in it.
`custom_retail_import` is installed in several Levi's databases; putting the
controller there would expose `/api/mdm/*` in all of them. Installing this module
only where the integration is wanted makes the route *not exist* elsewhere — a
stronger guarantee than any runtime flag.

## Business Flow
- The hub POSTs product JSON to `/api/mdm/products` behind
  `@secure_endpoint('mdm')`. The raw payload is staged on `retail.mdm.request`
  with its items on `retail.mdm.item`.
- Keeping the raw payload is deliberate: a mapping bug is fixed by editing code
  and **replaying** the stored request, never by asking the sender to
  retransmit. A unique `dedupe_key` makes a re-POST a no-op.
- `retail.mdm.category.map` crosswalks the feed's two-level taxonomy onto
  existing product categories. This is not optional — `categ_id` drives the
  revenue and COGS accounts and must not be guessed.
- The actual product writes go through
  `retail.import.executor._x101_upsert_items`, the same seam the X101 file import
  uses, so both routes produce identical records.
- **Everything is off until switched on.** The controller answers 503 unless
  `retail_import.mdm_api_enabled` is `1`, and a shadow mode
  (`retail_import.mdm_dry_run`) validates real traffic without touching master
  data.
- Request auditing lives on `retail.mdm.request` — payload, source IP, timings,
  state, per-item outcome — rather than in `custom.adapter.call.log`. That table
  is keyed to a `custom.adapter.config` whose `adapter_type` must name a
  registered *outbound* adapter, and it stores only `sha256(body)`, which is
  precisely what an inbound feed needs to keep. Rejected requests (bad key, wrong
  IP, oversize body) are logged by `secure_endpoint` itself.

## Key Models
- `retail.mdm.request` — one inbound call: raw payload, source IP, timings,
  state, dedupe key. The replay unit.
- `retail.mdm.item` — per-product outcome within a request.
- `retail.mdm.category.map` — feed taxonomy → `product.category` crosswalk.
- `retail.mdm.processor` — turns a staged request into executor calls.

## Important Fields
- `retail.mdm.request.dedupe_key` — unique; the idempotency guarantee.
- `retail.mdm.request.state` — where an operator looks when the hub reports a
  successful push but the product did not change.
- Config parameters `retail_import.mdm_api_enabled` and
  `retail_import.mdm_dry_run` — the two switches that decide whether the feed is
  live, shadow, or closed.

## Endpoints
`/api/mdm/ping`, `/api/mdm/products`, `/api/mdm/products/lookup`,
`/api/mdm/pending`, `/api/mdm/requests/<request_id>`, and
`/api/mdm/requests/<request_id>/replay` — six routes, all behind the platform
HMAC contract.
