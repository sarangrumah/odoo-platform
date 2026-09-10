# Project Estimation — Mandays & Timeline
## Implementasi PPOB / Bill-Payment Switching di atas Odoo 19

| | |
|---|---|
| **Dokumen** | 05 — Estimasi Mandays |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Pembaca** | Sponsor, PM, sales |
| **Sifat angka** | Indikatif berbasis asumsi tertulis — **bukan komitmen kontrak** |

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

> **Effort PM sengaja dikosongkan** di seluruh dokumen — diisi PM sesuai model tata kelola yang
> dipakai. Semua total di bawah adalah **BA + DEV + QA saja** dan harus dijumlahkan ulang
> setelah alokasi PM masuk.

| | **Skenario A — Greenfield** | **Skenario B — Brownfield** |
|---|---:|---:|
| | bangun suite PPOB dari nol | reuse 12 modul yang sudah ada |
| PM | *diisi PM* | *diisi PM* |
| BA | 76 | 47 |
| DEV | 284 | 108 |
| QA | 108 | 56 |
| Subtotal | 468 | 211 |
| Kontingensi 15% | 70 | 32 |
| **Total tanpa PM** | **≈ 538** | **≈ 243** |
| Durasi | ≈ 26 minggu | ≈ 13 minggu |

**Penghematan Brownfield vs Greenfield: 295 mandays (55%).**

Penghematan itu nyata karena 67 dari 80 kebutuhan bisnis pada BRD sudah berstatus SUDAH ADA di
repo — termasuk seluruh primitif uang (wallet atomik, bucket deposit, refund berpasangan,
reaper) yang justru paling mahal dan paling berisiko dibangun ulang.

## 2. Ruang lingkup effort

### 2.1 Termasuk (kedua skenario)

- Analisis kebutuhan, fit-gap, dan penulisan BRD/FSD/TSD.
- Konfigurasi master data, COA & pemetaan akun, tier harga, provider, SKU map.
- Integrasi **satu** biller riil, **satu** bank VA, dan **satu** kanal penjualan.
- Rollup faktur harian, komisi + PPh 23, target SLA & sampling.
- Migrasi saldo pembuka mitra dan deposit biller.
- SIT (termasuk uji konkurensi dan uji beban), UAT, pelatihan.
- Dual-run, gerbang paritas, cutover bertahap, hypercare.

### 2.2 Termasuk khusus Skenario B — pekerjaan gap yang sudah teridentifikasi

Enam gap pada PID §4.3 dibiayai eksplisit di fase Build gap (§5.2):

| Gap | Isi pekerjaan |
|---|---|
| G1 | API wallet sinkron: 5 endpoint, kolom saldo tertahan, penyesuaian ceiling, HMAC, idempotensi per langkah |
| G2 | Penyesuaian bridge: feed POS diganti API wallet, feed H2H dipertahankan untuk dual-run |
| G3 | Paket test untuk wallet, rollup, commission, core (termasuk uji konkurensi dua kursor) |
| G5 | Anti-replay + pemakaian toleransi selisih waktu pada gateway kanal, atau koreksi dokumentasi modul |
| G6 | Skrip konfigurasi tenant PPOB agar go-live reproducible |
| BR-OP-07 | Peringatan deposit menipis ke kanal notifikasi ops |

## 3. Asumsi

| # | Asumsi | Bila berubah |
|---|---|---|
| A1 | Satu perusahaan, satu mata uang (IDR), satu tenant | Multi-entitas menambah 10–20% (§9) |
| A2 | **Satu** biller riil pada lingkup dasar | Tiap biller tambahan: 8–14 mandays DEV + 3 QA |
| A3 | **Satu** bank VA | Tiap bank tambahan: 5–8 mandays DEV + 2 QA |
| A4 | **Satu** kanal penjualan yang memakai kontrak drop-in | Kanal dengan kontrak berbeda: 12–20 mandays |
| A5 | Volume dasar ≤ 50.000 transaksi/hari dengan jam sibuk terkonsentrasi | Volume lebih tinggi menambah pekerjaan kapasitas (§9) |
| A6 | Katalog ≤ 2.000 produk PPOB | Katalog lebih besar menambah pekerjaan migrasi data |
| A7 | Klien menyediakan sandbox biller/bank/kanal tepat waktu | Keterlambatan sandbox langsung menggeser jadwal |
| A8 | Kebijakan PPN per kelas diputuskan sebelum konfigurasi | Keputusan tertunda menghentikan fase konfigurasi |
| A9 | Migrasi historis terbatas pada saldo pembuka + periode rekonsiliasi | Migrasi riwayat penuh dihitung terpisah |
| A10 | 1 manday = 8 jam kerja efektif satu orang | — |

## 4. Skenario A — Greenfield

Membangun seluruh kapabilitas PPOB dari nol di atas Odoo 19 — dipakai sebagai pembanding nilai,
bukan sebagai rekomendasi.

### 4.1 Mandays per peran × fase

| Fase | PM | BA | DEV | QA | Total |
|---|:--:|---:|---:|---:|---:|
| 1. Requirement & analisis | *diisi PM* | 24 | 4 | 4 | 32 |
| 2. Desain arsitektur & teknis | *diisi PM* | 10 | 20 | 2 | 32 |
| 3. Build mesin inti (core, wallet, provider, sale) | *diisi PM* | 6 | 96 | 18 | 120 |
| 4. Build kanal & integrasi | *diisi PM* | 6 | 64 | 16 | 86 |
| 5. Build finance, pajak & observabilitas | *diisi PM* | 6 | 44 | 12 | 62 |
| 6. Migrasi data & setup master | *diisi PM* | 8 | 20 | 6 | 34 |
| 7. SIT (termasuk konkurensi & beban) | *diisi PM* | 4 | 16 | 30 | 50 |
| 8. UAT & pelatihan | *diisi PM* | 8 | 6 | 14 | 28 |
| 9. Go-live & hypercare | *diisi PM* | 4 | 14 | 6 | 24 |
| **Subtotal** | | **76** | **284** | **108** | **468** |
| Kontingensi 15% | | | | | 70 |
| **Total tanpa PM** | | | | | **538** |

### 4.2 Rincian fase Build per workstream

**Fase 3 — mesin inti (DEV 96):**

| Workstream | DEV |
|---|---:|
| Master data + pemetaan akun berbasis peran | 12 |
| Wallet mitra: primitif atomik, jurnal berpasangan, buku pembantu, kredit inklusif pajak | 24 |
| Provider: bucket atomik, registry adapter, SKU map, top-up DP-100% | 26 |
| Mesin transaksi: state machine, idempotensi, routing/failover, refund, reaper | 34 |

**Fase 4 — kanal & integrasi (DEV 64):**

| Workstream | DEV |
|---|---:|
| Gateway kanal H2H (7 endpoint + cron callback) | 22 |
| VA bank (inquiry + payment + rekonsiliasi rekening koran) | 16 |
| Adapter biller riil pertama | 14 |
| Feed mirror, join, antrean lewatan, backfill | 12 |

**Fase 5 — finance & observabilitas (DEV 44):**

| Workstream | DEV |
|---|---:|
| Rollup faktur harian + pengecualian jurnal non-GL | 14 |
| Komisi dua arah + PPh 23 + bukti potong | 16 |
| Target SLA + sampling throughput | 8 |
| Laporan marjin & rekonsiliasi | 6 |

## 5. Skenario B — Brownfield

Memakai 12 modul yang sudah terpasang; pekerjaan berpindah dari *membangun* ke
*mengonfigurasi, menutup gap, memigrasi, dan membuktikan paritas*.

### 5.1 Mandays per peran × fase

| Fase | PM | BA | DEV | QA | Total |
|---|:--:|---:|---:|---:|---:|
| 1. Requirement & fit-gap terhadap suite | *diisi PM* | 11 | 3 | 2 | 16 |
| 2. Desain & rencana cutover | *diisi PM* | 5 | 8 | 1 | 14 |
| 3. Konfigurasi & master data | *diisi PM* | 10 | 14 | 6 | 30 |
| 4. Build gap (G1, G2, G3, G5, G6, BR-OP-07) | *diisi PM* | 4 | 46 | 12 | 62 |
| 5. Migrasi data & saldo pembuka | *diisi PM* | 6 | 14 | 5 | 25 |
| 6. SIT + dual-run paritas | *diisi PM* | 3 | 10 | 18 | 31 |
| 7. UAT & pelatihan | *diisi PM* | 5 | 3 | 8 | 16 |
| 8. Go-live bertahap & hypercare | *diisi PM* | 3 | 10 | 4 | 17 |
| **Subtotal** | | **47** | **108** | **56** | **211** |
| Kontingensi 15% | | | | | 32 |
| **Total tanpa PM** | | | | | **243** |

### 5.2 Rincian fase Build gap (DEV 46)

| Gap | Isi | DEV |
|---|---|---:|
| G1 | API wallet sinkron: hold/commit/release/credit/balance + kolom saldo tertahan + HMAC + idempotensi per langkah | 16 |
| G3 | Paket test wallet, rollup, commission, core (sisi DEV; sisi QA 12 pada tabel §5.1) | 10 |
| G2 | Penyesuaian bridge: feed POS → API wallet, feed H2H dipertahankan untuk dual-run | 8 |
| G6 | Skrip konfigurasi tenant PPOB | 6 |
| G5 | Anti-replay + kesegaran waktu pada gateway kanal | 4 |
| BR-OP-07 | Peringatan deposit menipis | 2 |

### 5.3 Rincian fase Konfigurasi (DEV 14)

| Pekerjaan | DEV |
|---|---:|
| Impor master: produk, tier harga, SKU map | 8 |
| COA + pemetaan akun berbasis peran | 3 |
| Penyiapan provider, wallet, VA, kredensial kanal | 3 |

### 5.4 Rincian fase Migrasi (total 25)

| Pekerjaan | BA | DEV | QA |
|---|---:|---:|---:|
| Saldo pembuka mitra (ekstrak, muat, jurnal migrasi, berita acara) | 3 | 7 | 3 |
| Deposit biller awal + rekonsiliasi ke saldo riil | 2 | 4 | 1 |
| Pemetaan mitra/produk warisan → master baru | 1 | 3 | 1 |

## 6. Perbandingan & analisis penghematan

| Fase | Greenfield | Brownfield | Selisih |
|---|---:|---:|---:|
| Requirement & analisis | 32 | 16 | −16 |
| Desain | 32 | 14 | −18 |
| Build inti | 120 | — | −120 |
| Build kanal & integrasi | 86 | — | −86 |
| Build finance & observabilitas | 62 | — | −62 |
| Konfigurasi | — | 30 | +30 |
| Build gap | — | 62 | +62 |
| Migrasi & master | 34 | 25 | −9 |
| SIT | 50 | 31 | −19 |
| UAT & pelatihan | 28 | 16 | −12 |
| Go-live & hypercare | 24 | 17 | −7 |
| **Subtotal** | **468** | **211** | **−257** |
| Kontingensi 15% | 70 | 32 | −38 |
| **Total tanpa PM** | **538** | **243** | **−295 (55%)** |

Sumber penghematan terbesar bukan pada fitur yang terlihat, melainkan pada **primitif uang**:
wallet atomik, bucket non-negatif, refund idempoten, dan reaper yang tidak pernah refund buta.
Membangunnya ulang mahal bukan karena panjang kodenya, tetapi karena setiap kesalahan di sana
berbentuk rupiah.

## 7. Timeline & milestone

### 7.1 Skenario A — Greenfield (≈ 26 minggu)

```
  Mgg  1  3  5  7  9 11 13 15 17 19 21 23 25 26
       |--|  Requirement
          |--|  Desain
             |----------|  Build inti
                        |------|  Build kanal & integrasi
                               |----|  Build finance & observabilitas
                                    |--|  Migrasi & master
                                       |--|  SIT
                                          |--|  UAT & pelatihan
                                             |--|  Go-live & hypercare
```

### 7.2 Skenario B — Brownfield (≈ 13 minggu)

```
  Mgg  1  2  3  4  5  6  7  8  9 10 11 12 13
       |--|  Requirement & fit-gap
          |--|  Desain & rencana cutover
             |----|  Konfigurasi & master data
                  |------|  Build gap
                        |---|  Migrasi & saldo pembuka
                            |--|  SIT
                               |--|  UAT & pelatihan
                                  |--|  Dual-run + gerbang paritas
                                     |--|  Cutover bertahap & hypercare
```

Milestone mengikuti PID §8 (M1–M10). Gerbang paritas (M8) adalah **gerbang keras**: cutover
tidak dibuka sebelum selisih nol tercapai selama N hari berturut yang disepakati.

## 8. Komposisi & pembebanan tim

### Skenario A

| Peran | Jumlah | Periode |
|---|:--:|---|
| PM | *diisi PM* | sepanjang proyek |
| BA | 1 | penuh minggu 1–6, paruh setelahnya |
| DEV | 2–3 | puncak pada minggu 5–19 |
| QA | 1–1,5 | mulai minggu 7, puncak minggu 19–24 |

### Skenario B

| Peran | Jumlah | Periode |
|---|:--:|---|
| PM | *diisi PM* | sepanjang proyek |
| BA | 1 | penuh minggu 1–5, paruh setelahnya |
| DEV | 2 | puncak pada minggu 4–9 |
| QA | 1 | mulai minggu 4, puncak minggu 9–12 |

Peran klien yang harus tersedia dan sering diremehkan: Finance Lead untuk keputusan pajak, Ops
Lead untuk prosedur eksepsi, dan IT untuk allowlist IP serta kredensial — ketiganya berada di
jalur kritis jadwal.

## 9. Faktor pengubah estimasi

| Faktor | Pengali / tambahan |
|---|---|
| Biller riil tambahan | +8–14 mandays DEV, +3 QA per biller |
| Bank VA tambahan | +5–8 mandays DEV, +2 QA per bank |
| Kanal dengan kontrak berbeda (bukan drop-in) | +12–20 mandays |
| Multi-entitas / multi-perusahaan | +10–20% total |
| Volume > 50.000 transaksi/hari | +10–15% (kapasitas, uji beban, tuning) |
| Katalog > 2.000 produk | +5–10 mandays migrasi data |
| Migrasi riwayat transaksi penuh | +15–30 mandays |
| Jalur legacy Oracle diaktifkan | +10–15 mandays (koneksi, pemetaan, backfill) |
| Persyaratan audit/kepatuhan tambahan | +5–15 mandays |
| Window dual-run diperpanjang | +2 mandays QA per minggu tambahan |

## 10. Yang tidak termasuk

- Lisensi Odoo Enterprise (bila dipakai) dan biaya infrastruktur.
- Pengembangan aplikasi mitra/outlet.
- Negosiasi komersial dengan biller/bank dan biaya integrasi pihak ketiga.
- Perizinan penyelenggaraan PPOB.
- Dukungan operasional pasca-hypercare (kontrak terpisah).
- Migrasi riwayat transaksi di luar §2.1.
- Perubahan lingkup yang disetujui setelah baseline (ditangani lewat change request).

## 11. Risiko terhadap estimasi

| # | Risiko | Dampak estimasi | Mitigasi |
|---|---|---|---|
| E1 | Sandbox biller/bank terlambat | Menggeser jadwal, bukan menambah effort | Adapter mock membuat SIT tetap berjalan |
| E2 | Spesifikasi biller berbeda dari dokumen | +5–10 mandays per biller | Uji kontrak sedini mungkin |
| E3 | Keputusan pajak tertunda | Menghentikan fase konfigurasi | Jadikan gerbang milestone M3 |
| E4 | Saldo sistem lama tidak dapat direkonsiliasi | +10–20 mandays | Mulai ekstraksi & rekonsiliasi saldo di minggu pertama |
| E5 | Gerbang paritas gagal berulang | +1–3 minggu per siklus | Dual-run mulai lebih awal dan diperiksa harian |
| E6 | Perubahan skema wallet menimbulkan regresi | +5–15 mandays | Bangun paket test wallet **sebelum** menyentuh skema (G3 mendahului G1) |
| E7 | Kualitas data master klien rendah | +5–15 mandays | Profiling data pada fase fit-gap |

---

*Dokumen berikutnya: [`06-Addendum-PPS.md`](06-Addendum-PPS.md) — penerapan untuk engagement PPS.*
