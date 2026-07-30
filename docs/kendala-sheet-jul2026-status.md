# Status "List Kendala System ODOO" — EO (ARKA-AIM) & FASHION (Levi's/EBR)

Sumber: sheet klien `List Kendala System ODOO`
(`docs.google.com/spreadsheets/d/1dPHA5XX6M6mzeMT8KzSkVaaJFb6dQEuJ2MHIQ_ByNQk`,
owner ari.roodo@gmail.com, modified 2026-07-29).
Scope review: worksheet **EO** (15 item, live di `prd_arkaaim`) dan **FASHION**
(13 item, live di `prd_levis_begbal`). Worksheet **OTOMOTIF** (EIVO/EDOO, 16 item)
tidak masuk scope.

Tanggal review & eksekusi: **2026-07-30**. Semua item di sheet ditandai klien
"Not Yet" — audit menunjukkan sebagian sudah live.

> **STATUS POSTING: DITAHAN.** Backlog depresiasi Juni 2026 (Rp 565.523.083,57)
> **belum diposting** ke `prd_arkaaim` dan cron depresiasi **masih non-aktif** di
> semua DB, menunggu klarifikasi klien. Lihat [Menunggu klarifikasi klien](#menunggu-klarifikasi-klien).

---

## 1. Yang sudah diubah

### 1.0 Ronde kedua (2026-07-30, sore)

Lanjutan setelah ronde pertama: **FASHION #6/#7** (install `custom_wms_reports`
+ 2 dependensi di `prd_levis_begbal`), **EO #14** (kolom No. FP Masukan /
Keluaran di GL), **FASHION 1.3** (4 kolom Ekualisasi + pelebaran sumber data),
**FASHION #2** (Rekap PPh kini menangkap PPh dari native tax & jurnal manual),
**FASHION #11** (reset to draft tidak lagi menghilangkan keterangan / meng-orphan
jurnal PPh). Commit `849fadc`, `45b5f78`.

Versi akhir, seragam di semua DB yang memilikinya:
`custom_accounting_reports` **19.0.0.11.0** (16 DB) ·
`custom_tax_id` **19.0.0.5.0** (14 DB).

> **INSIDEN — 13 DB sempat rusak, sudah dipulihkan.** `custom_tax_id` 19.0.0.5.0
> menambah kolom `account_move_line.x_custom_tax_label`. Kode disinkronkan ke
> `/opt` tetapi `-u` hanya dijalankan di satu DB; karena `/opt` di-mount ke
> container yang melayani semua tenant, field itu masuk registry semua DB
> sementara kolomnya hanya ada di satu → **setiap pembacaan vendor bill gagal**
> di 13 DB, 5 di antaranya produksi. Dipulihkan dengan mengembalikan `/opt` ke
> git HEAD + restart container (± 15 menit), lalu dirilis ulang secara benar ke
> **seluruh** DB dalam satu window. Tidak ada data hilang — belum ada yang
> menulis ke kolom tersebut. Backup diambil sebelum rollout.
>
> Efek samping yang ikut ditemukan & diperbaiki: dua field wizard GL
> (`show_faktur_*`) dari `custom_accounting_reports` 19.0.0.10.0 juga membuat
> wizard GL gagal di 5 DB yang belum di-`-u` — termasuk `rnd_ppob` dan
> `gentlewoman`, yang **sebelumnya normal** (kolom lama seperti `show_clearing`
> ada; hanya kolom baru yang hilang). Jadi ini bukan drift lama seperti dugaan
> awal. Semuanya sudah di-`-u`.
>
> **Aturan yang berlaku sejak sekarang:** perubahan pada shared addon yang
> **menambah field** tidak bisa dirilis ke sebagian DB. Enumerasi dan
> otorisasi semua DB pemilik modul lebih dulu; kalau hanya sebagian yang boleh,
> jangan sinkronkan ke `/opt` sama sekali — uji lewat container sekali pakai.
> Menyalin ke `/opt` **adalah** langkah deploy, bukan staging.

### 1.1 Batch A — dispatcher report (commit `5a405ab`)

`addons/ee_gap/custom_accounting_reports` **19.0.0.8.0 → 19.0.0.9.0**

Satu bug menutup **3 keluhan klien**: EO #5, FASHION #3, FASHION #8.

Tiga report sudah lengkap (model + wizard + menu + template) tapi report code-nya
tidak pernah didaftarkan di `REPORT_MODEL_MAP`, yang fallback-nya
`custom.report.trial.balance`. Akibatnya View/Print mengembalikan Trial Balance
tanpa error apa pun. Export XLSX tetap benar karena wizard memanggil model
langsung — "XLSX benar tapi layar/PDF salah" adalah sidik jari bug ini.

| Perubahan | File |
|---|---|
| Daftarkan `purchase`, `credit_limit`, `ppn_masukan_import` | `models/custom_report_dispatch.py` |
| Cabang router QWeb `purchase` + `credit_limit` (template sudah di-load manifest tapi tidak pernah `t-call`; PDF cetak "Unknown report") | `reports/report_common.xml` |
| `_resolve_model_name()` + `_logger.warning` saat report code tidak terdaftar (fallback dipertahankan agar wizard lama tidak hard-error) | `models/custom_report_dispatch.py` |

Dua temuan tambahan **di luar sheet klien**: `credit_limit` kena bug yang sama
(belum dilaporkan klien), dan router QWeb juga bolong — kalau hanya map yang
diperbaiki, tombol Print tetap rusak.

**Verifikasi** (screen vs `_compute`, data nyata):
`prd_levis_begbal` purchase 69 baris / PPN Masukan 27 · `prd_arkaaim` 9 / 3.

### 1.2 Batch B — config ARKA (commit `8db557e`)

Script baru `scripts/tenants/arkaaim/setup_downpayment_account.py` (preview-first,
idempoten, commit/rollback eksplisit).

**EO #6 — jurnal DP tidak lagi masuk COA penjualan.** `downpayment_account_id`
NULL di kedua company, dan `sale_make_invoice_advance.py:211` memakai
`downpayment_account_id or account` → DP jatuh ke akun pendapatan produk.
Sekarang menunjuk `2108100001` *Advances from customers - Third parties*
(`liability_current`).

Script resolve **by code + company**, bukan hardcode id: CoA `prd_arkaaim`
per-company sehingga kode yang sama ada dua record (id 309 = AIM, id 1022 = ARKA),
dan `account.code` company-dependent di Odoo 19 sehingga lookup harus lewat
`with_company`. Ada guard agar field tidak diarahkan ke akun non-`liability_current`.

Diterapkan ke `prd_arkaaim` (2 company). Re-run melaporkan `OK / 0 changes`.

### 1.3 Batch C — PPh otomatis per kode objek ARKA

**EO #11.** Engine `custom_tax_id` sudah terpasang tapi registry-nya kosong
(`tax_withholding_category` = 0, `tax_withholding_rule` = 0), sementara
`prd_levis_begbal` punya 108/107 ter-mapping penuh.

- `custom_tax_id` di-upgrade **19.0.0.4.0 → 19.0.0.4.2** di `prd_arkaaim`
  (kode sudah ada di `/opt`, hanya perlu `-u`) — sekaligus membawa fix double
  booking PPh yang sudah ada di Levi's.
- Load 107 kode objek via script existing `scripts/tenants/levis/70_load_withholding.py`
  **tanpa modifikasi** — script-nya ternyata tenant-agnostic (iterasi semua company,
  resolve COA per company, SKIP + log kalau tidak ada).

Hasil: **107 kategori + 214 rule** (107 × 2 company), 0 rule tanpa akun, 0 SKIP.
Distribusi cocok: art 4(2) 20 · art 21 2 · art 23 140 · art 26 52 · 28 baris
tarif fleksibel (14 × 2 company). Keempat COA PPh payable
(`2104100001/3/5/8`) ada di kedua company.

Modul legacy `custom_pph_witholding` (namespace `custom.witholding.*`) terpasang
di `prd_arkaaim` tapi **tidak terpakai** (0 record) dan hanya menambah tombol
wizard manual — tanpa override `_post`, jadi tidak double-book dengan `custom_tax_id`.

### 1.4 Batch E — depresiasi bulanan (commit `d1c8952`)

`addons/ee_gap/custom_accounting_asset` **19.0.0.4.0 → 19.0.0.5.0**

**EO #9.** Akar masalahnya bukan penomoran: **seluruh 159.360** baris depresiasi
`move_id IS NULL` — jurnalnya belum pernah dibuat sama sekali. Cron `active=f`,
dan saat terakhir jalan (2026-06-17) belum ada yang jatuh tempo sehingga posting 0
lalu dimatikan.

Menyalakan cron apa adanya akan **memperburuk** keluhan: `_post_due_depreciation`
membuat satu `account.move` **per baris per aset** → 3.320 dokumen untuk Juni saja,
~119.520 sampai 2029. Yang diminta klien justru satu dokumen bulanan.

| Perubahan | Detail |
|---|---|
| Grouping | Satu move per `(company, journal, akun beban, akun accum, tanggal)`. Di-key ke **tanggal baris**, bukan bulan, supaya aset yang jadwalnya jatuh di tanggal lain tidak tertarik ke tanggal akuntansi aset lain. Detail per-aset tetap di subledger. |
| Opt-out | `custom_accounting_asset.group_depreciation_moves` (default **on**) untuk tenant yang mau satu jurnal per aset. |
| `action_reverse` | Grouping merusak asumsinya — tadinya `_reverse_moves` seluruh `line.move_id`, jadi reverse 1 aset akan membatalkan sebulan penuh untuk semua aset di jurnal itu. Sekarang `_reverse_partial` membukukan reversal terarah hanya sebesar baris tersebut bila move-nya shared; reversal penuh terekonsiliasi dipertahankan bila baris memiliki move sendiri. |

**Struktur baris yang wajib dibaca sebelum posting** (`prd_arkaaim`):

| Kelompok | Jumlah | Periode | Arti |
|---|---|---|---|
| `posted=true, move_id NULL` | 39.840 | Jun-2025 → Mei-2026 | Opening accum-dep, **sengaja** tanpa GL (saldo awal GL sudah memuatnya). Sudah `posted` sehingga cron melewatinya — **memposting ini akan double-count.** |
| `posted=false` | 119.520 | Jun-2026 → Mei-2029 | Jadwal riil ke depan. |

**Verifikasi di `trn_arkaaim_begbal`** (mirror persis prd_arkaaim: 3.329 aset /
159.360 baris — `trn_arkaaim` tidak dipakai karena **0 aset**, register-nya sengaja
tidak diinstall di sana):

- 3.320 baris jatuh tempo → **1 jurnal** `MISC/2026/06/0001` 30-Jun-2026,
  Dr `7204103000` / Cr `1205203000` **565.523.083,57**. GL accum-dep bergerak
  persis sebesar itu, dan jumlah 3.320 baris = nilai jurnal (tanpa rounding drift).
- Reverse 1 baris (34.483,75): jurnal bulanan tetap posted dan **tidak berubah**,
  3.319 baris lain tetap posted, reversal terpisah `MISC/2026/07/0001` terbentuk.
- Mode opt-out dicek: 2 baris → 2 jurnal per-aset.

Blast radius nol: `with_move` = 0 di **semua** DB dan DB Levi's 0 aset, jadi tidak
ada akuntansi existing yang berubah.

---

## 2. Status per item

### Worksheet EO — ARKA-AIM (`prd_arkaaim`)

| # | Item | Status |
|---|---|---|
| 1 | Migrasi TB tanpa detail AR/AP per partner | Perlu dev + **data klien**. Seluruh DB hanya 9 baris AR (2 partner) / 19 AP (7 partner) |
| 2 | Kurs valas belum di-set | **Menunggu klien** — `res_currency_rate` 0 baris untuk IDR/USD/CNY. Config saja, nol kode |
| 3 | Kartu utang/piutang tidak terintegrasi | Report sudah ada (`payable_card`/`receivable_card`); kosong karena #1 |
| 4 | Bank masuk/keluar lewat COA perantara | **TIDAK REPRODUCE — tidak diubah.** Lihat §3 |
| 5 | Purchase report keluar Trial Balance | ✅ **SELESAI** (Batch A) |
| 6 | Jurnal DP masuk COA penjualan | ✅ **SELESAI** (Batch B) |
| 7 | Akses closing period | **Menunggu klien** — lock date NULL; perlu konfirmasi periode mana yang ditutup karena lock date memblokir posting |
| 8 | Nilai perolehan asset selisih vs report | Terkonfirmasi, **belum dikerjakan**. Ternyata **dua** komponen — lihat §3 |
| 9 | No document depresiasi per bulan | ⏸ Kode **SELESAI** + teruji di DB training; **posting produksi DITAHAN** |
| 10 | Sales report kosong | Perlu dev. Akar masalah sama dengan FASHION #9 — lihat §3 |
| 11 | PPh otomatis per kode objek | ✅ **SELESAI** (Batch C). Perlu 1 bill UAT oleh klien |
| 12 | Due date belum sesuai aturan Erajaya | **Menunggu klien** — 12 payment term sudah ada, perlu aturan eksaknya |
| 13 | Alamat AIM belum lengkap di Bill/Journal Voucher | **Menunggu klien** — alamat NPWP AIM. Company 1 street hanya `"Erajaya Plaza"` (street2 & zip kosong); company 2 lengkap |
| 14 | Kolom nomor seri faktur pajak di GL | Dev kecil, belum dikerjakan. `x_custom_nsfp` sudah ada di `account.move` |
| 15 | Format impor PSIAP faktur keluaran | **Menunggu template klien** — 0 hasil "PSIAP" di seluruh addons tree |

### Worksheet FASHION — Levi's/EBR (`prd_levis_begbal`)

Item 1 klien berisi 6 sub-request.

| # | Item | Status |
|---|---|---|
| 1.1 | Rekap PPh + 5 kolom tambahan | ✅ **SUDAH LIVE SEBELUMNYA** — kelima kolom sudah ada. Nol development, cukup ditunjukkan |
| 1.2 | Report Import PPN Masukan (8 kolom) | ✅ **SELESAI** — report sudah punya persis 8 kolom itu; terblokir bug Batch A, kini terbuka |
| 1.3 | Report Ekualisasi Biaya vs Objek PPh | Partial. Report ada; kurang 4 kolom (NPWP, COA Expense, No. Dok Jurnal, Nilai PPN) |
| 1.4 | Report Upload Retur Pajak | **Menunggu template Coretax dari klien** |
| 1.5 | Report Upload Faktur Keluaran | **Menunggu template XLS Pajakku.** `custom_coretax_pajakku` adalah API adapter, bukan penulis template |
| 1.6 | Mapping COA jurnal PPh, tetap editable | ✅ **SUDAH TERPENUHI** — 107 rule active, `account_id` NULL = 0. Cukup konfirmasi COA sesuai sheet tim Tax |
| 2 | Jurnal PPh manual tidak muncul di Rekap PPh | Gap nyata, belum dikerjakan — lihat §3 |
| 3 | Import PPN Masukan keluar Trial Balance | ✅ **SELESAI** (Batch A) |
| 4 | GL Open items / Outstanding balance | Build baru, belum dikerjakan |
| 5 | Report mapping vendor bill ↔ payment number | Build baru. **Duplikat item 13** — kerjakan sekali |
| 6 | On Hand Inventory report | Kode **sudah ada** (`custom.wms.stock.summary.report`), belum diinstall. Keputusan: **install `custom_wms_reports`** |
| 7 | Purchase Return report | Kode **sudah ada** (`custom.wms.purchase.return.report`), belum diinstall. Sama seperti #6 |
| 8 | Purchase report keluar Trial Balance | ✅ **SELESAI** (Batch A) |
| 9 | Sales report kosong | Perlu dev — lihat §3 |
| 10 | Sales report detail ala X24DN | Build terbesar. Data sebagian besar ada; gap = **Register** (tidak dipersist) dan **COGS per baris + Margin** (COGS periodik per-OU via `levis.cogs.run`) |
| 11 | Keterangan PPh/PPN hilang saat reset to draft | Bug nyata, belum dikerjakan — lihat §3 |
| 12 | Modul Petty Cash all store | ✅ **SUDAH TER-DEPLOY** — `custom_petty_cash` 19.0.0.4.0 terinstall, 0 record. Perlu config per-store + training |
| 13 | Report payment bill | Duplikat item 5 |

**Rekap:** 8 item selesai/sudah live · 1 tidak reproduce · 9 menunggu input klien ·
11 sisa development.

---

## 3. Temuan yang mengoreksi asumsi sheet

Empat hal di mana kondisi sistem berbeda dari yang ditulis klien. Perlu dibahas
sebelum dijadikan development.

**EO #4 — tidak reproduce, dan tidak diubah.** Klien menulis bank masuk/keluar
lewat COA perantara. Faktanya `payment_account_id` NULL di semua
`account_payment_method_line`, yang di Odoo 19 berarti payment posting
**langsung** ke `journal.default_account_id`. Satu-satunya payment yang posted
(id 11): Dr `1103019290` BCA Main Bank / Cr `1106000001` Trade Receivables —
tanpa perantara. `account_bank_statement` = 0, jadi jalur `suspense_account_id`
juga belum pernah dipakai. **Perlu ditanya transaksi mana yang mereka lihat.**
Temuan sampingan: suspense account company 1 masih `101402` (format default Odoo
6 digit), tidak konsisten dengan `1103000002` di company 2.

**EO #9 bukan masalah penomoran** — jurnalnya belum pernah terbentuk sama sekali
(159.360 baris `move_id NULL`). Sudah ditangani, lihat §1.4.

**EO #8 ada dua komponen, bukan satu:**

| Komponen | Register | GL | Selisih |
|---|---|---|---|
| Nilai perolehan | 27.145.108.236 | `1205104000` 27.110.131.391 | **34.976.845** |
| Accum. depresiasi | 6.786.277.002,84 (baris opening) | `1205203000` 7.341.288.299 | **≈ 555.011.296** |

**EO #10 + FASHION #9 satu akar masalah.** `custom_report_sales.py` domain-nya
hanya `move_type in (out_invoice, out_refund)`. `prd_arkaaim` punya 1 customer
invoice (revenue ada di move `entry` saldo awal); revenue Levi's ada di **16.064
`pos.order`**. Report-nya tidak rusak — sumber datanya salah untuk kedua tenant.
Ini prasyarat FASHION #10.

Dua bug lain yang terkonfirmasi tapi belum dikerjakan:
**FASHION #11** — tidak ada override `button_draft` di `custom_tax_id` maupun
`custom_levis_localization`, sehingga saat reset to draft JE PPh
(`x_custom_withholding_move_id`) tetap posted & orphan lalu guard idempotent
memblokir regenerasi saat re-post; core Odoo juga me-recompute label tax line.
**FASHION #2** — Rekap PPh hanya membaca `account.move.withholding.line` yang
diisi saat bill di-post, jadi JE PPh yang diketik manual tidak terlihat.

---

## 4. Jejak deployment

**Modul & DB**

| Modul | Versi | DB |
|---|---|---|
| `custom_accounting_reports` | 19.0.0.9.0 | 11 DB: prd_arkaaim, prd_levis_begbal, prd_levis, prd_levis_AP, prd_detail_levis, trn_arkaaim, trn_arkaaim_begbal, rnd_levis, demo_updated_levis, tst_mdm_levis, tst_mdm_api |
| `custom_tax_id` | 19.0.0.4.2 | prd_arkaaim |
| `custom_accounting_asset` | 19.0.0.5.0 | **trn_arkaaim_begbal saja** (produksi sengaja belum) |

`/opt/odoo-platform` disinkronkan untuk ketiga modul (dicek bebas drift terhadap
git HEAD sebelum overwrite). Container `odoo19-platform-odoo` direstart untuk
Batch A (perubahan `.py` butuh restart; `-u` hanya me-reload registry).

**Drift pre-existing yang dibiarkan** (bukan akibat perubahan ini): `rnd_ppob` dan
`gentlewoman` masih `custom_accounting_reports` 19.0.0.5.0, beberapa versi di
belakang — upgrade akan menurunkan model/menu baru ke tenant yang belum pernah
punya, jadi itu keputusan tersendiri. Tiga snapshot `*_bak_20260709` juga dilewati.
Error `custom_retail_import_api` di 2 DB tst_mdm juga pre-existing (modul hanya ada
di `/home`, tidak di `/opt`).

**Backup** (pg_dump di dalam container postgres, ukuran & integritas gzip
diverifikasi — bukan gzip kosong 20 byte):

- `prd_arkaaim`, `prd_levis`, `prd_levis_begbal`, `prd_levis_AP`, `prd_detail_levis`
  → `*-pre-dispatch-fix-20260730-035459.sql.gz`
- `prd_arkaaim` → `*-pre-withholding-20260730-041117.sql.gz`
- `trn_arkaaim_begbal` → `*-pre-depr-20260730-062402.sql.gz`

**Commit** (branch `feat/industry-packs`, **belum di-push**):
`5a405ab` · `8db557e` · `d1c8952`

---

## 5. Menunggu klarifikasi klien

### Hold aktif

**Posting depresiasi `prd_arkaaim` — DITAHAN atas keputusan sendiri.** Backlog
Juni 2026 **Rp 565.523.083,57** (3.320 baris) belum diposting dan cron depresiasi
masih non-aktif di semua DB. Kode sudah siap dan teruji di `trn_arkaaim_begbal`.

Catatan operasional saat nanti dieksekusi: `odoo shell` rollback saat keluar
**tapi nomor `ir.sequence` tetap terpakai**, jadi lakukan sekali jalan langsung
commit — jangan dry-run dulu — supaya tidak ada gap nomor jurnal.

### Butuh nilai/dokumen dari klien

| Item | Yang dibutuhkan |
|---|---|
| EO #2 | Daftar kurs yang dipakai (kurs tengah BI / kurs pajak) dan per tanggal apa |
| EO #4 | Transaksi mana yang menunjukkan COA perantara (tidak reproduce di sistem) |
| EO #7 | Periode mana yang mau ditutup (lock date memblokir posting) |
| EO #12 | Aturan due date Erajaya yang eksak |
| EO #13 | Alamat AIM persis sesuai NPWP |
| EO #1 | Listing outstanding AR/AP per pelanggan/vendor |
| EO #15 | Template impor PSIAP |
| FASHION 1.4 | Template import Coretax untuk Retur Pajak |
| FASHION 1.5 | Template XLS Mitra Pajakku |
| FASHION 1.6 | Konfirmasi COA jurnal PPh sesuai sheet tim Tax |

### Backlog development

Diprioritaskan: FASHION #9 → #10 (sales POS + detail X24DN), FASHION #11 & #2
(bug PPh), EO #8 (rekonsiliasi asset 2 komponen), EO #14 & FASHION 1.3 (dev kecil),
FASHION #4 dan #5/#13, serta install `custom_wms_reports` untuk FASHION #6/#7.
