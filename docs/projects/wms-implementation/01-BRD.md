# Business Requirements Document (BRD)
## Implementasi Warehouse Management System di atas Odoo 19

| | |
|---|---|
| **Dokumen** | BRD — WMS Implementation (generic) |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Scope** | Operasi gudang: inbound, putaway/slotting, penyimpanan, picking/packing, outbound, stock opname, retur & scrap, pelaporan, perangkat handheld, integrasi host |
| **Basis platform** | Odoo 19 CE + 10 modul `custom_wms_*` (`addons/ee_gap/`) + `core/custom_hht_bridge` |
| **Bukti kapabilitas** | [`../warehouse-jds/WMS-POC-Scenario.md`](../warehouse-jds/WMS-POC-Scenario.md) — POC 14/14 PASS |
| **Dokumen terkait** | [`00-Project-Initiation-Document.md`](00-Project-Initiation-Document.md), [`02-FSD.md`](02-FSD.md), [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) |

---

## Contents

1. [Latar belakang](#1-latar-belakang)
2. [Masalah bisnis yang diselesaikan](#2-masalah-bisnis-yang-diselesaikan)
3. [Tujuan bisnis & KPI](#3-tujuan-bisnis--kpi)
4. [Ruang lingkup](#4-ruang-lingkup)
5. [Proses bisnis target](#5-proses-bisnis-target)
6. [Daftar kebutuhan bisnis (BR)](#6-daftar-kebutuhan-bisnis-br)
7. [Aturan bisnis kunci](#7-aturan-bisnis-kunci)
8. [Pemangku kepentingan & peran](#8-pemangku-kepentingan--peran)
9. [Asumsi & ketergantungan](#9-asumsi--ketergantungan)
10. [Risiko bisnis](#10-risiko-bisnis)

---

## 1. Latar belakang

Gudang distribusi retail dan e-commerce di Indonesia umumnya menjalankan Odoo (atau ERP lain)
hanya sampai tingkat *stock ledger*: berapa stok per gudang. Yang tidak tertangani adalah
lapisan **eksekusi gudang** — di rak mana barang diletakkan, siapa yang memindahkan, dengan
alat apa dipindai, dan bagaimana selisih hitung dipertanggungjawabkan.

Platform ini sudah memiliki lapisan tersebut dalam bentuk 10 modul WMS yang berjalan di atas
Odoo 19 dan sudah dibuktikan end-to-end lewat POC (14 dari 14 kategori transaksi lulus, dijalankan
terhadap record nyata, bukan mock). Dokumen ini menetapkan kebutuhan bisnis yang harus dipenuhi
oleh implementasi WMS untuk satu klien, terlepas dari klien mana.

Sebagai referensi skala yang sudah pernah dijalankan di platform ini:

| Dataset | Skala | Sumber |
|---|---|---|
| Demo JD Sport Cikupa | 1 gudang, 3 zona, 13 bin, 8 SKU | `scripts/tenants/wms_demo/` |
| W07 ECOMMERCE (racking SAP) | 1 gudang, 154 bin, 3.292 SKU | `scripts/tenants/wms_ecomm/` |

## 2. Masalah bisnis yang diselesaikan

| # | Masalah | Dampak bisnis hari ini |
|---|---|---|
| P1 | Penempatan barang mengandalkan hafalan operator | Barang "hilang" di gudang; waktu cari lama; rak penuh tidak merata |
| P2 | Tidak ada lokasi bin di sistem, hanya gudang | Picking berjalan tanpa rute; operator baru butuh berminggu-minggu untuk produktif |
| P3 | Penerimaan barang tanpa kontrol batch/expiry | Barang kedaluwarsa terkirim ke pelanggan; klaim & retur |
| P4 | Barang belum diperiksa QC ikut terjual | Barang cacat terkirim; rekonsiliasi manual |
| P5 | Stock opname dilakukan tahunan dengan tutup gudang | Operasi berhenti; selisih besar baru ketahuan setahun sekali |
| P6 | Selisih hitung tidak punya jejak persetujuan | Penyesuaian stok tidak dapat diaudit |
| P7 | Dokumen gudang tidak dapat dipindai | Setiap serah-terima diketik ulang; salah ketik jadi selisih |
| P8 | Laporan gudang dirakit manual di Excel | Laporan telat; angka berbeda antar-departemen |
| P9 | Handheld tidak terhubung ke sistem | Pemindaian dicatat di kertas lalu diinput; jeda data berjam-jam |
| P10 | Integrasi ke sistem host (SAP/marketplace) manual | ASN & delivery order diinput dua kali |

## 3. Tujuan bisnis & KPI

| # | Tujuan | KPI | Baseline umum | Target |
|---|---|---|---|---|
| G1 | Akurasi inventori per lokasi | Akurasi hitung siklik (line hit rate) | 90–95% | ≥ 99% |
| G2 | Hentikan tutup gudang untuk opname | Frekuensi opname penuh per tahun | 1–2× | 0 (diganti cycle count berkala) |
| G3 | Percepat penerimaan | Waktu GR per truk | — (diukur saat fit-gap) | turun ≥ 30% |
| G4 | Percepat picking | Baris pick per operator per jam | — | naik ≥ 25% |
| G5 | Kendali mutu inbound | % barang QC yang bocor ke outbound | > 0 | 0 |
| G6 | Ketertelusuran batch/serial | % pengiriman dengan lot/serial tercatat | parsial | 100% untuk SKU ber-tracking |
| G7 | Pelaporan tepat waktu | Lag laporan stok | harian–mingguan, manual | real-time (on-demand) |
| G8 | Kurangi input ganda | Dokumen yang diinput ulang manual | tinggi | 0 untuk alur terintegrasi |

> KPI baseline diisi pada fase **Requirement & fit-gap**; angka target di atas adalah target
> indikatif yang harus dikonfirmasi bersama klien sebelum masuk kontrak.

## 4. Ruang lingkup

### 4.1 In-scope

- Konfigurasi gudang bertingkat: gudang → zona → bin, dengan barcode, kapasitas, dan urutan jalan.
- Penerimaan barang (GR) dengan pemindaian, batch/expiry/serial, dan import massal.
- Karantina & gate QC inbound, termasuk registrasi barang yang belum ada di master.
- Mesin putaway/slotting bertingkat, termasuk mode pencarian penyimpanan dua dimensi ala SAP.
- Transfer internal & bin-to-bin, termasuk replenishment otomatis dari rak cadangan ke rak pick.
- Picking, packing, dan pengiriman.
- Cycle count / stock opname berkala dengan alur persetujuan selisih.
- Retur pembelian dan scrap.
- Dokumen tercetak berbarcode dan pelaporan (PDF + XLSX).
- Aplikasi handheld (PWA) untuk operator gudang.
- Integrasi ke sistem host eksternal melalui API ber-HMAC (ASN, delivery order, stok, ack).
- Hak akses per peran, jejak audit, dan kepatuhan UU PDP.

### 4.2 Out-of-scope (kecuali dinyatakan lain dalam SOW per klien)

| Area | Alasan | Pemilik |
|---|---|---|
| Pengembangan di sisi sistem host (SAP/WMS lama/marketplace) | Bukan Odoo; kontrak API disepakati, sisi host dibangun tim klien | Tim klien |
| Pengadaan perangkat handheld, printer label, jaringan Wi-Fi gudang | Infrastruktur fisik | Tim klien |
| Otomasi fisik (conveyor, ASRS, robot, put-to-light) | Di luar cakupan perangkat lunak WMS ini | Vendor otomasi |
| Transport Management (rute, ongkir, tracking kurir) | Modul terpisah | — |
| Akuntansi biaya lanjutan (landed cost multi-tier, standar costing revaluasi) | Domain modul akuntansi | Tim akuntansi |
| Migrasi data historis transaksi gudang bertahun-tahun | Yang dimigrasi adalah master + saldo awal stok | Kesepakatan per klien |

## 5. Proses bisnis target

```
                      ┌─────────────────────── SISTEM HOST (opsional) ───────────────────────┐
                      │  ASN masuk         Delivery order         Stok keluar        Ack     │
                      └────┬─────────────────────┬─────────────────────┬──────────────┬──────┘
                           v                     v                     ^              ^
  PO / ASN ─► PENERIMAAN ─► QC / KARANTINA ─► PUTAWAY ─► PENYIMPANAN ─► PICKING ─► PACKING ─► PENGIRIMAN
                 │               │                │           │            │          │
                 │               │                │           │            │          └─► Dokumen berbarcode
                 │               │                │           │            └─► Transfer bin-to-bin / replenishment
                 │               │                │           └─► CYCLE COUNT ─► Persetujuan selisih ─► Penyesuaian
                 │               │                └─► Saran lokasi (mesin slotting, berskor)
                 │               └─► Registrasi barang tak dikenal ─► Persetujuan ─► Master produk
                 └─► Retur pembelian (RTV)                     SCRAP ◄─── barang rusak dari bin mana pun
```

Ringkas per tahap:

| Tahap | Pemicu | Keluaran | Bukti cetak |
|---|---|---|---|
| Penerimaan | PO dikonfirmasi / ASN dari host | Receipt tervalidasi, lot & expiry tercatat | Picking List (dipakai juga sebagai lembar GR) |
| QC / karantina | Jenis operasi menandai perlu inspeksi | Barang lolos → siap putaway; barang tolak → ditahan | — |
| Putaway | Leg kedua penerimaan (2-step) | Saran bin berskor; operator menerima atau menimpa | — |
| Penyimpanan | — | Stok per bin, per lot/serial | Stock Summary |
| Picking | SO dikonfirmasi | Pick tervalidasi terhadap bin nyata | Picking List |
| Packing | Pick selesai | Paket terbentuk, berbarcode | Packing List, Barcode List |
| Pengiriman | Push rule dari pick | Delivery order terkirim | Delivery slip |
| Cycle count | Rencana berkala / spot check | Sesi hitung → selisih → penyesuaian terposting | Stock Take / Spot Check |
| Retur & scrap | Barang rusak / retur ke pemasok | RTV / scrap order | Scrap Note, Purchase Return |

## 6. Daftar kebutuhan bisnis (BR)

Prioritas memakai MoSCoW: **M** = Must, **S** = Should, **C** = Could.
Kolom **Status platform** menyatakan apakah kebutuhan ini sudah dipenuhi oleh modul yang ada
(**SUDAH ADA** = terverifikasi di repo) atau masih harus dibangun/dikonfigurasi.

### 6.1 Struktur gudang & master data

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-WH-01 | Sistem harus mendukung banyak gudang dalam satu basis data, dengan alur masuk/keluar 1-step, 2-step, atau 3-step per gudang | M | SUDAH ADA (Odoo core) |
| BR-WH-02 | Lokasi harus bertingkat gudang → zona → bin, setiap bin punya barcode unik | M | SUDAH ADA |
| BR-WH-03 | Setiap bin harus dapat menyimpan kapasitas (berat, volume, jumlah paket per tipe paket) dan urutan jalan (walk sequence) | M | SUDAH ADA |
| BR-WH-04 | Bin harus dapat ditandai sebagai area karantina/QC sehingga stok di dalamnya tidak dapat dipesan untuk outbound | M | SUDAH ADA |
| BR-WH-05 | Produk harus dapat membawa klasifikasi ABC, tipe paket, berat, dan volume sebagai dasar slotting | M | SUDAH ADA |
| BR-WH-06 | Satu SKU harus dapat memiliki lebih dari satu barcode (GTIN alternatif) | S | SUDAH ADA |
| BR-WH-07 | Master produk, pemasok, dan pelanggan harus dapat dimuat massal dari CSV/XLSX | M | SUDAH ADA (import Odoo + wizard WMS) |

### 6.2 Inbound & penerimaan

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-IN-01 | Penerimaan harus dapat dijalankan dengan memindai barcode item, bukan mengetik | M | SUDAH ADA |
| BR-IN-02 | Sistem harus membaca barcode GS1 dan mengambil tanggal kedaluwarsa (AI 17), nomor batch (AI 10), dan serial (AI 21) langsung dari hasil pindai | M | SUDAH ADA |
| BR-IN-03 | Nomor batch pemasok harus tersimpan terpisah dari nomor lot internal | S | SUDAH ADA |
| BR-IN-04 | Untuk SKU ber-serial (mis. IMEI), setiap unit harus menjadi satu baris tersendiri | M | SUDAH ADA |
| BR-IN-05 | Penerimaan berjumlah besar harus dapat diimpor dari CSV/XLSX dengan template kosong yang dapat diunduh | S | SUDAH ADA |
| BR-IN-06 | Penerimaan berjumlah sangat besar harus dapat divalidasi secara latar belakang tanpa memblokir layar operator | C | SUDAH ADA (`custom_receipt_async`) |
| BR-IN-07 | Barang yang dipindai tetapi tidak dikenal di master harus dapat diregistrasi oleh operator dan disetujui supervisor sebelum menjadi produk | S | SUDAH ADA |

### 6.3 QC inbound

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-QC-01 | Jenis operasi tertentu harus dapat mewajibkan inspeksi sebelum barang boleh disimpan | M | SUDAH ADA |
| BR-QC-02 | Stok yang berada di lokasi QC tidak boleh dapat dipesan untuk pengiriman, bahkan oleh proses otomatis | M | SUDAH ADA (dikecualikan pada tingkat *gather* `stock.quant`) |
| BR-QC-03 | Barang yang ditolak harus mencatat alasan penolakan | M | SUDAH ADA |
| BR-QC-04 | Keputusan lolos/tolak harus terekam beserta pelaku dan waktunya | M | SUDAH ADA (audit trail) |

### 6.4 Putaway & slotting

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-PA-01 | Sistem harus menyarankan lokasi simpan, bukan memaksa operator memilih sendiri | M | SUDAH ADA |
| BR-PA-02 | Aturan penempatan harus bertingkat (prioritas), sehingga aturan khusus mengalahkan aturan umum | M | SUDAH ADA (6 tier) |
| BR-PA-03 | Strategi penempatan harus mencakup minimal: lokasi tetap, bin kosong terdekat, rotasi antar-zona, kesesuaian volume, kesesuaian dimensi (PxLxT), sisa kapasitas berat, zona suhu, dan kecepatan putar (ABC) | M | SUDAH ADA (9 jenis aturan) |
| BR-PA-04 | Saran harus punya skor dan tingkat keyakinan, sehingga saran lemah dapat ditolak otomatis | M | SUDAH ADA |
| BR-PA-05 | Saran boleh diterapkan otomatis di atas ambang keyakinan tertentu, dan sisanya direview operator | M | SUDAH ADA (`auto_apply_suggestions`) |
| BR-PA-06 | Operator harus dapat menimpa saran, dan penimpaan itu tercatat | M | SUDAH ADA (`overridden_location_id`) |
| BR-PA-07 | Untuk gudang bergaya SAP, pencarian penyimpanan harus dua dimensi: tipe penyimpanan (Lagertyp) × seksi (Lagerbereich) | S | SUDAH ADA (`custom_wms_sap_slotting`) |
| BR-PA-08 | Aturan penempatan khusus harus dapat ditulis tanpa mengubah kode inti | C | SUDAH ADA (jenis aturan `custom_python`, dibatasi hak akses) |

### 6.5 Penyimpanan & pergerakan internal

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-ST-01 | Pemindahan bin-to-bin harus dapat dijalankan dari handheld dengan dua pindai (asal, tujuan) | M | SUDAH ADA |
| BR-ST-02 | Sistem harus dapat membuat perintah pemindahan otomatis saat stok rak pick turun di bawah batas | M | SUDAH ADA (trigger low-water) |
| BR-ST-03 | Sistem harus dapat membuat perintah pemindahan otomatis untuk barang mendekati kedaluwarsa | S | SUDAH ADA (trigger expiry) |
| BR-ST-04 | Sistem harus dapat membuat perintah konsolidasi zona | S | SUDAH ADA |
| BR-ST-05 | Setiap perintah pemindahan harus punya nomor dan slip berbarcode yang dapat dicetak | M | SUDAH ADA |
| BR-ST-06 | Perintah pemindahan harus dapat dievaluasi dan dieksekusi terjadwal | M | SUDAH ADA (cron `cron_evaluate_and_materialize`) |
| BR-ST-07 | Strategi pengeluaran per kategori produk harus dapat diatur (FEFO untuk barang berexpiry) | M | SUDAH ADA (Odoo core, dikonfigurasi skrip 51) |

### 6.6 Outbound: picking, packing, pengiriman

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-OU-01 | Pick harus memesan stok terhadap bin nyata, bukan hanya terhadap gudang | M | SUDAH ADA |
| BR-OU-02 | Operator harus memindai bin dan item saat picking untuk mencegah salah ambil | M | SUDAH ADA |
| BR-OU-03 | Barang terpick harus dapat dimasukkan ke paket berbarcode | M | SUDAH ADA |
| BR-OU-04 | Pengiriman harus terbentuk otomatis setelah pick divalidasi (push rule pada gudang 2-step) | M | SUDAH ADA |
| BR-OU-05 | Titipan pengiriman ke sistem host harus dapat dikirim otomatis saat pengiriman divalidasi | S | SUDAH ADA (outbox integrasi) |

### 6.7 Cycle count / stock opname

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-CC-01 | Sistem harus mendukung hitung berkala tanpa menutup gudang | M | SUDAH ADA |
| BR-CC-02 | Pemilihan objek hitung harus dapat memakai metode: kecepatan ABC, acak, per zona, per nilai, terlama tidak dihitung, dan spot check | M | SUDAH ADA (6 metode) |
| BR-CC-03 | Setiap sesi hitung harus punya nomor unik yang dapat dipindai | M | SUDAH ADA (urutan `CC/%(year)s/00001`) |
| BR-CC-04 | Penghitung harus dapat memasukkan hasil dari handheld | M | SUDAH ADA |
| BR-CC-05 | Selisih harus melalui persetujuan supervisor sebelum stok disesuaikan | M | SUDAH ADA |
| BR-CC-06 | Barang yang ditemukan di bin tetapi tidak ada di daftar hitung harus dapat dicatat sebagai temuan baru | S | SUDAH ADA (`is_new_item`) |
| BR-CC-07 | Cakupan hitung terhadap target periode harus terukur | S | SUDAH ADA (`coverage_pct`) |
| BR-CC-08 | Sesi hitung harus terbit otomatis dari rencana yang jatuh tempo, tanpa dibuat manual | M | **PERLU DIBANGUN** — metode `_cron_generate_sessions()` sudah ada, tetapi record `ir.cron`-nya belum terdefinisi (`data/cron.xml` masih placeholder) |

### 6.8 Retur & scrap

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-RT-01 | Barang rusak harus dapat di-scrap dari bin nyata dan menghasilkan Scrap Note berbarcode | M | SUDAH ADA |
| BR-RT-02 | Retur ke pemasok harus terlacak dan terlaporkan | M | SUDAH ADA (Purchase Return Report) |

### 6.9 Dokumen & pelaporan

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-RP-01 | Setiap dokumen gudang harus memuat barcode pada **tingkat transaksi** dan **tingkat baris item** | M | SUDAH ADA |
| BR-RP-02 | Dokumen wajib: Picking List, Packing List, Barcode List (lembar pindai), Label Produk/Price Tag, Stock Take, Scrap Note | M | SUDAH ADA (6 dokumen PDF) |
| BR-RP-03 | Laporan analisis wajib: Transfer, Stock Summary (qty + nilai), Stock Take, Purchase Return, Scrap | M | SUDAH ADA (5 laporan) |
| BR-RP-04 | Setiap laporan analisis harus dapat diekspor ke XLSX dengan gambar barcode tertanam pada kolom dokumen dan kolom item | M | SUDAH ADA |
| BR-RP-05 | Simbologi harus adaptif: payload 13 digit dicetak sebagai EAN-13, selebihnya Code128 | M | SUDAH ADA |
| BR-RP-06 | Lembar GR harus memakai dokumen yang sama dengan yang sudah dikenal picker (Picking List juga mencetak untuk receipt) | S | SUDAH ADA |

> Catatan simbologi: banyak handheld dikirim dengan pembacaan Code128 **dimatikan**
> (unit Denso BHT pada proyek ini hanya membaca EAN-13). Simbologi harus dikonfirmasi
> terhadap perangkat riil klien pada fase fit-gap, bukan diasumsikan.

### 6.10 Perangkat handheld

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-DV-01 | Operator harus bekerja dari aplikasi handheld, bukan dari layar desktop Odoo | M | SUDAH ADA (PWA `custom_wms_hht`) |
| BR-DV-02 | Aplikasi handheld harus mencakup: penerimaan, putaway, picking, packing, hitung, bin-to-bin, dan cek stok | M | SUDAH ADA (7 halaman) |
| BR-DV-03 | Perangkat harus terdaftar dan dapat dicabut aksesnya | M | SUDAH ADA (`hht.device` + wizard regenerasi secret) |
| BR-DV-04 | Setiap pindai harus tercatat untuk penelusuran | M | SUDAH ADA (`hht.scan.log`) |
| BR-DV-05 | Aplikasi harus tetap dapat dipakai saat jaringan gudang terputus sesaat, dan menyusul saat tersambung | S | **PERLU DIBANGUN/DIVERIFIKASI** — model antrean `hht.sync.queue` sudah ada, perilaku offline penuh harus diuji terhadap perangkat klien |
| BR-DV-06 | Perangkat Zebra harus dapat memakai profil DataWedge standar | S | SUDAH ADA (`../hht/datawedge.md`) |

### 6.11 Integrasi

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-IT-01 | Sistem host harus dapat mengirim ASN (rencana kedatangan) ke Odoo | S | SUDAH ADA (`POST /api/wms/asn`) |
| BR-IT-02 | Sistem host harus dapat mengirim perintah pengiriman ke Odoo | S | SUDAH ADA (`POST /api/wms/do`) |
| BR-IT-03 | Sistem host harus dapat membaca posisi stok dari Odoo | S | SUDAH ADA (`GET /api/wms/stock`) |
| BR-IT-04 | Kejadian gudang harus terkirim ke host secara andal, dengan percobaan ulang dan pencatatan galat | S | SUDAH ADA (pola outbox + cron drain) |
| BR-IT-05 | Kode master antara host dan Odoo harus dapat dipetakan tanpa mengubah kode | S | SUDAH ADA (`wms.integration.mapping`) |
| BR-IT-06 | Semua panggilan API harus tertandatangani dan tertolak bila kedaluwarsa atau diulang | M | SUDAH ADA (HMAC-SHA256 + drift + nonce + CIDR) |

### 6.12 Non-fungsional

| ID | Kebutuhan | Prio | Status platform |
|---|---|:--:|---|
| BR-NF-01 | Hak akses harus per peran gudang, bukan admin untuk semua | M | SUDAH ADA (13 grup) |
| BR-NF-02 | Perubahan data operasional harus terekam beserta pelakunya | M | SUDAH ADA (`pdp.audited.mixin`) |
| BR-NF-03 | Data pribadi harus diperlakukan sesuai UU PDP 27/2022 | M | SUDAH ADA (`../pdp-compliance.md`) |
| BR-NF-04 | Data satu klien harus terisolasi dari klien lain di platform | M | SUDAH ADA (satu basis data per tenant + `DBFILTER`) |
| BR-NF-05 | Dokumen harus tercetak dalam hitungan detik pada beban normal | M | SUDAH ADA (2,6–6,2 detik terukur melalui HTTP) |
| BR-NF-06 | Sistem harus dapat dipulihkan dari kegagalan dalam batas RPO/RTO yang disepakati | M | **PERLU DIKONFIRMASI** — RPO nyata saat ini 24 jam (backup harian); WAL archiving belum aktif. Lihat [`04-Architecture.md`](04-Architecture.md) §Batasan |

## 7. Aturan bisnis kunci

| # | Aturan |
|---|---|
| AB-1 | Stok di lokasi QC/karantina **tidak pernah** tersedia untuk pemesanan outbound — dikecualikan pada tingkat pengumpulan stok, bukan sekadar disembunyikan di layar. |
| AB-2 | Saran putaway bersifat **usulan**; operator berhak menimpa, tetapi penimpaan wajib tercatat lengkap dengan lokasi asal saran. |
| AB-3 | Saran diterapkan otomatis hanya bila skor keyakinan melewati ambang yang dikonfigurasi (referensi: ≥ 90 pada model SAP slotting). Di bawah ambang, wajib review manusia. |
| AB-4 | Penyesuaian stok hasil cycle count **tidak boleh** terposting tanpa persetujuan supervisor. |
| AB-5 | Barang ber-expiry dikeluarkan dengan FEFO; barang tanpa expiry mengikuti strategi kategori produknya. |
| AB-6 | SKU ber-serial: satu unit = satu baris. Tidak ada agregasi kuantitas. |
| AB-7 | Barang tak dikenal yang dipindai saat GR tidak langsung menjadi produk; ia menjadi *registrasi* yang harus disetujui. |
| AB-8 | Setiap dokumen cetak wajib membawa barcode transaksi **dan** barcode per baris item. |
| AB-9 | Panggilan API integrasi tanpa tanda tangan HMAC yang sah, atau di luar toleransi waktu, ditolak — tanpa pengecualian untuk "sementara". |
| AB-10 | Modul WMS berada di tier bersama (`addons/ee_gap/`). Perubahan untuk satu klien berdampak ke semua tenant yang memakainya, sehingga wajib melewati regression test lintas tenant. |

## 8. Pemangku kepentingan & peran

| Peran bisnis | Tanggung jawab | Grup akses teknis |
|---|---|---|
| Warehouse Manager | Menyetujui rancangan zona, ambang slotting, target cycle count | `group_putaway_admin`, `group_cycle_count_admin`, `group_to_admin` |
| Supervisor Gudang | Menyetujui selisih hitung, menugaskan penghitung, menyetujui perintah transfer | `group_cycle_count_supervisor`, `group_to_supervisor` |
| Operator Inbound / GR | Memindai penerimaan, mencatat batch/expiry | `group_putaway_user`, `group_hht_operator` |
| Inspektur QC | Meloloskan/menolak barang inbound | `group_wms_qc_inspector` |
| Manajer QC | Menyetujui registrasi produk baru, menetapkan aturan inspeksi | `group_wms_qc_manager` |
| Operator Putaway / Picker | Menjalankan saran putaway, picking, packing, bin-to-bin | `group_putaway_user`, `group_to_operator`, `group_hht_operator` |
| Penghitung (Counter) | Memasukkan hasil hitung | `group_cycle_count_user` |
| IT / Integrasi | Mengelola kunci HMAC, pemetaan kode host, memantau outbox | `group_wms_integration_manager`, `group_hht_admin` |
| Finance / Controller | Menerima laporan nilai stok, menyetujui dampak akuntansi penyesuaian | (grup akuntansi standar) |
| DPO / Compliance | Memastikan kepatuhan PDP atas data operator & mitra | (grup compliance) |

## 9. Asumsi & ketergantungan

1. Klien menyediakan master produk dengan barcode yang **unik dan valid**; barcode ganda atau kosong adalah temuan fit-gap, bukan kejutan saat go-live.
2. Klien menyediakan denah gudang (zona, rak, level, bin) dalam bentuk yang dapat diimpor.
3. Perangkat handheld, printer label, dan cakupan Wi-Fi di seluruh area rak disediakan klien sebelum SIT.
4. Simbologi barcode yang didukung perangkat klien dikonfirmasi pada fase fit-gap (lihat catatan BR-RP-05).
5. Bila ada integrasi host: kontrak API (payload JSON + pemetaan kode) difinalkan pada fase Requirement, dan sisi host siap sebelum SIT.
6. Saldo awal stok per bin disediakan klien pada saat cutover, hasil dari opname penuh terakhir.
7. Lingkungan dev/staging/produksi disediakan tepat waktu.
8. Pengguna kunci klien tersedia untuk workshop fit-gap, UAT, dan training sesuai jadwal.

## 10. Risiko bisnis

| # | Risiko | Dampak | Mitigasi |
|---|---|:--:|---|
| R1 | Kualitas master data buruk (barcode ganda/kosong, dimensi kosong) | Tinggi | Audit master data sebagai keluaran wajib fase fit-gap; slotting berbasis volume tidak dinyalakan sebelum dimensi terisi |
| R2 | Denah bin berubah setelah konfigurasi selesai | Sedang | Bekukan denah pada akhir fase Design; perubahan sesudahnya lewat change request |
| R3 | Perangkat handheld tidak membaca simbologi yang direncanakan | Tinggi | Uji perangkat riil pada fase fit-gap; simbologi item bersifat adaptif (EAN-13/Code128) |
| R4 | Sisi host (SAP/marketplace) belum siap saat SIT | Tinggi | Bangun terhadap kontrak API; sediakan mode manual/import sebagai jalur mundur |
| R5 | Resistensi operator terhadap alur berbasis pindai | Sedang | Training berbasis skenario nyata + pendampingan hypercare di lantai gudang |
| R6 | Modul WMS bersifat lintas tenant; perubahan untuk klien ini mengganggu klien lain | Tinggi | Regression test lintas tenant sebelum rilis; kebijakan tier modul (lihat AB-10) |
| R7 | Ekspektasi RPO/RTO lebih ketat dari kapabilitas terpasang | Sedang | Nyatakan RPO nyata 24 jam di awal; WAL archiving sebagai item terpisah bila diminta |
| R8 | Cutover stok awal tidak akurat | Tinggi | Opname penuh terkendali sebelum cutover + hitung siklik intensif di minggu pertama hypercare |

---

**Traceability.** Setiap BR di atas dipetakan ke fungsi konkret pada [`02-FSD.md`](02-FSD.md)
dan ke komponen teknis pada [`03-TSD.md`](03-TSD.md). BR bertanda **PERLU DIBANGUN** masuk sebagai
item effort eksplisit pada [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md).
