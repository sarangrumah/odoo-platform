# Architecture Document
## PPOB / Bill-Payment Switching di atas Odoo Platform

| | |
|---|---|
| **Dokumen** | 04 — Architecture |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Pembaca** | Arsitek, IT klien, security reviewer |
| **Konvensi** | **NOW** = terpasang hari ini · **TARGET** = direncanakan, belum dibangun. Mengikuti [`../../architecture.md`](../../architecture.md) — tidak ada yang berstatus TARGET boleh dijual sebagai sudah ada. |

---

## Contents

1. [Prinsip arsitektur](#1-prinsip-arsitektur)
2. [Tumpukan aplikasi (NOW)](#2-tumpukan-aplikasi-now)
3. [Tier modul](#3-tier-modul)
4. [Posisi Odoo dalam rantai PPOB](#4-posisi-odoo-dalam-rantai-ppob)
5. [Topologi deployment](#5-topologi-deployment)
6. [Isolasi multi-tenant](#6-isolasi-multi-tenant)
7. [Alur data](#7-alur-data)
8. [Integrasi eksternal](#8-integrasi-eksternal)
9. [Keamanan & kepatuhan](#9-keamanan--kepatuhan)
10. [Batasan yang harus dinyatakan ke klien](#10-batasan-yang-harus-dinyatakan-ke-klien)
11. [Keputusan arsitektur & alasannya](#11-keputusan-arsitektur--alasannya)

---

## 1. Prinsip arsitektur

| # | Prinsip | Konsekuensi konkret |
|---|---|---|
| P1 | **Sub-ledger dan buku besar tidak boleh berpisah** | Setiap mutasi saldo menulis jurnal pada transaksi basis data yang sama; tidak ada job "posting menyusul" |
| P2 | **Idempotensi milik basis data** | Constraint unik, bukan pemeriksaan aplikasi yang bisa balapan |
| P3 | **Protokol biller tidak bocor ke mesin transaksi** | Semua kekhususan biller berada di adapter |
| P4 | **Ketidakpastian bukan kegagalan** | Tri-state `ok`; refund hanya atas kegagalan terkonfirmasi |
| P5 | **Kanal cukup mengganti alamat** | Gateway meniru kontrak switcher lama sehingga migrasi kanal berbiaya nol |
| P6 | **Data yang tidak dipahami disimpan, bukan dibuang** | Antrean lewatan + backfill |
| P7 | **Perpindahan otoritas selalu bertahap dan reversible** | Dual-run, gerbang paritas, cutover per irisan |

## 2. Tumpukan aplikasi (NOW)

```
                    Mitra / outlet · kanal penjualan · bank · biller
                                        |
                        caddy (443) | nginx (18443)     <- TLS
                                        |
                                   odoo (8069)
                                        |
     +----------------+----------------+-----------------+------------------+
     |                |                |                 |                  |
  postgres        redis (nonce)   custom_adapter_    queue_job         minio
  (15432)         (16379)         framework          (in-process)      (backup)
  semua tenant    anti-replay     kredensial per     eksekusi async    objek
                                  tenant + call log
```

Catatan penting: **Redis dipakai sebagai penyimpan nonce dan cache, bukan broker job.**
Eksekusi asinkron memakai `queue_job` di dalam proses Odoo — dan hanya **satu** container yang
boleh memuat `queue_job`, karena dua container yang sama-sama memuatnya akan saling mengunci
pada pemilihan runner sehingga seluruh job berhenti.

## 3. Tier modul

| Tier | Modul | Boleh bergantung pada |
|---|---|---|
| 0 — Platform | `custom_core`, `custom_adapter_framework`, `custom_accounting_*`, `custom_pph_witholding`, `custom_coretax_bupot` | — |
| 1 — Fondasi PPOB | `custom_ppob_core` | Tier 0 |
| 2 — Sub-ledger | `custom_ppob_wallet`, `custom_ppob_provider` | Tier 0–1 |
| 3 — Mesin | `custom_ppob_sale` | Tier 0–2 |
| 4a — Integrasi keluar | `custom_ppob_biller_digiflazz`, `custom_ppob_oracle_bridge` | Tier 0–3 |
| 4b — Integrasi masuk | `custom_ppob_pps_gateway`, `custom_ppob_va`, `custom_ppob_eraspace_bridge` | Tier 0–3 |
| 5 — Finance & observabilitas | `custom_ppob_rollup`, `custom_ppob_commission`, `custom_ppob_sla` | Tier 0–3 |

Aturan yang menjaga arsitektur tetap dapat dirawat:

- Tier 2 **tidak pernah** memanggil adapter; tier 4a **tidak pernah** menulis saldo langsung.
- Modul integrasi masuk hanya berbicara ke tier 3 (mesin), tidak ke sub-ledger.
- Modul finance membaca hasil, tidak mengubah jalannya transaksi.

## 4. Posisi Odoo dalam rantai PPOB

Ada tiga posisi arsitektural yang berbeda, dan **klien harus memilih secara sadar** karena
konsekuensi operasionalnya jauh berbeda:

```
  A. MIRROR (Odoo di luar jalur kritis)
     mitra -> switcher -> biller
                 |
                 +--feed--> Odoo (pembukuan, pajak, rekonsiliasi)
     Risiko rendah. Odoo tidak pernah menghentikan penjualan.
     Kelemahan: saldo mitra bukan otoritas Odoo; selisih diselesaikan belakangan.

  B. WALLET AUTHORITATIVE (Odoo di jalur kritis, sebagian)
     mitra -> switcher --sinkron--> Odoo wallet (hold/commit/release)
                 |
                 +--> biller
                 +--feed--> Odoo (COGS, deposit, join, marjin)
     Saldo mitra otoritatif di Odoo; eksekusi biller tetap milik switcher.
     Prasyarat: API wallet sinkron (belum ada -- G1).

  C. SWITCHER (Odoo di jalur kritis, penuh)
     mitra -> Odoo -> biller
     Odoo memilih biller, memegang deposit, menentukan status, dan me-refund.
     Seluruh kapabilitasnya sudah ada di suite; yang menentukan adalah kesiapan
     operasional dan adapter biller riil per biller.
```

Kapabilitas untuk ketiga posisi **sudah tersedia (NOW)** kecuali API wallet sinkron pada posisi
B. Perpindahan A → B → C dijalankan dengan pola strangler-fig pada §7.5.

## 5. Topologi deployment

| Komponen | NOW | Catatan |
|---|---|---|
| Odoo web/worker | NOW | Satu container melayani seluruh tenant; endpoint PPOB adalah rute HTTP biasa |
| Container mgmt terpisah | NOW | Hanya satu yang boleh memuat `queue_job` |
| PostgreSQL | NOW | Satu cluster, satu basis data per tenant |
| Redis | NOW | Nonce anti-replay + cache |
| Reverse proxy | NOW | TLS; hanya proxy yang publik |
| Observability (Prometheus/Grafana/Loki) | overlay | Dipasang lewat overlay compose |
| Warm standby / replikasi otomatis | **TARGET** | Belum ada; DR bergantung pada backup terjadwal |
| Autoscaling worker | **TARGET** | Kapasitas ditambah manual |

Implikasi yang harus disampaikan ke klien PPOB: karena tidak ada standby panas, **RTO
ditentukan oleh waktu pemulihan dari backup**. Untuk sistem yang memegang saldo mitra, angka
ini harus disepakati tertulis sebelum go-live.

## 6. Isolasi multi-tenant

- Satu basis data per tenant; tidak ada tabel PPOB yang dibagi antar tenant.
- Kredensial biller/bank tersimpan per tenant (`custom.adapter.config` atau parameter sistem),
  sehingga tenant A tidak pernah memakai rahasia tenant B.
- Addon dipasang bersama di seluruh tenant. **Konsekuensi operasional yang keras:** menambah
  field pada modul PPOB lalu me-restart tanpa `-u` pada setiap basis data yang memasangnya akan
  menjatuhkan basis data yang tertinggal. Enumerasi target upgrade harus dari
  `ir_module_module` di setiap basis data, bukan dari pola nama basis data.

## 7. Alur data

### 7.1 Penjualan (posisi C — Odoo sebagai switcher)

```
  kanal --(sign)--> /pps/sell
                       |
                 auth: kredensial + IP + tanda tangan
                       |
                 idempotensi: (mitra, notrx) sudah ada? -> kembalikan hasil asli
                       |
                 buat transaksi -> dispatch
                       |
        +--------------+---------------+
        |                              |
  wallet._atomic_debit          bucket._atomic_debit
  Dr utang saldo mitra          Dr harga pokok
    Cr pendapatan                 Cr deposit biller
        |                              |
        +--------------+---------------+
                       |
                 adapter.pay()  (diukur latensinya)
                       |
       sukses ---------+--------- gagal ---------- belum selesai
          |                          |                    |
      status sukses           refund keduanya        biarkan; reaper
      token ke kanal          status gagal           tanya status berkala
```

### 7.2 Top-up mitra

```
  mitra transfer -> bank -> /api/ppob/va/<bank>/payment
                              |
                        HMAC + skew + nonce + IP
                              |
                        UNIQUE(bank_ref) -> duplikat? kembalikan ack asli
                              |
                        buat top-up -> wallet._atomic_credit
                        Dr transit bank / Cr utang saldo mitra
```

Bila bank tidak mengirim callback, jalur cadangan adalah rekonsiliasi rekening koran melalui
aturan rekonsiliasi yang mencocokkan baris statement ke nomor VA.

### 7.3 Top-up deposit biller

```
  ops -> wizard top-up (bruto, diskon, dibayar)
            |
      split DPP/PPN sesuai metode Coretax provider
            |
      invoice DP (+ pelunasan bila timing menghendaki)
            |
      bucket._atomic_credit_from_move
      Dr deposit biller + Dr PPN masukan / Cr kas atau utang vendor
```

### 7.4 Tutup hari

```
  cron rollup harian
      -> kumpulkan transaksi sukses per mitra
      -> sale.order + faktur ringkas (PPN sesuai mode kelas)
      -> tandai transaksi agar tidak terhitung dua kali
      -> jurnal ringkasan ditandai non-GL (dikecualikan dari laporan keuangan)

  akrual komisi -> potong PPh 23 -> settlement + bukti potong
  sampling throughput per jam -> bandingkan terhadap target SLA
```

### 7.5 Perpindahan otoritas (strangler-fig)

```
  [A mirror] --cutover saldo--> [B wallet authoritative] --canary--> [C switcher]
        |                              |                                  |
   feed masuk saja            API wallet sinkron               dispatch + deposit
                                       |                        + status + refund
                              gerbang paritas saldo         gerbang paritas per irisan
                              (selisih 0, N hari)           (marjin, status, deposit,
                                                             faktur, p95 latensi)
```

Rollback pada tiap panah: arahkan kembali irisan yang bersangkutan ke pemilik lama. Feed mirror
dipertahankan selama seluruh migrasi supaya tidak ada data yang hilang saat rollback.

## 8. Integrasi eksternal

| Sistem | Arah | Protokol | Autentikasi | Status |
|---|---|---|---|---|
| Kanal penjualan / POS | masuk | HTTP form + JSON, kontrak switcher | MD5 per endpoint + IP allowlist | NOW |
| Bank (VA) | masuk | HTTP JSON | HMAC-SHA256 + skew + nonce + IP | NOW |
| Switcher lama (feed) | masuk | HTTP JSON | HMAC-SHA256 + nonce + IP | NOW |
| Switcher lama (API wallet) | masuk | HTTP JSON | HMAC-SHA256 | **TARGET (G1)** |
| Biller Digiflazz | keluar | HTTP JSON | MD5 vendor + `ref_id` | NOW |
| Biller lain | keluar | per vendor | per vendor | **per biller, perlu dibangun** |
| Oracle EVShop (legacy) | dua arah | stored procedure + polling tabel | kredensial DB | NOW (opsional) |
| Coretax / e-Faktur | keluar | ekspor | — | NOW lewat modul platform |
| Kanal notifikasi ops | keluar | — | — | **TARGET (BR-OP-07)** |

## 9. Keamanan & kepatuhan

| Aspek | Penerapan |
|---|---|
| Endpoint uang | Bertanda tangan + allowlist IP; anti-replay pada VA dan feed |
| Gateway kanal | MD5 sesuai kontrak vendor, terisolasi di satu berkas; **anti-replay belum ada (G5)** |
| Rahasia | Parameter sistem / konfigurasi adapter per tenant; tidak pernah di record bisnis |
| Data pribadi | Nomor pelanggan disimpan; pertimbangkan masking pada feed dan log sesuai kebijakan PDP klien |
| Jejak audit | Perubahan status transaksi, referensi provider, dan kode galat terekam |
| Pemisahan tugas | Empat grup akses; pengubah tier harga sebaiknya bukan pelaksana refund manual |
| Kepatuhan pajak | PPN PMK-63 per kelas, faktur ringkas harian, PPh 23 + bukti potong |
| Backup | Dump terjadwal harian dengan rotasi; **tidak ada standby panas** |

## 10. Batasan yang harus dinyatakan ke klien

1. **MD5 pada gateway kanal** adalah warisan kontrak vendor, bukan pilihan platform. Kompensasi
   berupa IP allowlist, rahasia per mitra, dan idempotensi basis data — dan harus disetujui
   tertulis oleh keamanan klien.
2. **API wallet sinkron belum ada.** Sampai dibangun, saldo mitra tidak dapat menjadi otoritas
   Odoo bagi switcher eksternal.
3. **Empat modul tanpa test otomatis**, termasuk wallet yang paling money-critical.
4. **Adapter biller riil baru satu** (Digiflazz), dan jalur prepaid-nya tidak menyediakan
   inquiry maupun status read-only.
5. **PPN diakui pada faktur ringkas harian**, bukan per transaksi.
6. **Target SLA bersifat deklaratif** — tidak ada throttling otomatis saat lonjakan.
7. **Tidak ada standby panas**; RTO ditentukan waktu pemulihan backup.
8. **Addon dipasang bersama antar tenant**; setiap perubahan skema menuntut upgrade terkoordinasi
   di seluruh basis data.

## 11. Keputusan arsitektur & alasannya

| # | Keputusan | Alternatif yang ditolak | Alasan |
|---|---|---|---|
| D1 | Saldo bergerak lewat primitif atomik row-locked di dalam transaksi Odoo | Antrean/eventual consistency | Saldo mitra adalah uang; konsistensi akhir tidak dapat diterima saat mitra menjual detik itu juga |
| D2 | Idempotensi lewat constraint unik basis data | Pemeriksaan "sudah ada?" di aplikasi | Pemeriksaan aplikasi kalah balapan; constraint tidak |
| D3 | `ok` tri-state pada hasil adapter | Boolean sukses/gagal | Boolean memaksa "belum selesai" dibaca sebagai gagal → refund atas transaksi yang kemudian sukses |
| D4 | Jalur pembayaran tanpa retry otomatis | Retry transport standar | Retry di jalur pay = risiko menjual dua kali |
| D5 | Reaper menanyakan status sebelum refund | Refund otomatis setelah timeout | Refund buta merugikan salah satu pihak pada setiap provider asinkron |
| D6 | PPN diakui di faktur ringkas harian | Posting PPN per transaksi | Volume tinggi × marjin tipis; PMK-63 berbasis marjin lebih tepat diringkas per mitra per hari |
| D7 | Adapter sebagai registry, bukan konfigurasi generik | Satu adapter HTTP parametrik | Setiap biller punya kekhususan tanda tangan, kode galat, dan semantik status |
| D8 | Gateway meniru kontrak switcher lama | API baru yang lebih bersih | Migrasi kanal menjadi "ganti base URL", bukan proyek perubahan aplikasi mitra |
| D9 | MD5 diisolasi pada satu berkas dan dilarang diimpor | Menerima MD5 sebagai konvensi umum | Kontrak vendor tidak boleh menurunkan standar kriptografi seluruh platform |
| D10 | Akun diresolusi lewat peran, bukan kode akun | Kode akun literal | COA berbeda per klien; peran membuat modul portabel |
| D11 | Data masuk yang tak dikenali disimpan di antrean tinjauan | Tolak dan buang | Data uang yang hilang tidak dapat direkonstruksi; antrean membuat kesalahan pemetaan dapat diperbaiki |
| D12 | Perpindahan otoritas bertahap dengan gerbang paritas | Big-bang cutover | Kesalahan saldo pada cutover langsung berdampak ke ribuan mitra |

---

*Dokumen berikutnya: [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md).*
