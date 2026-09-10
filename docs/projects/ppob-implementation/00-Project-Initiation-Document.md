# Project Initiation Document (PID)
## Implementasi PPOB / Bill-Payment Switching di atas Odoo 19

| | |
|---|---|
| **Dokumen** | 00 — Project Initiation Document |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Status** | Untuk persetujuan sponsor |
| **Pemilik** | Platform Team · Product Owner PPOB |
| **Basis teknis** | `addons/verticals/custom_ppob_*` (12 modul, Odoo 19) |
| **Addendum klien** | [`06-Addendum-PPS.md`](06-Addendum-PPS.md) — Erajaya VAS / Eraspace |

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

Dokumen ini menetapkan mandat proyek implementasi **PPOB (Payment Point Online Bank) /
bill-payment & top-up** di atas Odoo 19: apa yang dikerjakan, apa yang tidak, siapa memutuskan
apa, kapan selesai, dan atas dasar apa proyek dinyatakan diterima.

PID ini **generik** — dapat dipakai untuk klien PPOB mana pun (aggregator, retailer dengan
jaringan mitra, penyelenggara VAS). Satu addendum klien tersedia untuk engagement **PPS
(Erajaya VAS / Eraspace)** pada dokumen 06.

Yang membedakan proyek PPOB dari implementasi Odoo pada umumnya: **Odoo berada di jalur uang
yang sinkron**. Saldo mitra didebit sebelum barang digital dikirim, dan setiap kegagalan
teknis adalah selisih rupiah — bukan sekadar data salah. Seluruh tata kelola di bawah dibentuk
oleh kenyataan itu.

## 2. Latar belakang

Model bisnis PPOB berjalan sebagai berikut:

- **Mitra/outlet prepaid** melakukan top-up saldo lebih dulu, lalu berjualan (pulsa, paket
  data, token PLN, tagihan PLN/PDAM/BPJS, e-wallet, voucher game).
- **Switcher / H2H (host-to-host)** mendistribusikan transaksi ke **biller** dan memegang
  **deposit** per biller.
- Marjin penyelenggara = harga jual ke mitra − harga modal biller, dengan PPN dihitung atas
  **nilai lain / marjin** sesuai PMK-63/2022, bukan atas nilai bruto transaksi.

Umumnya kapabilitas ini tersebar: saldo mitra di satu aplikasi warisan, eksekusi biller di
switcher pihak ketiga, dan akuntansi menyusul belakangan lewat rekonsiliasi manual. Akibatnya:
saldo mitra dan buku besar tidak pernah sama pada hari yang sama, marjin per produk tidak
terlihat, dan pelaporan PPN bergantung rekap manual.

Platform ini sudah memiliki **suite PPOB native berisi 12 modul** yang mencakup rantai penuh —
wallet mitra atomik, deposit biller, mesin transaksi, adapter biller, top-up VA bank, komisi &
PPh, rollup faktur harian, sampai gateway H2H masuk. Proyek implementasi berarti
**mengonfigurasi, mengintegrasikan, memigrasi, dan mengoperasikan** kapabilitas tersebut —
bukan membangunnya dari nol (lihat Skenario B pada dokumen 05).

## 3. Tujuan proyek

| # | Tujuan | Ukuran |
|---|---|---|
| T1 | Saldo mitra menjadi **otoritatif di Odoo** dan selalu berpasangan dengan buku besar | Selisih saldo wallet vs akun liability = 0 setiap hari |
| T2 | Setiap transaksi PPOB **tidak pernah dijual dua kali** dan tidak pernah menghilang | 0 transaksi ganda; 0 transaksi menggantung > SLA tanpa resolusi |
| T3 | Marjin per transaksi/produk/mitra terlihat **tanpa rekap manual** | Laporan marjin tersedia D+1 dari sistem |
| T4 | PPN PMK-63 dan PPh 23 komisi ter-posting otomatis dan siap Coretax | Faktur ringkas per mitra terbit otomatis harian |
| T5 | Top-up mitra masuk sendiri dari bank tanpa entri manual | ≥ 95% top-up terkredit otomatis via VA/rekonsiliasi |
| T6 | Kegagalan biller **mengembalikan saldo mitra secara otomatis dan berpasangan GL** | 100% transaksi gagal ter-refund dengan jurnal balik |

## 4. Ruang lingkup

### 4.1 In-scope

| Area | Isi |
|---|---|
| Master data | Kelas produk, katalog produk PPOB, tier harga per mitra, mitra & provider sebagai partner, pemetaan akun (role → akun) |
| Wallet mitra | Saldo prepaid per mitra per kelas, debit/kredit atomik row-locked, credit limit, freeze, buku pembantu berpasangan GL |
| Deposit biller | Bucket per provider (bulky / fixed-denom), drawdown atomik, low-water-mark, top-up DP-100% dengan split DPP/PPN |
| Mesin transaksi | State machine `pending → in_progress → success/failed/timeout/refunded`, idempotensi per mitra, routing & failover provider, reaper transaksi menggantung, refund berpasangan |
| Integrasi biller | Registry adapter (`@register_adapter`), adapter mock untuk QA, adapter Digiflazz, adapter HTTP generik, kredensial per tenant |
| Kanal masuk | Gateway H2H masuk (kontrak PPS/EVShop drop-in), ingest mirror POS/H2H, callback ke kanal |
| Top-up mitra | Virtual Account bank (callback inquiry + payment, HMAC), rekonsiliasi rekening koran |
| Keuangan & pajak | Jurnal wallet/deposit/COGS/revenue, rollup faktur harian per mitra, PPN PMK-63, komisi dua arah + PPh 23, bupot |
| Operasional | Target SLA & sampling throughput per jam, log panggilan adapter, antrean data yang dilewati (skipped queue), backfill |
| Non-fungsional | Konkurensi, idempotensi, keamanan endpoint, audit trail, kapasitas |

### 4.2 Out-of-scope

Kecuali dinyatakan lain dalam SOW per klien:

- Aplikasi mitra/outlet (mobile/web) — tetap milik klien; Odoo menyediakan API.
- Negosiasi dan onboarding komersial ke biller.
- Lisensi/legal penyelenggaraan PPOB (izin, kepatuhan BI/OJK).
- Perangkat keras, jaringan cabang, dan konektivitas mitra.
- Migrasi transaksi historis di luar saldo pembuka dan periode rekonsiliasi yang disepakati.
- Aplikasi warisan yang digantikan (mis. pemegang saldo lama) — dimatikan oleh klien.

### 4.3 Gap yang sudah diketahui dan masuk scope

Verifikasi basis kode pada 2026-08-11 menemukan hal-hal berikut **belum ada**. Semuanya
dinyatakan terbuka, masuk lingkup, dan dibiayai eksplisit di dokumen 05 — bukan diklaim sudah
tersedia:

| # | Gap | Konsekuensi |
|---|---|---|
| G1 | **API wallet sinkron** (`hold` / `commit` / `release` / `credit` / `balance`) belum ada — wallet hanya punya primitif internal `_atomic_debit`/`_atomic_credit`, tanpa controller | Switcher eksternal belum bisa menjadikan Odoo pemegang saldo otoritatif |
| G2 | `custom_ppob_eraspace_bridge` masih berpola **2-feed (POS + H2H)** dari konsep lama; desain sekarang menuntut feed POS diganti API wallet | Perlu penyesuaian sebelum fase wallet-authoritative |
| G3 | **Tidak ada test** pada `custom_ppob_core`, `custom_ppob_wallet`, `custom_ppob_commission`, `custom_ppob_rollup` | Justru wallet yang paling money-critical belum berpagar test |
| G4 | Adapter biller riil baru **Digiflazz** (+ mock); prepaid Digiflazz **tidak punya `inquiry()` maupun `status()`** (keduanya `NotImplementedError`) | Reaper tidak dapat meresolusi otomatis transaksi prepaid yang menggantung di jalur itu |
| G5 | Gateway PPS mendokumentasikan "replay guard + timestamp freshness", tetapi controller hanya menegakkan **IP allowlist + tanda tangan MD5 + idempotensi DB**; field `max_clock_skew_s` tidak pernah dibaca | Klaim kontrol keamanan harus dikoreksi atau kontrolnya dibangun |
| G6 | Tidak ada skrip konfigurasi tenant PPOB di `scripts/tenants/` | Seluruh konfigurasi go-live masih manual dan tidak reproducible |

## 5. Deliverable

| # | Deliverable | Bentuk |
|---|---|---|
| D1 | Dokumen kebutuhan bisnis tervalidasi | BRD (dokumen 01) ditandatangani |
| D2 | Spesifikasi fungsional & desain teknis | FSD + TSD (dokumen 02, 03) |
| D3 | Sistem PPOB terkonfigurasi di lingkungan non-produksi | Tenant SIT terisi master data & provider |
| D4 | Integrasi biller & kanal aktif | Adapter per biller + gateway kanal, lulus uji kontrak |
| D5 | Top-up VA bank aktif | Endpoint callback + rekonsiliasi rekening koran |
| D6 | Paket akuntansi & pajak | COA + mapping role, rollup faktur, PPN PMK-63, PPh 23 |
| D7 | Hasil SIT & UAT | Berita acara pengujian + daftar defect tertutup |
| D8 | Migrasi saldo & data master | Berita acara saldo pembuka mitra & deposit biller |
| D9 | Runbook operasional | Prosedur harian, monitoring, eskalasi, rollback |
| D10 | Pelatihan | Materi + sesi untuk ops, finance, IT |
| D11 | Sistem produksi + hypercare | Go-live bertahap dan periode pendampingan |

## 6. Pendekatan pelaksanaan

Pendekatan wajib: **strangler-fig dengan gerbang paritas** — tidak pernah *big-bang*.

```
  Fit-gap  ->  Konfigurasi  ->  Dual-run bayangan  ->  Gerbang paritas  ->  Canary
     |             |                   |                     |                |
  BRD/FSD     master data,      sistem lama tetap      selisih 0 selama    1 biller /
  disetujui   provider, COA     otoritatif; Odoo        N hari berturut    1 produk /
                                menghitung paralel                        1 segmen mitra
                                                                              |
                                                        Perluasan irisan  <---+
                                                                              |
                                                        Sistem lama mati  <---+
```

Prinsip yang tidak dapat ditawar:

1. **Uang tidak pernah dipindahkan dua kali.** Setiap jalur masuk idempoten pada tingkat
   basis data (`UNIQUE`), bukan pada tingkat aplikasi.
2. **Tidak pernah refund buta.** Transaksi menggantung diresolusi dengan menanyakan status ke
   biller; bila biller menjawab "masih diproses", transaksi dibiarkan.
3. **Setiap pergerakan sub-ledger berpasangan jurnal** pada transaksi basis data yang sama.
4. **Rollback selalu tersedia** pada setiap irisan cutover selama window yang disepakati.
5. **Paritas dibuktikan dengan angka**, bukan dengan opini: marjin, status akhir, saldo
   deposit, dan faktur ringkas harus cocok.

## 7. Organisasi & tata kelola

### 7.1 Peran

| Peran | Pihak | Tanggung jawab |
|---|---|---|
| Sponsor | Klien | Mandat, anggaran, keputusan go/no-go |
| Product Owner PPOB | Klien | Prioritas kebutuhan, penerimaan fungsional |
| Finance Lead | Klien | COA, kebijakan PPN/PPh, penerimaan akuntansi |
| Ops Lead | Klien | Prosedur harian, penanganan eksepsi, penerimaan operasional |
| IT / Integrasi | Klien | Konektivitas biller, bank, kanal; kredensial; jaringan |
| Project Manager | Pelaksana | Jadwal, risiko, komunikasi, change request |
| Business Analyst | Pelaksana | BRD/FSD, fit-gap, konfigurasi, UAT |
| Developer | Pelaksana | Build gap, adapter, integrasi, migrasi |
| QA | Pelaksana | Rencana uji, SIT, uji konkurensi & paritas |
| Security reviewer | Pelaksana | Tinjauan endpoint, kredensial, dan jejak audit |

### 7.2 Forum

| Forum | Frekuensi | Peserta | Keluaran |
|---|---|---|---|
| Daily stand-up | Harian (fase build) | Tim pelaksana | Hambatan harian |
| Weekly progress | Mingguan | PM, PO, Ops, Finance | Status, risiko, keputusan |
| Steering committee | Dwi-mingguan | Sponsor + PO + PM | Keputusan lingkup & anggaran |
| **Parity review** | Harian selama dual-run | QA, Finance, Ops, PM | Buka/tutup gerbang cutover |
| Hypercare war-room | Harian, 2 minggu pasca go-live | Semua | Insiden & resolusi |

### 7.3 Pengelolaan perubahan

Perubahan lingkup diajukan tertulis (dampak effort, jadwal, risiko), disetujui steering
committee. Perubahan yang menyentuh **jalur uang** (wallet, deposit, refund, pajak) selalu
naik ke steering committee — tidak boleh diselesaikan di tingkat tim.

## 8. Milestone & jadwal

Basis: Skenario B (brownfield, reuse suite) — ≈ **13 minggu**. Greenfield ≈ 26 minggu
(dokumen 05).

| # | Milestone | Minggu | Kriteria selesai |
|---|---|---:|---|
| M1 | Kickoff & fit-gap selesai | 2 | BRD disetujui, daftar gap dikunci |
| M2 | Desain & rancangan cutover disetujui | 3 | FSD/TSD + rencana migrasi saldo |
| M3 | Konfigurasi dasar selesai | 5 | COA, kelas, katalog, tier, provider, SKU map terisi |
| M4 | Gap build selesai | 8 | API wallet, penyesuaian bridge, test wallet |
| M5 | Integrasi biller & bank aktif di SIT | 9 | Adapter + VA callback lulus uji kontrak |
| M6 | SIT selesai | 10 | Semua acceptance test lulus, defect kritis 0 |
| M7 | Migrasi saldo & UAT selesai | 11 | Saldo pembuka cocok, UAT diterima |
| M8 | **Gerbang paritas dual-run lulus** | 12 | Selisih 0 selama N hari berturut |
| M9 | Go-live canary → penuh | 12–13 | Irisan pertama produksi tanpa recon break |
| M10 | Serah terima | 13 | Hypercare selesai, dokumen & runbook diserahkan |

## 9. Effort & sumber daya

> **Effort PM sengaja dikosongkan** — diisi PM sesuai model tata kelola yang dipakai. Angka di
> bawah adalah **BA + DEV + QA saja** dan harus dijumlahkan ulang setelah alokasi PM masuk.

| Peran | Greenfield | Brownfield |
|---|---:|---:|
| PM | *diisi PM* | *diisi PM* |
| BA | 76 | 47 |
| DEV | 284 | 108 |
| QA | 108 | 56 |
| **Total tanpa PM (termasuk kontingensi 15%)** | **≈ 538** | **≈ 243** |
| Durasi | ≈ 26 minggu | ≈ 13 minggu |

Rincian per fase, asumsi, dan faktor pengubah ada di dokumen 05.

## 10. Kriteria sukses

| # | Kriteria | Target |
|---|---|---|
| S1 | Selisih saldo wallet vs GL liability | 0, diperiksa harian |
| S2 | Transaksi terjual ganda | 0 |
| S3 | Transaksi menggantung tak terselesaikan > SLA | 0 |
| S4 | Transaksi gagal yang tidak ter-refund | 0 |
| S5 | Faktur ringkas harian terbit otomatis | 100% hari kerja |
| S6 | Top-up mitra terkredit otomatis | ≥ 95% |
| S7 | p95 latensi jalur jual | ≤ target SLA yang disepakati |
| S8 | Recon break pasca-cutover per irisan | 0 sebelum irisan berikut dibuka |

## 11. Asumsi, batasan, dan ketergantungan

### Asumsi

- Klien menyediakan spesifikasi API biller/switcher/bank beserta lingkungan sandbox.
- Kebijakan PPN (mode per kelas produk) diputuskan Finance Lead sebelum M3.
- Katalog produk dan harga modal tersedia dalam format yang dapat diimpor.
- Volume dasar: hingga puluhan ribu transaksi per hari (lihat batasan kapasitas di dokumen 04).

### Batasan yang harus diketahui sponsor

- **Gateway PPS memakai MD5** karena kontrak vendor mensyaratkannya. MD5 lemah secara
  kriptografis; kompensasinya IP allowlist + rahasia per mitra + idempotensi basis data.
  Kontrol ini harus disetujui secara tertulis oleh keamanan klien (lihat G5).
- **Odoo tidak menjadi otoritas status biller** sampai fase Odoo-as-switcher selesai; sebelum
  itu status akhir berasal dari switcher.
- PPN diakui pada **faktur ringkas harian**, bukan per transaksi. Ini keputusan desain yang
  disengaja dan harus diterima Finance.
- Adapter biller riil di luar Digiflazz **belum ada** dan dihitung per biller.

### Ketergantungan

| # | Ketergantungan | Pemilik | Dibutuhkan sebelum |
|---|---|---|---|
| K1 | Kredensial + sandbox biller | Klien / biller | M5 |
| K2 | Kontrak & kredensial VA bank | Klien / bank | M5 |
| K3 | Snapshot saldo mitra dari sistem lama | Klien | M7 |
| K4 | Snapshot deposit biller | Klien / switcher | M7 |
| K5 | Persetujuan kebijakan pajak | Finance Lead | M3 |
| K6 | Allowlist IP & jalur jaringan | IT klien | M5 |

## 12. Risiko tingkat proyek

| # | Risiko | Dampak | Mitigasi |
|---|---|---|---|
| R1 | Saldo mitra tidak cocok saat cutover | Kritis — mitra tidak bisa berjualan | Dual-run saldo + gerbang paritas + window rollback |
| R2 | Transaksi terjual dua kali saat retry kanal | Kritis — kerugian langsung | Idempotensi `UNIQUE(mitra_id, idempotency_key)`; jalur pay tanpa retry otomatis |
| R3 | Biller tidak menyediakan `status()` | Tinggi — transaksi menggantung manual | Wajibkan endpoint status/webhook di kontrak biller; bila tidak, siapkan prosedur ops manual (lihat G4) |
| R4 | Spesifikasi biller/bank berubah di tengah jalan | Tinggi | Adapter terisolasi per biller; kontrak versi; uji kontrak otomatis |
| R5 | Wallet tanpa test regresi | Tinggi | Bangun paket test wallet di awal fase build (G3), bukan di akhir |
| R6 | Volume puncak melampaui asumsi | Sedang | Sampling throughput + target SLA aktif sejak SIT; uji beban sebelum go-live |
| R7 | Keputusan pajak tertunda | Sedang | Keputusan PPN dijadikan gerbang M3 |
| R8 | Kredensial biller bocor | Tinggi | Rahasia via `ir.config_parameter`/adapter config per tenant, tidak pernah di record bisnis |

## 13. Kriteria penerimaan & serah terima

Proyek dinyatakan diterima bila seluruh butir berikut terpenuhi:

1. Semua acceptance test pada FSD §10 lulus di lingkungan produksi klien.
2. Seluruh kriteria sukses §10 tercapai dan diukur selama minimal periode hypercare.
3. Gerbang paritas dual-run lulus dan berita acara cutover ditandatangani.
4. Berita acara saldo pembuka mitra dan deposit biller ditandatangani Finance.
5. Runbook operasional, prosedur eskalasi, dan prosedur rollback diserahkan.
6. Pelatihan ops, finance, dan IT selesai dengan daftar hadir.
7. Daftar defect terbuka hanya berisi severity rendah dengan rencana penyelesaian disepakati.
8. Gap G1–G6 berstatus selesai, atau tercatat sebagai backlog yang diterima sponsor secara
   tertulis.

---

*Dokumen berikutnya: [`01-BRD.md`](01-BRD.md) — kebutuhan bisnis bernomor.*
