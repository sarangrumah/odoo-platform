# PPOB Implementation — Paket Dokumen

Paket dokumen implementasi **PPOB / bill-payment & top-up switching di atas Odoo 19**, ditulis
generik sehingga dapat dipakai ulang untuk klien mana pun, dengan satu addendum untuk program
**PPS (Erajaya VAS / Eraspace)**.

Paket ini menggambarkan kapabilitas yang **sudah terpasang** di platform: 12 modul
`addons/verticals/custom_ppob_*` (± 13.600 baris Python, 135 test otomatis pada 8 modul),
ditambah komponen platform bersama (`custom_core`, `custom_adapter_framework`,
`custom_pph_witholding`, `custom_coretax_bupot`, `custom_accounting_*`).

Bahasa: **Bahasa Indonesia** (dokumen menghadap klien). Rujukan teknis memakai nama modul,
model, dan rute apa adanya dari basis kode.

---

## Isi paket

| # | Dokumen | Untuk siapa | Isi |
|---|---|---|---|
| 00 | [`00-Project-Initiation-Document.md`](00-Project-Initiation-Document.md) | Sponsor, PM | Mandat, scope, gap yang diakui, tata kelola, milestone, kriteria sukses, risiko, serah terima |
| 01 | [`01-BRD.md`](01-BRD.md) | Sponsor, PO, Finance, Ops, BA | Konteks bisnis, 8 KPI, proses target, **80 kebutuhan bernomor (BR-xx)** dengan MoSCoW dan status platform, 12 aturan bisnis |
| 02 | [`02-FSD.md`](02-FSD.md) | Key user, BA, QA | Fungsi per area, 4 peran akses, permukaan API, keuangan & pajak, 8 user journey, **25 acceptance test**, matriks traceability |
| 03 | [`03-TSD.md`](03-TSD.md) | Developer, arsitek, IT klien | Komponen & model data per modul, permukaan API & cron, keamanan, konfigurasi, urutan instalasi & go-live, pengujian, 10 utang teknis, jebakan Odoo 19 |
| 04 | [`04-Architecture.md`](04-Architecture.md) | Arsitek, IT klien | Prinsip, tumpukan NOW/TARGET, tier modul, **tiga posisi Odoo dalam rantai PPOB**, topologi, isolasi multi-tenant, alur data, batasan nyata, 12 keputusan arsitektur |
| 05 | [`05-Estimasi-Mandays.md`](05-Estimasi-Mandays.md) | Sponsor, PM, sales | Estimasi BA/DEV/QA dua skenario, rincian per workstream, timeline, komposisi tim, faktor pengubah, eksklusi |
| 06 | [`06-Addendum-PPS.md`](06-Addendum-PPS.md) | Tim engagement PPS | Posisi engagement, pemetaan tiga fase program, 9 keputusan terbuka, estimasi & timeline per fase, risiko khusus |

## Angka utama

> **Effort PM sengaja dikosongkan** di seluruh paket — diisi PM sesuai model tata kelola yang
> dipakai. Semua total di bawah adalah **BA + DEV + QA saja** dan harus dijumlahkan ulang
> setelah alokasi PM masuk.

| | Greenfield (bangun dari nol) | Brownfield (reuse 12 modul) | PPS (tiga fase) |
|---|---:|---:|---:|
| PM | *diisi PM* | *diisi PM* | *diisi PM* |
| BA | 76 | 47 | 32 |
| DEV | 284 | 108 | 114 |
| QA | 108 | 56 | 56 |
| **Total tanpa PM (termasuk kontingensi 15%)** | **≈ 538** | **≈ 243** | **≈ 233** |
| Durasi | ≈ 26 minggu | ≈ 13 minggu | ≈ 23 minggu (3 fase) |

Penghematan Brownfield vs Greenfield: **295 mandays (55%)**. Angka PPS lebih besar dari
Brownfield generik karena mencakup **tiga gelombang perpindahan otoritas** (saldo → dispatch →
konsolidasi), masing-masing dengan gerbang paritasnya sendiri.

Angka bersifat **indikatif berbasis asumsi tertulis**, bukan komitmen kontrak. Lingkup dasar:
1 perusahaan, 1 mata uang, 1 biller riil, 1 bank VA, 1 kanal, ≤ 50.000 transaksi/hari,
≤ 2.000 produk. Pengali untuk skala lain ada di dokumen 05 §9.

## Urutan membaca

- **Sponsor / manajemen:** 00 → 05 → (bila PPS) 06
- **Business analyst / key user:** 01 → 02 → 06
- **Developer / arsitek / IT klien:** 04 → 03 → 02
- **Sales / pra-penjualan:** README ini → 05 → 06

## Konvensi

- **SUDAH ADA** = terpasang dan terverifikasi di repo pada 2026-08-11.
  **PERLU DIBANGUN** = belum ada, dan sudah dibiayai eksplisit di estimasi.
  **KONFIGURASI** = ada, perlu disetel per klien.
- **NOW** vs **TARGET** pada dokumen arsitektur mengikuti konvensi
  [`../../architecture.md`](../../architecture.md): tidak ada yang berstatus TARGET boleh dijual
  sebagai sudah ada.
- Diagram berupa ASCII di dalam blok kode, konsisten dengan arsitektur platform.
- Setiap kebutuhan (BR-xx) dapat ditelusuri ke fungsi FSD dan ke acceptance test — lihat FSD §11.

## Gap yang tercatat jujur

Verifikasi basis kode menemukan enam hal yang belum jadi. Semuanya masuk scope dan biaya, tidak
disembunyikan di balik klaim kapabilitas:

| Gap | Isi | Rujukan |
|---|---|---|
| G1 | API wallet sinkron (`hold`/`commit`/`release`/`credit`/`balance`) belum ada — wallet hanya punya primitif internal, tanpa controller | BRD BR-WL-07/08, TSD §4.4, T1 |
| G2 | `custom_ppob_eraspace_bridge` masih berpola 2-feed (POS + H2H) dari konsep lama | TSD T2 |
| G3 | Nol test otomatis pada `custom_ppob_core`, `custom_ppob_wallet`, `custom_ppob_commission`, `custom_ppob_rollup` | TSD §8, T3 |
| G4 | Digiflazz jalur prepaid tidak memiliki `inquiry()` maupun `status()` — reaper tidak dapat auto-resolusi di jalur itu | FSD §4.5, TSD T4 |
| G5 | Gateway PPS mendokumentasikan anti-replay + kesegaran waktu, tetapi controller hanya menegakkan IP allowlist + tanda tangan + idempotensi DB; `max_clock_skew_s` tidak pernah dibaca | FSD §4.6, TSD T5 |
| G6 | Tidak ada skrip konfigurasi tenant PPOB di `scripts/tenants/` — go-live belum reproducible | TSD §6, T7 |

Selain itu dua batasan yang diwarisi, bukan cacat implementasi: **MD5 pada kontrak gateway PPS**
(terisolasi di satu berkas, dikompensasi IP allowlist + rahasia per mitra + idempotensi DB) dan
**PPN diakui pada faktur ringkas harian**, bukan per transaksi.

## Sumber & bukti

| Aset | Lokasi |
|---|---|
| Modul PPOB (12) | `addons/verticals/custom_ppob_*` |
| Modul platform pendukung | `addons/core/custom_core`, `custom_adapter_framework`, `custom_pph_witholding`, `custom_coretax_bupot`, `custom_accounting_*` |
| Arsitektur program PPS — kondisi existing & Fase 1 | [`../ppob/ppob-eraspace-h2h-architecture.md`](../ppob/ppob-eraspace-h2h-architecture.md) |
| Arsitektur program PPS — target state (Fase 1–3) | [`../ppob/ppob-eraspace-odoo-target-architecture.md`](../ppob/ppob-eraspace-odoo-target-architecture.md) |
| Test otomatis (135 test pada 8 modul) | `addons/verticals/custom_ppob_*/tests/` |
| Basis data uji | `rnd_ppob` (dibuat 17-Jul-2026; urutan instalasi: CoA dulu) |
| Arsitektur platform | [`../../architecture.md`](../../architecture.md) |
| Kebijakan pajak & Coretax | [`../../coretax.md`](../../coretax.md), [`../../tax-reporting-requirements.md`](../../tax-reporting-requirements.md) |

---

**Terakhir diverifikasi terhadap repo: 2026-08-11.**
