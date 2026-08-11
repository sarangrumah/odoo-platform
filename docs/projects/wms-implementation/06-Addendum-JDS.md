# Addendum — Penerapan untuk JDS (JD Sport Cikupa)
## Warehouse Management System di atas Odoo 19

| | |
|---|---|
| **Dokumen** | Addendum klien — JDS |
| **Versi** | 1.1 |
| **Tanggal** | 2026-08-11 |
| **Status engagement** | **Pra-implementasi.** POC selesai dan lulus; kontrak implementasi belum |
| **Induk** | [`00-Project-Initiation-Document.md`](00-Project-Initiation-Document.md) dan seluruh paket `wms-implementation/` |
| **Bukti POC** | [`../warehouse-jds/WMS-POC-Scenario.md`](../warehouse-jds/WMS-POC-Scenario.md) |
| **Basis data POC** | `demo_wms` (demo JD Sport Cikupa), `rnd_wms` (implementasi referensi) |

Dokumen ini **tidak menggantikan** paket generik. Ia hanya mencatat apa yang khusus untuk JDS:
apa yang sudah dibuktikan, apa yang masih terbuka, dan berapa estimasinya setelah memperhitungkan
POC yang sudah selesai.

---

## Contents

1. [Posisi engagement saat ini](#1-posisi-engagement-saat-ini)
2. [Apa yang sudah dibuktikan POC](#2-apa-yang-sudah-dibuktikan-poc)
3. [Pemetaan terhadap lembar 15 kebutuhan JDS](#3-pemetaan-terhadap-lembar-15-kebutuhan-jds)
4. [Pemetaan terhadap deck SAP EWM](#4-pemetaan-terhadap-deck-sap-ewm)
5. [Yang masih terbuka](#5-yang-masih-terbuka)
6. [Estimasi mandays JDS](#6-estimasi-mandays-jds)
7. [Timeline JDS](#7-timeline-jds)
8. [Risiko khusus JDS](#8-risiko-khusus-jds)
9. [Langkah berikutnya](#9-langkah-berikutnya)

---

## 1. Posisi engagement saat ini

JDS tercatat pada indeks proyek platform sebagai pelanggan warehouse management yang **tidak
memiliki modul sendiri** — ia berjalan di atas `ee_gap/custom_wms_*` dan `core/custom_hht_bridge`.
Itu posisi yang benar dan sebaiknya dipertahankan: tidak ada alasan membuat modul `_tenants/`
untuk JDS kecuali muncul kebutuhan yang tidak layak digeneralisasi.

Yang sudah ada hari ini:

| Aset | Isi | Lokasi |
|---|---|---|
| Skenario POC | 12 kategori transaksi (A–L), **14/14 PASS** | `docs/projects/warehouse-jds/WMS-POC-Scenario.md` |
| Uji lembar kebutuhan | Uji otomatis terhadap 15 butir kebutuhan klien | `scripts/tenants/wms_demo/70_scenario_test.py` |
| Walkthrough POC | Skrip yang membangun gudang POC dan menjalankan seluruh alur | `scripts/tenants/wms_demo/80_poc_scenario.py` |
| Dataset demo | JD Sport Cikupa: gudang, bin, produk, PO, SO | `scripts/tenants/wms_demo/10..52_*.py` |
| Materi klien | Capability deck, configuration guide, workbook skenario uji | `docs/projects/warehouse-jds/` |

Artinya: fase *pembuktian kelayakan* untuk JDS **sudah dibayar dan sudah lewat**. Yang tersisa
adalah implementasi terhadap gudang riil.

## 2. Apa yang sudah dibuktikan POC

POC membangun gudang kedua, **POC Distribution Centre**, sengaja dikonfigurasi dengan penerimaan
2-step dan pengiriman 2-step supaya putaway dan picking masing-masing menjadi *leg* tersendiri:

```
Receipts (POC/IN)  →  Storage (POC/STOR)  →  POC/Stock/<zona>/<bin>
                         ↑ leg putaway — inilah yang di-slotting mesin

POC/Stock  →  Pick (POC/PICK)  →  POC/Output  →  Delivery (POC/OUT)  →  Pelanggan
```

| Zona | Bin | Kategori penyimpanan |
|---|---|---|
| Bulk Pallet | `POC-BLK-01…06` | Pallet Only — produk sama, 1.600 kg, 2 palet |
| Forward Pick | `POC-PCK-01…06` | Mixed Carton — campuran, 300 kg, 12 karton |
| Pack & Ship | `POC-PAK-01` | Staging — campuran, 500 kg, 40 karton |

Empat produk menutup seluruh mode pelacakan yang harus ditangani gudang JDS: ber-lot dengan
expiry, ber-lot saja, tanpa pelacakan, dan **serial/IMEI**.

Seluruh 12 kategori (Add Warehouse, Add Location, Storage Categories, Putaway, PO Inbound, Internal
Transfer, Delivery Order, Picking Out, Cycle Counting, Print Label, Scrap, Reporting) lulus
terhadap record nyata — bukan mock.

Enam cacat platform ditemukan dan **sudah diperbaiki** dalam proses ini (CSS laporan terbuang,
sesi `CC/NEW`, laporan SQL view membaca data basi, barcode via callback HTTP, salah diagnosis
performa PDF di shell, worker web memegang kode lama). Rinciannya di TSD §10.

## 3. Pemetaan terhadap lembar 15 kebutuhan JDS

Lembar kebutuhan klien ("Warehouse Management" 1–10 dan "Report" 11–15) diuji otomatis oleh
`70_scenario_test.py`, yang mencetak PASS/PARTIAL/FAIL per butir berikut bukti record yang dipakai.

| # | Butir kebutuhan JDS | Ditangani oleh | BR terkait |
|---|---|---|---|
| 1 | Master data: penyimpanan bin berbasis volume | Kapasitas volume bin + aturan `by_volume` | BR-WH-03, BR-PA-03 |
| 2 | Jadwal kedatangan pemasok | PO terkonfirmasi / ASN dari host | BR-IN-01, BR-IT-01 |
| 3 | GR lewat handheld: EAN, IMEI/serial, non-serial, expiry, batch pemasok | Halaman Receive + parsing GS1 AI 10/17/21 + batch pemasok | BR-IN-01..04 |
| 4 | Upload template untuk IMEI/EAN, serial/non-serial, expiry, batch | Wizard import penerimaan CSV/XLSX | BR-IN-05 |
| 5 | Total otomatis dari pemindaian / input kuantitas manual | Sesi pindai `custom_barcode` | BR-IN-01 |
| 6 | Pembuatan barcode + cetak stiker (IMEI & EAN) | Barcode List + Product Label / Price Tag | BR-RP-02, BR-RP-05 |
| 7 | Putaway: sistem menyarankan bin dari aturan yang telah ditetapkan | Mesin putaway 6 tier | BR-PA-01..05 |
| 8 | Perintah replenishment otomatis | Aturan transfer pemicu `low_water_mark` | BR-ST-02 |
| 9 | Picking: sistem menyarankan bin asal pengambilan | Reservasi terhadap bin + halaman Pick | BR-OU-01, BR-OU-02 |
| 10 | Racking: setiap rak menampilkan daftar material dan kuantitasnya | Stock Summary Report per bin | BR-RP-03 |
| 11 | Laporan retur pembelian | Purchase Return Report | BR-RT-02, BR-RP-03 |
| 12 | Ringkasan laporan stok | Stock Summary Report (kuantitas + nilai) | BR-RP-03 |
| 13–14 | Stock take + spot check | Cycle count metode `by_zone` dan `spot_check` | BR-CC-01..07 |
| 15 | Laporan transfer | Transfer Report | BR-RP-03 |

## 4. Pemetaan terhadap deck SAP EWM

Deck asli JDS ditulis dalam istilah SAP EWM (TO, PID, ZWME001, Sloc, PGI). Pemetaannya ke platform
ini sudah didokumentasikan di `scripts/tenants/wms_demo/README.md`:

| Istilah deck | Realisasi di platform |
|---|---|
| EAN SCAN GR | Halaman handheld Receive + sesi pindai `custom_barcode` + GS1 |
| Putaway ZWME001 | Strategi putaway 6 tier `custom_wms_putaway` (pencarian tipe/seksi penyimpanan, volume, ABC, bin kosong terdekat) |
| EAN SCAN PICK & PACK | Halaman handheld Pick dan Package |
| EAN SCAN BIN TO BIN | Halaman handheld Bin-to-Bin + `custom_wms_to_engine` (TO) |
| EAN SCAN STOCK OPNAME | Cycle count (PID) `custom_wms_cycle_count` |
| Host SAP | `custom_wms_integration` — `/api/wms/*` + outbox, adapter `wms_sap_host` |

Catatan penting untuk percakapan dengan klien: **tidak ada kode modul baru yang diperlukan** untuk
memenuhi deck tersebut — yang diperlukan adalah data dan konfigurasi. Itulah sebab estimasi JDS
berada di skenario Brownfield, bukan Greenfield.

## 5. Yang masih terbuka

Ini yang belum diketahui dan harus ditutup pada fase Requirement & fit-gap JDS:

| # | Hal | Mengapa penting |
|---|---|---|
| O1 | **Volume riil**: jumlah gudang, zona, bin, dan SKU aktif di Cikupa | Menentukan pengali estimasi (lihat estimasi generik §9). Demo memakai skala kecil; W07 ECOMMERCE di platform ini sudah pernah memuat 154 bin / 3.292 SKU |
| O2 | **Perangkat handheld riil** dan simbologi yang aktif | Unit Denso BHT pada lingkup proyek ini hanya membaca EAN-13. Harus diuji, bukan diasumsikan |
| O3 | **Integrasi SAP di-scope atau tidak** | Bila ya: kontrak payload + kesiapan sisi SAP menjadi gate SIT. Bila tidak: −10 mandays |
| O4 | **Kualitas master produk JDS** (barcode unik, dimensi, berat) | Slotting berbasis volume/dimensi tidak dapat dinyalakan tanpa data ini |
| O5 | **Mode SAP slotting dipakai atau tidak** | Bila ya, perlu daftar tipe & seksi penyimpanan riil JDS untuk menggantikan CSV referensi |
| O6 | **Denah bin riil** dan urutan jalan | Harus dibekukan di akhir fase Design |
| O7 | **Ekspektasi ketersediaan & RPO** | RPO nyata platform saat ini 24 jam (lihat Architecture §9) |
| O8 | Gap platform yang sudah diketahui: cron sesi hitung, berkas placeholder, mode offline handheld | Sudah dibiayai di estimasi, tetapi perlu dikonfirmasi relevansinya untuk JDS |

## 6. Estimasi mandays JDS

Basis: skenario Brownfield generik (179 mandays), **dikurangi** karena POC sudah menutup sebagian
fase Requirement dan Design — kelayakan sudah dibuktikan, alur sudah diperagakan, dan konfigurasi
referensi sudah ada dalam bentuk skrip.

Asumsi lingkup: **1 gudang (Cikupa), ≤3 zona, ≤200 bin, ≤5.000 SKU aktif, integrasi SAP
di-scope.** Bila O1 mengungkap skala lebih besar, terapkan pengali pada
[`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) §9.

> **Effort PM belum dihitung** — kolom PM dikosongkan dan diisi oleh PM. Total di bawah adalah
> BA + DEV + QA saja.

| Fase | PM | BA | DEV | QA | Total |
|---|:--:|---:|---:|---:|---:|
| 1. Requirement & fit-gap *(POC sudah menutup sebagian)* | — | 5 | 1 | 1 | **7** |
| 2. Design delta | — | 3 | 3 | 1 | **7** |
| 3. Konfigurasi + build gap | — | 8 | 26 | 10 | **44** |
| 4. Data migration & master setup | — | 5 | 6 | 3 | **14** |
| 5. SIT | — | 1 | 3 | 5 | **9** |
| 6. UAT + training | — | 4 | 3 | 4 | **11** |
| 7. Cutover & go-live | — | 2 | 5 | 2 | **9** |
| 8. Hypercare | — | 2 | 4 | 2 | **8** |
| **Subtotal** | *diisi PM* | **30** | **51** | **28** | **109** |
| Kontingensi 15% | *diisi PM* | 4 | 8 | 4 | **16** |
| **TOTAL** | *diisi PM* | **34** | **59** | **32** | **≈ 125** |

Perbandingan (seluruhnya tanpa PM):

| | Greenfield | Brownfield generik | **JDS (pasca-POC)** |
|---|---:|---:|---:|
| Total mandays | 448 | 179 | **125** |
| Durasi | ≈ 25 minggu | ≈ 12 minggu | **≈ 10 minggu** |
| Penghematan vs Greenfield | — | 60% | **72%** |

Selisih 54 mandays antara JDS dan Brownfield generik berasal dari: fase Requirement lebih pendek
(kelayakan sudah terbukti, alur sudah diperagakan ke klien), Design delta lebih kecil (konfigurasi
referensi sudah ada sebagai skrip), dan pengujian yang dapat memanfaatkan `70_scenario_test.py`
serta `80_poc_scenario.py` sebagai basis regresi.

**Penyesuaian bila asumsi berubah** (seluruhnya tanpa PM):

| Kondisi | Dampak |
|---|---:|
| Integrasi SAP **tidak** di-scope | −10 |
| Skala > 500 bin | +8 |
| Skala > 10.000 SKU | +10 |
| Mode SAP slotting tidak dipakai | −5 |
| Gudang kedua dengan tata letak serupa | +10 |
| Mode offline handheld terbukti wajib | +12 |
| Pembersihan master data massal | dinilai setelah audit (O4) |

## 7. Timeline JDS

≈ 10 minggu.

| Fase | Durasi | Minggu | Milestone |
|---|---|---|---|
| 1. Requirement & fit-gap | 2 mgg | W1–W2 | O1–O8 tertutup; audit master data selesai; baseline KPI terukur |
| 2. Design delta | 1 mgg | W2–W3 | Denah bin Cikupa dibekukan; spesifikasi gap sign-off |
| 3. Konfigurasi + build gap | 3 mgg | W3–W6 | Sistem terkonfigurasi pada data JDS; demo internal |
| 4. Data migration & master setup | 2 mgg | W5–W7 | Master + denah bin + saldo awal termuat |
| 5. SIT | 1 mgg | W7–W8 | *Gate:* handheld & sisi SAP siap; E2E lulus |
| 6. UAT + training | 2 mgg | W7–W9 | UAT sign-off; operator Cikupa terlatih |
| 7. Cutover & go-live | 1 mgg | W9–W10 | Opname penuh → saldo awal → go-live |
| 8. Hypercare | 1 mgg | W10 | Cycle count intensif; serah terima |

## 8. Risiko khusus JDS

Selain risiko generik pada PID §12:

| # | Risiko | Dampak | Mitigasi |
|---|---|:--:|---|
| J1 | **Denso BHT hanya membaca EAN-13.** Barcode dokumen memakai Code128 karena referensi mengandung `/` | Tinggi | Sudah dimitigasi di produk: barcode item dirender adaptif (13 digit → EAN-13). Namun barcode **dokumen** tetap Code128 — konfirmasi bahwa perangkat pembaca dokumen berbeda dari perangkat pembaca item, atau sesuaikan format referensi |
| J2 | Deck ditulis dalam istilah SAP EWM; ekspektasi klien bisa berupa "SAP EWM di Odoo" | Sedang | Pemetaan istilah (§4) dibawa ke workshop fit-gap sejak hari pertama; nyatakan mana yang setara dan mana yang berbeda |
| J3 | POC berjalan pada skala kecil (13 bin, 8 SKU); Cikupa jauh lebih besar | Sedang | Referensi skala yang sudah terbukti di platform: W07 ECOMMERCE, 154 bin / 3.292 SKU (`scripts/tenants/wms_ecomm/`). Uji beban dengan volume riil pada fase SIT |
| J4 | Sisi SAP JDS belum tentu siap menandatangani permintaan ber-HMAC | Sedang | Jangan matikan penjagaan HMAC "sementara". Siapkan jalur import manual sebagai jalur mundur |
| J5 | Modul WMS dibagi dengan tenant lain di platform | Tinggi | Kebutuhan JDS yang tidak layak digeneralisasi turun ke modul `_tenants/custom_jds_*`, bukan disisipkan ke `ee_gap/` |

## 9. Langkah berikutnya

1. Jadwalkan workshop fit-gap 2 minggu di Cikupa untuk menutup O1–O8.
2. Bawa perangkat handheld riil JDS ke workshop; uji simbologi hari pertama (J1).
3. Minta ekstraksi master produk JDS untuk audit kualitas data sebelum angka scope dikunci.
4. Putuskan bersama klien: integrasi SAP masuk fase 1 atau ditunda ke fase 2.
5. Peragakan ulang POC di depan pengguna kunci Cikupa memakai `80_poc_scenario.py`, kali ini lewat
   antarmuka, bukan skrip — skrip ada untuk membuktikan rantainya berjalan dan menghasilkan bukti cetak.
6. Kunci angka final memakai pengali pada §6 setelah O1–O8 tertutup.
