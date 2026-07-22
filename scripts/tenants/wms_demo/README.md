# demo_wms — WMS Demo (JD Sport Cikupa)

End-to-end Warehouse Management demo built to the **JD Sport Cikupa WMS** deck
(EAN scanning for Goods Receipt, Putaway, Pick & Pack, Bin-to-Bin, and Stock
Opname). It maps the SAP-EWM-style requirements onto this platform's existing
custom WMS modules — **no new module code is required**, only data + config.

> The deck is written in SAP EWM terms (TO, PID, ZWME001, Sloc, PGI). This demo
> realises each of those flows with Odoo 19 CE + the platform's `custom_wms_*`
> and `custom_barcode` modules.

---

## 1. Modules to install

Installed automatically by `00_create_db.sh`.

| Module | Source | Why |
|---|---|---|
| `stock` | core | Inventory, pickings, quants, lots |
| `purchase` | core | Inbound PO -> receipt (GR) |
| `sale_management` | core | Outbound SO -> delivery (Pick & Pack) |
| `product_expiry` | core | Batch + **expired-date** capture on lots (GR requirement) |
| `barcodes`, `barcodes_gs1_nomenclature` | core | EAN/GS1 scanning primitives |
| `stock_picking_batch` | core | Batch / wave picking |
| **`custom_barcode`** | `addons/ee_gap` | Handheld scan sessions: GR scan, Pick & Pack, GS1 (GTIN/lot/exp) parsing, label print, deviation report |
| **`custom_wms_putaway`** | `addons/ee_gap` | **ZWME001-style 6-tier putaway** engine (storage type/section search, volume/ABC/nearest-empty) |
| **`custom_wms_cycle_count`** | `addons/ee_gap` | **Stock Opname** (PID): plan-driven counting, scan count, New Item / New Remark, variance approval |
| **`custom_wms_to_engine`** | `addons/ee_gap` | **Bin-to-Bin** transfer orders (auto TO + confirm, low-water-mark replenishment) |
| **`custom_wms_inbound_qc`** | `addons/ee_gap` | **Inbound quarantine**: QC gate on receipts, inbound stock excluded from outbound reservation, unknown-item registration |
| **`custom_wms_docs`** | `addons/ee_gap` | **Picking List / Packing List / Barcode List / Price Tag** reports + label wizard (Code128 / QR / DataMatrix) |
| **`custom_wms_integration`** | `addons/ee_gap` | **Host integration** (SAP): `/api/wms/*` inbound REST (ASN, DO, stock, ack) + outbound event outbox |
| `custom_hht_bridge` | `addons/core` | Physical handheld (Zebra/Honeywell) bridge + PWA shell |
| `custom_receipt_async` | `addons/ee_gap` | Background validate for large receipts (avoids handheld timeout) |

`custom_core` and `custom_pdp_audit` install automatically as dependencies.

---

## 2. Run it

All commands run against the management container `odoo19-platform-odoo-mgmt`.

```bash
# 0. Create db + install all modules (clean, no Odoo demo data)
bash scripts/tenants/wms_demo/00_create_db.sh            # db = demo_wms

# 1. Seed + configure (run in order)
ODOO=odoo19-platform-odoo-mgmt
for f in 10_seed_warehouse 20_seed_products 30_seed_inbound \
         40_seed_outbound 50_config_wms 51_config_native_slotting 99_verify; do
  docker exec -i $ODOO odoo shell -d demo_wms --no-http \
      < scripts/tenants/wms_demo/$f.py
done
```

`51_config_native_slotting.py` is what makes the slotting engine actually decide
anything. It fills in the **native** Odoo 19 records the engine reasons about —
`stock.package.type` (PxLxT + tare + max weight), `stock.storage.category`
(+ per-package-type capacity), `stock.putaway.rule` (category routing, per
company), and FEFO removal strategies — then layers on bin geometry, walk order,
category reservation, and the inbound quarantine / QC gate. Without it those
tables are empty and every dimension- or weight-driven rule scores nothing.

`99_verify.py` prints a readiness summary (warehouse, bins, products, PO/SO
states, putaway strategy, cycle-count session, TO rules, on-hand quants).

All seed scripts are **idempotent** (guarded by `ir.config_parameter` markers),
so re-running is safe. To re-seed from scratch, drop and recreate the DB.

---

## 3. What gets built

**Warehouse `JD Sport Cikupa` (code JDC)** — 2-step receipt (Input → Stock) so
putaway has a leg to slot:

```
JDC/Stock
├── GR Dock           (storage type)   bin GR-IN-01
├── HD Palletised     (storage type)   bins HD-A-01 … HD-A-06   (vol 2.0 m³)
├── Forward Pick      (storage type)
│   ├── NIKE          (storage section / brand)  bins NIK-01 … NIK-04
│   ├── ADIDAS        (storage section / brand)  bins ADI-01 … ADI-04
│   └── PUMA          (storage section / brand)  bins PUM-01 … PUM-04
└── Pack & Ship       (storage type)   bin PACK-01
```

Every zone/bin is **barcoded** (`JDC-…`) and carries a volume capacity. 8 products
(Nike/Adidas/Puma footwear + apparel) with **valid EAN13**, **ABC class**, **lot
tracking**, and **expiry** enabled. Opening stock seeded into PICK bins with
batch lots + expiration dates.

---

## 4. Deck requirement → demo mapping

### EAN SCAN GR (Inbound / Goods Receipt)
- **Seeded:** confirmed PO `po_gr_demo` from *PT Sport Global Distribusi* → open
  receipt picking.
- **Demo:** Inventory ▸ open the JDC receipt ▸ *Barcode Scan* (`custom_barcode`):
  scan EAN, system validates article + qty vs PO, GS1 parse captures lot/expiry,
  capture batch + expired-date on the lot, record DO/surat-jalan in the chatter,
  confirm received. Mismatched/unknown EAN raises an error on the line.
- **Async:** large receipts use *Validate (Background)* from `custom_receipt_async`.

### Putaway (ZWME001)
- **Seeded:** strategy *JDC ZWME001 Putaway* with 6 tiers
  (`50_config_wms.py`): Footwear→HD fixed, A-class→NIKE by ABC velocity,
  volume-fit in PICK, nearest-empty PICK, nearest-empty HD, any next-empty bin.
- **Demo:** validating the receipt fires `custom_wms_putaway`; high-confidence
  suggestions auto-apply, others surface for handheld review. Print putaway label.

### EAN SCAN PICK & PACK (Outbound)
- **Seeded:** confirmed SO `so_pick_demo` → reserved delivery picking (FEFO from
  PICK bins by lot).
- **Demo:** open the delivery ▸ *Barcode Scan*: picking list already on the
  handheld with article/qty/**bin location**; scan EAN, validate qty/location,
  record pack label & packing list, popup on qty difference vs order, confirm &
  PGI (validate). Deviation report shows scanned vs expected %.

### EAN SCAN BIN TO BIN
- **Seeded:** a native **internal transfer picking** `JDC/INT/00001`
  (HD-A-01 → NIK-02, 10× Nike Pegasus, state *assigned*), plus a TO planning
  record and the low-water TO rule *Replenish PICK from HD*.
- **Demo:** open `JDC/INT/00001` ▸ *Barcode Scan*: scan source bin, scan
  product EAN, scan destination bin, confirm — the deck's bin-to-bin flow.
- **Seed shape:** the seed stages the move as a **native internal transfer**
  (which is what `custom_barcode` scans anyway) and creates the low-water rule
  **without location domains**, so the demo works out of the box without relying
  on the TO engine.
- **Enabling the auto-TO rule** (optional): set the rule's domains to
  `[('location_id', 'child_of', <zone_id>)]`. Mind the **inverted semantics** —
  `source_location_domain` selects the quants *below* the threshold (the bins to
  replenish, i.e. PICK) while `target_location_domain` selects the *donor* (HD);
  the proposal then flips them into source=donor / target=low bin. Low-water only
  sees bins that already carry a quant row, and `low_water_qty` must exceed the
  seeded PICK qty (40) for any proposal to fire.
- **Fixed in v19.0.0.2.0:** `materialize()` used to write the removed
  `stock.move.name` field, and the TO `ir.sequence` was a placeholder stub (every
  TO came out named `TO/NEW`). Both are resolved; the engine, its domain rules and
  `cron_evaluate_and_materialize` are verified working on Odoo 19.

### EAN SCAN STOCK OPNAME (Cycle Count / PID)
- **Seeded:** plan *JDC PICK Zone Opname* + one **started session** with count
  lines (`custom_wms_cycle_count`).
- **Demo:** open the session ▸ scan-count each bin (item auto-matched from the
  scanned EAN, no manual line pick). **New Item** (SKU exists but not on list) and
  **New Remark** (SKU not yet registered) both supported on the line. Variance is
  routed to supervisor **approval** before the stock adjustment posts — equivalent
  to the deck's "Create PID → Confirm → Posting by accounting".

---

## 5. Notes / extending

- Putaway `auto_apply_suggestions` is **off** so reviewers can see suggestions on
  the handheld; flip it on the strategy to auto-slot.
- To demo physical scanners, register the device under `custom_hht_bridge`
  (Inventory ▸ HHT) and point DataWedge at its ingest endpoint.
- Brands map to PICK sections via the `default_code` prefix (`NK-`/`AD-`/`PM-`);
  add brands by extending the section locations in `10_seed_warehouse.py` and the
  product list in `20_seed_products.py`.
