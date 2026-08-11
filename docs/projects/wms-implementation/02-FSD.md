# Functional Specification Document (FSD)
## Implementasi Warehouse Management System di atas Odoo 19

| | |
|---|---|
| **Dokumen** | FSD — WMS Implementation (generic) |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Sumber requirement** | [`01-BRD.md`](01-BRD.md) |
| **Bukti fungsional** | [`../warehouse-jds/WMS-POC-Scenario.md`](../warehouse-jds/WMS-POC-Scenario.md) — 12 kategori transaksi, 14/14 PASS |
| **Rujukan teknis** | [`03-TSD.md`](03-TSD.md) |
| **Penanda status** | **SUDAH ADA** = terpasang & terverifikasi di repo · **PERLU DIBANGUN** = belum ada, masuk effort |

---

## Contents

1. [Gambaran solusi](#1-gambaran-solusi)
2. [Peta modul & navigasi](#2-peta-modul--navigasi)
3. [Peran & hak akses](#3-peran--hak-akses)
4. [Spesifikasi fungsional per area](#4-spesifikasi-fungsional-per-area)
5. [Aplikasi handheld (HHT)](#5-aplikasi-handheld-hht)
6. [Dokumen & pelaporan](#6-dokumen--pelaporan)
7. [Integrasi sistem host](#7-integrasi-sistem-host)
8. [User journey](#8-user-journey)
9. [Perilaku non-fungsional (sudut pandang fungsional)](#9-perilaku-non-fungsional-sudut-pandang-fungsional)
10. [Acceptance test representatif](#10-acceptance-test-representatif)
11. [Matriks traceability BR → fungsi](#11-matriks-traceability-br--fungsi)

---

## 1. Gambaran solusi

Solusi terdiri dari tiga lapis yang dipakai oleh tiga kelompok pengguna berbeda:

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │  LAPIS KONFIGURASI  — Warehouse Manager, IT                          │
  │  Gudang · Zona · Bin · Kategori penyimpanan · Tipe paket             │
  │  Strategi & aturan putaway · Aturan transfer · Rencana cycle count   │
  └──────────────────────────────────────────────────────────────────────┘
                                    │ mengendalikan
                                    v
  ┌──────────────────────────────────────────────────────────────────────┐
  │  LAPIS EKSEKUSI  — Operator gudang, lewat handheld (PWA)             │
  │  Receive · Putaway · Pick · Package · Count · Bin-to-Bin · Stock     │
  └──────────────────────────────────────────────────────────────────────┘
                                    │ menghasilkan
                                    v
  ┌──────────────────────────────────────────────────────────────────────┐
  │  LAPIS KENDALI  — Supervisor, Finance, IT                            │
  │  Persetujuan selisih · Dokumen berbarcode · Laporan PDF/XLSX         │
  │  Outbox integrasi · Jejak audit                                      │
  └──────────────────────────────────────────────────────────────────────┘
```

Modul yang menyusunnya (semua di `addons/ee_gap/`, kecuali yang ditandai):

| Modul | Versi | Peran fungsional |
|---|---|---|
| `custom_wms_putaway` | 19.0.0.3.0 | Mesin slotting bertingkat + saran penempatan |
| `custom_wms_sap_slotting` | 19.0.1.0.0 | Pencarian penyimpanan dua dimensi ala SAP |
| `custom_wms_inbound_qc` | 19.0.0.1.0 | Karantina, gate QC, registrasi barang tak dikenal |
| `custom_wms_cycle_count` | 19.0.0.2.0 | Rencana, sesi, dan persetujuan hitung siklik |
| `custom_wms_to_engine` | 19.0.0.3.0 | Perintah transfer internal & replenishment |
| `custom_wms_receiving_ext` | 19.0.0.2.0 | GS1, batch pemasok, import penerimaan |
| `custom_wms_docs` | 19.0.0.2.0 | Dokumen cetak berbarcode |
| `custom_wms_reports` | 19.0.0.2.0 | Laporan analisis + ekspor XLSX berbarcode |
| `custom_wms_hht` | 19.0.0.4.0 | Aplikasi handheld (PWA) |
| `custom_wms_integration` | 19.0.0.1.0 | API host + outbox kejadian |
| `core/custom_hht_bridge` | 19.0.0.2.0 | Registrasi perangkat, log pindai, antrean sinkron |
| `core/custom_product_barcode` | 19.0.0.1.0 | GTIN alternatif per SKU |
| `custom_barcode` | 19.0.2.0.0 | Sesi pindai, parsing GS1, template & antrean label |
| `custom_receipt_async` | 19.0.1.0.0 | Validasi penerimaan besar di latar belakang |

## 2. Peta modul & navigasi

| Menu | Isi | Modul |
|---|---|---|
| Inventory ▸ Configuration ▸ Warehouses / Locations / Storage Categories / Package Types | Struktur gudang, kapasitas bin, kategori penyimpanan | Odoo core |
| Inventory ▸ Configuration ▸ Putaway Rules | Aturan putaway native Odoo (kategori produk → zona) | Odoo core |
| WMS ▸ Putaway ▸ Strategies / Rules / Suggestions | Strategi bertingkat, aturan berskor, antrean saran | `custom_wms_putaway` |
| WMS ▸ Putaway ▸ Storage Types / Storage Sections | Lagertyp × Lagerbereich + urutan pencarian | `custom_wms_sap_slotting` |
| WMS ▸ Inbound QC ▸ Product Registrations | Barang tak dikenal menunggu persetujuan | `custom_wms_inbound_qc` |
| WMS ▸ Cycle Count ▸ Plans / Sessions | Rencana berkala dan sesi hitung | `custom_wms_cycle_count` |
| WMS ▸ Transfer Orders ▸ Rules / Orders | Aturan pemicu dan perintah transfer | `custom_wms_to_engine` |
| Inventory ▸ Reporting ▸ WMS Reports | 5 laporan analisis + tombol ekspor XLSX | `custom_wms_reports` |
| Inventory ▸ Print Labels | Wizard label produk / price tag | `custom_wms_docs` |
| Settings ▸ Technical ▸ WMS Integration ▸ Events / Mappings | Outbox dan pemetaan kode host | `custom_wms_integration` |
| Settings ▸ Technical ▸ HHT ▸ Devices / Scan Logs | Perangkat terdaftar dan log pindai | `core/custom_hht_bridge` |
| `/hht/` (di luar backend) | Aplikasi handheld PWA | `custom_wms_hht` |

## 3. Peran & hak akses

13 grup keamanan terpasang. Pemberian grup dilakukan per peran bisnis (lihat BRD §8).

| Grup teknis | Boleh |
|---|---|
| `group_putaway_user` | Melihat & menjalankan saran putaway |
| `group_putaway_admin` | Membuat/mengubah strategi & aturan putaway, termasuk aturan Python |
| `group_wms_qc_inspector` | Meloloskan/menolak barang inbound, membuat registrasi produk |
| `group_wms_qc_manager` | Menyetujui registrasi produk, mengatur kewajiban inspeksi |
| `group_cycle_count_user` | Memasukkan hasil hitung pada sesi yang ditugaskan |
| `group_cycle_count_supervisor` | Menyetujui selisih, menutup sesi |
| `group_cycle_count_admin` | Membuat & mengubah rencana hitung |
| `group_to_operator` | Menjalankan perintah transfer |
| `group_to_supervisor` | Menyetujui/menjadwalkan perintah transfer |
| `group_to_admin` | Membuat & mengubah aturan transfer |
| `group_wms_integration_manager` | Mengelola outbox, pemetaan kode, memicu kirim ulang |
| `group_hht_operator` | Login ke aplikasi handheld |
| `group_hht_admin` | Mendaftarkan/mencabut perangkat, meregenerasi secret |

> Aturan record multi-perusahaan aktif pada modul integrasi dan HHT bridge, sehingga pengguna
> hanya melihat data perusahaan/gudangnya.

## 4. Spesifikasi fungsional per area

### 4.1 Struktur gudang & master data — `BR-WH-01..07`

| Fungsi | Perilaku | Status |
|---|---|---|
| F-WH-01 | Gudang dibuat dengan alur masuk/keluar 1/2/3-step. Alur 2-step in memisahkan *Receipt* dan *Storage*, sehingga leg kedua inilah yang di-slotting | SUDAH ADA |
| F-WH-02 | Lokasi bertingkat `Gudang/Stock/<zona>/<bin>`; setiap bin punya field barcode | SUDAH ADA |
| F-WH-03 | Bin membawa: kapasitas berat, kapasitas volume, kapasitas per tipe paket (via kategori penyimpanan), urutan jalan, penanda karantina/QC | SUDAH ADA |
| F-WH-04 | Kategori penyimpanan membatasi apakah satu bin boleh memuat satu produk (`same`) atau campuran (`mixed`), lengkap dengan plafon berat dan jumlah paket | SUDAH ADA |
| F-WH-05 | Produk membawa klasifikasi ABC, zona suhu, tipe paket, berat, volume, dan dimensi sebagai masukan slotting | SUDAH ADA |
| F-WH-06 | Satu SKU dapat memiliki banyak GTIN; pemindaian GTIN mana pun mengarah ke SKU yang sama | SUDAH ADA |
| F-WH-07 | Master dimuat massal melalui import standar Odoo (CSV/XLSX) | SUDAH ADA |

**Validasi.** Barcode bin wajib unik dalam satu perusahaan. Bin tanpa kapasitas tetap dapat dipakai,
tetapi aturan slotting berbasis volume/berat/dimensi akan melewatinya — ini disengaja, dan menjadi
temuan yang harus dibereskan di fase data cleansing.

### 4.2 Penerimaan barang (GR) — `BR-IN-01..07`

| Fungsi | Perilaku | Status |
|---|---|---|
| F-IN-01 | Penerimaan dibuka dari PO terkonfirmasi atau dari ASN host; operator memindai item satu per satu | SUDAH ADA |
| F-IN-02 | Barcode GS1 diurai otomatis: AI 10 → nomor lot, AI 17 → tanggal kedaluwarsa, AI 21 → serial. Nilai hasil urai langsung mengisi baris penerimaan | SUDAH ADA |
| F-IN-03 | Digit polos 14–16 karakter dikenali sebagai IMEI dan diperlakukan sebagai serial | SUDAH ADA |
| F-IN-04 | Nomor batch pemasok tersimpan sebagai field terpisah pada lot, sehingga penelusuran ke pemasok tetap mungkin walau lot internal dinomori ulang | SUDAH ADA |
| F-IN-05 | SKU ber-serial menghasilkan satu baris per unit; kuantitas per baris selalu 1 | SUDAH ADA |
| F-IN-06 | Wizard import penerimaan menerima CSV/XLSX dan menyediakan template kosong yang dapat diunduh | SUDAH ADA |
| F-IN-07 | Penerimaan sangat besar dapat divalidasi asinkron; layar tidak terkunci menunggu | SUDAH ADA |
| F-IN-08 | Barang tak dikenal yang dipindai membuka form registrasi: barcode, deskripsi hasil pindai, kuantitas, usulan nama & kode, kategori, satuan, berat, volume, tipe paket, kelas ABC | SUDAH ADA |

**Validasi.** Penerimaan tidak dapat divalidasi bila SKU ber-tracking belum memiliki lot/serial.
SKU ber-expiry menolak tanggal kedaluwarsa yang sudah lewat, kecuali dikonfirmasi pengguna berhak.

### 4.3 QC inbound & karantina — `BR-QC-01..04`

| Fungsi | Perilaku | Status |
|---|---|---|
| F-QC-01 | Jenis operasi dapat ditandai "wajib inspeksi"; penerimaan yang memakainya mengarahkan barang ke lokasi karantina | SUDAH ADA |
| F-QC-02 | Lokasi bertanda QC dikecualikan saat sistem mengumpulkan stok untuk pemesanan outbound — bukan sekadar disembunyikan di layar | SUDAH ADA |
| F-QC-03 | Inspektur meloloskan (barang berpindah ke jalur putaway) atau menolak (barang tetap tertahan, alasan wajib diisi) | SUDAH ADA |
| F-QC-04 | Registrasi produk berjalan dari `draft` → menunggu persetujuan → disetujui (produk dibuat) atau ditolak (alasan wajib) | SUDAH ADA |

**Aturan.** Selama sebuah registrasi belum disetujui, barangnya tidak dapat dijual — ia tidak punya
produk untuk dijual. Ini sengaja: mencegah master produk kotor akibat tekanan operasional.

### 4.4 Putaway & slotting — `BR-PA-01..08`

**Model kerja.** Strategi = kumpulan aturan bertingkat untuk satu gudang. Aturan dievaluasi dari
tier 1 (prioritas tertinggi) sampai tier 6. Setiap aturan menghasilkan kandidat lokasi berikut
**skor** dan **skor keyakinan**. Kandidat terbaik menjadi saran.

| Jenis aturan | Dasar pemilihan lokasi | Status |
|---|---|---|
| `fixed_location` | Lokasi tetap yang ditentukan untuk produk/kategori | SUDAH ADA |
| `nearest_empty` | Bin kosong dengan jarak jalan terpendek dari dock | SUDAH ADA |
| `zone_round_robin` | Rotasi antar-zona memakai kursor, agar beban merata | SUDAH ADA |
| `by_volume` | Bin dengan sisa volume paling pas | SUDAH ADA |
| `by_dimension` | Kesesuaian dimensi P×L×T barang terhadap bin | SUDAH ADA |
| `by_weight` | Sisa kapasitas berat bin | SUDAH ADA |
| `by_temperature` | Kesesuaian zona suhu produk | SUDAH ADA |
| `by_abc_velocity` | Kelas ABC produk → kedekatan ke area pick | SUDAH ADA |
| `custom_python` | Ekspresi Python terbatas (`safe_eval`), hanya untuk `group_putaway_admin` | SUDAH ADA |
| `sap_storage_search` | Pencarian dua dimensi: tipe penyimpanan × seksi | SUDAH ADA (`custom_wms_sap_slotting`) |

Bobot penilaian dapat diatur per aturan: bobot volume, jarak, umur stok, dan kelas ABC.

**Mode SAP (opsional).** Produk membawa tipe penyimpanan dan seksi. Mesin menelusuri daftar urut
tipe penyimpanan, lalu daftar urut seksi, dan memberi skor:

```
skor = 100 − 12 × (langkah menuruni urutan tipe penyimpanan)
           −  1 × (langkah menuruni urutan seksi)
```

Saran dengan skor ≥ 90 (yakni pilihan pertama atau nyaris pertama) boleh diterapkan otomatis;
di bawah itu masuk antrean review operator.

| Fungsi | Perilaku | Status |
|---|---|---|
| F-PA-01 | Saat leg putaway terbentuk, mesin menghasilkan saran per baris pergerakan | SUDAH ADA |
| F-PA-02 | Saran menyimpan: lokasi tujuan asli, lokasi yang disarankan, aturan & strategi pemicu, skor, skor keyakinan, dan alasan tekstual | SUDAH ADA |
| F-PA-03 | Bila `auto_apply_suggestions` menyala dan keyakinan melewati ambang, saran langsung diterapkan ke baris pergerakan | SUDAH ADA |
| F-PA-04 | Operator dapat menimpa saran; nilai timpaan tersimpan terpisah dari saran asli sehingga kualitas mesin dapat diukur | SUDAH ADA |
| F-PA-05 | Wizard "Propose" dapat menjalankan ulang mesin atas satu picking untuk melihat saran tanpa menerapkannya | SUDAH ADA |
| F-PA-06 | Aturan putaway native Odoo tetap berjalan berdampingan (kategori produk → zona, disaring kategori penyimpanan); mesin bertingkat bekerja di atasnya | SUDAH ADA |

### 4.5 Transfer internal & replenishment — `BR-ST-01..07`

| Fungsi | Perilaku | Status |
|---|---|---|
| F-ST-01 | Aturan transfer dipicu oleh salah satu dari lima kondisi: batas bawah stok (`low_water_mark`), mendekati kedaluwarsa (`expiry_approaching`), konsolidasi zona (`zone_consolidation`), replenishment picking (`picking_replenishment`), atau manual | SUDAH ADA |
| F-ST-02 | Aturan memilih lokasi asal & tujuan melalui ekspresi domain, dan produk melalui filter JSON | SUDAH ADA |
| F-ST-03 | Cron `cron_evaluate_and_materialize` mengevaluasi aturan lalu **materialisasi** perintah menjadi `stock.move` transfer internal | SUDAH ADA |
| F-ST-04 | Setiap perintah bernomor `TO/<tahun>/xxxxx` dan berstatus dari dibuat → dipick → didrop | SUDAH ADA |
| F-ST-05 | Slip pick perintah transfer dapat dicetak, berbarcode | SUDAH ADA |
| F-ST-06 | Perintah transfer manual dapat dibuat lewat wizard tanpa aturan | SUDAH ADA |
| F-ST-07 | Titik pemesanan ulang (min/max per SKU) tersedia melengkapi mesin transfer, untuk pengisian dari pemasok, bukan antar-bin | SUDAH ADA (Odoo core, dikonfigurasi skrip 52) |

### 4.6 Outbound: picking, packing, pengiriman — `BR-OU-01..05`

| Fungsi | Perilaku | Status |
|---|---|---|
| F-OU-01 | SO terkonfirmasi menghasilkan leg pick yang memesan stok terhadap bin nyata | SUDAH ADA |
| F-OU-02 | Picker memindai bin lalu item; ketidakcocokan ditolak di layar handheld | SUDAH ADA |
| F-OU-03 | Barang terpick dimasukkan ke paket; paket punya barcode sendiri dan dapat dipindahkan sebagai satu unit | SUDAH ADA |
| F-OU-04 | Pada gudang 2-step keluar, delivery order **belum ada** saat SO dikonfirmasi — ia terbentuk oleh push rule ketika pick divalidasi. Pelatihan pengguna harus menyebut ini eksplisit | SUDAH ADA |
| F-OU-05 | Validasi pengiriman menaruh kejadian di outbox integrasi bila integrasi host aktif | SUDAH ADA |

### 4.7 Cycle count / stock opname — `BR-CC-01..08`

| Fungsi | Perilaku | Status |
|---|---|---|
| F-CC-01 | Rencana hitung mendefinisikan gudang, frekuensi, metode, zona cakupan, target jumlah hitung per periode, dan tanggal jalan berikutnya | SUDAH ADA |
| F-CC-02 | Metode pemilihan objek: `abc_velocity`, `random`, `by_zone`, `by_value`, `last_counted`, dan `spot_check` | SUDAH ADA (5 metode inti + `spot_check` dari `custom_wms_reports`) |
| F-CC-03 | Sesi bernomor `CC/<tahun>/00001`, punya jadwal, waktu mulai/selesai, dan daftar penghitung yang ditugaskan | SUDAH ADA |
| F-CC-04 | Baris hitung menyimpan kuantitas ekspektasi, kuantitas hitung, selisih (nilai & persentase), penghitung, waktu, dan catatan | SUDAH ADA |
| F-CC-05 | Barang yang ditemukan tetapi tidak ada di daftar dapat dicatat sebagai temuan baru berikut nama sementaranya | SUDAH ADA |
| F-CC-06 | Selisih memerlukan persetujuan supervisor; setelah disetujui, penyesuaian stok terbentuk dan sesi ditutup | SUDAH ADA |
| F-CC-07 | Rencana menampilkan persentase cakupan terhadap target periode | SUDAH ADA |
| F-CC-08 | Sesi terbit otomatis dari rencana yang jatuh tempo | **PERLU DIBANGUN** — metode `_cron_generate_sessions()` sudah ada di model, tetapi record `ir.cron` belum terdefinisi. Sampai dibangun, sesi harus dibuat manual atau dipicu dari shell |

### 4.8 Retur & scrap — `BR-RT-01..02`

| Fungsi | Perilaku | Status |
|---|---|---|
| F-RT-01 | Scrap dilakukan dari bin nyata; Scrap Note tercetak dengan barcode referensi dan barcode per baris | SUDAH ADA |
| F-RT-02 | Retur pembelian terekam sebagai picking retur dan tampil pada Purchase Return Report | SUDAH ADA |

## 5. Aplikasi handheld (HHT)

Aplikasi berjalan di `/hht/` sebagai PWA (bukan layar backend Odoo), dirancang untuk layar kecil
dan pemindaian beruntun. Autentikasi memakai sesi pengguna Odoo; perangkat terdaftar di
`hht.device` dan dapat dicabut.

| Halaman | Fungsi operator | Rute utama |
|---|---|---|
| Receive | Memindai penerimaan, mengisi lot/expiry/serial, memvalidasi | `/hht/wms/receive/scan`, `/hht/wms/receive/validate` |
| Putaway | Melihat saran lokasi, menerima atau menimpa | `/hht/wms/putaway/suggest`, `/hht/wms/putaway/apply` |
| Pick | Memindai bin & item, mengonfirmasi baris, memvalidasi | `/hht/wms/pick/confirm`, `/hht/wms/pick/validate` |
| Package | Membentuk paket dan memindahkannya | `/hht/wms/pick/pack`, `/hht/wms/package`, `/hht/wms/package/move` |
| Count | Mengambil sesi & baris hitung, mengirim hasil | `/hht/wms/count/sessions`, `/count/lines`, `/count/submit` |
| Bin-to-Bin | Memindahkan stok antar bin dengan dua pindai | `/hht/wms/bin2bin/list`, `/hht/wms/bin2bin/execute` |
| Stock | Cek stok per bin atau per item | `/hht/wms/stock/lookup` |
| (umum) | Daftar gudang, antrean tugas, resolusi barcode, daftar & detail picking, gate QC | `/warehouses`, `/queue`, `/scan/resolve`, `/pickings`, `/picking`, `/qc` |

Total 21 rute JSON-RPC beraut `auth="user"`, ditambah rute shell `/hht/`.

**Perilaku pemindaian.** Modul menangani "scan burst" — beberapa pindai berurutan yang tiba lebih
cepat dari siklus render — sehingga karakter tidak tercecer antar-field. Perangkat Zebra memakai
profil DataWedge terdokumentasi ([`../hht/datawedge.md`](../../hht/datawedge.md)) dengan simbologi
Code128, EAN-13, QR, dan GS1-128.

**Batas yang harus dinyatakan ke pengguna.** Antrean sinkron (`hht.sync.queue`) tersedia di
platform, tetapi mode kerja **offline penuh** belum diverifikasi terhadap perangkat klien —
lihat `BR-DV-05`. Sampai diuji, asumsi kerja adalah handheld **online**.

## 6. Dokumen & pelaporan

### 6.1 Dokumen PDF — `BR-RP-01..02, BR-RP-06`

| Dokumen | Objek | Barcode transaksi | Barcode baris item |
|---|---|---|---|
| WMS Picking List | `stock.picking` | nama picking (Code128) | barcode item + QR lokasi per baris |
| WMS Packing List | `stock.picking` | nama picking (Code128) | Code128 paket + QR per blok |
| WMS Barcode List (lembar pindai) | `stock.picking` | — | setiap paket & produk, QR dan Code128 |
| WMS Price Tag / Product Label | `product.product` | — | satu barcode per stiker |
| WMS Stock Take Report | `custom.cycle.count.session` | nama sesi (Code128) | lot atau SKU per baris hitung |
| WMS Scrap Note | `stock.scrap` | referensi scrap (Code128) | lot atau SKU per baris |

Picking List juga tercetak untuk **receipt**, sehingga lembar GR adalah dokumen yang sama dengan
yang sudah dikenal picker dan operator putaway.

### 6.2 Laporan analisis & ekspor XLSX — `BR-RP-03..04`

| Laporan | Barcode dokumen | Barcode item |
|---|---|---|
| Transfer Report | picking | lot / SKU |
| Stock Summary (kuantitas + nilai) | bin | lot / SKU |
| Stock Take | sesi hitung | lot / SKU |
| Purchase Return | picking | SKU |
| Scrap Report | scrap order | lot / SKU |

Setiap laporan memiliki tombol **Export XLSX (with barcode)** di header list. Dengan baris terpilih,
yang diekspor adalah pilihan; tanpa pilihan, seluruh laporan. Workbook memuat dua kolom gambar
barcode — `Document Barcode` (kolom A) dan `Item Barcode` (kolom B) — lalu kolom data, satu baris
header datar, autofilter, dan baris total.

### 6.3 Simbologi — `BR-RP-05`

- Barcode **dokumen** selalu Code128, karena referensi mengandung karakter `/`.
- Barcode **item** dirender adaptif: payload 13 digit menjadi EAN-13 sungguhan, selebihnya jatuh ke
  Code128. Ini penting karena handheld kerap dikirim dengan pembacaan Code128 dimatikan.

## 7. Integrasi sistem host — `BR-IT-01..06`

| Arah | Endpoint | Isi |
|---|---|---|
| Host → Odoo | `POST /api/wms/asn` | Rencana kedatangan; membentuk penerimaan di Odoo |
| Host → Odoo | `POST /api/wms/do` | Perintah pengiriman; membentuk delivery di Odoo |
| Host → Odoo | `POST /api/wms/ack` | Pengakuan atas kejadian yang dikirim Odoo |
| Odoo → Host | `GET /api/wms/stock` | Posisi stok terkini (ditarik host) |
| Odoo → Host | Outbox `wms.integration.event` | Kejadian gudang dikirim dengan percobaan ulang; cron `cron_drain_wms_outbox` yang menguras antrean |

Setiap kejadian menyimpan jenis, model & id sumber, payload, status, jumlah percobaan, galat
terakhir, referensi eksternal, waktu kirim, dan waktu di-ack — sehingga pertanyaan "dokumen ini
sudah sampai ke host belum?" dapat dijawab dari satu layar.

Pemetaan kode host ↔ Odoo dikelola di `wms.integration.mapping`, jadi perbedaan penamaan gudang
atau SKU tidak memerlukan perubahan kode.

**Keamanan.** Seluruh endpoint bertipe `json2`, `auth="none"`, dan dijaga oleh dekorator
`@secure_endpoint('wms')`: tanda tangan HMAC-SHA256, toleransi selisih waktu, nonce anti-replay,
dan pembatasan CIDR. Panggilan tanpa tanda tangan sah ditolak.

## 8. User journey

### J1 — Penerimaan barang dari PO (operator inbound)

1. Supervisor mengonfirmasi PO; Odoo membuat receipt `IN`.
2. Operator membuka handheld ▸ **Receive**, memindai nomor receipt atau memilih dari antrean.
3. Untuk setiap baris: pindai barcode item. Bila GS1, lot dan tanggal kedaluwarsa terisi sendiri.
   Bila SKU ber-serial, tiap pindai membuat satu baris.
4. Barang tak dikenal → tombol registrasi; operator mengisi deskripsi & kuantitas, dokumen fisik
   disisihkan menunggu persetujuan.
5. Operator memvalidasi. Pada gudang 2-step, leg kedua (`STOR`) terbentuk berikut saran putaway.
6. Lembar GR dicetak dari Print ▸ WMS Picking List.

### J2 — Putaway (operator putaway)

1. Handheld ▸ **Putaway** menampilkan antrean baris `STOR` beserta bin yang disarankan dan skornya.
2. Operator memindai barang, membaca saran, lalu memindai bin fisik.
3. Bin dipindai sama dengan saran → baris selesai. Bin berbeda → sistem menerima sebagai penimpaan
   dan menyimpannya untuk evaluasi kualitas mesin.
4. Setelah semua baris selesai, leg `STOR` divalidasi; stok kini duduk di bin.

### J3 — Picking sampai pengiriman (picker & packer)

1. SO dikonfirmasi → leg `PICK` memesan stok terhadap bin nyata.
2. Picker membuka handheld ▸ **Pick**; sistem menuntun mengikuti urutan jalan bin.
3. Di setiap perhentian: pindai bin, pindai item, konfirmasi kuantitas. Salah bin atau salah item ditolak.
4. Picker memvalidasi pick. **Push rule membuat delivery order** — sebelum langkah ini, DO belum ada.
5. Packer membuka handheld ▸ **Package**, membentuk paket, mencetak Packing List dan Barcode List.
6. Pengiriman divalidasi; bila integrasi aktif, kejadian masuk outbox.

### J4 — Cycle count (penghitung & supervisor)

1. Sesi terbit dari rencana (saat ini: dibuat manual — lihat F-CC-08), lalu penghitung ditugaskan.
2. Penghitung membuka handheld ▸ **Count**, mengambil baris sesinya, memindai bin dan item,
   memasukkan kuantitas hitung.
3. Barang yang ditemukan tetapi tidak terdaftar dicatat sebagai temuan baru.
4. Sistem menghitung selisih per baris (kuantitas dan persentase).
5. Supervisor memeriksa selisih, meminta hitung ulang bila perlu, lalu menyetujui.
6. Penyesuaian stok terbentuk, sesi ditutup, Stock Take Report dicetak sebagai bukti.

### J5 — Replenishment rak pick (otomatis + operator)

1. Stok bin pick turun di bawah batas bawah yang diatur pada aturan transfer.
2. Cron mengevaluasi aturan dan memateralisasi perintah `TO/<tahun>/xxxxx`.
3. Operator membuka handheld ▸ **Bin-to-Bin**, memindai bin asal dan bin tujuan.
4. Stok berpindah; perintah ditandai selesai. Slip pick berbarcode tersedia bila dibutuhkan.

### J6 — Menyalakan integrasi host pertama kali (IT)

1. Sepakati kontrak: payload ASN, DO, format stok, dan format ack.
2. Daftarkan kunci HMAC dan daftar CIDR yang diizinkan di sisi Odoo.
3. Isi pemetaan kode host ↔ Odoo untuk gudang, SKU, dan mitra.
4. Uji `POST /api/wms/asn` di staging → penerimaan terbentuk → validasi → kejadian keluar di outbox.
5. Nyalakan cron pengurasan outbox; pantau layar kejadian selama minggu pertama.

### J7 — Onboarding gudang baru (Warehouse Manager)

1. Buat gudang dengan alur masuk/keluar yang sesuai.
2. Impor zona dan bin berikut barcode, kapasitas, dan urutan jalan.
3. Definisikan kategori penyimpanan dan tipe paket, lalu stempelkan ke bin.
4. Buat strategi putaway dan aturan bertingkatnya; jalankan dengan `auto_apply_suggestions` **mati**
   selama masa observasi.
5. Buat rencana cycle count dan aturan transfer.
6. Muat saldo awal stok per bin.
7. Naikkan `auto_apply_suggestions` setelah kualitas saran terbukti dari data penimpaan.

## 9. Perilaku non-fungsional (sudut pandang fungsional)

| Aspek | Perilaku yang dijanjikan ke pengguna |
|---|---|
| Kecepatan cetak | Dokumen tercetak dalam 2,6–6,2 detik melalui HTTP normal. Pengukuran lewat `odoo shell --no-http` **tidak sah** — tanpa server HTTP, wkhtmltopdf menunggu callback dan butuh puluhan detik per dokumen |
| Konkurensi | Beberapa operator dapat menghitung, memick, dan menyimpan bersamaan; pemesanan stok dikendalikan Odoo pada tingkat quant |
| Jejak audit | Perubahan pada objek WMS terekam beserta pelaku dan waktunya |
| Isolasi data | Satu basis data per klien; pengguna satu klien tidak dapat menjangkau data klien lain |
| Ketersediaan | Layanan berjalan di kontainer dengan restart otomatis; batas pemulihan bencana dinyatakan di [`04-Architecture.md`](04-Architecture.md) |
| Bahasa | Antarmuka mengikuti bahasa pengguna Odoo; dokumen cetak menghormati UTF-8 (charset dideklarasikan di dalam `<main>`) |

## 10. Acceptance test representatif

Diturunkan dari POC yang sudah dijalankan (12 kategori, 14/14 PASS). Setiap baris adalah kriteria
lulus yang dapat diperagakan di depan klien.

| # | Skenario | Kriteria lulus | BR |
|---|---|---|---|
| AT-01 | Buat gudang 2-step masuk & 2-step keluar | Empat jenis operasi (IN/STOR/PICK/OUT) terbentuk otomatis | BR-WH-01 |
| AT-02 | Impor 3 zona dan 13 bin berbarcode | Setiap bin punya barcode unik, kapasitas volume, dan urutan jalan | BR-WH-02, BR-WH-03 |
| AT-03 | Definisikan kategori penyimpanan berkapasitas per tipe paket | Kategori tertempel pada seluruh bin; pelanggaran kapasitas tertolak | BR-WH-03 |
| AT-04 | Terima PO berisi SKU ber-lot+expiry dan SKU ber-serial | Lot & tanggal kedaluwarsa terisi dari pindai GS1; SKU serial menghasilkan satu baris per unit | BR-IN-02, BR-IN-04 |
| AT-05 | Pindai barang tak dikenal saat GR | Registrasi terbentuk; barang tidak menjadi produk sebelum disetujui | BR-IN-07 |
| AT-06 | Arahkan penerimaan ke lokasi QC lalu coba jual barangnya | Pemesanan outbound **tidak** mengambil stok QC | BR-QC-02 |
| AT-07 | Jalankan mesin putaway atas leg `STOR` | Saran terbit dengan skor, keyakinan, aturan pemicu, dan alasan | BR-PA-01, BR-PA-04 |
| AT-08 | Timpa satu saran dari handheld | Lokasi timpaan tersimpan terpisah dari lokasi saran | BR-PA-06 |
| AT-09 | Aktifkan mode SAP dan slot satu produk | Lokasi terpilih sesuai urutan tipe penyimpanan × seksi; skor sesuai formula | BR-PA-07 |
| AT-10 | Pindahkan stok `bin-A → bin-B` dari handheld | Pergerakan internal tercatat; stok kedua bin berubah sesuai | BR-ST-01 |
| AT-11 | Turunkan stok bin pick di bawah batas lalu jalankan evaluasi aturan | Perintah transfer terbit dan termaterialisasi menjadi pergerakan stok | BR-ST-02, BR-ST-06 |
| AT-12 | Konfirmasi SO, pick, lalu validasi | Delivery order **baru terbentuk** setelah pick divalidasi (push rule) | BR-OU-04 |
| AT-13 | Jalankan sesi hitung dengan satu selisih kurang | Selisih terhitung; penyesuaian **tidak** terposting sebelum supervisor menyetujui | BR-CC-05 |
| AT-14 | Catat barang temuan baru saat menghitung | Baris bertanda temuan baru, lengkap dengan nama sementara | BR-CC-06 |
| AT-15 | Scrap barang rusak dari bin nyata | Scrap Note tercetak dengan barcode referensi dan barcode per baris | BR-RT-01 |
| AT-16 | Cetak keenam dokumen PDF | Setiap dokumen membawa barcode transaksi dan/atau barcode baris sesuai tabel §6.1 | BR-RP-01, BR-RP-02 |
| AT-17 | Ekspor kelima laporan ke XLSX | Setiap workbook punya kolom Document Barcode dan Item Barcode berisi gambar barcode | BR-RP-04 |
| AT-18 | Cetak label untuk SKU ber-GTIN 13 digit dan SKU berkode internal | Yang 13 digit keluar sebagai EAN-13; sisanya Code128 | BR-RP-05 |
| AT-19 | Daftarkan handheld lalu cabut aksesnya | Perangkat tercabut tidak dapat lagi memanggil API HHT | BR-DV-03 |
| AT-20 | Kirim `POST /api/wms/asn` tanpa tanda tangan HMAC yang sah | Permintaan ditolak; tidak ada penerimaan terbentuk | BR-IT-06 |
| AT-21 | Validasi pengiriman dengan integrasi aktif | Kejadian masuk outbox dan terkuras oleh cron; status berubah menjadi terkirim/ter-ack | BR-IT-04 |
| AT-22 | Masuk sebagai penghitung lalu coba ubah aturan putaway | Akses ditolak sesuai grup | BR-NF-01 |

## 11. Matriks traceability BR → fungsi

| Area BR | BR | Fungsi FSD | Acceptance test |
|---|---|---|---|
| Struktur gudang | BR-WH-01..07 | F-WH-01..07 | AT-01, AT-02, AT-03 |
| Inbound | BR-IN-01..07 | F-IN-01..08 | AT-04, AT-05 |
| QC | BR-QC-01..04 | F-QC-01..04 | AT-06 |
| Putaway | BR-PA-01..08 | F-PA-01..06 (+tabel jenis aturan) | AT-07, AT-08, AT-09 |
| Penyimpanan | BR-ST-01..07 | F-ST-01..07 | AT-10, AT-11 |
| Outbound | BR-OU-01..05 | F-OU-01..05 | AT-12 |
| Cycle count | BR-CC-01..08 | F-CC-01..08 | AT-13, AT-14 |
| Retur & scrap | BR-RT-01..02 | F-RT-01..02 | AT-15 |
| Dokumen & laporan | BR-RP-01..06 | §6.1, §6.2, §6.3 | AT-16, AT-17, AT-18 |
| Handheld | BR-DV-01..06 | §5 | AT-19 |
| Integrasi | BR-IT-01..06 | §7 | AT-20, AT-21 |
| Non-fungsional | BR-NF-01..06 | §9 | AT-22 |

**Item bertanda PERLU DIBANGUN pada dokumen ini:** F-CC-08 (record `ir.cron` untuk penerbitan sesi
hitung otomatis) dan verifikasi BR-DV-05 (mode offline handheld). Keduanya masuk sebagai effort
eksplisit pada [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md).
