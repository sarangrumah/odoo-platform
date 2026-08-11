# Technical Specification Document (TSD)
## Implementasi Warehouse Management System di atas Odoo 19

| | |
|---|---|
| **Dokumen** | TSD — WMS Implementation (generic) |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Sumber fungsional** | [`02-FSD.md`](02-FSD.md) |
| **Arsitektur** | [`04-Architecture.md`](04-Architecture.md) |
| **Basis kode** | `addons/ee_gap/custom_wms_*`, `addons/core/custom_hht_bridge`, `addons/core/custom_product_barcode`, `addons/ee_gap/custom_barcode` |
| **Verifikasi** | Seluruh nama model, rute, grup, dan versi pada dokumen ini diambil langsung dari repo pada 2026-08-11 |

---

## Contents

1. [Arsitektur perangkat lunak](#1-arsitektur-perangkat-lunak)
2. [Komponen](#2-komponen)
3. [Ringkasan model data](#3-ringkasan-model-data)
4. [Permukaan API](#4-permukaan-api)
5. [Keamanan](#5-keamanan)
6. [Konfigurasi](#6-konfigurasi)
7. [Deployment & operasi](#7-deployment--operasi)
8. [Pengujian](#8-pengujian)
9. [Utang teknis & trade-off yang diketahui](#9-utang-teknis--trade-off-yang-diketahui)
10. [Jebakan platform Odoo 19 yang sudah terdokumentasi](#10-jebakan-platform-odoo-19-yang-sudah-terdokumentasi)
11. [Kriteria penerimaan teknis](#11-kriteria-penerimaan-teknis)

---

## 1. Arsitektur perangkat lunak

WMS ini **bukan** aplikasi terpisah. Ia adalah sekumpulan modul Odoo yang memperluas `stock`,
sehingga seluruh pergerakan tetap melewati `stock.move` / `stock.move.line` / `stock.quant`
milik Odoo. Konsekuensinya penting dan disengaja: laporan keuangan, valuasi, dan penelusuran
lot tetap konsisten dengan sisa ERP tanpa rekonsiliasi tambahan.

```
        ┌─────────────────────────────────────────────────────────────────────┐
        │                     KLIEN / ANTARMUKA                               │
        │  Backend Odoo (web)      PWA handheld (/hht/)     Sistem host        │
        └──────────┬──────────────────────┬────────────────────────┬──────────┘
                   │ ORM                  │ JSON-RPC auth=user     │ json2 + HMAC
                   v                      v                        v
        ┌─────────────────────────────────────────────────────────────────────┐
        │                     LAPIS MODUL WMS (addons/ee_gap)                 │
        │                                                                      │
        │  putaway ──► sap_slotting        inbound_qc        cycle_count       │
        │     │  (custom.putaway.engine)        │                 │            │
        │     │                                 │                 │            │
        │  to_engine (custom.to.engine)    receiving_ext     docs / reports    │
        │     │                                 │                 │            │
        │  hht (controllers, tanpa model)  integration (outbox + adapter)      │
        └──────────────────────────────┬──────────────────────────────────────┘
                                       │ selalu lewat ORM stock.*
                                       v
        ┌─────────────────────────────────────────────────────────────────────┐
        │  ODOO 19 CORE: stock, stock_account, purchase, sale, product, mail  │
        │  + core/custom_core (secure_endpoint), compliance/custom_pdp_audit  │
        └─────────────────────────────────────────────────────────────────────┘
```

### Tiering modul

Tier ditentukan oleh **direktori**, bukan oleh `category` pada manifest.

| Tier | Direktori | Konsekuensi |
|---|---|---|
| Core | `addons/core/` | Dipakai seluruh tenant. `custom_hht_bridge`, `custom_product_barcode` ada di sini |
| EE-gap | `addons/ee_gap/` | Delta CE→EE. **Seluruh 10 modul `custom_wms_*` ada di sini** |
| Tenant | `addons/_tenants/` | Milik satu pelanggan |

Implikasi rekayasa: perubahan pada modul WMS untuk satu klien **berdampak ke semua tenant yang
memasangnya**. Kustomisasi khusus klien yang tidak layak digeneralisasi harus diletakkan di
modul `_tenants/` milik klien tersebut, bukan disisipkan ke `ee_gap/`.

### Reuse yang sudah tersedia (jangan bangun ulang)

| Kebutuhan | Komponen yang sudah ada | Lokasi |
|---|---|---|
| Endpoint API tertandatangani | dekorator `@secure_endpoint(...)` | `addons/core/custom_core/controllers/secure_endpoint.py` |
| Jejak audit PDP | `pdp.audited.mixin` | `addons/compliance/custom_pdp_audit/` |
| Kerangka adapter eksternal | `@register_adapter(...)` | `addons/core/custom_adapter_framework/` |
| Job latar belakang | `queue_job` (OCA, ter-vendor) | `addons/_vendor/queue_job/` |
| Render barcode | `wms.barcode.mixin` | `addons/ee_gap/custom_wms_docs/models/` |
| Ekspor XLSX berbarcode | `custom.wms.xlsx.report` | `addons/ee_gap/custom_wms_reports/models/wms_xlsx_mixin.py` |
| Parsing GS1, sesi pindai, template label | `custom_barcode` | `addons/ee_gap/custom_barcode/` |
| Registrasi perangkat & log pindai | `hht.device`, `hht.scan.log` | `addons/core/custom_hht_bridge/models/` |

## 2. Komponen

### 2.1 `custom_wms_putaway` — mesin slotting

`__manifest__.py` v19.0.0.3.0 · depends: `custom_core`, `custom_pdp_audit`, `custom_barcode`,
`stock`, `product`.

| Model | Berkas | Peran |
|---|---|---|
| `custom.wms.putaway.strategy` | `models/wms_putaway_strategy.py` | Wadah aturan per gudang; `rule_set`, `auto_apply_suggestions`; mewarisi `mail.thread` + `pdp.audited.mixin` |
| `custom.wms.putaway.rule` | `models/wms_putaway_rule.py` | Satu aturan berskor; `tier` 1..6, `kind` dari `_STRATEGY_KINDS` |
| `custom.wms.putaway.suggestion` | `models/wms_putaway_suggestion.py` | Hasil evaluasi; menyimpan lokasi asli, lokasi saran, lokasi timpaan, `score`, `confidence_score`, `reason`, `status` |
| `custom.putaway.engine` | `models/putaway_engine.py` | `AbstractModel` — layanan evaluasi & penilaian |
| `custom.wms.hd.pallet` | `models/wms_hd_pallet.py` | Palet kepadatan tinggi |
| `custom.wms.putaway.propose.wizard` | `wizard/putaway_propose_wizard.py` | Menjalankan mesin atas satu picking tanpa menerapkan |

Model yang diperluas: `stock.location`, `stock.move.line`, `product.template`, `product.product`.

**Jenis aturan** (`_STRATEGY_KINDS`, 9 nilai): `fixed_location`, `nearest_empty`,
`zone_round_robin`, `by_volume`, `by_dimension`, `by_weight`, `by_temperature`,
`by_abc_velocity`, `custom_python`. Modul `custom_wms_sap_slotting` menambahkan
`sap_storage_search` lewat `selection_add`.

**Bobot penilaian** per aturan: `weight_volume`, `weight_distance`, `weight_age`, `weight_abc`.
Aturan `custom_python` dievaluasi dengan `safe_eval` dan hanya dapat diubah oleh
`group_putaway_admin`.

**Alur evaluasi.**

```
leg putaway terbentuk (stock.move.line dengan tujuan zona penyimpanan)
        │
        v
custom.putaway.engine.evaluate(move_line)
        │  iterasi strategi gudang, aturan urut tier 1→6
        │  tiap aturan menghasilkan (lokasi, score, confidence, reason)
        v
kandidat terbaik → custom.wms.putaway.suggestion (status pending)
        │
        ├─ auto_apply_suggestions ON dan confidence ≥ ambang
        │     └─► tulis ke move_line.location_dest_id, status applied
        └─ selain itu → menunggu review operator (handheld / layar Suggestions)
```

### 2.2 `custom_wms_sap_slotting` — pencarian penyimpanan dua dimensi

v19.0.1.0.0 · depends: `custom_wms_putaway`, `stock`, `product`.

| Model | Peran |
|---|---|
| `custom.wms.storage.type` | SAP *Lagertyp*; `code`, `sequence`, `bin_type`, `is_high_density` |
| `custom.wms.storage.type.search.line` | Urutan pencarian tipe: `type_id` → `target_type_id` |
| `custom.wms.storage.section` | SAP *Lagerbereich* |
| `custom.wms.storage.section.search.line` | Urutan pencarian seksi |

Rumus skor yang diimplementasikan:

```
score = 100 − 12 × (jumlah langkah menuruni urutan tipe penyimpanan)
            −  1 × (jumlah langkah menuruni urutan seksi)
auto-apply bila score ≥ 90
```

Data referensi disertakan sebagai CSV (`data/custom.wms.storage.type.csv` dan tiga berkas
sejenis) berisi tipe AC1/AC2/AP1/AP2/FO1/FO2/FL1 dan seksi
BB1/GF1/GO1/LS1/OD1/RU1/SL1/SS1/TR1/GA2 — titik awal yang wajib disesuaikan per klien.

> **Catatan operasional:** modul ini sengaja **tidak** dimasukkan ke daftar upgrade bersama pada
> `scripts/tenants/apply_updates.sh`. Ia dipasang per-tenant secara eksplisit.

### 2.3 `custom_wms_inbound_qc` — karantina & gate QC

v19.0.0.1.0 · depends: `custom_core`, `custom_pdp_audit`, `custom_wms_putaway`, `stock`,
`product`, `mail`.

Model baru: `custom.wms.product.registration` (urutan `REG/<tahun>/`) — barcode, deskripsi hasil
pindai, picking, mitra, pemindai, kuantitas, usulan nama & kode internal, kategori, satuan, berat,
volume, tipe paket, kelas ABC, produk hasil, alasan penolakan.

Model yang diperluas: `stock.quant`, `stock.location`, `stock.picking.type`, `stock.picking`,
`stock.move`, `stock.move.line`.

**Mekanisme kunci.** Pengecualian stok QC dilakukan pada tingkat *gather* `stock.quant` — bukan
lewat domain di tampilan. Artinya, proses otomatis (penjadwal, aturan reordering, reservasi ulang)
pun tidak dapat mengambil stok karantina. Ini implementasi teknis dari aturan bisnis AB-1.

### 2.4 `custom_wms_cycle_count` — hitung siklik

v19.0.0.2.0 · depends: `custom_core`, `custom_pdp_audit`, `custom_barcode`, `stock`, `product`, `mail`.

| Model | Peran |
|---|---|
| `custom.cycle.count.plan` | `warehouse_id`, `frequency`, `method`, `scope_zone_ids`, `target_count_per_period` (default 50), `next_run_date`, `state` (active/paused), `coverage_pct` |
| `custom.cycle.count.session` | Nama dari urutan `CC/%(year)s/00001`; jadwal, waktu mulai/selesai, penghitung, `variance_count`, `variance_value` |
| `custom.cycle.count.line` | Ekspektasi vs hasil hitung, `variance_qty`, `variance_pct`, penghitung, waktu, catatan, `is_new_item` |
| `custom.cycle.count.adjustment` | Penyesuaian stok hasil persetujuan |
| `custom.cycle.count.start.wizard` | Memulai sesi dari rencana |

`METHOD` = `abc_velocity`, `random`, `by_zone`, `by_value`, `last_counted`; `custom_wms_reports`
menambahkan `spot_check` via `selection_add` dengan `ondelete={"spot_check": "set default"}`.

Metode `_advance_next_run()` dan `_cron_generate_sessions()` sudah ada di
`models/cycle_count_plan.py`.

> **Gap terverifikasi.** `data/cron.xml` modul ini berisi komentar placeholder tanpa record apa pun.
> Akibatnya `_cron_generate_sessions()` **tidak pernah terpanggil terjadwal**. Ini adalah item
> `PERLU DIBANGUN` (F-CC-08): tambahkan record `ir.cron` yang memanggil metode tersebut, dengan
> `noupdate="1"` dan interval harian.

Migrasi `migrations/19.0.0.2.0/post-backfill_session_names.py` menomori ulang sesi lama bernama
`CC/NEW` — akibat urutan yang dahulu juga berupa placeholder.

### 2.5 `custom_wms_to_engine` — perintah transfer

v19.0.0.3.0 · depends: `custom_core`, `custom_pdp_audit`, `stock`, `product`, `barcodes`, `mail`.

| Model | Peran |
|---|---|
| `custom.to.rule` | `trigger` dari `TRIGGER`, `source_location_domain` & `target_location_domain` (domain teks, dievaluasi `safe_eval`), `product_filter_json` (field `Json`), `low_water_qty`, `expiry_days_ahead`, `priority`, `schedule_interval_minutes`, `last_run_at` |
| `custom.transfer.order` | Urutan `TO/%(year)s/`; sumber, tujuan, produk, lot, qty rencana & aktual, picker, waktu pick & drop, `stock_move_id` |
| `custom.to.engine` | Evaluasi aturan + `materialize()` menjadi `stock.move` transfer internal |
| `custom.transfer.order.manual.wizard` | Pembuatan perintah manual |

`TRIGGER` = `low_water_mark`, `expiry_approaching`, `zone_consolidation`, `picking_replenishment`,
`manual`.

Cron `cron_evaluate_and_materialize` (`data/cron.xml`) menjalankan evaluasi terjadwal.
Laporan `reports/to_pick_slip_report.xml` mencetak slip pick berbarcode.

### 2.6 `custom_wms_receiving_ext` — kelengkapan penerimaan

v19.0.0.2.0 · depends: `stock`, `product_expiry`, `custom_barcode`, `custom_product_barcode`.

Tidak membuat model bisnis baru; ia memperluas `custom.barcode.scan.line`,
`custom.barcode.scan.session`, `stock.lot` (referensi batch pemasok), dan `stock.move.line`.
Wizard `custom.wms.receipt.import.wizard` menerima CSV/XLSX dan menyediakan template kosong.

Penanganan GS1: AI 17 → tulis-tembus ke tanggal kedaluwarsa lot, AI 10 → nomor lot, AI 21 → serial;
digit polos 14–16 karakter diperlakukan sebagai IMEI.

### 2.7 `custom_wms_docs` — dokumen berbarcode

v19.0.0.2.0. `wms.barcode.mixin` merender barcode **di dalam proses** menjadi
`data:image/png;base64,…`, bukan `<img src="/report/barcode/…">`. Ini menghilangkan panggilan HTTP
balik per barcode saat wkhtmltopdf merender.

Template: `report/picking_list_report.xml`, `packing_list_report.xml`, `barcode_list_report.xml`,
`product_label_report.xml`. Model laporan `report.custom_wms_docs.report_wms_product_label`.
Wizard `custom.wms.label.wizard` dilindungi record rule "own records only".

### 2.8 `custom_wms_reports` — laporan analisis

v19.0.0.2.0 · depends: `stock_account`, `purchase_stock`, `custom_wms_cycle_count`, `custom_wms_docs`.

Lima model laporan berupa **SQL view** (`_auto = False`), semuanya mewarisi
`custom.wms.xlsx.report`: `custom.wms.purchase.return.report`, `custom.wms.stock.summary.report`,
`custom.wms.stock.take.report`, `custom.wms.transfer.report`, `custom.wms.scrap.report`.

`custom.wms.xlsx.report` (`models/wms_xlsx_mixin.py`) menghasilkan workbook dengan dua kolom
gambar barcode (kolom A `Document Barcode`, kolom B `Item Barcode`), satu baris header datar,
autofilter, dan baris total.

Setiap model laporan **wajib mendeklarasikan `_depends`** atas model dasarnya. Alasannya teknis:
model `_auto=False` hanya melakukan flush terhadap dirinya sendiri, sehingga tanpa `_depends`,
perubahan yang belum ter-flush pada transaksi yang sama terbaca basi lewat view.

Laporan PDF tambahan: `report/stock_take_report_pdf.xml`, `report/scrap_note_pdf.xml`.

### 2.9 `custom_wms_hht` — aplikasi handheld

v19.0.0.4.0 · depends: `custom_hht_bridge`, `custom_barcode`, `custom_product_barcode`,
`custom_wms_putaway`, `custom_wms_inbound_qc`, `custom_wms_cycle_count`, `custom_wms_to_engine`,
`custom_wms_receiving_ext`, `stock`.

**Tidak mendefinisikan model apa pun** — hanya controller dan frontend OWL.

- Controller: `controllers/shell.py` (rute shell `/hht/`), `controllers/wms_api.py` (21 rute JSON-RPC).
- Frontend: `static/src/js/wms_hht/pages/` berisi `ReceivePage.js`, `PutawayPage.js`, `PickPage.js`,
  `PackagePage.js`, `CountPage.js`, `BinToBinPage.js`, `StockPage.js`; ditambah `wms_shell.js/xml`,
  `scanBurst.js`, `pickingScan.js`, `rpc.js`.
- Bundle aset: `custom_wms_hht.pwa_assets`.

`scanBurst.js` menangani pemindaian beruntun yang tiba lebih cepat dari siklus render — tanpa ini,
karakter dari dua pindai berdekatan dapat tercampur antar-field.

### 2.10 `custom_wms_integration` — integrasi host

v19.0.0.1.0 · depends: `custom_core`, `custom_pdp_audit`, `custom_adapter_framework`, `stock`,
`purchase`, `sale_management`.

| Model | Peran |
|---|---|
| `wms.integration.event` | Outbox; urutan `WMSEVT/<tahun>/`; `event_type`, `res_model`, `res_id`, payload JSON, `state`, `attempts`, `last_error`, `external_ref`, `sent_at`, `acked_at` |
| `wms.integration.mapping` | Terjemahan kode host ↔ Odoo |

Adapter di `models/wms_host_adapter.py` didaftarkan lewat `@register_adapter("wms_host")` dan
`@register_adapter("wms_sap_host")`. Cron `cron_drain_wms_outbox` menguras antrean.

**Pola outbox** dipilih agar validasi dokumen di Odoo tidak pernah gagal hanya karena host sedang
tidak tersedia: kejadian ditulis dalam transaksi yang sama dengan dokumennya, lalu dikirim
terpisah dengan percobaan ulang.

### 2.11 Modul pendukung

| Modul | Versi | Isi teknis |
|---|---|---|
| `core/custom_hht_bridge` | 19.0.0.2.0 | `hht.device`, `hht.scan.log`, `hht.sync.queue`, wizard `hht.regenerate.secret.wizard`; PWA di `/hht/`, REST `/api/hht/*`, ingest DataWedge; 2 grup + 6 record rule |
| `core/custom_product_barcode` | 19.0.0.1.0 | Model `product.barcode` (GTIN alternatif) + `product.product._resolve_barcode` |
| `ee_gap/custom_barcode` | 19.0.2.0.0 | `custom.barcode.scan.session` / `.scan.line`, sesi batch, cluster run, template label, konfigurasi printer, antrean cetak, parsing GS1 |
| `ee_gap/custom_receipt_async` | 19.0.1.0.0 | Validasi penerimaan besar di latar belakang |

## 3. Ringkasan model data

| Model | Modul | Jenis | Kunci |
|---|---|---|---|
| `custom.wms.putaway.strategy` | putaway | Model | per gudang + perusahaan |
| `custom.wms.putaway.rule` | putaway | Model | `strategy_id`, `tier`, `kind` |
| `custom.wms.putaway.suggestion` | putaway | Model | `move_line_id` |
| `custom.putaway.engine` | putaway | AbstractModel | — |
| `custom.wms.hd.pallet` | putaway | Model | — |
| `custom.wms.storage.type` / `.section` | sap_slotting | Model | `code` |
| `custom.wms.storage.type.search.line` / `.section.search.line` | sap_slotting | Model | `type_id`/`section_id` + `sequence` |
| `custom.wms.product.registration` | inbound_qc | Model | urutan `REG/<tahun>/` |
| `custom.cycle.count.plan` / `.session` / `.line` / `.adjustment` | cycle_count | Model | sesi: urutan `CC/<tahun>/` |
| `custom.to.rule` / `custom.transfer.order` | to_engine | Model | order: urutan `TO/<tahun>/` |
| `custom.to.engine` | to_engine | AbstractModel | — |
| `wms.barcode.mixin` | docs | AbstractModel | — |
| `custom.wms.label.wizard` | docs | TransientModel | — |
| `custom.wms.xlsx.report` | reports | AbstractModel | — |
| `custom.wms.{purchase.return,stock.summary,stock.take,transfer,scrap}.report` | reports | Model `_auto=False` | SQL view + `_depends` |
| `custom.wms.receipt.import.wizard` | receiving_ext | TransientModel | — |
| `wms.integration.event` / `.mapping` | integration | Model | event: urutan `WMSEVT/<tahun>/` |
| `hht.device` / `hht.scan.log` / `hht.sync.queue` | hht_bridge | Model | — |
| `product.barcode` | product_barcode | Model | GTIN unik |

**Urutan (`ir.sequence`) yang terdefinisi:** `CC/%(year)s/`, `REG/%(year)s/`, `TO/%(year)s/`,
`WMSEVT/%(year)s/`.

> **Gap terverifikasi.** `addons/ee_gap/custom_wms_putaway/data/ir_sequence_data.xml` masih berupa
> placeholder. Bila ada objek di modul putaway yang membutuhkan penomoran berurutan, ia akan jatuh
> ke nilai literal — kelas bug yang sama dengan `CC/NEW` dan `TO/NEW` yang sudah pernah menggigit.
> Verifikasi ini sebagai bagian fase Design.

## 4. Permukaan API

### 4.1 API handheld — `auth="user"`, JSON-RPC

| Rute | Fungsi |
|---|---|
| `/hht/wms/warehouses` | Daftar gudang yang boleh diakses pengguna |
| `/hht/wms/queue` | Antrean tugas operator |
| `/hht/wms/scan/resolve` | Menerjemahkan satu barcode menjadi objek (produk, lot, bin, paket, picking) |
| `/hht/wms/pickings`, `/hht/wms/picking` | Daftar dan detail picking |
| `/hht/wms/receive/scan`, `/hht/wms/receive/validate` | Penerimaan |
| `/hht/wms/qc` | Gate QC |
| `/hht/wms/putaway/suggest`, `/hht/wms/putaway/apply` | Saran & penerapan putaway |
| `/hht/wms/pick/confirm`, `/hht/wms/pick/pack`, `/hht/wms/pick/validate` | Picking dan packing |
| `/hht/wms/package`, `/hht/wms/package/move` | Manajemen paket |
| `/hht/wms/count/sessions`, `/count/lines`, `/count/submit` | Cycle count |
| `/hht/wms/bin2bin/list`, `/bin2bin/execute` | Bin-to-bin |
| `/hht/wms/stock/lookup` | Cek stok |

### 4.2 API integrasi host — `type="json2"`, `auth="none"`, `@secure_endpoint('wms')`

| Metode | Rute | Arah | Fungsi |
|---|---|---|---|
| POST | `/api/wms/asn` | Host → Odoo | Kirim rencana kedatangan |
| POST | `/api/wms/do` | Host → Odoo | Kirim perintah pengiriman |
| GET | `/api/wms/stock` | Host ← Odoo | Baca posisi stok |
| POST | `/api/wms/ack` | Host → Odoo | Akui kejadian yang dikirim Odoo |

Kontrak payload disepakati per klien pada fase Requirement dan dilampirkan sebagai adendum TSD.

## 5. Keamanan

| Lapis | Mekanisme |
|---|---|
| API host | `@secure_endpoint('wms')`: HMAC-SHA256 atas body, toleransi selisih waktu (anti-replay lambat), nonce (anti-replay cepat), pembatasan CIDR |
| API handheld | Sesi pengguna Odoo (`auth="user"`); perangkat terdaftar di `hht.device` dengan secret yang dapat diregenerasi/dicabut |
| Otorisasi dalam aplikasi | 13 grup keamanan + ACL per model; record rule multi-perusahaan pada modul integrasi dan HHT bridge |
| Jejak audit | `pdp.audited.mixin` pada model strategi putaway, registrasi produk, dan objek WMS lain yang memuat data pelaku |
| Eksekusi kode dinamis | Aturan `custom_python` dan domain aturan transfer dievaluasi lewat `safe_eval`, dan hanya dapat diubah oleh grup admin masing-masing |
| Isolasi tenant | Satu basis data per tenant; `DBFILTER` di sisi Odoo publik menolak akses lintas basis data |
| Data pribadi | Mengikuti kerangka UU PDP platform ([`../pdp-compliance.md`](../../pdp-compliance.md)) |

**Yang tidak boleh dilonggarkan.** Endpoint host tidak boleh dijalankan tanpa HMAC "untuk sementara
selama UAT". Bila host belum siap menandatangani, pakai jalur import manual — jangan matikan
penjagaan.

## 6. Konfigurasi

Konfigurasi implementasi mengikuti pola skrip yang sudah terbukti di
`scripts/tenants/wms_demo/` dan `scripts/tenants/wms_ecomm/`. Skrip-skrip ini adalah **referensi
konfigurasi**, bukan sekadar demo — mereka mendokumentasikan urutan yang benar.

| Langkah | Skrip referensi | Yang dikonfigurasi |
|---|---|---|
| 1 | `10_seed_warehouse.py` | Gudang, alur 2-step, tipe & seksi penyimpanan, bin berbarcode berkapasitas volume |
| 2 | `20_seed_products.py` | Produk, EAN-13 valid, kelas ABC, pelacakan lot, expiry |
| 3 | `50_config_wms.py` | Strategi putaway 6 tier, rencana cycle count, aturan transfer low-water |
| 4 | `51_config_native_slotting.py` | **Wajib.** `stock.package.type` (P×L×T, tara, berat maks), `stock.storage.category` (plafon berat + kapasitas per tipe paket), `stock.putaway.rule` per perusahaan, strategi keluar FEFO per kategori produk, geometri bin + urutan jalan + penanda karantina. Idempoten di balik parameter `wms_demo.native_slotting_configured` |
| 5 | `52_config_orderpoints.py` | `stock.warehouse.orderpoint` min/max per SKU + route Buy + pricelist pemasok |
| 6 | `30_config_putaway.py` (varian ecomm) | Konfigurasi pencarian penyimpanan SAP dari CSV |

Parameter sistem yang relevan berada di `data/ir_config_parameter_data.xml` masing-masing modul.

**Urutan yang tidak boleh dibalik:** kategori penyimpanan dan tipe paket harus ada **sebelum**
bin distempel, dan bin harus ada **sebelum** aturan putaway yang menargetkannya dibuat.

## 7. Deployment & operasi

### Pemasangan

Modul dipasang lewat mekanisme addon Odoo standar. Urutan dependensi ditegakkan oleh manifest,
tetapi urutan praktis yang aman:

```
custom_core, custom_pdp_audit, custom_adapter_framework
  → custom_product_barcode, custom_barcode, custom_hht_bridge
    → custom_wms_putaway
      → custom_wms_sap_slotting, custom_wms_inbound_qc, custom_wms_to_engine
    → custom_wms_cycle_count, custom_wms_receiving_ext, custom_wms_docs
      → custom_wms_reports
        → custom_wms_hht
    → custom_wms_integration
```

### Urutan go-live

1. Pasang modul di staging; jalankan seluruh suite test.
2. Konfigurasikan gudang, bin, kategori penyimpanan (langkah §6.1–§6.4).
3. Muat master produk, verifikasi keunikan barcode.
4. Konfigurasikan strategi putaway dengan `auto_apply_suggestions` **mati**.
5. Daftarkan perangkat handheld; uji pindai dengan perangkat riil.
6. Bila ada integrasi: tukar kunci HMAC, isi pemetaan, uji keempat endpoint di staging.
7. Cutover: opname penuh → muat saldo awal stok per bin → bekukan pergerakan manual.
8. Go-live; jalankan cycle count intensif minggu pertama.
9. Nyalakan `auto_apply_suggestions` setelah kualitas saran terbukti dari data penimpaan.

### Pemantauan

| Yang dipantau | Di mana |
|---|---|
| Kejadian integrasi gagal | `wms.integration.event` dengan `state` gagal dan `attempts` menaik |
| Cron macet | Settings ▸ Technical ▸ Scheduled Actions; khususnya `cron_evaluate_and_materialize` dan `cron_drain_wms_outbox` |
| Kualitas saran putaway | Rasio saran yang ditimpa (`overridden_location_id` terisi) terhadap total |
| Cakupan cycle count | `coverage_pct` pada rencana |
| Log pindai handheld | `hht.scan.log` |

### Rollback

Rollback modul dilakukan dengan menurunkan versi image/kode lalu menjalankan `-u` pada modul
terkait. **Hati-hati:** modul WMS berada di tier bersama, sehingga rollback berdampak ke seluruh
tenant yang memasangnya. Rollback data cycle count yang sudah menghasilkan penyesuaian stok tidak
otomatis — penyesuaian harus dibalik sebagai pergerakan stok tersendiri.

## 8. Pengujian

Seluruh sepuluh modul WMS memiliki suite test sendiri:

| Modul | Berkas test | Metode `def test_*` |
|---|---|---:|
| `custom_wms_hht` | `tests/test_wms_hht_api.py` | 39 |
| `custom_wms_putaway` | `tests/test_putaway.py` | 29 |
| `custom_wms_integration` | `tests/test_wms_integration.py` | 16 |
| `custom_wms_inbound_qc` | `tests/test_inbound_qc.py` | 15 |
| `custom_wms_docs` | `tests/test_wms_docs.py` | 11 |
| `custom_wms_reports` | `tests/test_wms_reports.py` | 11 |
| `custom_wms_receiving_ext` | `tests/test_receiving_ext.py` | 9 |
| `custom_wms_cycle_count` | `tests/test_cycle_count.py` | 7 |
| `custom_wms_to_engine` | `tests/test_to_engine.py` | 7 |
| `custom_wms_sap_slotting` | `tests/test_storage_search.py` | 5 |
| **Total** | | **149** |

Run POC terakhir melaporkan **101 tes hijau** pada enam modul yang dicakupnya
(`custom_wms_docs`, `custom_wms_reports`, `custom_wms_cycle_count`, `custom_wms_putaway`,
`custom_wms_hht`, `custom_wms_inbound_qc`) di basis data `demo_wms`.

**Uji skenario end-to-end** dijalankan terhadap record nyata, bukan mock:

```bash
# Walkthrough POC 12 kategori (A–L); menulis bukti cetak ke /var/lib/odoo/poc_wms/POC<nn>/
docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
    < scripts/tenants/wms_demo/80_poc_scenario.py

# Uji terhadap lembar 15 poin kebutuhan klien
docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
    < scripts/tenants/wms_demo/70_scenario_test.py
```

Keduanya mencetak PASS / PARTIAL / FAIL per langkah berikut bukti record yang dipakai.

## 9. Utang teknis & trade-off yang diketahui

| # | Hal | Konsekuensi | Sikap |
|---|---|---|---|
| T1 | `custom_wms_cycle_count/data/cron.xml` masih placeholder | Sesi hitung tidak terbit otomatis | Dibangun pada fase implementasi (F-CC-08) |
| T2 | `custom_wms_putaway/data/ir_sequence_data.xml` masih placeholder | Risiko penomoran jatuh ke literal | Diverifikasi pada fase Design |
| T3 | `custom_hht_bridge/data/cron.xml` dan `ir_config_parameter_data.xml` masih placeholder | Tugas terjadwal & parameter default HHT tidak tersedia | Diverifikasi pada fase Design |
| T4 | Mode offline penuh handheld belum diverifikasi terhadap perangkat klien | Asumsi kerja saat ini adalah online | Uji perangkat pada fit-gap; bangun bila diperlukan |
| T5 | `custom_wms_sap_slotting` di luar daftar upgrade bersama | Bisa tertinggal versi saat upgrade massal | Sengaja; pasang & upgrade eksplisit per tenant |
| T6 | Aturan `custom_python` memungkinkan logika per klien di dalam data | Sulit di-review lewat diff kode | Batasi ke `group_putaway_admin`; logika yang stabil dipromosikan menjadi jenis aturan sungguhan |
| T7 | Modul WMS di tier bersama `ee_gap/` | Perubahan satu klien berdampak lintas tenant | Regression test lintas tenant wajib sebelum rilis |

## 10. Jebakan platform Odoo 19 yang sudah terdokumentasi

Enam hal berikut ditemukan dan **sudah diperbaiki** saat membangun POC. Dicantumkan karena
kelasnya akan menggigit lagi di tempat lain.

1. **CSS dan charset laporan diam-diam dibuang.** `ir_actions_report._prepare_html` hanya
   mempertahankan *anak dari `<main>`*. Setiap `<style>` dan `<meta charset="utf-8">` karena itu
   harus diletakkan **di dalam `<main>`**, bukan di `<head>`. Bila tidak: laporan tercetak tanpa
   gaya dan karakter non-ASCII menjadi mojibake.
2. **Urutan placeholder menghasilkan nama literal.** Sesi cycle count dahulu semuanya bernama
   `CC/NEW` karena `next_by_code` mengembalikan `None`. Akibatnya barcode sesi tidak terpindai dan
   pengelompokan laporan mustahil. Selalu verifikasi `ir.sequence` benar-benar ada.
3. **Laporan SQL view dapat membaca data basi.** Model `_auto=False` hanya melakukan flush terhadap
   dirinya sendiri. Wajib mendeklarasikan `_depends` atas model dasar.
4. **Barcode ditanam, bukan diambil.** Barcode dirender in-process menjadi data-URI agar
   wkhtmltopdf tidak melakukan panggilan HTTP balik per barcode.
5. **`odoo shell --no-http` membuat semua PDF tampak rusak.** Tanpa server HTTP, wkhtmltopdf
   menunggu callback: ±60 detik per dokumen (delivery slip bawaan Odoo sendiri ±123 detik). Lewat
   HTTP normal dokumen yang sama selesai dalam 2,6–6,2 detik. **Jangan pernah mendiagnosis performa
   laporan dari run shell.**
6. **Python baru butuh restart kontainer web.** Upgrade modul dari kontainer manajemen memperbarui
   basis data, tetapi worker web yang berjalan lama masih memegang kode lama — metode yang baru
   ditambahkan akan 500 sampai kontainer web di-restart.

## 11. Kriteria penerimaan teknis

| # | Kriteria |
|---|---|
| TA-1 | Seluruh 149 metode test pada 10 modul WMS lulus di basis data klien |
| TA-2 | `80_poc_scenario.py` (atau turunannya untuk klien) berjalan 14/14 PASS terhadap konfigurasi klien |
| TA-3 | `70_scenario_test.py` menghasilkan PASS untuk seluruh butir kebutuhan yang disepakati |
| TA-4 | Tidak ada berkas `data/*.xml` berstatus placeholder yang masih menutup fungsi yang dijanjikan (T1–T3 tertutup) |
| TA-5 | Keempat endpoint integrasi menolak permintaan tanpa HMAC sah, dan menerima yang sah, di staging |
| TA-6 | Waktu cetak keenam dokumen PDF melalui HTTP berada dalam rentang detik, bukan puluhan detik |
| TA-7 | Matriks hak akses terverifikasi: setiap peran hanya dapat melakukan yang tercantum pada FSD §3 |
| TA-8 | Cron `cron_evaluate_and_materialize`, `cron_drain_wms_outbox`, dan cron penerbitan sesi hitung yang baru terdaftar dan berjalan |
| TA-9 | Regression test lintas tenant lulus untuk seluruh tenant lain yang memasang modul `ee_gap/custom_wms_*` |
