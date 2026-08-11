# WMS Implementation — Paket Dokumen

Paket dokumen implementasi **Warehouse Management System di atas Odoo 19**, ditulis generik
sehingga dapat dipakai ulang untuk klien mana pun, dengan satu addendum contoh untuk calon klien
**JDS (JD Sport Cikupa)**.

Paket ini menggambarkan kapabilitas yang **sudah terpasang** di platform: 10 modul
`addons/ee_gap/custom_wms_*` ditambah modul pendukung di `addons/core/`, dengan bukti end-to-end
berupa POC 14/14 PASS di [`../warehouse-jds/WMS-POC-Scenario.md`](../warehouse-jds/WMS-POC-Scenario.md).

Bahasa: **Bahasa Indonesia** (dokumen menghadap klien). Rujukan teknis memakai nama modul, model,
dan rute apa adanya dari basis kode.

---

## Isi paket

| # | Dokumen | Untuk siapa | Isi |
|---|---|---|---|
| 00 | [`00-Project-Initiation-Document.md`](00-Project-Initiation-Document.md) | Sponsor, PM | Mandat, scope, tata kelola & RACI, milestone, kriteria sukses, risiko, kriteria serah terima |
| 01 | [`01-BRD.md`](01-BRD.md) | Sponsor, Warehouse Manager, BA | Konteks bisnis, KPI, proses target, **60+ kebutuhan bernomor (BR-xx)** dengan prioritas MoSCoW dan status platform |
| 02 | [`02-FSD.md`](02-FSD.md) | Key user, BA, QA | Fungsi per area, peran & hak akses, aplikasi handheld, dokumen & laporan, 7 user journey, **22 acceptance test**, matriks traceability |
| 03 | [`03-TSD.md`](03-TSD.md) | Developer, arsitek, IT klien | Komponen & model data per modul, permukaan API, keamanan, konfigurasi, deployment & rollback, pengujian, utang teknis, jebakan Odoo 19 |
| 04 | [`04-Architecture.md`](04-Architecture.md) | Arsitek, IT klien | Prinsip, tumpukan aplikasi, tier modul, topologi deployment, isolasi multi-tenant, alur data, batasan nyata, keputusan arsitektur |
| 05 | [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) | Sponsor, PM, sales | **Estimasi effort PM/BA/DEV/QA** dua skenario, rincian per workstream, timeline, komposisi tim, faktor pengubah, eksklusi |
| 06 | [`06-Addendum-JDS.md`](06-Addendum-JDS.md) | Tim engagement JDS | Posisi engagement, hasil POC, pemetaan 15 kebutuhan & deck SAP EWM, yang masih terbuka, estimasi & timeline JDS |

## Angka utama

> **Effort PM sengaja dikosongkan** di seluruh paket — diisi oleh PM sesuai model tata kelola yang
> dipakai. Semua total di bawah adalah **BA + DEV + QA saja**, dan harus dijumlahkan ulang setelah
> alokasi PM masuk.

| | Greenfield (bangun dari nol) | Brownfield (reuse modul) | JDS (pasca-POC) |
|---|---:|---:|---:|
| PM | *diisi PM* | *diisi PM* | *diisi PM* |
| BA | 90 | 51 | 34 |
| DEV | 252 | 84 | 59 |
| QA | 106 | 44 | 32 |
| **Total tanpa PM (termasuk kontingensi 15%)** | **≈ 448** | **≈ 179** | **≈ 125** |
| Durasi | ≈ 25 minggu | ≈ 12 minggu | ≈ 10 minggu |

Penghematan Brownfield vs Greenfield: **269 mandays (60%)**. Untuk JDS, karena POC sudah lulus:
**323 mandays (72%)**.

Angka bersifat **indikatif berbasis asumsi tertulis**, bukan komitmen kontrak. Lingkup dasar:
1 gudang, ≤3 zona, ≤200 bin, ≤5.000 SKU. Pengali untuk skala lain ada di dokumen 05 §9.

## Urutan membaca

- **Sponsor / manajemen:** 00 → 05 → (bila JDS) 06
- **Business analyst / key user:** 01 → 02 → 06
- **Developer / arsitek / IT klien:** 04 → 03 → 02
- **Sales / pra-penjualan:** README ini → 05 → 06

## Konvensi

- **SUDAH ADA** = terpasang dan terverifikasi di repo pada 2026-08-11.
  **PERLU DIBANGUN** = belum ada, dan sudah dibiayai eksplisit di estimasi.
- **NOW** vs **TARGET** pada dokumen arsitektur mengikuti konvensi [`../../architecture.md`](../../architecture.md):
  tidak ada yang berstatus TARGET boleh dijual sebagai sudah ada.
- Diagram berupa ASCII di dalam blok kode, konsisten dengan arsitektur platform.
- Setiap kebutuhan (BR-xx) dapat ditelusuri ke fungsi FSD dan ke acceptance test — lihat FSD §11.

## Gap yang tercatat jujur

Verifikasi basis kode menemukan tiga hal yang belum jadi. Ketiganya masuk scope dan biaya, tidak
disembunyikan di balik klaim kapabilitas:

| Gap | Rujukan |
|---|---|
| Penerbitan sesi cycle count belum terjadwal — metode `_cron_generate_sessions()` ada, record `ir.cron` belum (`data/cron.xml` masih placeholder) | FSD F-CC-08, TSD T1 |
| Berkas `data/*.xml` placeholder lain: `custom_wms_putaway/ir_sequence_data.xml`, `custom_hht_bridge/cron.xml` dan `ir_config_parameter_data.xml` | TSD T2, T3 |
| Mode kerja offline handheld belum diverifikasi terhadap perangkat klien | BRD BR-DV-05, TSD T4 |

## Sumber & bukti

| Aset | Lokasi |
|---|---|
| Modul WMS (10) | `addons/ee_gap/custom_wms_*` |
| Modul pendukung | `addons/core/custom_hht_bridge`, `addons/core/custom_product_barcode`, `addons/ee_gap/custom_barcode`, `addons/ee_gap/custom_receipt_async` |
| Skenario POC (14/14 PASS) | [`../warehouse-jds/WMS-POC-Scenario.md`](../warehouse-jds/WMS-POC-Scenario.md) |
| Uji 15 butir kebutuhan klien | `scripts/tenants/wms_demo/70_scenario_test.py` |
| Walkthrough POC 12 kategori | `scripts/tenants/wms_demo/80_poc_scenario.py` |
| Konfigurasi referensi | `scripts/tenants/wms_demo/50_config_wms.py`, `51_config_native_slotting.py`, `52_config_orderpoints.py` |
| Referensi skala besar (154 bin / 3.292 SKU) | `scripts/tenants/wms_ecomm/` |
| Profil handheld Zebra | [`../../hht/datawedge.md`](../../hht/datawedge.md) |
| Arsitektur platform | [`../../architecture.md`](../../architecture.md) |

---

**Terakhir diverifikasi terhadap repo: 2026-08-11.**
