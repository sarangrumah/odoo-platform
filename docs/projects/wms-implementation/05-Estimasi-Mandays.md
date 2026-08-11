# Project Estimation — Mandays & Timeline
## Implementasi Warehouse Management System di atas Odoo 19

| | |
|---|---|
| **Dokumen** | Project Estimation — WMS Implementation (generic) |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Sumber scope** | [`01-BRD.md`](01-BRD.md), [`02-FSD.md`](02-FSD.md), [`03-TSD.md`](03-TSD.md) |
| **Peran yang diestimasi** | PM · BA · DEV · QA |
| **Skenario** | A = Greenfield (bangun dari nol) · B = Brownfield (reuse 10 modul `custom_wms_*`) |
| **Sifat angka** | **Estimasi indikatif berbasis asumsi tertulis di §3 — bukan komitmen kontrak** |

---

## Contents

1. [Ringkasan eksekutif](#1-ringkasan-eksekutif)
2. [Ruang lingkup effort](#2-ruang-lingkup-effort)
3. [Asumsi](#3-asumsi)
4. [Skenario A — Greenfield](#4-skenario-a--greenfield)
5. [Skenario B — Brownfield](#5-skenario-b--brownfield)
6. [Perbandingan & analisis penghematan](#6-perbandingan--analisis-penghematan)
7. [Timeline & milestone](#7-timeline--milestone)
8. [Komposisi & pembebanan tim](#8-komposisi--pembebanan-tim)
9. [Faktor pengubah estimasi](#9-faktor-pengubah-estimasi)
10. [Yang tidak termasuk](#10-yang-tidak-termasuk)
11. [Risiko terhadap estimasi](#11-risiko-terhadap-estimasi)

---

## 1. Ringkasan eksekutif

| Metrik | Skenario A — Greenfield | Skenario B — Brownfield |
|---|---:|---:|
| Effort tanpa kontingensi | **483 mandays** | **208 mandays** |
| Kontingensi 15% | 72 mandays | 32 mandays |
| **Effort dengan kontingensi** | **≈ 555 mandays** | **≈ 240 mandays** |
| Durasi kalender | **≈ 28 minggu (±7 bulan)** | **≈ 14 minggu (±3,5 bulan)** |
| Komposisi tim | 1 PM (paruh waktu), 1–2 BA, 3–4 DEV, 2 QA | 1 PM (paruh waktu), 1 BA, 2 DEV, 1 QA |

**Penghematan Brownfield: 315 mandays (≈ 57%) dan 14 minggu.**

Penghematan itu bukan diskon — ia berasal dari 10 modul WMS yang **sudah terbangun, teruji, dan
terbukti end-to-end** (POC 14/14 PASS, 149 metode test di sepuluh modul). Skenario A dicantumkan
agar nilai yang sudah ada terlihat dan agar keputusan build-vs-reuse dapat diambil dengan angka.

## 2. Ruang lingkup effort

### 2.1 Termasuk (kedua skenario)

Seluruh kebutuhan BR-WH, BR-IN, BR-QC, BR-PA, BR-ST, BR-OU, BR-CC, BR-RT, BR-RP, BR-DV, BR-IT,
BR-NF pada [`01-BRD.md`](01-BRD.md), yakni:

- Struktur gudang, zona, bin berbarcode, kapasitas, kategori penyimpanan.
- Penerimaan dengan GS1, batch/expiry/serial, import massal, registrasi barang tak dikenal.
- Karantina & gate QC inbound.
- Mesin slotting bertingkat (9 jenis aturan) dan mode SAP dua dimensi.
- Transfer internal, replenishment, dan bin-to-bin.
- Picking, packing, pengiriman.
- Cycle count enam metode berikut alur persetujuan selisih.
- Retur dan scrap.
- Enam dokumen PDF berbarcode dan lima laporan analisis + ekspor XLSX berbarcode.
- Aplikasi handheld PWA (7 halaman, 21 rute).
- Integrasi host: 4 endpoint ber-HMAC + outbox + pemetaan kode.
- Hak akses 13 grup, jejak audit, kepatuhan PDP.
- Data migration master + saldo awal stok per bin, SIT, UAT, training, cutover, hypercare.

### 2.2 Termasuk khusus Skenario B — pekerjaan gap yang sudah teridentifikasi

Verifikasi repo pada 2026-08-11 menemukan tiga item yang **belum jadi** dan sudah dibiayai di
skenario B, bukan disembunyikan:

| Item | Rujukan | Effort DEV |
|---|---|---:|
| Record `ir.cron` untuk penerbitan sesi cycle count otomatis (metodenya sudah ada, cron-nya belum) | FSD F-CC-08, TSD T1 | 2 |
| Verifikasi berkas `data/*.xml` placeholder lain (`custom_wms_putaway/ir_sequence_data.xml`, `custom_hht_bridge/cron.xml` + `ir_config_parameter_data.xml`) dan pembangunan isinya | TSD T2, T3 | 2 |
| Uji dan, bila perlu, pembangunan mode kerja offline handheld terhadap perangkat klien | BRD BR-DV-05, TSD T4 | 3 |

## 3. Asumsi

1. **1 manday = 1 orang-hari**, ±20 hari kerja per bulan. **Mandays ≠ durasi kalender** — ada paralelisasi antar-peran dan antar-workstream.
2. Lingkup dasar: **1 gudang, hingga 3 zona, hingga ±200 bin, hingga ±5.000 SKU aktif**. Di luar ini, lihat §9.
3. Klien menyediakan denah gudang (zona/rak/level/bin) dalam bentuk yang dapat diimpor.
4. Master produk klien memiliki barcode unik dan valid. Pembersihan data massal **bukan** bagian dari angka ini — lihat §10.
5. Perangkat handheld, printer label, dan cakupan Wi-Fi gudang disediakan klien sebelum SIT.
6. Bila integrasi host di-scope: kontrak API difinalkan pada fase Requirement dan **sisi host siap sebelum SIT**. Keterlambatan sisi host menggeser SIT → Go-Live.
7. Lingkungan dev/staging/produksi tersedia tepat waktu.
8. Pengguna kunci klien tersedia untuk workshop fit-gap, UAT, dan training sesuai jadwal.
9. Saldo awal stok per bin tersedia saat cutover, hasil opname penuh terakhir.
10. Kontingensi 15% menutup ketidakpastian normal — **bukan** menutup risiko dependensi eksternal (sisi host, perangkat, kualitas data).
11. **Khusus Skenario B:** 10 modul `custom_wms_*` dipasang apa adanya. Permintaan perubahan perilaku inti modul bersama dinilai terpisah, termasuk biaya regression test lintas tenant.

## 4. Skenario A — Greenfield

Membangun seluruh kapabilitas WMS dari nol di atas Odoo 19 CE, tanpa memanfaatkan modul yang sudah ada.

### 4.1 Mandays per peran × fase

| Fase | PM | BA | DEV | QA | Total |
|---|---:|---:|---:|---:|---:|
| 1. Requirement gathering & analysis | 8 | 24 | 4 | 4 | **40** |
| 2. Design (FSD/TSD, model data, UX handheld) | 4 | 10 | 14 | 6 | **34** |
| 3. Build / development | 22 | 30 | 165 | 55 | **272** |
| 4. SIT | 5 | 6 | 14 | 20 | **45** |
| 5. UAT + training | 6 | 12 | 12 | 12 | **42** |
| 6. Cutover & go-live | 6 | 6 | 10 | 4 | **26** |
| 7. Hypercare | 5 | 5 | 10 | 4 | **24** |
| **Subtotal** | **56** | **93** | **229** | **105** | **483** |
| Kontingensi 15% | 8 | 14 | 34 | 16 | **72** |
| **TOTAL** | **64** | **107** | **263** | **121** | **≈ 555** |

### 4.2 Rincian fase Build per workstream

| # | Workstream | DEV | BA | QA |
|---|---|---:|---:|---:|
| W1 | Fondasi: struktur modul, tier, security & ACL, CI, kerangka audit | 8 | 2 | 2 |
| W2 | Master data & struktur gudang: lokasi bertingkat, bin berbarcode, kapasitas, kategori penyimpanan, GTIN alternatif | 10 | 4 | 4 |
| W3 | Mesin putaway bertingkat: 9 jenis aturan, penilaian & keyakinan, model saran, wizard propose | 26 | 4 | 9 |
| W4 | Slotting SAP dua dimensi: tipe & seksi penyimpanan, urutan pencarian, formula skor | 10 | 2 | 3 |
| W5 | Inbound QC: karantina, pengecualian tingkat gather, registrasi barang tak dikenal | 12 | 3 | 5 |
| W6 | Kelengkapan penerimaan: parsing GS1 (AI 10/17/21), batch pemasok, IMEI, import CSV/XLSX | 10 | 2 | 4 |
| W7 | Mesin transfer order: 5 pemicu, evaluasi domain, materialisasi ke `stock.move`, slip pick | 14 | 3 | 5 |
| W8 | Cycle count: rencana/sesi/baris/penyesuaian, 6 metode, alur persetujuan, cakupan | 14 | 3 | 5 |
| W9 | Dokumen berbarcode: mixin render in-process, 6 template PDF | 11 | 1 | 4 |
| W10 | Laporan analisis: 5 SQL view + mesin ekspor XLSX berbarcode | 13 | 2 | 4 |
| W11 | Aplikasi handheld PWA: 7 halaman OWL, 21 rute JSON-RPC, penanganan scan burst | 24 | 3 | 7 |
| W12 | Integrasi host: outbox, adapter, 4 endpoint ber-HMAC, pemetaan kode | 13 | 1 | 3 |
| | **Subtotal Build** | **165** | **30** | **55** |

## 5. Skenario B — Brownfield

Memanfaatkan 10 modul `custom_wms_*` yang sudah ada dan teruji. Effort bergeser dari *membangun*
ke *fit-gap, konfigurasi, migrasi data, pengujian, dan adopsi*.

### 5.1 Mandays per peran × fase

| Fase | PM | BA | DEV | QA | Total |
|---|---:|---:|---:|---:|---:|
| 1. Requirement & fit-gap analysis | 5 | 14 | 3 | 2 | **24** |
| 2. Design delta (hanya gap) | 2 | 5 | 5 | 2 | **14** |
| 3. Konfigurasi + build gap | 8 | 12 | 38 | 14 | **72** |
| 4. Data migration & master setup | 2 | 6 | 8 | 4 | **20** |
| 5. SIT | 3 | 3 | 6 | 10 | **22** |
| 6. UAT + training | 4 | 8 | 6 | 8 | **26** |
| 7. Cutover & go-live | 4 | 3 | 6 | 3 | **16** |
| 8. Hypercare | 3 | 3 | 6 | 2 | **14** |
| **Subtotal** | **31** | **54** | **78** | **45** | **208** |
| Kontingensi 15% | 5 | 8 | 12 | 7 | **32** |
| **TOTAL** | **36** | **62** | **90** | **52** | **≈ 240** |

### 5.2 Rincian fase Konfigurasi + build gap

| # | Workstream | DEV | BA | QA |
|---|---|---:|---:|---:|
| K1 | Konfigurasi struktur gudang: zona, bin berbarcode, kapasitas, kategori penyimpanan, tipe paket, urutan jalan (pola skrip `51_config_native_slotting.py`) | 5 | 3 | 2 |
| K2 | Konfigurasi strategi & aturan putaway bertingkat + penyetelan bobot penilaian | 6 | 2 | 3 |
| K3 | Konfigurasi slotting SAP (bila dipakai): tipe, seksi, urutan pencarian dari CSV klien | 3 | 1 | 1 |
| K4 | Konfigurasi cycle count **+ pembangunan cron penerbitan sesi (F-CC-08)** | 4 | 1 | 2 |
| K5 | Konfigurasi aturan transfer & replenishment (batas bawah, expiry, konsolidasi) | 3 | 1 | 1 |
| K6 | Konfigurasi QC: jenis operasi wajib inspeksi, lokasi karantina, alur registrasi | 2 | 1 | 1 |
| K7 | Penyesuaian dokumen & laporan: branding, kolom tambahan klien, template label | 5 | 1 | 2 |
| K8 | Handheld: pendaftaran perangkat, profil DataWedge, verifikasi simbologi, **uji mode offline (BR-DV-05)**, verifikasi berkas placeholder (T2, T3) | 5 | 1 | 2 |
| K9 | Integrasi host (bila di-scope): pemetaan kode, pertukaran kunci HMAC, uji 4 endpoint di staging | 5 | 1 | 0 |
| | **Subtotal** | **38** | **12** | **14** |

> QA untuk K9 dibebankan pada fase SIT, karena pengujian integrasi baru bermakna setelah sisi host siap.

### 5.3 Rincian fase Data migration & master setup (20 mandays)

| Aktivitas | DEV | BA | QA | PM |
|---|---:|---:|---:|---:|
| Audit kualitas master produk (barcode ganda/kosong, dimensi & berat kosong, satuan) | 2 | 3 | 1 | — |
| Pemuatan master produk, pemasok, pelanggan | 2 | 1 | 1 | 1 |
| Pemuatan denah bin + kapasitas + urutan jalan | 2 | 1 | 1 | — |
| Pemuatan saldo awal stok per bin dan rekonsiliasinya | 2 | 1 | 1 | 1 |
| **Subtotal** | **8** | **6** | **4** | **2** |

## 6. Perbandingan & analisis penghematan

| Fase | A — Greenfield | B — Brownfield | Selisih | Penghematan |
|---|---:|---:|---:|---:|
| Requirement / fit-gap | 40 | 24 | −16 | 40% |
| Design | 34 | 14 | −20 | 59% |
| Build → Konfigurasi + gap | 272 | 72 | −200 | 74% |
| Data migration & master setup | (di dalam fase lain) | 20 | +20 | — |
| SIT | 45 | 22 | −23 | 51% |
| UAT + training | 42 | 26 | −16 | 38% |
| Cutover & go-live | 26 | 16 | −10 | 38% |
| Hypercare | 24 | 14 | −10 | 42% |
| **Subtotal** | **483** | **208** | **−275** | **57%** |
| **Dengan kontingensi** | **555** | **240** | **−315** | **57%** |

Penghematan per peran:

| Peran | A | B | Penghematan |
|---|---:|---:|---:|
| PM | 64 | 36 | 44% |
| BA | 107 | 62 | 42% |
| DEV | 263 | 90 | **66%** |
| QA | 121 | 52 | 57% |

**Bacaan yang penting.** Penghematan terbesar ada di DEV (66%) — wajar, karena itulah yang sudah
dibangun. Penghematan BA hanya 42%: pemahaman proses gudang klien tetap harus digali dari nol,
tidak peduli seberapa matang perangkat lunaknya. Jangan memangkas fase fit-gap dengan alasan
"modulnya sudah jadi" — di situlah proyek WMS biasanya gagal.

## 7. Timeline & milestone

### 7.1 Skenario A — Greenfield (≈ 28 minggu)

| Fase | Durasi | Minggu | Milestone |
|---|---|---|---|
| 1. Requirement & analysis | 4 mgg | W1–W4 | BRD sign-off; kontrak integrasi final |
| 2. Design | 3 mgg | W4–W7 | FSD & TSD sign-off; model data beku |
| 3. Build (sprint 2-mingguan) | 12 mgg | W7–W19 | Demo per sprint; feature complete |
| 4. SIT | 4 mgg | W18–W22 | *Gated:* sisi host & perangkat siap; E2E lulus |
| 5. UAT + training | 3 mgg | W22–W25 | UAT sign-off; operator terlatih |
| 6. Cutover & go-live | 1 mgg | W25–W26 | Saldo awal termuat; go-live |
| 7. Hypercare | 2 mgg | W26–W28 | Serah terima ke operasi |

### 7.2 Skenario B — Brownfield (≈ 14 minggu)

| Fase | Durasi | Minggu | Milestone |
|---|---|---|---|
| 1. Requirement & fit-gap | 3 mgg | W1–W3 | Daftar gap disepakati; keputusan config-vs-build |
| 2. Design delta | 1 mgg | W3–W4 | Spesifikasi gap sign-off; denah bin beku |
| 3. Konfigurasi + build gap | 4 mgg | W4–W8 | Sistem terkonfigurasi; gap tertutup; demo internal |
| 4. Data migration & master setup | 2 mgg | W7–W9 | Master & denah bin termuat; audit kualitas data selesai |
| 5. SIT | 2 mgg | W9–W11 | *Gated:* perangkat handheld & sisi host siap; E2E lulus |
| 6. UAT + training | 2 mgg | W10–W12 | UAT sign-off; operator terlatih |
| 7. Cutover & go-live | 1 mgg | W12–W13 | Opname penuh → saldo awal → go-live |
| 8. Hypercare | 1–2 mgg | W13–W14 | Cycle count intensif; serah terima |

Fase yang bertumpang tindih (mis. W7–W9 dan W10–W12) memang disengaja: migrasi data berjalan
paralel dengan penutupan gap, dan training dimulai sebelum SIT tuntas.

## 8. Komposisi & pembebanan tim

### Skenario A

| Peran | Jumlah | Pembebanan | Puncak |
|---|---|---|---|
| Project Manager | 1 | ±50% sepanjang proyek | Cutover |
| Business Analyst | 1–2 | 100% pada W1–W7, lalu ±50% | Requirement, UAT |
| Developer | 3–4 | 100% pada W7–W19 | Build |
| QA Engineer | 2 | ±50% pada Build, 100% pada SIT/UAT | SIT |

### Skenario B

| Peran | Jumlah | Pembebanan | Puncak |
|---|---|---|---|
| Project Manager | 1 | ±30% sepanjang proyek | Cutover |
| Business Analyst | 1 | 100% pada W1–W4 dan W9–W12 | Fit-gap, UAT & training |
| Developer | 2 | 100% pada W4–W9 | Konfigurasi + gap |
| QA Engineer | 1 | ±50% pada W4–W8, 100% pada W9–W12 | SIT |

Peran klien yang harus dialokasikan (di luar mandays ini): Warehouse Manager sebagai product owner,
1–2 supervisor gudang sebagai key user, 1 orang IT untuk perangkat & jaringan, dan 1 orang untuk
master data.

## 9. Faktor pengubah estimasi

Angka dasar berlaku untuk 1 gudang / ≤3 zona / ≤200 bin / ≤5.000 SKU. Berikut pengalinya:

| Faktor | Kondisi | Dampak pada Skenario B |
|---|---|---:|
| Gudang tambahan | Setiap gudang tambahan dengan tata letak serupa | +12 mandays |
| Gudang tambahan dengan tata letak berbeda | Zona/strategi/bin berbeda total | +25 mandays |
| Skala bin | > 500 bin | +8 mandays (impor, verifikasi, penomoran) |
| Skala SKU | > 10.000 SKU aktif | +10 mandays (audit & pembersihan master) |
| Mode SAP slotting | Dipakai (tipe × seksi penyimpanan) | sudah termasuk (K3); bila tidak dipakai, −5 |
| Integrasi host | Tidak di-scope | −18 mandays (K9 + porsi SIT) |
| Integrasi host kompleks | > 4 endpoint, atau transformasi payload berat | +15–30 mandays |
| Multi-perusahaan | > 1 perusahaan legal dalam satu basis data | +10 mandays |
| Multi-bahasa antarmuka | Selain ID/EN | +6 mandays |
| Perangkat handheld non-standar | Bukan Zebra/Denso yang sudah terverifikasi | +5 mandays per jenis perangkat |
| Mode offline penuh handheld | Bila terbukti diperlukan setelah uji lapangan | +12 mandays |
| Pembersihan master data | Barcode ganda/kosong dalam jumlah besar | dinilai terpisah setelah audit |
| WAL archiving / RPO < 24 jam | Diminta klien | dinilai terpisah (pekerjaan infrastruktur) |
| Perubahan perilaku inti modul bersama | Diminta klien | + effort perubahan **+ regression test lintas tenant** |

## 10. Yang tidak termasuk

| Area | Alasan | Pemilik |
|---|---|---|
| Pengembangan di sisi sistem host (SAP/WMS lama/marketplace) | Bukan Odoo; Odoo dibangun terhadap kontrak yang disepakati | Tim klien |
| Pengadaan & konfigurasi jaringan Wi-Fi gudang | Infrastruktur fisik | Tim klien |
| Pengadaan perangkat handheld dan printer label | Perangkat keras | Tim klien |
| Pembersihan master data massal | Volume tidak dapat diperkirakan sebelum audit fase fit-gap | Dinilai terpisah |
| Otomasi fisik (conveyor, ASRS, put-to-light) | Di luar cakupan perangkat lunak | Vendor otomasi |
| Transport management (rute, ongkir, tracking kurir) | Modul terpisah | — |
| Migrasi data historis transaksi gudang bertahun-tahun | Yang dimigrasi adalah master + saldo awal | Dinilai terpisah |
| Lapisan BI / data warehouse | Belum ada di platform (lihat [`04-Architecture.md`](04-Architecture.md) §9) | Dinilai terpisah |
| Pemisahan tier host (DB/redundan/pelaporan/backup) | Pekerjaan infrastruktur platform, bukan proyek WMS | Dinilai terpisah |
| Lisensi Odoo Enterprise | Modul ini menutup gap di atas CE; keputusan lisensi terpisah | Klien |

## 11. Risiko terhadap estimasi

| # | Risiko | Kemungkinan | Dampak pada mandays | Mitigasi |
|---|---|:--:|---|---|
| E1 | Kualitas master data jauh lebih buruk dari asumsi | Tinggi | +10 s/d +40 | Audit master data sebagai keluaran wajib fase fit-gap, sebelum angka dikunci |
| E2 | Sisi host belum siap saat SIT | Sedang | Menggeser jadwal, bukan menambah mandays — kecuali diperlukan jalur mundur manual (+8) | Bangun terhadap kontrak; siapkan jalur import manual |
| E3 | Perangkat handheld tidak sesuai asumsi simbologi | Sedang | +5 per jenis perangkat | Uji perangkat riil pada fase fit-gap, bukan saat SIT |
| E4 | Denah bin berubah setelah design beku | Sedang | +5 s/d +15 | Bekukan denah pada akhir fase Design; sesudahnya lewat change request |
| E5 | Permintaan perubahan perilaku inti modul bersama | Sedang | + effort + regression lintas tenant | Kanalkan ke modul tier tenant bila memungkinkan |
| E6 | Mode offline handheld ternyata wajib | Rendah–Sedang | +12 | Uji lapangan pada fase fit-gap |
| E7 | Ketersediaan key user klien di bawah rencana | Sedang | Menggeser UAT & training | Kunci jadwal key user di PID sebagai komitmen klien |
| E8 | Saldo awal stok tidak akurat saat cutover | Sedang | +5 s/d +10 pada hypercare | Opname penuh terkendali sebelum cutover; cycle count intensif minggu pertama |

---

**Cara membaca angka ini.** Mandays adalah *effort*, bukan *durasi*. 240 mandays pada Skenario B
terdistribusi ke ±5 orang selama ±14 minggu, bukan satu orang selama 240 hari. Angka final untuk
satu klien dikunci setelah fase Requirement & fit-gap, memakai pengali pada §9.
