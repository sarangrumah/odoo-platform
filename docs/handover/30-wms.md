# Handover — WMS

Serah terima tumpukan **Warehouse Management System** di atas Odoo 19 CE. Setiap angka dan
tanggal menyebut sumbernya dalam tanda kurung: nama file memory, path repo, nomor PR, atau nama
basis data. Terakhir diverifikasi terhadap runtime **28-Sep-2026** (`pg_database` +
`ir_module_module` pada `odoo19-platform-postgres`).

## 1. Status sebenarnya

> **WMS BELUM DIPAKAI PRODUKSI OLEH SIAPA PUN.** Yang ada adalah demo, DB riset, dan satu
> integrasi tipis ke produksi Levi's. Jangan menjual dokumen ini sebagai "sudah live".

Fakta yang bisa diperiksa hari ini:

| Basis data | Ukuran | Isi nyata | Arti |
| --- | --- | --- | --- |
| `rnd_wms` | 172 MB | 3 gudang, 223 lokasi, 3.302 produk, 13 picking, 1.957 quant | DB referensi/riset |
| `demo_wms` | 380 MB | 3 gudang, 67 lokasi, 13 produk, 55 picking | Demo JD Sport Cikupa |
| `db_wms` | 67 MB | 2 gudang, 1 produk, 2 picking | Sisi WMS demo 3PL 21-Sep |
| `prd_wms` | 63 MB | **1 gudang default, 12 lokasi, 0 produk, 0 picking** | Kerangka kosong, bukan produksi |
| `tst_wms_scope` | 69 MB | DB uji unit | Sekali pakai |

- **`prd_wms` menyandang awalan `prd` tetapi KOSONG** — dibuat 28-Jul-2026, 10 modul WMS
  terpasang, nol data master, nol transaksi (DB `prd_wms`). Jangan memperlakukannya sebagai
  produksi dan jangan menyebutnya ke klien sebagai bukti.
- **Yang benar-benar menyentuh produksi hanyalah empat modul di `prd_levis_begbal`**:
  `custom_wms_base`, `custom_wms_cycle_count`, `custom_wms_docs`, `custom_wms_reports`
  berstatus `installed`; **`custom_wms_integration` masih `uninstalled`** (DB
  `prd_levis_begbal`, 28-Sep-2026). Gudang **DC SCM id=80 `wms_mode=remote`** sudah ada
  (`wms-erp-round-trip`).
- **TO engine (`custom_wms_to_engine`) bukan mesin otonom.** `cron_evaluate_and_materialize`
  hanya membuat TO berstatus `proposed`; tidak ada eksekusi digerakkan status — `action_start`
  dan `action_done` manual (`addons/ee_gap/custom_wms_to_engine/MODULE_KNOWLEDGE.md`).
  Tiga cacat yang pernah membuatnya tidak berguna sudah diperbaiki 17-Jul-2026 dan
  diverifikasi menghasilkan `TO/2026/00001` di `rnd_wms` (`wms-demo-and-to-engine-runtime-bug`),
  tetapi **semantik low-water-nya terbalik dari proposal** dan **bin kosong tidak pernah
  memicu** — lihat §9. Di `rnd_wms` hanya ada **1 `custom.to.rule`** dan 203 transfer order
  (DB `rnd_wms`), jadi cakupan aturannya belum pernah diuji pada konfigurasi klien nyata.
- Tidak ada modul `_tenants/` untuk WMS — JDS berjalan di atas `ee_gap/custom_wms_*` + `core/custom_hht_bridge` (`docs/projects/README.md`).

## 2. Modul custom_wms_*

Sepuluh modul `custom_wms_*` ada di `main`; `custom_wms_base` **hanya ada di branch
`feat/wms-warehouse-scope`** (tip `589c8fad`, belum di-push, belum ada PR —
`wms-erp-round-trip`) padahal sudah `installed` di `prd_levis_begbal`. Dua modul pendukung
melengkapi tumpukan menjadi 13.

| Modul | Versi | Fungsi |
| --- | --- | --- |
| `custom_wms_base` | branch-only | `stock.warehouse.wms_mode` (`none`/`local`/`remote`); `post_init_hook` menaikkan gudang yang sudah punya strategy/plan/TO rule ke `local` |
| `custom_wms_putaway` | 19.0.0.3.0 | Mesin putaway bertingkat (tier 1..6, 9 jenis rule + `custom_python`), menumpang model kapasitas native Odoo 19 |
| `custom_wms_to_engine` | 19.0.0.3.0 | Orkestrasi transfer internal berbasis rule (low-water, expiry, konsolidasi, replenishment pick) |
| `custom_wms_cycle_count` | 19.0.0.2.0 | Cycle count berbasis plan: session → line → adjustment + gerbang persetujuan varian |
| `custom_wms_inbound_qc` | 19.0.0.1.0 | Karantina inbound nyata: quant di lokasi ber-flag tak bisa direservasi, gerbang QC, registrasi barang tak dikenal |
| `custom_wms_receiving_ext` | 19.0.0.2.0 | Kelengkapan GR: GS1 AI 17 → `stock.lot.expiration_date`, `supplier_batch_ref`, wizard impor CSV/XLSX |
| `custom_wms_docs` | 19.0.0.2.0 | Picking list, packing list, barcode list, price tag/label (QR + Code128) |
| `custom_wms_reports` | 19.0.0.2.0 | 5 laporan SQL view read-only + PDF stock take + metode `spot_check` |
| `custom_wms_sap_slotting` | 19.0.1.0.0 | Pencarian penyimpanan dua dimensi gaya SAP (Lagertyp × Lagerbereich) |
| `custom_wms_integration` | 19.0.0.1.0 | REST `/api/wms/*` masuk + event outbox keluar (SAP dan host generik) |
| `custom_wms_hht` | 19.0.0.4.0 | Aplikasi handheld berbasis task (sidebar, scan paket, stock move nyata) |
| `custom_hht_bridge` | 19.0.0.2.0 | Registry perangkat HHT + HMAC `/api/hht/*` + PWA shell + antrean offline |
| `custom_barcode` | 19.0.2.0.0 | Scan-in/scan-out picking ala EE untuk CE; dipakai 15 DB, **jangan diubah sembarangan** |

Semuanya tier `ee_gap`/`core` = **shared**. `custom_barcode` terpasang di 15 DB (levis, arkaaim,
wms, esb) — itulah alasan `custom_wms_receiving_ext` sengaja dibuat sebagai modul baru, bukan
perubahan `custom_barcode` (`wms-receiving-ext`).

## 3. Slotting & SAP (W07)

- Mesin putaway ditulis ulang 22-Jul-2026 agar **menumpang model kapasitas native Odoo 19**
  (`stock.package.type`, `stock.storage.category`, `removal_strategy_id`) dan hanya menambah
  yang tidak ada padanannya: geometri bin (`wms_length_mm`/`width`/`height`), urutan jalan
  (`wms_walk_sequence`), reservasi kategori produk (`wms_allowed_categ_ids`). Sebelum itu
  `rnd_wms` punya 0 baris `stock_package_type`/`stock_storage_category`/`stock_putaway_rule`
  (`rnd-wms-native-slotting-build`).
- **`scripts/tenants/wms_demo/51_config_native_slotting.py` WAJIB dijalankan**, bukan data demo
  opsional. Tanpa itu rule dimensi/berat tidak mencetak skor apa pun
  (`rnd-wms-native-slotting-build`).
- **W07 ECOMMERCE / SAP slotting** dibangun 30-Jul-2026 dari workbook klien
  "Config BIN WMS - Ecomm Under Armour.xlsx". Modul `custom_wms_sap_slotting` menambah
  storage **type** (AC1/AC2/AP1/AP2/FO1/FO2/FL1) dan **section** (BB1…TR1/GA2) plus jenis rule
  `sap_storage_search` (`w07-ecomm-sap-slotting`).
- Skoring `100 - 12*type_step - 1*section_step`. Kalibrasi ini **disengaja**: tetap di storage
  type yang benar selalu ≥91 dan auto-apply pada ambang 90; fallback type pertama mendarat di 87
  dan berhenti untuk review HHT. Terverifikasi: **154 bin, kapasitas 67.824.000 cm3, 3.292 SKU
  (1.908 berstok), 0 overflow, utilisasi 42,7%**; 5 test modul + 29 regresi `custom_wms_putaway`
  hijau; runbook `scripts/tenants/wms_ecomm/README.md` (`w07-ecomm-sap-slotting`).
- `custom_wms_sap_slotting` **terpasang hanya di `rnd_wms`** (diverifikasi 28-Sep-2026:
  `uninstalled` di `demo_wms` dan `prd_wms`), sengaja TIDAK masuk `apply_updates.sh`, dan
  `custom_wms_putaway` dibiarkan byte-identik supaya tidak ada tenant lain yang butuh `-u`
  (`w07-ecomm-sap-slotting`).

## 4. Receiving, cycle count, inbound QC

### Receiving

- `custom_wms_receiving_ext` menutup item 3 & 4 lembar kebutuhan WMS: GS1 AI 17 ditulis ke
  `stock.lot.expiration_date`, `supplier_batch_ref` baru (fallback AI 10), dan
  `custom.wms.receipt.import.wizard` (CSV/XLSX via openpyxl 3.1.5, validasi all-or-nothing,
  unduh template) (`wms-receiving-ext`).
- **Jebakan over-receipt yang nyata:** Odoo 19 mengisi move line incoming dengan demand penuh,
  sementara `custom_barcode.action_apply_to_picking` **menambah** hasil scan di atasnya — 18
  yang di-scan terbukukan 36. Diperbaiki di 19.0.0.2.0 dengan field provenance
  `stock.move.line.wms_scan_session_id`: scan **men-SET** qty, baris sesi lain dipertahankan,
  re-apply idempoten (`wms-demo-scenario-15-point`). Wizard impor punya masalah kembar dan
  **menol-kan** qty move-line produk terdaftar lebih dulu (4 menjadi 14) (`wms-receiving-ext`).
- `product_expiry` auto-stamp `expiration_date` saat lot dibuat, jadi guard "tulis hanya bila
  kosong" diam-diam membuang tanggal GS1/template — tanggal eksplisit harus menang
  (`wms-receiving-ext`).

### Cycle count

- Plan per `stock.warehouse` dengan `frequency` dan `method` (ABC velocity, random, per zona,
  per nilai, last-counted); cron harian memanggil start-wizard, session `draft → in_progress →
  reviewing → closed`, varian disetujui supervisor lalu `action_post()` membuat `stock.move` ke
  `stock.location_inventory` (`addons/ee_gap/custom_wms_cycle_count/MODULE_KNOWLEDGE.md`).
  **`spot_check`** ditambahkan lewat `selection_add`, ukuran sampel dari parameter
  `custom_wms_reports.spot_check_sample_size` (default 10) (`wms-reports-pack`).
- Dua cacat historis: `ir_sequence_data.xml` adalah **placeholder** sehingga semua session
  bernama `CC/NEW` (`wms-report-barcodes`), dan modul ini memposting `stock.move` dengan field
  `name` yang sudah tidak ada di Odoo 19 — artinya **setiap** penyesuaian cycle count rusak,
  ESB atau bukan; kini `reference` + `description_picking` (`esb-odoo-efn-integration`).
  Di `rnd_wms` baru ada **3 `custom_cycle_count_session`** (DB `rnd_wms`).

### Inbound QC

- Odoo 19 CE mereservasi stok yang baru mendarat di dok, jadi penerimaan dua langkah adalah
  *routing*, bukan *hold*. Modul ini menjadikannya gerbang nyata: `wms_is_qc_area` (implies
  `wms_block_reservation`) diwarisi seluruh bin anak
  (`addons/ee_gap/custom_wms_inbound_qc/MODULE_KNOWLEDGE.md`).
- Bug yang hanya ketangkap smoke test ujung-ke-ujung: putaway auto-apply menulis ulang tujuan
  receipt yang masih `qc_state=pending` ke bin penyimpanan — barang lewat karantina. Diperbaiki
  dengan membuat `stock.move.line._is_incoming()` mengembalikan False selama
  `wms_qc_state == 'pending'`. Di shell/test uid adalah `__system__` (uid 1), **bukan**
  `base.user_admin` (uid 2) — grant `group_wms_qc_inspector` dulu sebelum `action_wms_qc_pass`
  (`rnd-wms-native-slotting-build`, `wms-demo-scenario-15-point`).

## 5. Handheld (HHT) & barcode

- `custom_wms_hht` dibangun 27-Jul-2026 sebagai modul BARU, bukan perubahan
  `custom_hht_bridge` — bridge terpasang di 5 DB termasuk `prd_arkaaim` yang tidak punya model
  `custom_wms_*` sama sekali (`wms-hht-app`).
- Bridge lama ternyata **cangkang demo**: 5 tab datar, dropdown lokasi kosong, dan
  `/api/hht/scan` yang cuma menulis `hht.scan.log` dengan `"applied": False`. Handheld itu
  tidak pernah menerima atau memetik apa pun (`wms-hht-app`).
- Aplikasi baru: sidebar (drawer <640px) dengan badge pekerjaan + pemilih gudang, satu kotak
  scan yang selalu ter-fokus, halaman Receive / Put-away / Pick & Pack / Package / Stock Count /
  Bin to Bin / Stock Check; 19/19 test hijau di `demo_wms` dan `rnd_wms`, naik ke 57 setelah
  halaman Stock Check. `/hht/wms/*` memakai `type="jsonrpc", auth="user"` sehingga pergerakan
  stok teratribusi ke operator; API perangkat HMAC `/api/hht/*` tidak disentuh (`wms-hht-app`).
- **Denso BHT-1700QWB-1 hanya membaca EAN-13, gagal pada SEMUA Code128.** Itu konfigurasi
  simbologi perangkat, bukan barcode yang jelek: `zbarimg` berhasil mendekode 31/31 barcode
  pada 300 dpi dari PDF yang sama (`denso-bht-code128-disabled`). Barcode bin/lokasi dan
  dokumen (`JDC-GR-IN-01`, `JDC/IN/00012`) alfanumerik dan **hanya bisa** Code128 — tidak ada
  fallback EAN-13, jadi mengaktifkan Code128 di perangkat itu **wajib**, bukan opsional.
- `_resolve_barcode` **tidak** menormalkan GTIN-14 ke EAN-13; script demo mendaftarkan alias
  `product.barcode` dengan `barcode.zfill(14)`. Serial/IMEI: GS1 AI 21 kini menamai lot, dan
  scan 14–16 digit polos diresolusi ke satu-satunya produk serial pada picking itu
  (`wms-demo-scenario-15-point`) — tapi `rnd_wms` masih **0 produk bertracking serial**, jadi
  alur IMEI butuh konfigurasi `product.tracking='serial'` untuk didemokan (`wms-receiving-ext`).

## 6. Laporan

- **Kontrak pelaporan: setiap laporan membawa barcode di tingkat transaksi DAN tingkat baris.**
  PDF (Picking, Packing, Barcode List, Label, Stock Take, Scrap Note) plus XLSX lewat mixin
  `custom.wms.xlsx.report` — kolom A/B adalah Document Barcode + Item Barcode sebagai gambar
  tertanam, tombol "Export XLSX (with barcode)" di header tiap list. Barcode dokumen = Code128;
  barcode item dirender `auto` sehingga payload 13 digit keluar sebagai **EAN-13**, justru
  karena handheld Denso hanya membaca EAN-13 (`wms-report-barcodes`,
  `denso-bht-code128-disabled`).
- `custom_wms_reports` menutup item 11–15 lembar kebutuhan: 4 SQL view `_auto=False` dengan
  list+pivot (ekspor XLSX native) — purchase return, stock summary (qty + nilai), stock take
  (baris cycle count + nilai varian), transfer — plus PDF Stock Take / Spot Check; menu di
  Inventory > Reporting > WMS Reports (`wms-reports-pack`).
Jebakan yang sudah dibayar sekali:

- `<head>` dibuang dari template report; wrapper `<main>` wajib
  (`odoo19-report-head-dropped`, `odoo19-report-wrapper-needs-main`). Model report
  `_auto=False` hanya men-flush dirinya sendiri — kelima view model kini mendeklarasikan
  `_depends` (`wms-report-barcodes`).
- `'%.1f%%'` di dalam atribut `<template>` diciutkan jadi satu `%` oleh data loader →
  `ValueError: incomplete format`. Pakai `str.format` di QWeb, **jangan** `%`-formatting
  (`wms-demo-scenario-15-point`).
- Odoo 19: kwarg field adalah `aggregator=`, bukan `group_operator=`; `<group>` di search view
  TIDAK menerima `expand`/`string` (RelaxNG hard error); `standard_price` company-dependent
  adalah JSONB per company id — SQL harus `(pp.standard_price->>company_id::text)::float`
  (`wms-reports-pack`).
- **`odoo shell --no-http` membuat setiap PDF ~60 detik** (wkhtmltopdf tak punya server untuk
  callback; delivery slip core Odoo ~123 detik). Lewat HTTP nyata 3–6 detik. Jangan pernah
  menilai kecepatan report dari shell (`wms-report-barcodes`,
  `odoo19-slow-pdf-report-callback`).

## 7. Integrasi WMS ↔ ERP & DC SCM

Dikerjakan 20/21-Sep-2026 di branch **`feat/wms-warehouse-scope`** (4 commit: `2663b0b0`,
`5336885b`, `032e57ca`, `589c8fad`). **Belum di-push, belum ada PR** (`wms-erp-round-trip`).

- **Keputusan klien:** WMS menjadi DB terpisah yang dibagi banyak principal (3PL); stack WMS
  juga dipasang di Levi's; empat alur menyeberang (PO→DC, DC→toko, retur, e-commerce). Ini
  **sengaja membatalkan K1 dan K10** di `docs/projects/wms-implementation/04-Architecture.md`.
- **Garis potong yang tidak boleh digeser: picking penerimaan WAJIB tetap di DB ERP.** GR/IR dan
  analitik Operating Unit lahir dari `stock.move._action_done` yang membaca
  `picking_type_id.warehouse_id` (`custom_levis_localization/models/stock_move.py:93,161`).
  Karena itu `/api/wms/confirm` menulis kuantitas lalu memanggil `button_validate` milik tenant
  sendiri (`wms-erp-round-trip`).
- **Pagar wajib sebelum stack ini boleh masuk DB retail:** putaway `[]` kecuali `local`;
  inbound_qc tidak lagi menempel `NOT IN` ke reservasi gudang lain; outbox butuh gudang aktif
  DAN host terkonfigurasi + cron di-seed MATI; `/hht/` menyerah ke bridge bila pengguna tak
  punya gudang WMS; `to.rule.warehouse_id` wajib (`wms-erp-round-trip`).
- **Terbukti end-to-end, HTTP nyata, data Levi's asli:** PO ke DC SCM → `asn` terkirim → picking
  mendarat di WMS → terima 9 dari 10 → `goods_receipt` balik → ERP memposting Dr `1113100021` /
  Cr `2103109121` **Rp 1.216.216,26** dengan analitik DC SCM 100% di kedua kaki,
  `qty_received` 9, backorder 1; kirim ulang = tidak ada perubahan. **Demo dua DB (21-Sep):**
  `demo_levis_wms` ↔ `db_wms`, principal LEVIS, PO 12 unit → terima 11 → posting
  `STJ/2026/09/07765` **Rp 1.486.486,54**, backorder 1, **213 test hijau** (custom_core 19 +
  WMS 194) (`wms-erp-round-trip`).
- **Fase 3 selesai:** `wms.principal` (kode + secret sendiri via `credential_ref` →
  `ir.config_parameter` + company) dan `secure_endpoint(scope, secret_resolver=...)` di
  `custom_core`. Pemanggil menyebut diri di header `X-WMS-Principal`; tanda tangan yang
  membuktikannya, lalu company diturunkan dari situ (`wms-erp-round-trip`).
- **Kontrak resolver punya TIGA jawaban dan tidak boleh disamakan:** `("", None)` = tak menyebut
  nama → jatuh ke secret scope; `(None, None)` = TOLAK; `(secret, caller)` = verifikasi dengan
  kunci itu. Draf pertama meng-coerce `None` → `""` sehingga setiap penolakan jadi fallback ke
  secret bersama (`wms-erp-round-trip`).
- Di gudang bersama, **KOSONGKAN** `custom_core.secure_endpoint.wms.secret` supaya hanya
  principal terdaftar bisa masuk (`wms-erp-round-trip`).
- Outbox: `stock.picking.button_validate()` mengantre `wms.integration.event` (`goods_receipt`,
  `goods_issue` + `pick_confirmed`, `putaway_done`, `pack_created`, `stock_adjustment`); cron
  `_cron_drain_outbox()` tiap 5 menit lewat adapter `custom_adapter_framework` (retry/backoff +
  circuit breaker) (`addons/ee_gap/custom_wms_integration/MODULE_KNOWLEDGE.md`).

## 8. Demo & skenario 15 titik

- `scripts/tenants/wms_demo/` menyemai demo WMS JD Sport Cikupa lengkap: `00_create_db.sh`
  (menerima argumen nama DB), `10–50` gudang/produk/PO inbound/SO outbound/putaway+cyclecount+
  bin2bin, `60_admin_login`, `99` verifikasi — **baris terakhir 99 menghardcode "demo_wms"**
  berapa pun nama DB sebenarnya (`wms-demo-and-to-engine-runtime-bug`).
- `70_scenario_test.py` menelusuri **lembar 15 kebutuhan klien** dan mencetak
  PASS/PARTIAL/FAIL + bukti per item. Hasil: **15/15 PASS** di `demo_wms` (SCN03) dan `rnd_wms`
  (SCN01), **93/93 unit test hijau**, commit `a03f297` di `feat/industry-packs`. Item 8 ditutup
  DUA cara: TO engine low-water plus reordering rule SKU native dari
  `52_config_orderpoints.py` (commit `23a9bd4`) — 9 `stock.warehouse.orderpoint` + route Buy +
  vendor pricelist, scheduler menaikkan RFQ P00002 di kedua DB (`wms-demo-scenario-15-point`).
- `80_poc_scenario.py` membangun gudang **POC** sendiri (2-step in / 2-step out) dan menelusuri
  Warehouse → Location → Storage Category → Putaway → PO inbound → Internal transfer →
  Delivery order → Picking out → Cycle count → Print label → Scrap → Reporting: **14/14 PASS**,
  artefak ke `/var/lib/odoo/poc_wms/POC<nn>/`, tulisan di
  `docs/projects/warehouse-jds/WMS-POC-Scenario.md` (`wms-report-barcodes`).
- Hasil uji dipublikasikan sebagai sheet BARU "WMS Requirement Test Result — demo_wms + rnd_wms
  (27 Jul 2026) rev2", id `1neyxAkmQ3RpNwCQVhfWjV2K0g_Y9LEmpdyLYgQEBRr0`. **Sheet rev2 sudah
  BASI** — masih menyebut orderpoint belum terkonfigurasi (`wms-demo-scenario-15-point`).

## 9. Bug/jebakan yang diketahui

| # | Jebakan | Konsekuensi jika diabaikan |
| --- | --- | --- |
| J1 | Semantik low-water TO **terbalik** dari proposal: `source_location_domain` memilih quant di BAWAH ambang (bin yang diisi), `target_location_domain` memilih DONOR | Aturan dibuat terbalik, replenishment mengalir ke arah salah (`wms-demo-and-to-engine-runtime-bug`) |
| J2 | Low-water hanya melihat bin yang **sudah punya baris quant**; bin kosong tidak pernah memicu | Bin yang benar-benar habis tidak pernah direplenish (`wms-demo-and-to-engine-runtime-bug`) |
| J3 | `-u custom_wms_putaway,custom_wms_hht` bersamaan di `rnd_wms` mati dengan `ir_model_inherit` `parent_id` NULL pada model 590 = `stock.picking` | Registry gagal. Ini **state DB lama**, bukan regresi kode; upgrade satu per satu (`rnd-wms-ir-model-inherit-crash`) |
| J4 | `auth="none"` = **tidak ada uid sama sekali**, bukan public user; `.sudo()` tidak cukup | `Expected singleton: res.users()` di `message_post`/tracking — setiap `/api/wms/*` yang menyentuh chatter gagal di produksi (`wms-erp-round-trip`) |
| J5 | Rute tulis tanpa `readonly=False`; outbox membungkus payload di `_envelope()` sementara `/api/wms/asn` membaca bentuk datar; adapter yang di-pin namanya mengabaikan `status=disabled` | J5a laten di `WORKERS=0` lalu fatal; J5b **200 OK** tapi picking lahir di gudang salah tanpa baris; J5c event terkirim ke adapter yang sudah dimatikan (`wms-erp-round-trip`) |
| J6 | Placeholder `ir_sequence_data.xml` di `custom_wms_to_engine` dan `custom_wms_cycle_count` | Semua TO bernama `TO/NEW`, semua session `CC/NEW` (`wms-demo-and-to-engine-runtime-bug`, `wms-report-barcodes`) |
| J7 | Container `odoo19-platform-odoo` memegang kode LAMA sampai di-restart; upgrade dari container mgmt tidak me-reload Python container web | Method baru 500 walau `-u` sukses (`wms-report-barcodes`, `restart-both-odoo-containers`) |
| J8 | `pkill` dan `wget` TIDAK ADA di image odoo; `odoo shell`/`-u` di container mgmt butuh `--http-port=8171 --gevent-port=8172`; test HTTP butuh `--db-filter='^<db>$'` | Server lama tetap hidup ("Address already in use") — pakai `kill -9 <pid>`; tanpa db-filter semua rute jawab 404 (`wms-erp-round-trip`, `wms-demo-scenario-15-point`) |
| J9 | Odoo 19 mengganti nama `stock.quant.package` → **`stock.package`**; `custom.transfer.order` punya `stock_move_id`, BUKAN `picking_id`; test controller harus mem-patch `wms_api.request` DAN `odoo.http.request` | AttributeError; `_()` mati di `NoneType.uid` sehingga setiap error bisnis jadi INTERNAL (`wms-hht-app`) |
| J10 | Rule putaway menyasar **zona** (JDC-HD) sementara stok ada di bin anak; dua rule bisa meranking bin yang sama | "Sudah ada stok" harus membandingkan prefix `parent_path`, dan saran harus di-dedup sebelum top-3 (`wms-hht-app`) |

## 10. Paket dokumen klien

### `docs/projects/wms-implementation/` — paket generik + addendum JDS

Tujuh dokumen (00 PID, 01 BRD, 02 FSD, 03 TSD, 04 Architecture, 05 Estimasi Mandays,
06 Addendum JDS) plus deck PPTX/PDF v1.0. BRD memuat **60+ kebutuhan bernomor (BR-xx)** dengan
MoSCoW; FSD memuat **22 acceptance test**; terakhir diverifikasi terhadap repo **2026-08-11**.
Estimasi berikut semua **tanpa PM** — kolom PM sengaja dikosongkan dan harus dijumlahkan ulang
setelah alokasi PM masuk (`docs/projects/wms-implementation/README.md`):

| Skenario | BA | DEV | QA | Total (+15% kontingensi) |
| --- | ---: | ---: | ---: | ---: |
| Greenfield | 90 | 252 | 106 | ≈ 448 md / ≈ 25 minggu |
| Brownfield (reuse modul) | 51 | 84 | 44 | ≈ 179 md / ≈ 12 minggu |
| JDS pasca-POC | 34 | 59 | 32 | ≈ 125 md / ≈ 10 minggu |

Lingkup dasar angka itu: **1 gudang, ≤3 zona, ≤200 bin, ≤5.000 SKU**. Angka **indikatif berbasis
asumsi tertulis, bukan komitmen kontrak** (`docs/projects/wms-implementation/README.md`).

### `docs/projects/warehouse-jds/` — materi klien JDS

Capability deck HTML, WMS Feature Configuration Guide HTML, `WMS-POC-Scenario.md`,
`WMS-Test-Scenario-rnd_wms.xlsx`, 18 screenshot di `img/`, script capture Playwright di
`shotter/`, plus `seed_wms_demo.py` dan `seed_barcode_config.py`. Status engagement JDS:
**pra-implementasi — POC selesai dan lulus, kontrak implementasi belum**
(`docs/projects/wms-implementation/06-Addendum-JDS.md` v1.1, 2026-08-11).

## 11. Yang MASIH TERBUKA

Sisa pekerjaan teknis (`wms-erp-round-trip`):

1. **Pasang `custom_wms_integration` di produksi.** Masih `uninstalled` di `prd_levis_begbal`
   per 28-Sep-2026. Controller-nya memanggil `secure_endpoint(SCOPE, secret_resolver=...)` saat
   import, sementara keempat container odoo (`odoo`, `-mgmt`, `-front`, `-vaspmo`) masih
   memegang `custom_core` LAMA di memori — memasangnya sekarang = `TypeError` saat import =
   **registry Levi's gagal dimuat**. Urutan wajib: **restart keempat container DULU**, baru
   `-i custom_wms_integration`.
2. **Push branch `feat/wms-warehouse-scope`** dan buka PR-nya. 4 commit termasuk
   `custom_wms_base` yang sudah terpasang di produksi tetapi belum ada di `main`.
3. **Fase 4.4** sinkronisasi master data (SKU masih dibuat manual di sisi WMS), **Fase 6**
   rekonsiliasi stok bernilai, lalu **pairing produksi ke `db_wms`**.

Pertanyaan terbuka untuk fase Requirement JDS
(`docs/projects/wms-implementation/06-Addendum-JDS.md` §5):

| # | Hal | Mengapa penting |
| --- | --- | --- |
| O1 | Volume riil: jumlah gudang, zona, bin, SKU aktif di Cikupa | Menentukan pengali estimasi; demo memakai skala kecil |
| O2 | Perangkat handheld riil dan simbologi aktif | Unit Denso hanya membaca EAN-13 — harus diuji, bukan diasumsikan |
| O3 | Integrasi SAP di-scope atau tidak | Bila ya, kontrak payload + kesiapan SAP jadi gate SIT; bila tidak, −10 md |
| O4 | Kualitas master produk JDS (barcode unik, dimensi, berat) | Slotting volume/dimensi tak bisa dinyalakan tanpa itu |
| O5 | Mode SAP slotting dipakai atau tidak | Bila ya, butuh daftar type & section riil JDS |
| O6 | Denah bin riil dan urutan jalan | Harus dibekukan di akhir fase Design |
| O7 | Ekspektasi ketersediaan & RPO | RPO nyata platform saat ini 24 jam |

Utang kebersihan: DB tertinggal `demo_levis_wms` (1.843 MB), `db_wms`, `tst_wms_scope`,
`tst_levis_wms`, dan **`prd_wms` yang kosong** perlu diputuskan nasibnya (`pg_database`
28-Sep-2026); salinan modul uji di `/opt/odoo-platform/data/odoo-filestore/wms-scope-test` masih
ada (`wms-erp-round-trip`).

## 12. JANGAN — khusus WMS

- **JANGAN menyebut WMS "sudah produksi".** `prd_wms` kosong; satu-satunya jejak produksi adalah
  4 modul + gudang DC SCM di `prd_levis_begbal` (DB `prd_levis_begbal`, 28-Sep-2026).
- **JANGAN memasang `custom_wms_integration` sebelum keempat container odoo di-restart** —
  registry Levi's akan gagal dimuat. Dan jangan memasang stack WMS penuh ke DB retail tanpa
  pagar `wms_mode` di `custom_wms_base` (`wms-erp-round-trip`).
- **JANGAN memindahkan picking penerimaan ke DB WMS.** GR/IR dan analitik OU lahir dari
  `stock.move._action_done` di DB ERP (`wms-erp-round-trip`).
- **JANGAN mengubah `custom_barcode`** untuk kebutuhan WMS — 15 DB memakainya; buat modul
  extension. Dengan alasan sama: jangan masukkan `custom_wms_sap_slotting` ke
  `apply_updates.sh` dan jangan tambah field ke `custom_wms_putaway` tanpa alasan
  (`wms-receiving-ext`, `w07-ecomm-sap-slotting`, `shared-addon-new-field-breaks-every-db`).
- **JANGAN `-u` dua modul WMS sekaligus di `rnd_wms`**, dan jangan menyalahkan perubahan sendiri
  untuk crash registry sebelum A/B terhadap `git archive` commit terakhir
  (`rnd-wms-ir-model-inherit-crash`).
- **JANGAN memakai `%`-formatting di template QWeb**, dan jangan menilai kecepatan PDF dari
  `odoo shell --no-http` (`wms-demo-scenario-15-point`, `wms-report-barcodes`).
- **JANGAN mengasumsikan HHT bisa membaca Code128** sebelum simbologi perangkat diaktifkan;
  dekode PDF dengan `zbarimg -q --raw` dulu (`denso-bht-code128-disabled`).
- **JANGAN rsync seluruh pohon `addons` ke `/opt`** — kedua checkout berbeda dan ada modul yang
  hanya ada di `/opt` (`odoo-platform-checkouts`, `opt-untracked-module-inline-assets`).
