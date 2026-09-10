# Technical Specification Document (TSD)
## Implementasi PPOB / Bill-Payment Switching di atas Odoo 19

| | |
|---|---|
| **Dokumen** | 03 — Technical Specification Document |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Pembaca** | Developer, arsitek, IT klien |
| **Basis kode** | `addons/verticals/custom_ppob_*` — 12 modul, ± 13.600 baris Python |

---

## Contents

1. [Arsitektur perangkat lunak](#1-arsitektur-perangkat-lunak)
2. [Komponen per modul](#2-komponen-per-modul)
3. [Ringkasan model data](#3-ringkasan-model-data)
4. [Permukaan API](#4-permukaan-api)
5. [Keamanan](#5-keamanan)
6. [Konfigurasi](#6-konfigurasi)
7. [Deployment & operasi](#7-deployment--operasi)
8. [Pengujian](#8-pengujian)
9. [Utang teknis & trade-off yang diketahui](#9-utang-teknis--trade-off-yang-diketahui)
10. [Jebakan platform Odoo 19 yang relevan](#10-jebakan-platform-odoo-19-yang-relevan)
11. [Kriteria penerimaan teknis](#11-kriteria-penerimaan-teknis)

---

## 1. Arsitektur perangkat lunak

### 1.1 Prinsip

1. **Uang hanya bergerak lewat primitif atomik.** `_atomic_debit` / `_atomic_credit` pada
   wallet dan bucket melakukan `SELECT ... FOR UPDATE`, memvalidasi, memposting jurnal, menulis
   mutasi sub-ledger, lalu memperbarui saldo — semuanya di dalam satu transaksi basis data.
   Tidak ada penulisan `balance` secara langsung di luar helper ini.
2. **Idempotensi ditegakkan skema, bukan aplikasi.** `unique(mitra_id, idempotency_key)`,
   `unique(bank_ref)`, `unique(pos_ref)`, `unique(h2h_ref)`.
3. **Adapter tidak mengetahui akuntansi; mesin transaksi tidak mengetahui protokol biller.**
   Kontrak di antara keduanya adalah objek hasil bertri-state.
4. **Tri-state `ok`.** `True` sukses, `False` gagal, `None` belum selesai. Perbedaan
   `None` vs `False` adalah pembeda antara transaksi yang dibiarkan dan transaksi yang
   direfund — dan ditegakkan secara eksplisit di dua tempat (dispatch dan reaper).
5. **Jalur pembayaran tidak pernah di-retry otomatis.** Retry adalah keputusan manusia atau
   hasil pemeriksaan status, bukan perilaku transport.

### 1.2 Tiering modul

| Tier | Modul | Sifat |
|---|---|---|
| Fondasi | `custom_ppob_core` | Master data + pemetaan akun; tidak memuat logika uang |
| Sub-ledger | `custom_ppob_wallet`, `custom_ppob_provider` | Primitif atomik + jurnal berpasangan |
| Mesin | `custom_ppob_sale` | State machine, routing, refund, reaper |
| Integrasi keluar | `custom_ppob_biller_digiflazz`, adapter HTTP/mock, `custom_ppob_oracle_bridge` | Bicara ke biller/legacy |
| Integrasi masuk | `custom_ppob_pps_gateway`, `custom_ppob_va`, `custom_ppob_eraspace_bridge` | Menerima kanal, bank, dan feed |
| Finance | `custom_ppob_rollup`, `custom_ppob_commission` | Faktur ringkas, komisi & PPh |
| Observabilitas | `custom_ppob_sla` | Target + sampling throughput |

### 1.3 Reuse yang sudah tersedia (jangan bangun ulang)

| Kebutuhan | Sudah disediakan |
|---|---|
| Verifikasi HMAC, nonce store (Redis, fallback memori), allowlist IP | `custom_core.controllers.secure_endpoint` |
| Kredensial adapter per tenant + log panggilan | `custom_adapter_framework` (`custom.adapter.config`, `custom.adapter.call.log`) |
| PPh & bukti potong | `custom_pph_witholding`, `custom_coretax_bupot` |
| Laporan keuangan & pengecualian jurnal non-GL | `custom_accounting_reports` (`x_custom_report_excluded`) |
| Rekonsiliasi rekening koran | `custom.reconcile.rule` |
| Eksekusi asinkron | `_vendor/queue_job` |

## 2. Komponen per modul

### 2.1 `custom_ppob_core` — fondasi

Model: `custom.ppob.product.class`, `custom.ppob.product`, `custom.ppob.price.tier`(+`.line`),
`custom.ppob.account.mapping`; ekstensi `res.partner`.

- Kelas produk menyimpan akun default (wallet liability, revenue, COGS) dan `vat_mode`
  (`margin` · `other_valuation` · `gross` · `exempt`).
- Produk: `code` (unik), `denom`, `cost_price_default`, `inquiry_required`, dengan
  `_get_revenue_account()` / `_get_cogs_account()` yang jatuh ke default kelas.
- Tier harga: `_get_sell_price(partner, product)` — menolak bila partner tanpa tier dan tidak
  ada default.
- `res.partner`: `x_custom_ppob_is_mitra`, `x_custom_ppob_is_provider`,
  `x_custom_ppob_mitra_code` (unik), `x_custom_ppob_mitra_tier_id`,
  `x_custom_ppob_daily_txn_cap`, `x_custom_ppob_monthly_txn_cap`, `x_custom_ppob_has_npwp`.
- `custom.ppob.account.mapping._get_account(role, company)` — resolusi akun **berbasis peran**
  per perusahaan. Semua modul lain memakai ini, bukan kode akun literal.
- Hook instalasi membuat kerangka akun PPOB bila belum ada (lihat §7 untuk urutan instalasi).

### 2.2 `custom_ppob_wallet` — saldo mitra

Model: `custom.ppob.wallet`, `custom.ppob.wallet.move`.

- Unik `(partner_id, class_id, company_id)`.
- `_lock()` → `SELECT id, balance FROM custom_ppob_wallet WHERE id = %s FOR UPDATE`,
  mengembalikan saldo segar (menangani NULL warisan).
- `_atomic_debit(amount, reason, counterpart_account, **extras)` — menolak nilai ≤ 0, wallet
  beku, dan `amount > balance + credit_limit`; memposting Dr *wallet liability* / Cr
  *counterpart*; menulis `wallet.move` berisi `amount_signed`, `balance_after`, tautan jurnal;
  memperbarui saldo lewat SQL lalu meng-invalidate cache.
- `_atomic_credit(...)` — kebalikannya.
- `_atomic_credit_with_tax(gross, output_tax, ...)` — memecah DPP/PPN dari pajak inklusif,
  wallet hanya bertambah DPP, PPN ke akun repartisi pajak; menolak bila pajak tanpa akun
  repartisi.
- `_build_move_vals` menambahkan kolom tautan opsional (`ppob_transaction_id`, `va_topup_id`)
  hanya bila kolomnya benar-benar ada — modul wallet tetap dapat berdiri sendiri.

### 2.3 `custom_ppob_provider` — deposit biller & adapter

Model: `custom.ppob.provider`, `custom.ppob.provider.bucket`(+`.move`),
`custom.ppob.provider.sku.map`, `custom.ppob.provider.topup.log`, wizard top-up; ekstensi
`account.move`, `stock.picking`.

- Provider: `settlement_mode` (prabayar deposit / pascabayar), `status`, `failover_priority`,
  `stale_threshold_minutes`, `bucket_mode` (`bulky` / `fixed_denom`), `tax_rate_topup`,
  akun deposit/PPN masukan/AP, `adapter_class`, `adapter_config_id`, `coretax_method`,
  `dpp_factor`, `ppn_rate`, `discount_handling`, `topup_dp_timing`.
- Bucket: saldo + `low_water_mark`, constraint non-negatif di tingkat basis data,
  `_atomic_debit` / `_atomic_credit` / `_atomic_credit_from_move`, opsional tertaut produk
  inventaris + gudang sehingga pemakaian deposit menerbitkan pengeluaran barang.
- `_resolve_bucket_for(product)` mengikuti `bucket_mode`; `action_ensure_buckets()` membuat
  bucket yang belum ada.
- Registry adapter: kelas turunan `PPOBProviderAdapter` didaftarkan lewat `@register_adapter`
  dan muncul otomatis pada `adapter_class`. Kontrak: `inquiry()`, `pay()`, `status()`,
  `topup()`, `check_balance()`.
- `action_test_connection()` memanggil adapter dan menoleransi `NotImplementedError`.
- Top-up deposit DP-100%: wizard menghitung split DPP/PPN sesuai `coretax_method`, membuat
  invoice DP (dan pelunasan bila timing menghendaki), lalu mengkredit bucket dari jurnal.

### 2.4 `custom_ppob_sale` — mesin transaksi

Model: `custom.ppob.transaction` (+ ekstensi `wallet.move`, `bucket.move`, `stock.picking`),
wizard penjualan manual.

- Field kunci: `state`, `idempotency_key` (unik per mitra), `attempt_no`, `provider_ref`,
  `serial_token`, `dispatched_at`, `completed_at`, `provider_latency_ms`, `dpp_amount`,
  `ppn_amount`, `margin`, tautan ke jurnal serta mutasi wallet/bucket dan pasangan refund-nya.
- `_resolve_provider()` — bila provider ditetapkan, wajib ada SKU map; bila tidak, urutkan SKU
  map aktif berdasarkan `priority asc, id asc` di antara provider berstatus aktif.
- `_check_caps()` — akumulasi transaksi sukses + diproses terhadap cap harian/bulanan mitra.
- `_dispatch_one()` — urutan: cek status → cek cap → resolusi provider (**menulis ulang
  `cost_price` dari `sku_line.buy_price`**) → debit wallet → debit bucket (bila prabayar) →
  status `in_progress` → panggil adapter dengan pengukuran `time.monotonic()` → cabang
  tri-state.
- `_refund_subledgers()` — idempoten; mengembalikan wallet dan bucket beserta jurnal balik.
- `_cron_reap_stale_inprogress()` — pra-filter kasar 1 menit, lalu ambang per provider;
  memanggil `adapter.status()`; `NotImplementedError` → tidak refund, hanya log; `ok is None` →
  dibiarkan; sukses → tutup; gagal → refund + `timeout`.
- PPN dihitung sebagai field tersimpan (`_compute_tax`) tetapi **tidak diposting per
  transaksi** — pengakuan terjadi di rollup.

### 2.5 `custom_ppob_va` — top-up mitra

Model: `custom.ppob.va.account`, `custom.ppob.va.topup`, `custom.ppob.va.bank.connection`;
ekstensi `custom.reconcile.rule` dan `account.bank.statement.line`.

- Dua rute per bank: `POST /api/ppob/va/<bank_code>/inquiry` dan `.../payment`.
- Verifikasi: HMAC-SHA256 atas `timestamp || body` dengan rahasia dari `credential_ref`
  (kunci `ir.config_parameter`), toleransi `max_clock_skew_s`, penjaga replay `_NonceStore`,
  allowlist IP (hop pertama `X-Forwarded-For`).
- Idempotensi uang: `UNIQUE(bank_ref)` pada `custom.ppob.va.topup` — callback ganda
  mengembalikan acknowledgment asli.
- `action_credit_wallet()` mengkredit wallet lewat primitif atomik dengan akun transit sebagai
  counterpart; mendukung varian inklusif pajak lewat `output_tax_id` pada VA.
- Jalur rekening koran: aturan rekonsiliasi mencocokkan baris statement ke VA untuk bank yang
  tidak mengirim callback.

### 2.6 `custom_ppob_pps_gateway` — gateway H2H masuk

Model: `custom.ppob.pps.mitra.credential`, `custom.ppob.pps.callback.log`,
`custom.ppob.pps.game.field`; ekstensi transaksi (`pps_serveridtrx`, `pps_produk`,
`pps_callback_url`).

- Tujuh rute `POST /pps/*` (lihat §4.1) yang meniru kontrak vendor sehingga kanal cukup
  mengganti base URL.
- `_authn(endpoint, params)`: resolusi kredensial dari `user` → allowlist IP → verifikasi
  tanda tangan per endpoint.
- Tanda tangan **MD5** terisolasi di `controllers/pps_signature.py` dengan formula berbeda per
  endpoint dan pembandingan `hmac.compare_digest`. Modul lain dilarang mengimpor berkas ini;
  konvensi platform (HMAC-SHA256) tidak ikut terdilusi.
- Sell: idempoten pada `notrx`; transaksi dibuat di dalam `savepoint()` lalu di-dispatch;
  `UserError` dipetakan ke kode galat kontrak vendor.
- Inquiry stateless (`checknocustomer`, `inquiry-pln`) memakai objek pembawa non-persisten agar
  adapter dapat dipanggil tanpa membuat transaksi.
- Cron `_cron_pps_dispatch_callbacks(batch_size=200)` tiap menit mengirim hasil ke URL callback
  mitra; status polling tetap menjadi cadangan.

### 2.7 `custom_ppob_eraspace_bridge` — mirror & join

Model: `custom.ppob.eraspace.connection`, `custom.ppob.eraspace.txn` (join),
`custom.ppob.eraspace.settlement`, `custom.ppob.eraspace.ingest.skipped`, wizard backfill.

- Dua rute masuk (`/api/ppob/eraspace/pos`, `/api/ppob/eraspace/h2h`), HMAC + IP + nonce,
  idempoten `UNIQUE(pos_ref)` / `UNIQUE(h2h_ref)`.
- Join per `pos_trx_ref`: sisi POS memproyeksikan penjualan/top-up/refund ke wallet mirror,
  sisi H2H memproyeksikan COGS/deposit; `match_state` dan `margin` terhitung dari keduanya.
- Data yang tidak dapat dipetakan (mitra/produk/biller tak dikenal, status belum final, galat
  posting) masuk `ingest.skipped` beserta alasan dan payload asli; dapat dimasukkan ulang.
- Cron rekonsiliasi tiap 5 menit menandai transaksi yang hanya punya satu sisi melewati SLA.

### 2.8 `custom_ppob_oracle_bridge` — jalur legacy (opsional)

Adapter yang memanggil stored procedure `SellWithDenom_HA` pada Oracle EVShop, ditambah tiga
cron: sinkronisasi status (`MSG016T`, tiap menit), ingest baris baru (tiap menit), dan mirror
saldo member (`MSG019T`, tiap 5 menit). Membutuhkan paket Python `oracledb` pada image.

### 2.9 `custom_ppob_biller_digiflazz` — adapter biller riil

- Penandatanganan MD5 sesuai spesifikasi vendor, `ref_id` sebagai kunci idempotensi.
- `pay()` untuk prepaid dan pascabayar; `inquiry()` hanya untuk pascabayar; `topup()`,
  `check_balance()`, `price_list()` tersedia.
- **Batasan:** prepaid tidak memiliki endpoint inquiry maupun status read-only — keduanya
  menolak dengan `NotImplementedError`. Konsekuensinya reaper tidak dapat meresolusi otomatis
  transaksi prepaid Digiflazz yang menggantung.

### 2.10 `custom_ppob_rollup` & `custom_ppob_commission` — finance

- Rollup: model abstrak dengan `_cron_daily_rollup(rollup_date=None)` harian; mengelompokkan
  transaksi sukses per mitra menjadi `sale.order` + faktur ringkas; idempoten lewat penanda
  `x_custom_ppob_rollup_so_id`; jurnal ringkasan ditandai non-GL agar tidak dihitung ganda pada
  laporan keuangan.
- Komisi: `custom.ppob.commission.rule` (scope dari-provider / ke-mitra, cakupan kelas/produk/
  mitra, tipe persentase atau tetap, masa berlaku, prioritas) dan
  `custom.ppob.commission.accrual` (akrual per transaksi, jurnal akrual dan settlement),
  dengan pemotongan PPh 23 lewat engine platform dan bukti potong Coretax.

### 2.11 `custom_ppob_sla` — target & pengukuran

- `custom.ppob.sla.target`: target throughput/latensi bercakupan provider × kelas (dengan
  wildcard), lengkap dengan field provenance ("angka ini dari mana, disetujui siapa").
- `custom.ppob.throughput.sample`: sampel per jam berisi jumlah transaksi, sukses/gagal/timeout,
  `peak_tps`, `mean_tps`, `avg_latency_ms`, `p95_latency_ms`, `success_rate_pct`, dan penanda
  pelanggaran; `source` membedakan **baseline historis sistem lama** dari **aktual Odoo**
  sehingga uji paritas dual-run dapat dibandingkan langsung.
- Target bersifat **deklaratif** — tidak ada throttling di jalur dispatch yang membacanya.

## 3. Ringkasan model data

| Model | Kunci unik / constraint | Catatan |
|---|---|---|
| `custom.ppob.product.class` | `code` | Membawa `vat_mode` + akun default |
| `custom.ppob.product` | `code` | Denominasi, harga modal default, penanda inquiry |
| `custom.ppob.price.tier(.line)` | tier × produk | Harga jual wajib positif |
| `custom.ppob.account.mapping` | `(company, role)` | Resolusi akun berbasis peran |
| `custom.ppob.wallet` | `(partner, class, company)` | Saldo tidak boleh ditulis langsung |
| `custom.ppob.wallet.move` | — | `amount_signed`, `balance_after`, tautan jurnal |
| `custom.ppob.provider` | `code` | Mode settlement, prioritas, ambang stale |
| `custom.ppob.provider.bucket` | provider × mode × produk | Saldo non-negatif (DB) |
| `custom.ppob.provider.sku.map` | provider × produk | `buy_price`, `priority`, `active` |
| `custom.ppob.transaction` | **`(mitra_id, idempotency_key)`** | Jantung idempotensi |
| `custom.ppob.va.account` | bank × nomor VA | Akun transit + pajak opsional |
| `custom.ppob.va.topup` | **`bank_ref`** | Idempotensi callback bank |
| `custom.ppob.eraspace.txn` | **`pos_ref`**, **`h2h_ref`** | Join dua feed per `pos_trx_ref` |
| `custom.ppob.pps.mitra.credential` | `pps_user` | Rahasia lewat `credential_ref` |
| `custom.ppob.commission.rule` / `.accrual` | — | Akrual per transaksi sukses |
| `custom.ppob.sla.target` / `.throughput.sample` | jam × cakupan | Baseline vs aktual |

## 4. Permukaan API

### 4.1 Kanal H2H masuk (`custom_ppob_pps_gateway`)

| Rute | Tipe | Formula tanda tangan (MD5) |
|---|---|---|
| `POST /pps/sell` | form | `md5(mdn + produk + notrx + md5(password))` |
| `POST /pps/statustrx` | form | `md5(notrx + md5(password))` |
| `POST /pps/statustrxwithdeposit` | form | `md5(notrx + md5(password))` |
| `POST /pps/checknocustomer` | form | `md5(notrx + user + product + md5(password) + customer_no)` |
| `POST /pps/inquiry-pln` | JSON | `md5(customerNumber + user + md5(password))` |
| `POST /pps/game-list` | JSON | `md5(timestamp + md5(password))` |
| `POST /pps/direct-topup` | JSON | `md5(md5(password) + user + produk + notrx)` |

### 4.2 Bank VA (`custom_ppob_va`)

| Rute | Autentikasi |
|---|---|
| `POST /api/ppob/va/<bank_code>/inquiry` | HMAC-SHA256(`timestamp‖body`) + skew + nonce + IP |
| `POST /api/ppob/va/<bank_code>/payment` | idem, plus idempotensi `bank_ref` |

### 4.3 Feed mirror (`custom_ppob_eraspace_bridge`)

| Rute | Autentikasi |
|---|---|
| `POST /api/ppob/eraspace/pos` | HMAC + skew + nonce + IP; idempoten `pos_ref` |
| `POST /api/ppob/eraspace/h2h` | idem; idempoten `h2h_ref` |

### 4.4 API wallet sinkron — **PERLU DIBANGUN**

Rancangan yang harus dibangun agar switcher eksternal dapat menjadikan Odoo pemegang saldo
otoritatif:

| Rute | Guna | Idempotensi |
|---|---|---|
| `POST /api/ppob/wallet/hold` | Cek + tahan saldo | `(trx_ref, 'hold')` |
| `POST /api/ppob/wallet/commit` | Commit debit + jurnal | `(trx_ref, 'commit')` |
| `POST /api/ppob/wallet/release` | Lepas hold, tanpa jurnal | `(trx_ref, 'release')` |
| `POST /api/ppob/wallet/credit` | Refund/koreksi | `(trx_ref, 'credit')` |
| `GET  /api/ppob/wallet/balance` | Snapshot saldo | — |

Semua HMAC-SHA256 dengan `secure_endpoint` platform. Model hold memerlukan kolom saldo tertahan
pada wallet dan penyesuaian ceiling di `_atomic_debit` — perubahan skema pada modul paling
money-critical, karena itu wajib disertai paket test (gap G3).

### 4.5 Cron

| Cron | Interval | Modul |
|---|---|---|
| Reap transaksi menggantung | 5 menit | `custom_ppob_sale` |
| Kirim callback ke kanal | 1 menit | `custom_ppob_pps_gateway` |
| Rekonsiliasi bridge | 5 menit | `custom_ppob_eraspace_bridge` |
| Sampling throughput | 1 jam | `custom_ppob_sla` |
| Rollup faktur harian | 1 hari | `custom_ppob_rollup` |
| Sinkronisasi status Oracle | 1 menit | `custom_ppob_oracle_bridge` (opsional) |
| Ingest baris Oracle | 1 menit | `custom_ppob_oracle_bridge` (opsional) |
| Mirror saldo member Oracle | 5 menit | `custom_ppob_oracle_bridge` (opsional) |

## 5. Keamanan

| Kontrol | Penerapan |
|---|---|
| Tanda tangan | HMAC-SHA256 untuk VA, feed mirror, dan API wallet; MD5 **hanya** pada gateway PPS karena kontrak vendor |
| Isolasi MD5 | Seluruh formula MD5 berada di satu berkas dan tidak boleh diimpor modul lain |
| Allowlist IP | Per koneksi bank, per feed, per kredensial mitra kanal; hop pertama `X-Forwarded-For` |
| Anti-replay | `_NonceStore` (Redis, fallback memori) pada VA dan feed; **belum** pada gateway PPS (G5) |
| Idempotensi uang | Constraint unik basis data pada transaksi, top-up, dan feed |
| Rahasia | `ir.config_parameter` atau `custom.adapter.config` per tenant; tidak pernah di record bisnis |
| Hak akses | Empat grup di bawah satu privilege; 88 aturan akses model tersebar di 11 berkas `ir.model.access.csv` |
| Jejak audit | `mail.thread` pada transaksi (status, referensi provider, kode galat) dan koneksi legacy |

## 6. Konfigurasi

| Objek | Yang harus disetel | Kapan |
|---|---|---|
| Pemetaan akun (`role → account`) | revenue, COGS, deposit, PPN keluaran/masukan, transit bank, komisi | Sebelum semua |
| Kelas produk | Kode, akun default, **mode PPN** | Sebelum katalog |
| Katalog produk | Kode, denominasi, harga modal default, penanda inquiry | Sebelum SKU map |
| Tier harga | Harga jual per produk per tier | Sebelum mitra transaksi |
| Mitra | Kode unik, tier, cap harian/bulanan, NPWP | Onboarding |
| Wallet | Kelas, akun liability, jurnal, credit limit | Onboarding mitra |
| Provider | Mode settlement, status, prioritas, ambang stale, mode bucket, akun & jurnal, kelas adapter, konfigurasi adapter | Sebelum dispatch |
| SKU map | Produk → SKU biller, harga modal, prioritas | Sebelum dispatch |
| Bucket | Mode + low-water-mark (+ produk inventaris bila dipakai) | Sebelum dispatch |
| VA & koneksi bank | Nomor VA, akun transit, `credential_ref`, allowlist IP, skew | Sebelum top-up |
| Kredensial kanal | `pps_user`, rahasia, allowlist IP, URL callback | Sebelum kanal live |
| Target SLA | Throughput & latensi per provider/kelas + provenance | Sebelum dual-run |
| Aturan komisi | Cakupan, tipe, tarif, masa berlaku | Sebelum settlement pertama |

> **Gap G6:** belum ada skrip konfigurasi tenant PPOB di `scripts/tenants/`. Seluruh tabel di
> atas kini disetel manual. Membangun skrip seed/konfigurasi adalah bagian dari lingkup agar
> go-live dapat direproduksi dan diaudit.

## 7. Deployment & operasi

### 7.1 Urutan instalasi (wajib)

1. **Pasang CoA lokal lebih dulu** (`-i l10n_id` atau CoA klien) pada basis data kosong.
2. Baru pasang modul PPOB.

Alasannya konkret: pada basis data tanpa CoA, hook `custom_ppob_core` membuat akun PPOB-nya
sendiri; di akhir pemuatan modul, `account` menjalankan auto-install template yang menghapus
akun placeholder → pelanggaran foreign key pada pemetaan akun PPOB. Memasang CoA lebih dulu
membuat auto-install tidak pernah menyala.

### 7.2 Urutan pemasangan modul

```
  custom_ppob_core
      -> custom_ppob_wallet
      -> custom_ppob_provider        (butuh custom_adapter_framework, stock, purchase)
          -> custom_ppob_sale
              -> custom_ppob_va                 (butuh custom_accounting_full)
              -> custom_ppob_pps_gateway
              -> custom_ppob_eraspace_bridge
              -> custom_ppob_oracle_bridge      (butuh paket python oracledb)
              -> custom_ppob_biller_digiflazz   (butuh requests)
              -> custom_ppob_rollup             (butuh custom_accounting_reports)
              -> custom_ppob_commission         (butuh custom_pph_witholding, custom_coretax_bupot)
              -> custom_ppob_sla
```

### 7.3 Urutan go-live

1. Konfigurasi master + pemetaan akun di tenant SIT.
2. Aktifkan adapter mock; jalankan seluruh acceptance test.
3. Aktifkan adapter biller di sandbox; uji kontrak per endpoint.
4. Muat saldo pembuka mitra dan deposit biller (berita acara ditandatangani).
5. Nyalakan dual-run: sistem lama tetap otoritatif, Odoo menghitung paralel.
6. Rapat paritas harian sampai selisih 0 selama N hari berturut.
7. Cutover canary satu irisan (satu biller / satu produk / satu segmen mitra).
8. Perluas irisan hanya setelah recon break irisan sebelumnya nol.
9. Matikan sistem lama setelah window rollback berakhir.

### 7.4 Pemantauan

| Sinyal | Sumber | Ambang tindakan |
|---|---|---|
| Transaksi diproses melewati ambang | `custom.ppob.transaction` | > 0 setelah dua siklus reaper |
| Antrean lewatan bertambah | `ingest.skipped` | > 0 per hari perlu ditinjau |
| Saldo bucket < low-water-mark | `provider.bucket` | Peringatan ke ops (**perlu dibangun**, BR-OP-07) |
| Pelanggaran SLA | `throughput.sample.breach` | Dua jam berturut |
| Selisih wallet vs GL | Laporan rekonsiliasi | Apa pun ≠ 0 |
| Galat adapter | `custom.adapter.call.log` | Lonjakan tingkat galat |

### 7.5 Rollback

- **Per irisan cutover:** arahkan kembali trafik irisan tersebut ke sistem lama. Wallet tetap
  di Odoo bila fase saldo sudah stabil; yang dibalik hanya rute eksekusi.
- **Per rilis modul:** modul bersama harus di-`-u` pada seluruh basis data yang memasangnya
  sebelum image/container di-restart — menambah field pada addon bersama tanpa upgrade akan
  menjatuhkan setiap basis data yang belum di-upgrade.
- **Per transaksi:** refund manual oleh Ops dengan jurnal balik; tidak ada penghapusan record.

## 8. Pengujian

Status test otomatis di repo pada 2026-08-11:

| Modul | Berkas test | Jumlah `def test_` |
|---|---:|---:|
| `custom_ppob_sla` | 3 | 33 |
| `custom_ppob_biller_digiflazz` | 2 | 28 |
| `custom_ppob_oracle_bridge` | 5 | 23 |
| `custom_ppob_sale` | 2 | 13 |
| `custom_ppob_eraspace_bridge` | 2 | 13 |
| `custom_ppob_pps_gateway` | 2 | 10 |
| `custom_ppob_provider` | 2 | 9 |
| `custom_ppob_va` | 2 | 6 |
| `custom_ppob_core` | 0 | **0** |
| `custom_ppob_wallet` | 0 | **0** |
| `custom_ppob_commission` | 0 | **0** |
| `custom_ppob_rollup` | 0 | **0** |
| **Total** | **20** | **135** |

Yang wajib ditambahkan sebelum go-live (gap G3), diurut berdasarkan risiko uang:

1. **Wallet** — debit melampaui ceiling, wallet beku, kredit inklusif pajak, konkurensi dua
   kursor pada wallet yang sama, kebenaran `balance_after`.
2. **Rollup** — idempotensi menjalankan dua kali, mode PPN per kelas, pengecualian jurnal
   non-GL dari laporan.
3. **Commission** — pemilihan aturan, pemotongan PPh 23 dengan/tanpa NPWP, settlement.
4. **Core** — resolusi akun berbasis peran, `_get_sell_price` tanpa tier, keunikan kode.

Uji tambahan di luar unit test: uji beban pada volume puncak yang disepakati, uji konkurensi
dua kursor, dan **uji paritas dual-run** yang membandingkan marjin, status akhir, saldo deposit,
dan faktur ringkas terhadap sistem lama.

## 9. Utang teknis & trade-off yang diketahui

| # | Utang teknis | Dampak | Rencana |
|---|---|---|---|
| T1 | API wallet sinkron belum ada (G1) | Odoo belum bisa jadi otoritas saldo bagi switcher luar | Bangun 5 endpoint + kolom hold + test |
| T2 | Bridge masih pola 2-feed dari konsep lama (G2) | Feed POS tidak lagi merepresentasikan desain | Ganti feed POS dengan API wallet; pertahankan feed H2H untuk dual-run |
| T3 | Nol test pada 4 modul, termasuk wallet (G3) | Perubahan jalur uang tanpa jaring pengaman | Paket test wajib sebelum perubahan skema wallet |
| T4 | Digiflazz prepaid tanpa `inquiry()`/`status()` (G4) | Reaper tak bisa auto-resolusi jalur itu | Webhook vendor atau prosedur ops manual terdokumentasi |
| T5 | Gateway PPS tanpa anti-replay & pemeriksaan kesegaran (G5) | Klaim keamanan lebih besar dari kenyataan | Tambahkan nonce + pemakaian `max_clock_skew_s`, atau koreksi dokumentasi modul |
| T6 | MD5 pada gateway PPS | Kelemahan kriptografis yang diwarisi kontrak vendor | Tetap; kompensasi IP allowlist + rahasia per mitra + idempotensi; butuh persetujuan tertulis keamanan klien |
| T7 | Tidak ada skrip konfigurasi tenant (G6) | Go-live tidak reproducible | Bangun skrip seed + konfigurasi |
| T8 | Target SLA deklaratif, tanpa penegakan | Tidak ada throttling saat lonjakan | Disengaja; penegakan adalah keputusan terpisah |
| T9 | PPN tidak diposting per transaksi | Perbedaan dengan intuisi finance | Disengaja (rollup); harus dinyatakan dan diterima Finance |
| T10 | `oracle_bridge` menambah dependensi `oracledb` pada image | Beban image untuk klien tanpa Oracle | Modul opsional; jangan dipasang bila tidak dipakai |

## 10. Jebakan platform Odoo 19 yang relevan

| # | Jebakan | Konsekuensi |
|---|---|---|
| J1 | Controller yang menulis harus `auth="public"` + `readonly=False` | `auth="none"` tidak punya `env.user` sehingga posting jurnal gagal |
| J2 | Request `auth="public"` tidak punya konteks perusahaan | Harus mengikat perusahaan eksplisit sebelum menyentuh ORM, jika tidak default mata uang/jurnal tidak menyala |
| J3 | `_sql_constraints` diabaikan Odoo 19 | Semua constraint harus `models.Constraint`; verifikasi lewat `pg_constraint` |
| J4 | `res.groups` memakai `privilege_id` dan `user_ids` | Definisi grup versi lama tidak akan termuat |
| J5 | Field pada addon bersama bersifat *stored* | Menambah field lalu restart tanpa `-u` di semua basis data akan menjatuhkan basis data yang tertinggal |
| J6 | `account.code` company-dependent | Membaca kode akun tanpa `with_company` menghasilkan nilai kosong |
| J7 | Dua container memuat `queue_job` sekaligus | Pemilihan runner saling mengunci dan seluruh job berhenti |

## 11. Kriteria penerimaan teknis

1. Seluruh acceptance test FSD §10 lulus pada tenant produksi.
2. Cakupan test untuk wallet, rollup, commission, dan core sudah ada dan hijau (gap G3 tertutup).
3. API wallet sinkron terpasang, bertanda tangan, idempoten, dan lulus uji konkurensi (G1).
4. Uji konkurensi dua kursor pada wallet dan bucket lulus tanpa saldo negatif.
5. Uji beban pada volume puncak yang disepakati memenuhi target latensi p95.
6. Seluruh endpoint uang menegakkan tanda tangan + allowlist IP; gap G5 tertutup atau
   dokumentasinya dikoreksi dan disetujui keamanan klien.
7. Skrip konfigurasi tenant tersedia dan dijalankan untuk membentuk lingkungan produksi (G6).
8. Rekonsiliasi wallet vs GL, deposit vs biller, dan faktur ringkas menghasilkan selisih 0 pada
   periode paritas yang disepakati.

---

*Dokumen berikutnya: [`04-Architecture.md`](04-Architecture.md).*
