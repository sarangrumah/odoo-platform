# Project Initiation Document (PID)
## Implementasi Warehouse Management System di atas Odoo 19

| | |
|---|---|
| **Dokumen** | PID — WMS Implementation (generic) |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Pemilik dokumen** | Delivery Team — Odoo Platform |
| **Sponsor / Product Owner** | *(diisi per klien — umumnya Warehouse Director atau COO)* |
| **Skenario baseline** | Brownfield (reuse 10 modul `custom_wms_*`) — lihat [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) |
| **Dokumen turunan** | [`01-BRD.md`](01-BRD.md) · [`02-FSD.md`](02-FSD.md) · [`03-TSD.md`](03-TSD.md) · [`04-Architecture.md`](04-Architecture.md) · [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) |

---

## Contents

1. [Maksud dokumen](#1-maksud-dokumen)
2. [Latar belakang](#2-latar-belakang)
3. [Tujuan proyek](#3-tujuan-proyek)
4. [Ruang lingkup](#4-ruang-lingkup)
5. [Deliverable](#5-deliverable)
6. [Pendekatan pelaksanaan](#6-pendekatan-pelaksanaan)
7. [Organisasi & tata kelola](#7-organisasi--tata-kelola)
8. [Milestone & jadwal](#8-milestone--jadwal)
9. [Effort & sumber daya](#9-effort--sumber-daya)
10. [Kriteria sukses](#10-kriteria-sukses)
11. [Asumsi, batasan, dan ketergantungan](#11-asumsi-batasan-dan-ketergantungan)
12. [Risiko tingkat proyek](#12-risiko-tingkat-proyek)
13. [Kriteria penerimaan & serah terima](#13-kriteria-penerimaan--serah-terima)

---

## 1. Maksud dokumen

Menetapkan mandat, ruang lingkup, tata kelola, jadwal, kebutuhan sumber daya, dan kriteria sukses
untuk implementasi Warehouse Management System (WMS) di atas Odoo 19 pada satu klien. Dokumen ini
adalah rujukan yang disepakati sebelum pekerjaan dimulai; perubahan terhadapnya berjalan lewat
change request.

Dokumen ini bersifat **generik dan dapat dipakai ulang**. Bagian bertanda *(diisi per klien)*
dilengkapi pada saat inisiasi engagement. Contoh pengisian untuk satu calon klien tersedia pada
[`06-Addendum-JDS.md`](06-Addendum-JDS.md).

## 2. Latar belakang

Sebagian besar operasi gudang yang berjalan di atas ERP hanya terkelola sampai tingkat *stock
ledger*: sistem tahu berapa stok di suatu gudang, tetapi tidak tahu di rak mana barang berada,
siapa yang memindahkannya, dan bagaimana selisih hitung dipertanggungjawabkan. Akibatnya:
pencarian barang lama, penempatan bergantung hafalan operator, opname harus menutup gudang, dan
laporan dirakit manual.

Platform Odoo ini sudah memiliki lapisan eksekusi gudang tersebut berupa **10 modul WMS yang
terpasang dan teruji**, dengan bukti end-to-end berupa POC 14/14 PASS terhadap record nyata
(bukan mock) — lihat [`../warehouse-jds/WMS-POC-Scenario.md`](../warehouse-jds/WMS-POC-Scenario.md).

Proyek ini karena itu bukan proyek riset. Ia adalah proyek **adopsi**: mencocokkan kapabilitas yang
sudah ada dengan proses gudang klien, menutup gap yang teridentifikasi, memigrasikan data,
melatih operator, dan membawa sistem ke produksi.

## 3. Tujuan proyek

1. Membuat setiap unit stok memiliki **lokasi bin yang diketahui sistem**, bukan hanya gudang.
2. Menggantikan penempatan berbasis hafalan dengan **saran penempatan berbasis aturan** yang dapat diaudit.
3. Menghentikan praktik **tutup gudang untuk opname**, digantikan hitung siklik berkala tanpa menghentikan operasi.
4. Menjadikan **pemindaian barcode** sebagai cara kerja standar di seluruh alur inbound, internal, dan outbound.
5. Memastikan **barang belum lolos QC tidak pernah terkirim** ke pelanggan.
6. Menyediakan **dokumen dan laporan berbarcode** yang dapat dipakai langsung di lantai gudang.
7. Menghubungkan gudang ke **sistem host** klien (bila di-scope) tanpa input ganda.
8. Menjalankan semuanya **di dalam ERP yang sama**, sehingga tidak ada ledger stok kedua yang harus direkonsiliasi.

KPI terukur untuk tujuan-tujuan di atas terdapat pada [`01-BRD.md`](01-BRD.md) §3. Baseline KPI
diukur pada fase Requirement & fit-gap.

## 4. Ruang lingkup

### 4.1 In-scope

Ringkasan; rincian bernomor ada di [`01-BRD.md`](01-BRD.md) §6.

- Struktur gudang: gudang, zona, bin berbarcode, kapasitas, kategori penyimpanan, urutan jalan.
- Inbound: penerimaan berbasis pindai, GS1 (batch/expiry/serial), import massal, registrasi barang tak dikenal.
- QC inbound: karantina dan gate lolos/tolak.
- Putaway & slotting: mesin bertingkat 9 jenis aturan, opsional mode SAP dua dimensi.
- Pergerakan internal: bin-to-bin, replenishment otomatis, konsolidasi zona.
- Outbound: picking, packing, pengiriman.
- Cycle count: enam metode, alur persetujuan selisih, penyesuaian stok.
- Retur pembelian dan scrap.
- Dokumen (6 PDF) dan laporan (5 analisis + ekspor XLSX), seluruhnya berbarcode.
- Aplikasi handheld PWA: 7 halaman operator.
- Integrasi sistem host: 4 endpoint ber-HMAC + outbox kejadian *(opsional, per klien)*.
- Hak akses per peran, jejak audit, kepatuhan UU PDP.
- Migrasi master data + saldo awal stok per bin.
- SIT, UAT, training operator, cutover, hypercare.

### 4.2 Out-of-scope

Lihat [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) §10 untuk daftar lengkap berikut pemiliknya.
Ringkasnya: pengembangan di sisi sistem host, perangkat keras dan jaringan gudang, pembersihan
master data massal, otomasi fisik, transport management, migrasi transaksi historis, lapisan BI,
pemisahan tier infrastruktur, dan keputusan lisensi Odoo Enterprise.

### 4.3 Gap yang sudah diketahui dan masuk scope

Verifikasi basis kode pada 2026-08-11 menemukan tiga hal yang belum jadi. Ketiganya sudah dibiayai
dalam estimasi, bukan disembunyikan:

| Gap | Rujukan |
|---|---|
| Penerbitan sesi cycle count belum terjadwal — metode ada, record `ir.cron` belum | FSD F-CC-08, TSD T1 |
| Beberapa berkas `data/*.xml` masih placeholder dan harus diverifikasi/diisi | TSD T2, T3 |
| Mode kerja offline handheld belum diverifikasi terhadap perangkat klien | BRD BR-DV-05, TSD T4 |

## 5. Deliverable

| # | Deliverable | Fase | Penerima |
|---|---|---|---|
| D1 | Laporan fit-gap + audit kualitas master data + baseline KPI | Requirement | Sponsor, Warehouse Manager |
| D2 | Spesifikasi gap yang disetujui (delta FSD/TSD) | Design | Sponsor, Tim IT |
| D3 | Denah gudang terkonfigurasi: zona, bin, kapasitas, kategori penyimpanan | Konfigurasi | Warehouse Manager |
| D4 | Strategi & aturan putaway, aturan transfer, rencana cycle count terkonfigurasi | Konfigurasi | Warehouse Manager |
| D5 | Gap tertutup (cron sesi hitung, berkas placeholder, mode handheld) | Konfigurasi | Tim IT |
| D6 | Master data & saldo awal stok per bin termuat dan terekonsiliasi | Data migration | Finance, Warehouse Manager |
| D7 | Laporan hasil SIT (E2E lulus, integrasi terverifikasi) | SIT | Sponsor, Tim IT |
| D8 | Paket UAT: skenario, hasil, dan sign-off | UAT | Sponsor |
| D9 | Materi training + operator terlatih | UAT | Supervisor gudang |
| D10 | Runbook operasional: pemantauan cron, outbox, kualitas saran, cakupan hitung | Cutover | Tim IT & operasi |
| D11 | Sistem live di produksi | Go-live | Semua |
| D12 | Laporan hypercare + serah terima ke operasi | Hypercare | Sponsor |

## 6. Pendekatan pelaksanaan

Delapan fase, dengan dua *gate* yang menahan kemajuan sampai prasyarat eksternal terpenuhi.

| Fase | Isi | Gate |
|---|---|---|
| 1. Requirement & fit-gap | Workshop proses gudang, walkthrough kapabilitas terhadap sistem nyata, audit master data, baseline KPI | — |
| 2. Design delta | Spesifikasi hanya untuk gap; **denah bin dibekukan** di akhir fase | Sign-off denah & spesifikasi gap |
| 3. Konfigurasi + build gap | Konfigurasi berbasis pola skrip referensi; pembangunan item gap | — |
| 4. Data migration & master setup | Muat master, denah bin, saldo awal | — |
| 5. SIT | Uji end-to-end lintas alur dan integrasi | **Gate: perangkat handheld & sisi host siap** |
| 6. UAT + training | Pengguna kunci menjalankan skenario nyata; operator dilatih di lantai gudang | Sign-off UAT |
| 7. Cutover & go-live | Opname penuh → muat saldo awal → bekukan pergerakan manual → go-live | Keputusan go/no-go sponsor |
| 8. Hypercare | Pendampingan di lantai gudang, cycle count intensif, serah terima | Serah terima diterima operasi |

**Prinsip pelaksanaan yang tidak dinegosiasikan:**

- Konfigurasi berjalan dengan `auto_apply_suggestions` **mati** sampai kualitas saran terbukti dari data penimpaan.
- Cutover selalu didahului opname penuh terkendali. Tidak ada go-live di atas saldo awal yang tidak diverifikasi.
- Simbologi barcode diverifikasi terhadap **perangkat riil klien** pada fase fit-gap, bukan diasumsikan.
- Kustomisasi khusus klien diletakkan di tier tenant. Perubahan modul bersama memerlukan regression test lintas tenant.

## 7. Organisasi & tata kelola

### 7.1 Peran

| Peran | Pihak | Tanggung jawab |
|---|---|---|
| Sponsor / Product Owner | Klien | Prioritas, sign-off, pembukaan hambatan, keputusan go/no-go |
| Warehouse Manager | Klien | Menyetujui denah zona, ambang slotting, target cycle count; pemilik proses |
| Key user (supervisor gudang) | Klien | Menyediakan detail proses, menjalankan UAT, melatih rekan |
| IT klien | Klien | Perangkat handheld, printer, jaringan gudang, kunci integrasi |
| Master data owner | Klien | Kualitas data produk, pemasok, pelanggan |
| Project Manager | Delivery | Jadwal, risiko, komunikasi, change request |
| Business Analyst | Delivery | Fit-gap, spesifikasi, UAT, training |
| Developer | Delivery | Konfigurasi, penutupan gap, migrasi data |
| QA Engineer | Delivery | Rencana uji, SIT, regression lintas tenant |
| Platform owner | Delivery | Menjaga dampak lintas tenant dari perubahan modul bersama |
| DPO / Compliance | Klien | Retensi log pindai, kepatuhan PDP |

### 7.2 Forum

| Forum | Frekuensi | Peserta | Keluaran |
|---|---|---|---|
| Daily stand-up (internal delivery) | Harian | Tim delivery | Hambatan harian |
| Weekly progress | Mingguan | PM, BA, Warehouse Manager, IT klien | Status, risiko, keputusan |
| Steering committee | 2 mingguan | Sponsor, PM, Warehouse Manager | Keputusan scope & anggaran |
| Go/no-go review | Sekali, sebelum cutover | Sponsor, PM, Warehouse Manager, IT | Keputusan go-live |

### 7.3 Pengelolaan perubahan

Perubahan scope diajukan sebagai change request tertulis, dinilai memakai pengali pada
[`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) §9, dan disetujui di steering committee.
Perubahan yang menyentuh perilaku inti modul bersama wajib menyertakan effort regression test
lintas tenant.

## 8. Milestone & jadwal

Baseline Brownfield, ±12 minggu. Rincian mingguan pada [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) §7.2.
Jadwal ini belum memuat siklus tata kelola yang menjadi ranah PM.

| # | Milestone | Minggu | Kriteria tercapai |
|---|---|---|---|
| M1 | Fit-gap selesai | W2 | Daftar gap disepakati; audit master data selesai; baseline KPI terukur |
| M2 | Design beku | W3 | Denah bin & spesifikasi gap sign-off |
| M3 | Sistem terkonfigurasi | W7 | Demo internal seluruh alur berjalan pada data klien |
| M4 | Data termuat | W8 | Master + denah bin + saldo awal terekonsiliasi |
| M5 | SIT lulus | W10 | E2E lulus; integrasi terverifikasi (bila di-scope) |
| M6 | UAT sign-off | W11 | Seluruh skenario UAT lulus; operator terlatih |
| M7 | Go-live | W12 | Sistem produktif; pergerakan manual dibekukan |
| M8 | Serah terima | W12 | Runbook diserahkan; hypercare ditutup |

## 9. Effort & sumber daya

| | Brownfield (baseline) | Greenfield (pembanding) |
|---|---:|---:|
| PM | *diisi PM* | *diisi PM* |
| BA | 51 | 90 |
| DEV | 84 | 252 |
| QA | 44 | 106 |
| **Total tanpa PM (termasuk kontingensi 15%)** | **≈ 179 mandays** | **≈ 448 mandays** |
| Durasi | ≈ 12 minggu | ≈ 25 minggu |

> **Effort PM belum masuk angka ini.** Kolom PM sengaja dikosongkan dan diisi oleh PM sesuai model
> tata kelola yang dipakai. Sebelum angka ini dipakai untuk penawaran komersial, alokasi PM harus
> ditambahkan dan totalnya dijumlahkan ulang.

Komposisi tim Brownfield: 1 BA, 2 DEV, 1 QA, ditambah PM. Rincian pembebanan pada
[`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) §8.

**Sumber daya dari pihak klien** (di luar mandays di atas, tetapi wajib dialokasikan): Warehouse
Manager sebagai product owner, 1–2 supervisor gudang sebagai key user, 1 orang IT untuk perangkat
& jaringan, 1 orang pemilik master data.

## 10. Kriteria sukses

| # | Kriteria | Cara diukur |
|---|---|---|
| S1 | Akurasi inventori per lokasi ≥ 99% | Line hit rate pada cycle count 4 minggu pertama pasca go-live |
| S2 | Tidak ada lagi penutupan gudang untuk opname | Rencana cycle count aktif dengan cakupan berjalan |
| S3 | Nol kebocoran stok QC ke outbound | Tidak ada pengiriman yang mengandung stok dari lokasi karantina |
| S4 | Seluruh SKU ber-tracking terkirim dengan lot/serial tercatat | Audit atas pengiriman periode hypercare |
| S5 | Operator bekerja dari handheld, bukan kertas | Volume transaksi lewat rute `/hht/wms/*` |
| S6 | Laporan tersedia on-demand, bukan dirakit manual | Tidak ada lagi rekap Excel manual untuk 5 laporan yang tercakup |
| S7 | Nol input ganda pada alur terintegrasi | Kejadian outbox terkirim & ter-ack tanpa entri manual di host |
| S8 | Seluruh kriteria penerimaan teknis terpenuhi | [`03-TSD.md`](03-TSD.md) §11 (TA-1 s/d TA-9) |
| S9 | Seluruh acceptance test fungsional lulus | [`02-FSD.md`](02-FSD.md) §10 (AT-01 s/d AT-22) |

## 11. Asumsi, batasan, dan ketergantungan

### Asumsi
Lihat [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) §3. Yang paling menentukan: lingkup dasar
1 gudang / ≤3 zona / ≤200 bin / ≤5.000 SKU; master produk berbarcode unik dan valid; perangkat dan
jaringan gudang siap sebelum SIT.

### Batasan yang harus diketahui sponsor

Diambil dari [`04-Architecture.md`](04-Architecture.md) §9 — kondisi nyata platform hari ini:

1. **RPO nyata 24 jam.** WAL archiving belum terpasang. Bila operasi gudang menuntut RPO lebih ketat, itu pekerjaan infrastruktur terpisah.
2. **Backup offsite bersifat nominal** — berada di host yang sama.
3. **Satu host menjalankan seluruh tumpukan.** Tier basis data, redundan, dan pelaporan belum dibangun.
4. **Modul WMS dibagi lintas tenant.** Isolasi data ada di tingkat basis data; perilaku tidak terisolasi.
5. **Tidak ada lapisan BI dan tidak ada event bus.** Pelaporan berjalan dari basis data produksi; integrasi bersifat REST + outbox.

### Ketergantungan

| # | Ketergantungan | Pemilik | Dibutuhkan sebelum |
|---|---|---|---|
| C1 | Denah gudang (zona/rak/level/bin) dalam format yang dapat diimpor | Klien | Fase Design (W4) |
| C2 | Master produk dengan barcode unik & valid | Klien | Data migration (W7) |
| C3 | Perangkat handheld + printer + Wi-Fi gudang | Klien | SIT (W9) |
| C4 | Kontrak API + kesiapan sisi host *(bila integrasi di-scope)* | Klien | SIT (W9) |
| C5 | Saldo awal stok hasil opname penuh | Klien | Cutover (W12) |
| C6 | Ketersediaan key user untuk workshop, UAT, training | Klien | Sesuai jadwal fase |
| C7 | Lingkungan dev/staging/produksi | Delivery + Klien | Fase Konfigurasi (W4) |

## 12. Risiko tingkat proyek

| # | Risiko | Kemungkinan | Dampak | Mitigasi | Pemilik |
|---|---|:--:|:--:|---|---|
| R1 | Kualitas master data jauh di bawah asumsi | Tinggi | Tinggi | Audit master data sebagai gate fase fit-gap; angka scope dikunci setelahnya | BA + Master data owner |
| R2 | Sisi host belum siap saat SIT | Sedang | Tinggi | Bangun terhadap kontrak; siapkan jalur import manual sebagai jalur mundur | PM + IT klien |
| R3 | Perangkat handheld tidak membaca simbologi yang diasumsikan | Sedang | Tinggi | Uji perangkat riil pada fit-gap; barcode item dirender adaptif | BA + IT klien |
| R4 | Resistensi operator terhadap alur berbasis pindai | Sedang | Sedang | Training berbasis skenario nyata + pendampingan di lantai gudang saat hypercare | BA + Supervisor |
| R5 | Denah bin berubah setelah design beku | Sedang | Sedang | Bekukan di M2; sesudahnya lewat change request | PM + Warehouse Manager |
| R6 | Perubahan modul bersama mengganggu tenant lain | Sedang | Tinggi | Regression test lintas tenant wajib sebelum rilis; kustomisasi diarahkan ke tier tenant | QA + Platform owner |
| R7 | Saldo awal stok tidak akurat saat cutover | Sedang | Tinggi | Opname penuh terkendali sebelum cutover; cycle count intensif minggu pertama | Warehouse Manager |
| R8 | Ekspektasi ketersediaan/RPO melebihi kapabilitas terpasang | Sedang | Sedang | Dinyatakan di PID ini (§11); peningkatan sebagai pekerjaan terpisah | PM + Sponsor |
| R9 | Ketersediaan key user di bawah rencana | Sedang | Sedang | Komitmen alokasi key user dicatat sebagai C6 dan dipantau mingguan | PM + Sponsor |

## 13. Kriteria penerimaan & serah terima

Proyek dinyatakan selesai bila seluruh butir berikut terpenuhi:

1. Seluruh acceptance test fungsional lulus — [`02-FSD.md`](02-FSD.md) §10, AT-01 s/d AT-22.
2. Seluruh kriteria penerimaan teknis lulus — [`03-TSD.md`](03-TSD.md) §11, TA-1 s/d TA-9.
3. Skenario UAT klien lulus dan ditandatangani sponsor.
4. Deliverable D1–D12 (§5) diserahkan dan diterima.
5. Operator terlatih dan menjalankan operasi harian dari handheld tanpa pendampingan.
6. Runbook operasional diserahkan ke tim IT & operasi klien, mencakup pemantauan cron, outbox
   integrasi, kualitas saran putaway, dan cakupan cycle count.
7. Tidak ada cacat berkategori kritis yang terbuka pada akhir hypercare.
8. Gap yang tercatat pada §4.3 tertutup dan terverifikasi.
