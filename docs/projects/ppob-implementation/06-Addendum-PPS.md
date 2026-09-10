# Addendum — Penerapan untuk PPS (Erajaya VAS / Eraspace)
## PPOB / Bill-Payment Switching di atas Odoo 19

| | |
|---|---|
| **Dokumen** | 06 — Addendum klien |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Pembaca** | Tim engagement PPS |
| **Induk** | [`README.md`](README.md) — paket dokumen 00–05 |
| **Dokumen arsitektur terkait** | [`../ppob/ppob-eraspace-h2h-architecture.md`](../ppob/ppob-eraspace-h2h-architecture.md) · [`../ppob/ppob-eraspace-odoo-target-architecture.md`](../ppob/ppob-eraspace-odoo-target-architecture.md) |

---

## Contents

1. [Posisi engagement saat ini](#1-posisi-engagement-saat-ini)
2. [Apa yang sudah dibangun dan terverifikasi](#2-apa-yang-sudah-dibangun-dan-terverifikasi)
3. [Pemetaan terhadap tiga fase arsitektur PPS](#3-pemetaan-terhadap-tiga-fase-arsitektur-pps)
4. [Yang masih terbuka](#4-yang-masih-terbuka)
5. [Estimasi mandays PPS](#5-estimasi-mandays-pps)
6. [Timeline PPS](#6-timeline-pps)
7. [Risiko khusus PPS](#7-risiko-khusus-pps)
8. [Langkah berikutnya](#8-langkah-berikutnya)

---

## 1. Posisi engagement saat ini

PPS adalah program PPOB / VAS Erajaya (Eraspace). Kondisi yang menjadi titik berangkat, sesuai
dua dokumen arsitektur PPOB di repo:

| Aspek | Kondisi existing |
|---|---|
| Jalur transaksi | Aplikasi mitra/outlet memanggil **switcher H2H langsung** |
| Posisi POS Eraspace | **Di luar** jalur transaksi PPOB |
| Saldo mitra prepaid | Dipegang aplikasi warisan (Azecs) |
| Deposit biller & dispatch | Milik switcher H2H |
| Odoo | Belum berada di jalur transaksi |

Arah yang sudah disepakati dalam dokumen arsitektur: tiga gelombang —

1. **Fase 1** — Odoo menggantikan pemegang saldo: wallet **otoritatif** + mirror ledger sisi
   biller dari feed H2H.
2. **Fase 2** — Odoo menggantikan switcher H2H: dispatch, deposit biller, adapter, reaper.
3. **Fase 3** — konsolidasi penuh: top-up VA, katalog/SKU master, komisi.

Addendum ini menerjemahkan arah tersebut menjadi lingkup, effort, dan jadwal, memakai kerangka
dokumen 00–05 sebagai basis dan **Skenario B (brownfield)** sebagai titik tolak.

## 2. Apa yang sudah dibangun dan terverifikasi

Seluruh 12 modul suite berada di repo pada 2026-08-11:

| Modul | Peran dalam program PPS |
|---|---|
| `custom_ppob_core` | Master data + pemetaan akun berbasis peran |
| `custom_ppob_wallet` | Saldo mitra atomik + jurnal berpasangan — inti Fase 1 |
| `custom_ppob_provider` | Bucket deposit, registry adapter, DP-100% — inti Fase 2 |
| `custom_ppob_sale` | State machine, routing/failover, refund, reaper — inti Fase 2 |
| `custom_ppob_va` | Top-up mitra lewat VA bank — Fase 1/3 |
| `custom_ppob_pps_gateway` | **Kontrak PPS/EVShop drop-in** sehingga kanal cukup mengganti base URL |
| `custom_ppob_eraspace_bridge` | Ingest dua feed + join per referensi transaksi + mirror GL |
| `custom_ppob_oracle_bridge` | Jalur legacy Oracle EVShop (`SellWithDenom_HA` + polling `MSG016T`/`MSG019T`) |
| `custom_ppob_biller_digiflazz` | Adapter biller riil pertama |
| `custom_ppob_rollup` | Faktur ringkas harian per mitra untuk Coretax |
| `custom_ppob_commission` | Komisi dua arah + PPh 23 + bukti potong |
| `custom_ppob_sla` | Target SLA + sampling throughput, dengan pemisahan **baseline historis** vs **aktual Odoo** untuk uji paritas |

Test otomatis yang ada: **135 test pada 8 modul**. Empat modul tanpa test —
`custom_ppob_core`, `custom_ppob_wallet`, `custom_ppob_commission`, `custom_ppob_rollup`
(lihat TSD §8).

Basis data uji `rnd_ppob` dibuat 17-Jul-2026 untuk vertical ini, dengan urutan instalasi wajib
**CoA lokal dulu, baru modul PPOB** (lihat TSD §7.1). `custom_ppob_sla` dan
`custom_ppob_biller_digiflazz` menyusul di repo setelah tanggal itu — status pemasangannya di
`rnd_ppob` perlu diverifikasi ulang sebelum demo.

## 3. Pemetaan terhadap tiga fase arsitektur PPS

| Kapabilitas | Fase 1 | Fase 2 | Fase 3 | Status platform |
|---|:--:|:--:|:--:|---|
| Wallet mitra atomik + GL | ● inti | ● | ● | SUDAH ADA |
| **API wallet sinkron** (hold/commit/release/credit/balance) | ● inti | ○ internal | ○ | **PERLU DIBANGUN (G1)** |
| Ingest feed fulfillment H2H + join + marjin | ● | ◐ dual-run | — | SUDAH ADA |
| Penyesuaian bridge: feed POS → API wallet | ● | — | — | **PERLU DIBANGUN (G2)** |
| Top-up mitra via VA bank | ● | ● | ● | SUDAH ADA |
| Bucket deposit biller atomik + DP-100% | ○ bypass | ● inti | ● | SUDAH ADA |
| Dispatch, routing/failover, refund, reaper | ○ bypass | ● inti | ● | SUDAH ADA |
| Adapter biller riil | — | ● per biller | ● | Digiflazz SUDAH ADA; biller lain perlu dibangun |
| Gateway PPS drop-in untuk kanal | ◐ opsional | ● | ● | SUDAH ADA |
| Rollup faktur + Coretax | ● | ● | ● | SUDAH ADA |
| Komisi + PPh 23 | ◐ | ◐ | ● | SUDAH ADA |
| Target SLA + sampling paritas | ● | ● | ● | SUDAH ADA |
| Katalog/SKU sebagai master di Odoo | ○ mirror | ◐ | ● | SUDAH ADA (perlu migrasi master) |

● = aktif penuh · ◐ = sebagian · ○ = tidak dipakai / dilewati · — = tidak relevan

Konsekuensi penting yang harus dinyatakan ke stakeholder PPS: **satu-satunya pekerjaan build
yang menghalangi Fase 1 adalah API wallet sinkron (G1) dan penyesuaian bridge (G2).** Selebihnya
konfigurasi, migrasi saldo, dan pembuktian paritas.

## 4. Yang masih terbuka

Sembilan keputusan berikut belum tertutup dan menahan kepastian jadwal:

| # | Keputusan terbuka | Pemilik | Menahan apa |
|---|---|---|---|
| O1 | Mekanisme opening balance saldo mitra dari sistem warisan (format snapshot, tanggal, siapa memutus) | Klien | Fase 1 cutover |
| O2 | Kesediaan switcher H2H memanggil API wallet Odoo | Klien + vendor H2H | **Prasyarat mutlak Fase 1** |
| O3 | Panjang window dual-run saldo (N hari selisih nol) | Steering committee | Gerbang paritas Fase 1 |
| O4 | Fulfillment Fase 2: sinkron dengan timeout + fallback pending (rekomendasi) vs asinkron | Klien | Desain Fase 2 |
| O5 | Daftar biller riil beserta prioritas cutover-nya | Klien | Effort adapter Fase 2 |
| O6 | Sumber dan mekanisme saldo deposit awal per biller | Klien + vendor H2H | Cutover Fase 2 |
| O7 | Kesepakatan pemakaian `trx_ref` sebagai kunci idempotensi bersama selama dual-run | Klien | Keamanan dual-run |
| O8 | Lama mirror bridge + sistem warisan dipertahankan read-only untuk rollback & audit | Klien | Penutupan program |
| O9 | Persetujuan tertulis keamanan atas MD5 pada kontrak gateway PPS, plus keputusan atas gap G5 | Security klien | Go-live kanal |

## 5. Estimasi mandays PPS

Basis: Skenario B (brownfield) pada dokumen 05, dipecah mengikuti tiga fase program PPS.
**Effort PM dikosongkan; total adalah BA + DEV + QA saja.**

### 5.1 Ringkasan per fase

| Fase | PM | BA | DEV | QA | Subtotal | Kontingensi 15% | **Total** |
|---|:--:|---:|---:|---:|---:|---:|---:|
| Fase 1 — Wallet otoritatif + mirror | *diisi PM* | 14 | 40 | 20 | 74 | 11 | **85** |
| Fase 2 — Odoo menggantikan H2H | *diisi PM* | 12 | 52 | 26 | 90 | 14 | **104** |
| Fase 3 — Konsolidasi penuh | *diisi PM* | 6 | 22 | 10 | 38 | 6 | **44** |
| **Total tanpa PM** | | **32** | **114** | **56** | **202** | **31** | **233** |

### 5.2 Fase 1 — Wallet otoritatif + mirror (85)

| Pekerjaan | BA | DEV | QA |
|---|---:|---:|---:|
| API wallet sinkron: 5 endpoint, kolom saldo tertahan, penyesuaian ceiling, HMAC, idempotensi per langkah (G1) | 3 | 16 | 6 |
| Paket test wallet termasuk uji konkurensi dua kursor (G3, **dikerjakan sebelum G1 menyentuh skema**) | 1 | 8 | 6 |
| Penyesuaian bridge: feed POS → API wallet, feed H2H dipertahankan (G2) | 2 | 8 | 3 |
| Perkakas cutover saldo: ekstraksi snapshot, pemuatan, jurnal migrasi, laporan paritas harian | 3 | 8 | 3 |
| Konfigurasi master + COA + pemetaan akun + wallet per mitra | 5 | — | 2 |

### 5.3 Fase 2 — Odoo menggantikan H2H (104)

| Pekerjaan | BA | DEV | QA |
|---|---:|---:|---:|
| Adapter biller riil (asumsi 2 biller pertama @ 12) | 2 | 24 | 6 |
| Harness dual-run dispatch + laporan paritas (marjin, status, deposit, faktur, p95) | 3 | 10 | 8 |
| Perkakas cutover per irisan + monitoring + prosedur rollback | 3 | 8 | 5 |
| Saldo deposit awal per biller + rekonsiliasi ke saldo riil | 2 | 6 | 4 |
| Penguatan gateway kanal: anti-replay + kesegaran waktu (G5) | 1 | 4 | 3 |
| Konfigurasi provider, SKU map, target SLA per biller | 1 | — | — |

> Setiap biller tambahan di luar dua yang diasumsikan: **+8–14 mandays DEV, +3 QA**.

### 5.4 Fase 3 — Konsolidasi penuh (44)

| Pekerjaan | BA | DEV | QA |
|---|---:|---:|---:|
| Katalog/SKU menjadi master di Odoo (migrasi + proses pemeliharaan) | 3 | 8 | 4 |
| Top-up VA sebagai jalur utama mitra (bank tambahan bila perlu) | 1 | 6 | 3 |
| Komisi + PPh 23 aktif penuh + settlement rutin | 1 | 4 | 2 |
| Skrip konfigurasi tenant PPOB agar go-live reproducible (G6) | 1 | 4 | 1 |

## 6. Timeline PPS

```
  Fase 1 (≈ 8 minggu)          Fase 2 (≈ 10 minggu)           Fase 3 (≈ 5 minggu)
  |------------------|         |----------------------|        |-----------|
   konfigurasi                  adapter biller                  katalog master
   test wallet                  dual-run dispatch               top-up VA penuh
   API wallet + bridge          cutover per biller              komisi rutin
   opening balance              deposit opening                 skrip konfigurasi
   dual-run saldo
        |                              |                             |
   GERBANG PARITAS SALDO        GERBANG PARITAS PER IRISAN     penutupan program
   (selisih 0, N hari)          (recon break = 0 sebelum
                                 irisan berikutnya dibuka)
```

Total ≈ **23 minggu** kerja, **belum termasuk lamanya window gerbang paritas** yang ditentukan
keputusan O3 dan O8 — dua gerbang itu adalah waktu tunggu terkendali, bukan effort.

## 7. Risiko khusus PPS

| # | Risiko | Dampak | Mitigasi |
|---|---|---|---|
| RP-1 | Vendor H2H tidak bersedia/tidak mampu memanggil API wallet Odoo (O2) | **Fase 1 batal** dalam bentuk sekarang | Klarifikasi O2 sebelum pekerjaan build dimulai; alternatifnya lompat langsung ke pola switcher untuk irisan kecil |
| RP-2 | Snapshot saldo warisan tidak dapat direkonsiliasi | Cutover tertunda berminggu-minggu | Mulai ekstraksi & rekonsiliasi saldo di minggu pertama, bukan menjelang cutover |
| RP-3 | Wallet diubah skemanya tanpa jaring test | Regresi pada komponen paling money-critical | Test wallet dikerjakan **sebelum** API wallet menyentuh skema |
| RP-4 | Bridge existing berpola 2-feed yang sudah tidak sesuai desain | Salah asumsi saat integrasi | Penyesuaian G2 dijadwalkan di Fase 1, bukan ditunda |
| RP-5 | Digiflazz prepaid tanpa `inquiry()`/`status()` | Transaksi menggantung tidak dapat diresolusi otomatis | Minta webhook vendor; bila tidak ada, tulis prosedur ops manual dan sampaikan sebagai batasan |
| RP-6 | Kontrak gateway memaksa MD5 | Temuan keamanan saat audit | Persetujuan tertulis (O9) + kompensasi IP allowlist, rahasia per mitra, idempotensi DB |
| RP-7 | Addon PPOB dipakai bersama lintas basis data | Perubahan field dapat menjatuhkan basis data lain | Upgrade terkoordinasi ke seluruh basis data yang memasang modul sebelum restart |
| RP-8 | Volume puncak jam sibuk melampaui asumsi | Latensi melewati SLA saat cutover | Aktifkan sampling throughput sejak dual-run; bandingkan langsung dengan baseline historis |

## 8. Langkah berikutnya

1. Tutup **O2** (kesediaan H2H memanggil API wallet) — ini prasyarat mutlak; tidak ada
   pekerjaan Fase 1 yang layak dimulai sebelum jawabannya ada.
2. Tutup **O1** dan **O3**: format snapshot saldo dan panjang window paritas.
3. Verifikasi status pemasangan `custom_ppob_sla` dan `custom_ppob_biller_digiflazz` di
   `rnd_ppob`, lalu siapkan demo alur penuh dengan adapter mock.
4. Mulai paket test wallet (G3) — tidak bergantung pada keputusan mana pun dan menurunkan risiko
   terbesar dalam program.
5. Sepakati daftar biller Fase 2 (**O5**) supaya effort adapter dapat dikunci.
6. Ajukan **O9** ke tim keamanan klien bersama dokumen kontrol kompensasi.

---

*Kembali ke [`README.md`](README.md).*
