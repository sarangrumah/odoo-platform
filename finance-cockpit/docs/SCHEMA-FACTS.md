# Tahap 0 — fakta skema `prd_levis_begbal`

Diverifikasi 2026-08-28 lewat `information_schema` dan query langsung. Setiap
angka di sini diukur, bukan dibaca dari kode di `/home` — versi modul di
produksi lebih maju daripada git.

## Koreksi terhadap rencana

| Asumsi rencana | Kenyataan |
|---|---|
| IDR `rounding = 1.0` | **`0.01`** (`decimal_places = 2`). Ambang `is_zero` = **0.005**, bukan 0.5 |
| m2m `levis_clearing_config_pos_receivable_rel` | **`levis_clearing_config_posrec_rel(config_id, account_id)`** |
| `account_lock_exception.state` | kolom itu tidak ada. Yang ada: `active`, `lock_date_field`, `lock_date`, `company_lock_date`, `end_datetime`, `user_id`, `reason` |
| GR/IR ditemukan lewat `levis_purchase_account_map.grir_account_id` | map hanya mengisi `grir_account_id = 319` untuk baris `non_trade`; saldo GR/IR yang sesungguhnya ada di akun **778** dan **780**. Temukan lewat prefix kode `21031091%`, jangan dari map saja |

## Angka dasar

- Company tunggal: `id = 1` (PT. ERA Busana Retailindo), `parent_path = '1/'` → root company id **1**, jadi `code_store ->> '1'`.
- `account_move_line`: **173.608** baris, tanggal **2026-01-01 … 2026-09-03**.
- `account_partial_reconcile`: **29.329** baris. Partial dengan sisi non-posted: **0** saat ini (guard tetap dipertahankan — logikanya benar dan report mendokumentasikannya).
- `account_move`: 49.565.
- Jurnal ber-`x_custom_report_excluded`: **0**. Cek #13 karena itu bernilai nol sekarang; filternya tetap dipasang.
- `res_company.fiscalyear_lock_date = 2026-07-31`; `tax`/`sale`/`purchase`/`hard` lock date kosong.
- `account_lock_exception`: 36 baris, **6 aktif** (id 49–54) tanpa `end_datetime` → permanen dan **disengaja**. Whitelist id-nya.

## Saldo acuan (posted, per 2026-08-28)

| | baris | saldo |
|---|---|---|
| `asset_receivable` | 10.990 | 13.702.159.829,00 |
| `liability_payable` | 1.021 | −55.052.711.976,32 |

## Volume GR/IR (menentukan strategi netting)

| Akun | Kode | Nama | Baris posted | Tanpa partner | Terbuka (view) | Saldo |
|---|---|---|---|---|---|---|
| 778 | 2103109121 | GR/IR Clearing-Third Parties-textile | 75.546 | 36.839 | 58.840 | 3.889.178.868,63 |
| 780 | 2103109123 | GR/IR Clearing-Third Parties-accessories | 6.203 | 3.164 | 4.732 | 196.132.356,00 |

Partial yang menyentuh akun 778: 16.598.

Akun rekonsiliasi lain dengan open item terbanyak: 654 Bank Suspense (3.144),
119 Trade Receivables (1.123), 872/869/870/868/873/871/875 POS Receivable per
tender, 295 Trade Payables (348), 884 POS Suspense Clearing (81).

## Konfigurasi clearing

`levis_clearing_config` id 1: suspense **654**, MDR **465**, AR **119**, sweep
**693**, bank charge **600**, `settlement_lag_days = 1`, `lookback_days = 10`.
`levis_clearing_config_posrec_rel` **kosong** — akun POS receivable belum
didaftarkan di config; temukan lewat prefix kode `11060001%` sampai config diisi.

`levis_pos_clearing`: **satu** run saja — id 10, `POSCLR/2026/0010`,
`POSCLR-2026-08`, state **`computed`** (belum diposting), 2026-08-01…08-31.
Konsekuensi: cek #10 dan #12 belum punya run terposting untuk diuji; halaman
POS akan tipis datanya sampai run berikutnya diposting.

## Kolom yang benar-benar ada

- `levis_pos_clearing` (30 kolom): tidak ada `total_*`, `short_count`,
  `mismatch_count` — semuanya `compute` tanpa `store`. Yang ada:
  `bal_suspense_before/after_sim/after_actual`, `bal_mdr_*`, `bal_ar_*`,
  `posrec_open_before/after_sim/after_actual`, `posrec_lines_before/after_actual`,
  `warning_text`, `ar_fallback`, `ignore_warnings`.
- `levis_pos_clearing_line` (40 kolom) memuat `statement_amount`, `gross`, `mdr`,
  `mdr_booked`, `cash_in`, `allocated`, `short_amount`, `mismatch_amount`,
  `state`, `block`, `kind`, `channel`, `mid_key`, `tid_key`,
  `analytic_account_id`, `x24_match`, `x24_tender`, `x24_tender_mismatch`,
  `matched_total`, `match_gap`, `run_state`, `run_period_ref`, `move_name`.
- `account_account` fisik: `code_store`, `name`, `account_type`, `reconcile`,
  `non_trade`, `active`, `l10n_allow_payment_destination`. **Tidak ada** `code`.
- Ketiga view ada: `custom_reconcile_account(id, account_id, line_count, debit,
  credit, residual, oldest_date)`, `custom_followup_stat_by_partner`,
  `custom_report_journal_item_analysis`.
