# Architecture Document
## Warehouse Management System di atas Odoo Platform

| | |
|---|---|
| **Dokumen** | Architecture — WMS Implementation (generic) |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Induk** | [`../../architecture.md`](../../architecture.md) — arsitektur platform; dokumen ini adalah irisan WMS-nya |
| **Rujukan** | [`03-TSD.md`](03-TSD.md) |

**Penanda status.** Dokumen ini memakai konvensi yang sama dengan arsitektur platform:
**NOW** = terpasang dan berjalan hari ini · **TARGET** = direncanakan, **belum dibangun**.
Tidak ada yang berstatus TARGET boleh dijual sebagai sudah ada.

---

## Contents

1. [Prinsip arsitektur](#1-prinsip-arsitektur)
2. [Tumpukan aplikasi (NOW)](#2-tumpukan-aplikasi-now)
3. [Tier modul](#3-tier-modul)
4. [Topologi deployment](#4-topologi-deployment)
5. [Isolasi multi-tenant](#5-isolasi-multi-tenant)
6. [Alur data](#6-alur-data)
7. [Integrasi eksternal](#7-integrasi-eksternal)
8. [Keamanan & kepatuhan](#8-keamanan--kepatuhan)
9. [Batasan yang harus dinyatakan ke klien](#9-batasan-yang-harus-dinyatakan-ke-klien)
10. [Keputusan arsitektur & alasannya](#10-keputusan-arsitektur--alasannya)

---

## 1. Prinsip arsitektur

| # | Prinsip | Konsekuensi praktis |
|---|---|---|
| A1 | **WMS adalah perluasan `stock`, bukan sistem terpisah.** | Semua pergerakan tetap melewati `stock.move` / `stock.quant`. Tidak ada ledger stok kedua yang harus direkonsiliasi dengan akuntansi |
| A2 | **Mesin keputusan memberi saran; manusia memegang kendali.** | Saran putaway berskor dan dapat ditimpa; penimpaan tercatat sehingga kualitas mesin terukur |
| A3 | **Kebijakan tinggal di data, bukan di kode.** | Strategi, aturan, tipe penyimpanan, aturan transfer, dan rencana hitung semuanya adalah record — dapat diubah tanpa rilis |
| A4 | **Kegagalan sistem luar tidak boleh menggagalkan operasi gudang.** | Integrasi memakai pola outbox: dokumen tervalidasi dulu, pengiriman ke host menyusul dengan percobaan ulang |
| A5 | **Perangkat lapangan berbicara ke API sempit, bukan ke backend penuh.** | Handheld memanggil 21 rute JSON-RPC khusus, bukan merender layar backend Odoo di layar kecil |
| A6 | **Tier modul menentukan radius ledakan.** | Modul WMS ada di tier bersama; kustomisasi khusus klien turun ke tier tenant |
| A7 | **Tenant terisolasi pada tingkat basis data.** | Satu basis data per klien; tidak ada baris klien A di basis data klien B |

## 2. Tumpukan aplikasi (NOW)

```
    ┌────────────────────────────────────────────────────────────────────────────┐
    │  PENGGUNA                                                                  │
    │  Browser backend       Handheld (PWA di /hht/)       Sistem host klien      │
    └──────────┬───────────────────────┬──────────────────────────┬──────────────┘
               │ HTTPS                 │ HTTPS                    │ HTTPS + HMAC
               v                       v                          v
    ┌────────────────────────────────────────────────────────────────────────────┐
    │  CADDY (ingress)                                                           │
    │  TLS wildcard · routing per-subdomain · WAF Coraza/CRS (DetectionOnly)     │
    └──────────┬───────────────────────────────────────────────┬─────────────────┘
               │                                               │
               v                                               v
    ┌──────────────────────────────┐              ┌────────────────────────────┐
    │  odoo (publik)               │              │  odoo-mgmt                 │
    │  DBFILTER=^%d$               │              │  LIST_DB=True              │
    │  LIST_DB=False               │              │  hanya 127.0.0.1           │
    │  ── modul WMS berjalan di sini│              │  ── operasi & upgrade      │
    └──────────┬───────────────────┘              └──────────┬─────────────────┘
               │                                             │
               └──────────────┬──────────────────────────────┘
                              │  wajib berbagi satu cluster Postgres
                              │  DAN satu mount ./data/odoo-filestore
                              v
    ┌────────────────────────────────────────────────────────────────────────────┐
    │  postgres 16      redis      minio      queue_job (DB-backed, in-Odoo)     │
    │  satu DB per tenant                                                        │
    └────────────────────────────────────────────────────────────────────────────┘
```

Layanan yang **tidak** dipakai WMS tetapi ada di platform: `ai-gateway`, `tenant-orchestrator`,
`hub-portal`, `storefront`, `baileys`, `ftps`. Ketergantungan WMS terbatas pada Odoo + Postgres
+ Caddy.

**Redis bukan broker job.** Antrean latar belakang memakai `queue_job` (OCA, disimpan di basis
data). Jangan merancang WMS di atas asumsi broker pesan — belum ada broker di compose mana pun.

## 3. Tier modul

| Tier | Direktori | Modul WMS di dalamnya | Radius perubahan |
|---|---|---|---|
| Vendor | `addons/_vendor/` | `queue_job` | Jangan diedit |
| Core | `addons/core/` | `custom_core`, `custom_pdp_audit`*, `custom_adapter_framework`, `custom_hht_bridge`, `custom_product_barcode` | Seluruh tenant |
| EE-gap | `addons/ee_gap/` | **10 modul `custom_wms_*`**, `custom_barcode`, `custom_receipt_async` | Seluruh tenant yang memasangnya |
| Vertical | `addons/verticals/` | `custom_fnb_stock_ops` (memakai `custom_wms_cycle_count`) | Satu industri |
| Tenant | `addons/_tenants/` | — (tempat kustomisasi khusus klien) | Satu klien |

\* `custom_pdp_audit` berada di `addons/compliance/`.

**Aturan yang menentukan letak kode baru:**

1. Mesin bersama → `ee_gap/` atau `core/`, tidak pernah `_tenants/`.
2. Kebutuhan yang unik untuk satu klien → `_tenants/custom_<klien>_wms_*`.
3. Pola yang muncul untuk klien kedua → dipromosikan dari `_tenants/` ke `ee_gap/`.

Konsekuensi komersial yang harus dinyatakan di SOW: karena modul WMS bersama, permintaan perubahan
perilaku inti dari satu klien memerlukan regression test lintas tenant, dan biayanya masuk ke
estimasi.

## 4. Topologi deployment

**NOW:** satu VPS menjalankan seluruh tumpukan (±15 kontainer). Ini juga berlaku untuk deployment
WMS.

**TARGET:** pemisahan host produksi / basis data / redundan / pelaporan / backup.

| Peran host | Status | Penghambat |
|---|---|---|
| PROD | Ada, menjalankan semuanya | Seluruh jalur data adalah bind-mount `./data/*` pada satu filesystem |
| DB terpisah | **Belum dibangun** | `HOST: postgres` ter-hardcode di `docker-compose.yml` dan `docker-compose.multitenant.yml`; tidak ada env `PG_HOST` untuk layanan odoo |
| Redundan | **Belum dibangun** | Baris replikasi masih dikomentari di `postgres/pg_hba.conf` |
| Pelaporan | **Belum dibangun** | Peran `odoo_readonly` berstatus `NOLOGIN` dan hanya di-grant pada skema `pdp`; tidak ada replika |
| Backup | **Separuh** | `pg-backup-s3` mati secara default; MinIO berada di host yang sama menulis ke disk yang sama, sehingga "offsite" bersifat nominal. **WAL archiving belum terpasang — RPO nyata 24 jam** |

Batasan yang harus dihormati saat memisahkan tier:

1. `odoo` dan `odoo-mgmt` **wajib** berbagi satu cluster Postgres **dan** mount
   `./data/odoo-filestore` yang sama. Bila dipisah, aset 404.
2. Model kapasitas di `.env.example` (`HOST_CPU_CORES`, `HOST_RAM_GB`, `HOST_DISK_GB`) bersifat
   tunggal — mengasumsikan satu mesin.
3. Bootstrap VPS per-tenant (`tenant-orchestrator/.../vps.py`) mengkloning monolit per tenant;
   ia **tidak** memisahkan tier.

**Implikasi untuk WMS.** Gudang adalah operasi 24/7 atau minimal dua shift. Ekspektasi ketersediaan
dan RPO klien harus dicocokkan terhadap tabel di atas **sebelum** kontrak, bukan setelah insiden
pertama. Bila klien menuntut RPO < 24 jam, pemasangan WAL archiving adalah pekerjaan terpisah yang
harus masuk scope dan biaya.

## 5. Isolasi multi-tenant

Isolasi ditegakkan oleh Odoo, bukan oleh cluster terpisah: **satu basis data per tenant** pada satu
cluster Postgres.

| Instans Odoo | `DBFILTER` | `LIST_DB` | Peran |
|---|---|---|---|
| `odoo` (publik) | `^%d$` — hostname hanya menjangkau basis data yang cocok dengan subdomainnya | `False` | Melayani pengguna & handheld tenant |
| `odoo-mgmt` | `^.*$` | `True` | Manajer basis data; terikat hanya ke `127.0.0.1` |
| `odoo-front` | `^.*$` | `False` | Penelusuran lintas basis data tanpa manajer basis data |

Caddy memetakan `<slug>.platform.<domain>` ke basis data tenant yang sesuai
(`caddy/Caddyfile.multitenant`).

**Yang ini berarti bagi klien WMS:** data gudang klien berada di basis datanya sendiri. Namun
**kode** modul WMS dibagi. Isolasi data ≠ isolasi perilaku.

## 6. Alur data

### 6.1 Inbound sampai tersimpan di bin

```
PO dikonfirmasi ─┐
                 ├─► stock.picking (IN) ─► pindai GS1 ─► stock.move.line + stock.lot
ASN dari host ───┘        │                                    │ AI 10/17/21
                          │                                    v
                          │                          gate QC (opsional)
                          │                                    │
                          v                                    v
              validasi ─► leg STOR terbentuk ─► custom.putaway.engine.evaluate()
                                                       │
                                        custom.wms.putaway.suggestion (score, confidence)
                                                       │
                          ┌────────────────────────────┴────────────────────┐
                          │ auto-apply (confidence ≥ ambang)                │ review operator
                          v                                                 v
              move_line.location_dest_id diperbarui              handheld Putaway
                          └────────────────► validasi STOR ─► stock.quant per bin
```

### 6.2 Outbound

```
SO dikonfirmasi ─► leg PICK ─► reservasi terhadap stock.quant per bin
                                    │ (stok di lokasi QC dikecualikan pada tingkat gather)
                                    v
                     handheld Pick: pindai bin → pindai item → konfirmasi
                                    │
                                    v
                        validasi PICK ─► push rule ─► delivery order terbentuk
                                    │
                                    ├─► handheld Package: paket berbarcode
                                    └─► validasi pengiriman ─► wms.integration.event (outbox)
```

Catatan pelatihan: pada gudang 2-step keluar, **delivery order belum ada** saat SO dikonfirmasi.
Ia lahir dari push rule ketika pick divalidasi.

### 6.3 Replenishment internal

```
cron_evaluate_and_materialize (terjadwal)
        │
        v
custom.to.engine mengevaluasi custom.to.rule aktif
        │  trigger: low_water_mark / expiry_approaching / zone_consolidation /
        │           picking_replenishment / manual
        v
custom.transfer.order (TO/<tahun>/xxxxx)  ──materialize()──►  stock.move internal
        │
        v
handheld Bin-to-Bin: pindai bin asal → pindai bin tujuan → eksekusi
```

### 6.4 Cycle count

```
custom.cycle.count.plan (jatuh tempo)
        │  ⚠ NOW: dipicu manual — record ir.cron belum ada (lihat §9)
        v
custom.cycle.count.session (CC/<tahun>/00001) ─► custom.cycle.count.line
        │
        v
handheld Count: pindai bin & item → masukkan kuantitas
        │
        v
selisih terhitung ─► persetujuan supervisor ─► custom.cycle.count.adjustment
        │                                              │
        │                                              v
        └─────────────────────────────────► pergerakan penyesuaian stok
```

### 6.5 Integrasi keluar (pola outbox)

```
Dokumen divalidasi di Odoo
        │  transaksi yang sama
        v
wms.integration.event (state=pending, attempts=0)
        │
        v
cron_drain_wms_outbox ─► adapter (wms_host / wms_sap_host) ─► HTTP ke host
        │                                                          │
        ├─ sukses ──► state=sent, sent_at terisi                   │
        └─ gagal ───► attempts++, last_error terisi, coba lagi     │
                                                                   v
                                              host ─► POST /api/wms/ack ─► acked_at
```

Kegagalan host **tidak pernah** menggagalkan validasi dokumen di gudang. Ini adalah keputusan
arsitektur, bukan kebetulan.

## 7. Integrasi eksternal

| Sistem | Status | Mekanisme |
|---|---|---|
| Sistem host WMS/ERP klien (generik) | **NOW: siap pakai** | `POST /api/wms/asn`, `POST /api/wms/do`, `GET /api/wms/stock`, `POST /api/wms/ack` — `json2`, `auth="none"`, dijaga `@secure_endpoint('wms')` |
| SAP | **NOW: adapter terdaftar, kontrak per klien** | `@register_adapter("wms_sap_host")`. Odoo **tidak pernah** berbicara RFC/IDoc langsung; integrasi berjalan lewat REST + HMAC ke jembatan di sisi klien |
| Kafka / event bus | **NOW: tidak ada** | Tidak ada broker di compose mana pun. Jangan merancang alur WMS di atas asumsi event bus |
| Handheld Zebra | **NOW: siap pakai** | Profil DataWedge terdokumentasi ([`../../hht/datawedge.md`](../../hht/datawedge.md)); simbologi Code128, EAN-13, QR, GS1-128 |
| Handheld lain (mis. Denso BHT) | **NOW: perlu verifikasi per perangkat** | Sebagian unit dikirim dengan pembacaan Code128 dimatikan; barcode item karena itu dirender adaptif (13 digit → EAN-13) |
| Printer label | **NOW: lewat antrean cetak `custom_barcode`** | Konfigurasi printer + template label per klien |
| BI / data warehouse | **NOW: tidak ada** | `odoo_readonly` berstatus `NOLOGIN` dan hanya pada skema `pdp`; tidak ada replika, ODBC, atau ETL. Greenfield |

## 8. Keamanan & kepatuhan

| Lapis | NOW |
|---|---|
| Ingress | Caddy: TLS wildcard, WAF Coraza/CRS berjalan dalam mode DetectionOnly |
| API host | HMAC-SHA256 + toleransi drift + nonce + pembatasan CIDR, lewat `@secure_endpoint('wms')` |
| API handheld | Sesi pengguna Odoo; perangkat terdaftar dengan secret yang dapat dicabut/diregenerasi |
| Otorisasi | 13 grup WMS + ACL per model + record rule multi-perusahaan |
| Audit | `pdp.audited.mixin` pada objek WMS yang memuat data pelaku |
| Data pribadi | Kerangka UU PDP 27/2022 platform ([`../../pdp-compliance.md`](../../pdp-compliance.md)) |
| Eksekusi dinamis | `safe_eval` untuk aturan Python dan domain aturan transfer; terbatas grup admin |

Data pribadi di lingkup WMS relatif sedikit tetapi nyata: identitas operator pada setiap log pindai,
setiap baris hitung, dan setiap penimpaan saran. Retensi log pindai harus ditetapkan bersama DPO
klien.

## 9. Batasan yang harus dinyatakan ke klien

Delapan hal berikut adalah kondisi nyata hari ini. Menyembunyikannya berarti memindahkan risiko ke
fase hypercare.

1. **RPO nyata 24 jam.** WAL archiving belum terpasang. Angka 1 jam yang tercantum pada runbook
   pemulihan bencana belum didukung konfigurasi.
2. **Backup offsite bersifat nominal.** MinIO berada di host yang sama menulis ke disk yang sama;
   `pg-backup-s3` mati secara default.
3. **Satu host menjalankan semuanya.** Tier basis data, redundan, dan pelaporan belum dibangun.
4. **Penerbitan sesi cycle count belum terjadwal.** Metodenya ada, record `ir.cron`-nya belum —
   lihat TSD §2.4 (T1).
5. **Mode offline penuh handheld belum diverifikasi** terhadap perangkat klien. Asumsi kerja: online.
6. **Modul WMS dibagi lintas tenant.** Perubahan perilaku inti berdampak ke klien lain dan
   memerlukan regression test lintas tenant.
7. **Tidak ada lapisan BI.** Pelaporan berjalan dari basis data produksi melalui laporan bawaan
   modul. Kebutuhan analitik berat memerlukan pekerjaan terpisah.
8. **Tidak ada event bus.** Integrasi bersifat REST permintaan-tanggapan plus outbox.

## 10. Keputusan arsitektur & alasannya

| # | Keputusan | Alternatif yang ditolak | Alasan |
|---|---|---|---|
| K1 | WMS sebagai perluasan `stock` Odoo | WMS berdiri sendiri yang disinkronkan ke Odoo | Ledger stok ganda selalu berakhir dengan rekonsiliasi manual; valuasi dan penelusuran lot akan pecah |
| K2 | Handheld sebagai PWA dengan API sempit | Aplikasi native per platform; atau backend Odoo di layar kecil | PWA menghindari distribusi aplikasi ke ratusan perangkat; API sempit menjaga permukaan serang dan performa |
| K3 | Saran putaway, bukan penempatan paksa | Penempatan otomatis penuh | Kepercayaan operator dibangun bertahap; data penimpaan menjadi umpan balik kualitas mesin |
| K4 | Pola outbox untuk integrasi | Panggilan sinkron saat validasi dokumen | Gudang tidak boleh berhenti karena host sedang tidak tersedia |
| K5 | Barcode dirender in-process sebagai data-URI | `<img src="/report/barcode/…">` | Menghilangkan panggilan HTTP balik per barcode saat merender PDF |
| K6 | Pengecualian stok QC pada tingkat *gather* | Menyaring di domain tampilan | Penyaringan tampilan tidak menghentikan proses otomatis mengambil stok karantina |
| K7 | Kebijakan slotting sebagai data (record), bukan kode | Aturan ter-hardcode per klien | Perubahan tata letak gudang adalah kejadian rutin; tidak boleh menuntut rilis |
| K8 | Modul WMS di tier `ee_gap/` | Modul per klien di `_tenants/` | Sepuluh modul yang digandakan per klien mustahil dipelihara; harga yang dibayar adalah disiplin regression test |
| K9 | Simbologi item adaptif (EAN-13/Code128) | Code128 seragam | Sebagian handheld dikirim dengan Code128 dimatikan; keseragaman akan gagal di lapangan |
| K10 | Satu basis data per tenant | Skema bersama dengan kolom perusahaan | Isolasi yang dapat dijelaskan ke auditor, dan pemulihan per klien yang sederhana |

---

**Terakhir diverifikasi terhadap repo: 2026-08-11.** Nama modul, versi, rute, grup, dan status
placeholder pada dokumen ini diambil langsung dari basis kode pada tanggal tersebut.
