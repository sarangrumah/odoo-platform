# Handover — ARKA-AIM

Rangkuman vertikal ARKA-AIM (drone rental & drone show) per **28-Sep-2026**. Setiap angka dan tanggal diberi sumber dalam tanda kurung — nama catatan memory, path repo, nomor PR, atau nama DB — supaya dokumen tetap bisa diaudit setelah catatan memory dihapus.

> Batas dokumen ini: semua klaim berasal dari catatan memory + repo, **bukan** dari query langsung ke DB hari ini. Sebelum bertindak atas angka apa pun, verifikasi ulang ke DB. Beberapa catatan menandai dirinya sendiri sebagai basi dan itu ditulis sebagai peringatan, bukan fakta.

## 1. Ringkasan vertikal

Dua perusahaan di **satu** database, bukan dua tenant:

| id | Perusahaan | Singkatan | Peran | Sumber |
| --- | --- | --- | --- | --- |
| 1 | PT Aero Inovasi Media | AIM | pemilik armada drone | arkaaim-golive-issue-sheet |
| 2 | PT Aero Reksa Kreasi Angkasa | ARKA | penjual jasa drone show | arkaaim-golive-issue-sheet |

Model bisnisnya: **ARKA menjual jasa drone show ke pelanggan akhir** (lump-sum per event, qty 1), lalu **membeli sewa unit dari AIM** lewat rantai intercompany. AIM yang memegang 3.590 unit aset drone dan komponennya (rental-sale-deployment, arkaaim-event-chain-analytic).

ARKA **tidak** memakai `rental.order` sebagai dokumen komersial: per 8-Sep-2026 `prd_arkaaim` punya 11 sale order dan **0 rental order** (rental-sale-deployment).

| DB | Peran | Catatan penting | Sumber |
| --- | --- | --- | --- |
| `prd_arkaaim` | produksi | satu-satunya DB yang dikonfigurasi penuh | arkaaim-gr-journal-grir |
| `trn_arkaaim` | training | CoA **berbeda** (l10n_id 8 digit) | arkaaim-trade-nontrade-purchase-type |
| `trn_arkaaim_begbal` | klon UAT begbal | catatan 13-Aug: **sudah tidak ada** | arkaaim-drone-asset-in-stock |
| `scratch_asset_lifecycle` | klon uji sekali pakai | restore segar prd_arkaaim | asset-lifecycle-module |

> **`erp_dev_aimarka` TIDAK ditemukan di sumber mana pun** yang dibaca (memory + repo). Yang ada riwayatnya adalah `uat_aimarka`, dan DB itu **sudah dihapus dari cluster** beserta satu-satunya dump-nya atas instruksi user (no-automated-tenant-db-backups). Kalau `erp_dev_aimarka` memang ada hari ini, ia tidak terdokumentasi — jangan diasumsikan setara `prd_arkaaim`.

Perbedaan CoA antar DB bukan detail kosmetik. `prd_arkaaim` memakai chart EBR 10 digit (mis. `2103100001`), `trn_arkaaim` memakai chart generik 8 digit (`21100010`). Banyak skrip konfigurasi karena itu menghasilkan mapping **kosong** di trn, dan itu **degradasi yang disengaja, bukan bug** (arkaaim-trade-nontrade-purchase-type, cash-advance-arkaaim).

Yang sudah LIVE di `prd_arkaaim` per 8-Sep-2026: register aset drone per unit + serial fisik, aset juga hadir di stok, lifecycle kondisi aset, jurnal GR/IR saat receipt, charge-out biaya show, penomoran PO Trade/Non-Trade, analytic per event, cash advance/petty cash, payment voucher, admin fee, wizard Lock Dates, dan 8 laporan tambahan.

## 2. Modul yang dimiliki

Modul tenant-scoped (`addons/_tenants/`), versi dibaca dari `__manifest__.py` di checkout `/home/odoo-erp/odoo-platform` branch `feat/asset-lifecycle`:

| Modul | Versi | Fungsi inti |
| --- | --- | --- |
| `custom_arka_show_date` | 19.0.1.10.0 | Show Date, event, deskripsi DP, charge-out biaya show |
| `custom_arka_aim_asset_register` | 19.0.2.1.0 | subledger aset drone per unit + serial |
| `custom_arka_aim_purchase_type` | 19.0.1.2.0 | PO Trade/Non-Trade, AP routing, jurnal GR/IR |
| `custom_arka_aim_opening_balance` | 19.0.2.0.0 | saldo awal 31-Mei-2026 (detail) |
| `custom_arka_fx_header` | 19.0.1.1.0 | header kurs valas + popup Register Payment |
| `custom_arka_aim_numbering` | 19.0.1.0.0 | penomoran dokumen + `x_monthly_reset` |
| `custom_arka_aim_seed` | 19.0.1.1.0 | seed CoA — **uninstalled di 16 DB** |

Modul `ee_gap` (shared) yang membawa fitur ARKA-AIM:

| Modul | Versi | Catatan |
| --- | --- | --- |
| `custom_rental` | 19.0.0.4.0 | terpasang di 3 DB ARKA saja |
| `custom_rental_bom_explosion` | 19.0.0.2.0 | dibangun untuk bundel 1.500 drone, belum dipakai |
| `custom_rental_invoicing` | 19.0.0.1.0 | auto-invoice-on-return |
| `custom_asset_lifecycle` | 19.0.1.0.0 | kondisi rusak/hilang/perbaikan |
| `custom_asset_stock_link` | 19.0.1.2.0 | aset → serial di stok |
| `custom_asset_from_receipt` | 19.0.0.3.0 | GR → aset (pooled/serial) |
| `custom_accounting_asset` | 19.0.0.7.0 | register aset generik + pooled quantity |
| `custom_ops_reports` | 19.0.0.2.0 | 5 laporan operasional (opname, event movement, dll.) |
| `custom_petty_cash` | 19.0.0.6.2 | cash advance + petty cash |
| `custom_payment_admin_fee` | 19.0.1.1.0 | biaya admin bank di Register Payment |
| `custom_payment_fx_rate` | 19.0.1.1.0 | input kurs manual di payment |
| `custom_payment_voucher` | 19.0.1.0.0 | Payment Voucher / Receipt PDF |
| `custom_payment_methods_id` | 19.0.1.0.0 | Giro + Bank Transfer |
| `custom_intercompany_procurement` | 19.0.0.3.0 | mirror PO → SO sister company |

Dua modul hidup di produksi tapi **tidak ada di checkout `/home` branch `feat/asset-lifecycle`**: `custom_service_receipt` (jasa ikut GR, PR #219 MERGED `74dc1ab`, service-receipt-module) dan `custom_rental_sale` (SO → deployment, PR #227 di atas PR #222, rental-sale-deployment). Keduanya ada di `origin/main` dan `/opt`. Ini konsekuensi langsung dari branch `/home` yang tertinggal.

> **JANGAN pasang `custom_payment_admin_fee` berdampingan dengan `custom_levis_localization`** — keduanya mewarisi wizard yang sama, grup Admin Fees dirender dua kali dan dua onchange saling berebut `amount` (payment-admin-fee-module).

## 3. Aset drone

### Register aset per unit

Register aset (`custom.fixed.asset`) adalah **subledger**, bukan sumber jurnal perolehan. Drone sudah ada di GL saldo awal AIM sebagai lump sum, jadi modul register **tidak memposting jurnal apa pun**; `custom.fixed.asset.create()` tidak pernah menyentuh GL (aim-drone-asset-register, `addons/_tenants/custom_arka_aim_asset_register/MODULE_KNOWLEDGE.md`).

| Akun | Uraian | Nilai |
| --- | --- | --- |
| `1205104000` | Fixed Assets-Cost-Office & outlet equipment | Dr 27.110.131.391 |
| `1205203000` | Accum depre-Office & outlet equipment | Cr 6.776.493.895 |
| | nilai buku | 20.333.637.496 |

Populasi register **sesudah rebuild 4-Aug-2026** (`docs/projects/arka-aim/BEGBAL_DETAIL.md`):

| Populasi | Unit | Nilai perolehan |
| --- | --- | --- |
| AIM `Registered` — Device | 1.500 | 22.641.197.295 |
| AIM `Registered` — Komponen Drone | 1.680 | 4.468.934.094 |
| AIM `Unregistered` — spare (reclass Office Supplies) | 144 | 42.101.540 |
| ARKA `Unregistered` — Alat Pendukung | 266 | 98.637.293 |

Total 3.590 unit; `sum(acquisition_value)` = **27.250.870.222,12**, dan angka itu dipakai sebagai invariant di setiap verifikasi pasca-deploy (asset-lifecycle-module, arkaaim-asset-serial-numbers). Selisih terhadap GL setelah rebuild tinggal **Rp 1,88** di cost dan **Rp 160,91** di akumulasi — murni pembulatan jadwal per unit, tidak dikoreksi ke GL (`docs/projects/arka-aim/BEGBAL_DETAIL.md`).

> **Selisih Rp 34.976.845 yang sering dikutip adalah angka register LAMA** (3.329 unit, harga PO seragam 30-Jan-2025, aim-drone-asset-register). Setelah rebuild 4-Aug-2026 selisih itu tidak berlaku lagi. Jangan mencampur dua generasi angka ini.

Trik penyusutan saldo awal: baris jadwal s/d **30-Jun-2026** ditandai `posted=True, move_id=False` karena Juni sudah dijurnal manual (`Depre-0626`), sehingga cron bulanan mulai **Juli-2026** dan tidak membukukan Juni dua kali. Penyusutan bulanan ke depan **564.794.390,59** vs `Depre-0626` 564.794.404, beda Rp 13,41 (`docs/projects/arka-aim/BEGBAL_DETAIL.md`).

### Serial fisik

Kolom **Serial Number** di `prd_arkaaim` dulu berisi kode aset (`AS0000868545`) untuk 3.590 dari 3.590 baris — bukan salah loader begbal, tapi wizard *Materialise Into Stock* yang sengaja menyalin `asset.code` → `serial_number`. Diperbaiki 8-Sep-2026: **3.100 serial fisik** dimuat (1.600 baterai + 1.500 drone), 490 unit sisanya memang tidak berserial. Verifikasi: 3.100 `with_serial`, 0 echo, `sum(acquisition_value)` tetap 27.250.870.222,12 (arkaaim-asset-serial-numbers).

> **Pemasangan kode↔serial ARBITRER per unit.** Tidak ada kunci join antara `Kode Aset` begbal dan serial listing; jumlah per jenis cocok persis sehingga dipasangkan **berurutan dalam tiap kelompok produk**. Populasi dan nilainya benar, **pasangan per unit bukan bukti**. Ganti `data/asset_serials.csv` utuh begitu klien kirim mapping asli — tidak ada kode yang perlu berubah (arkaaim-asset-serial-numbers).

Serial **tidak unik**: listing klien mengulang 8 serial baterai. Jangan pasang constraint unik, dan kartu `maintenance.equipment` dikunci pada **kode aset** bukan serial karena `maintenance.equipment.serial_no` punya `unique()` global (asset-lifecycle-module).

Git: PR **#217** (`effee9d`) lalu PR **#218** (`8c3f352`), keduanya MERGED ke main 8-Sep-2026 dalam urutan itu — #218 mencabut penulisan `serial_number`, #217 yang memindahkan laporan Opname ke FK (arkaaim-asset-serial-numbers).

### Aset juga hidup di stok

`custom_asset_stock_link` membuat setiap unit punya `lot_id` + `product_id`: 55 produk `FA/...` (serial, harga 0, kategori **Fixed Assets (Non-Valuated)**), 3.590 `stock.lot`, 3.590 quant, 3.590 `rental.asset`. Perlakuan akuntansi **tidak berubah** — stok murni pelacakan fisik dan bernilai nol; `account_move` 76 → 76 sebelum/sesudah (arkaaim-drone-asset-in-stock).

Guard nol-GL Odoo 19 butuh 3 syarat sekaligus: produk storable valued + lokasi punya `valuation_account_id` + `product.valuation == 'real_time'`. Selection Odoo 19 adalah `periodic` / `real_time` — kode gaya lama yang menulis `manual_periodic` **tidak akan pernah cocok dan diam-diam lolos** (arkaaim-drone-asset-in-stock).

> **JEBAKAN NAMA GUDANG.** AIM punya **EMPAT** gudang, semuanya `sequence = 10`: `WH` (id 1), `ARKA` (id 11), `DMG` (id 12), `WH/LM` (id 14). Gudang bernama `ARKA` itu **milik AIM**; gudang perusahaan ARKA yang sebenarnya adalah `WH-01` (id 13). Kode gudang TIDAK unik antar perusahaan — `search([("code","=",code)])` menyerahkan gudang AIM ke ARKA (bug nyata, diperbaiki di PR #232). Selalu sertakan `company_id`; kalau gudang harus ditebak, **tanya register lokasi mana yang menampung unit terbanyak** milik perusahaan itu (arkaaim-drone-asset-in-stock, asset-lifecycle-module).

Bug posisi fisik: `_sync_stock_from_lots` memfilter `("quantity", ">", 0)` di dalam `_read_group`, sehingga baris +1 terbaca sementara −1 diabaikan alih-alih di-net-kan. Akibatnya **2.572 dari 3.590** unit menyimpan `stock_location_id` = `ARKA/Stock` padahal fisiknya di PALEM. **SELESAI 8-Sep-2026**: posisi tersimpan kini 3.324 `WH/RUKO GUDANG PALEM` + 266 `WH-01/RUKO GUDANG PALEM`, **0 di ARKA/Stock** (arkaaim-drone-asset-in-stock).

> **Urutan wajib:** resync DULU, baru restart container. Kalau container lama (kode buggy) masih hidup, cron `_cron_sync_stock_locations`-nya menimpa balik hasil resync (arkaaim-drone-asset-in-stock, asset-lifecycle-module).

`ARKA/Stock` adalah **tujuan pinjaman (loan) by design** — unit dipindah ke sana lewat internal transfer saat dipinjamkan. Itu sebabnya bug netting menggigit: query lama melihat +1 keluar dan tidak pernah melihat −1 kembali (asset-lifecycle-module).

### Quant kembar

Fosil dari bug mislokasi di atas: `prd_arkaaim` sempat punya **5.144 pasangan (lot, lokasi) berbaris ganda** atas 2.572 serial, 11.929 baris total, 3.195 baris `quantity = 0`, 2.572 baris negatif — tapi **net semua = 1** dan **nol unit hilang atau ganda**. Konsekuensi hidupnya: baris `0.00` di PALEM itulah yang ditemukan reservasi Odoo dan diturunkan ke −1, jadi tiap pemindahan menambah satu pasangan baru (arkaaim-duplicate-quant-rows).

**SELESAI di produksi 8-Sep-2026 10:23 WIB** lewat `scripts/tenants/arkaaim/repair_asset_quants.py` (commit `943cf9c`, PR #232): **11.929 → 3.590 baris**, nol negatif, nol kosong, reservasi 0, `account.move` delta 0. Skrip memakai SQL bukan `unlink` — unlink quant di ORM menyesuaikan `reserved_quantity` sebagai efek samping dan melawan kolom yang sedang diperbaiki (arkaaim-duplicate-quant-rows).

> **PELAJARAN PROSEDUR:** perbaikan itu berjalan saat pengguna sungguhan sedang bekerja (uid 50 membuat 2 SO jam 10:20–10:21). Aman **secara kebetulan** karena `reserved_quantity` = 0 untuk seluruh serial aset. "Ada yang sedang bekerja di sistem?" masuk pre-flight bersama dump, bukan post-mortem (arkaaim-duplicate-quant-rows).

### Lifecycle rusak / hilang

`custom_asset_lifecycle` 19.0.1.0.0 (naik ke 19.0.1.2.0 lewat PR #232) — PR **#222 MERGED** 8-Sep-2026, **TERDEPLOY ke `prd_arkaaim` saja**, tidak terpasang di tenant lain. Nol dampak GL: `account_move` tetap 144, `account_move_line` 709, 152.640 baris penyusutan utuh (asset-lifecycle-module).

Aturan inti: **`condition` BUKAN `state`.** Aset rusak / diperbaiki / dilaporkan hilang tetap `state='running'` dan tetap disusutkan (IAS 16.55 / PSAK 16 — penyusutan berhenti saat penghentian pengakuan, bukan saat aset menganggur). Tidak ada kode di modul ini yang menulis `state`. Kondisi: ok / damaged / in_repair / repaired / missing / written_off, riwayat di `custom.asset.condition.log` (asset-lifecycle-module).

Wizard aset pengganti **memposting jurnal sendiri** (`DR aset / CR pendapatan ganti rugi` sebesar nilai wajar), karena `custom.fixed.asset.create()` tidak pernah memposting jurnal perolehan dan unit dari klien tak punya tagihan vendor (asset-lifecycle-module).

Akun yang disetujui user: rugi `7701000000` Loss on sale of Fixed Assets, pendapatan `7609000000` Reimbursement Income, jurnal MISC (AIM) / JM (ARKA). **BUKAN `7706000000`** — impairment bukan penghentian pengakuan (asset-lifecycle-module).

Cacat lintas-perusahaan (diperbaiki 8-Sep, PR #232): deploy pertama menaruh company 2 di gudang milik company 1 karena skrip memilih `DMG`/`WH/LM` hanya lewat kode. Stok menolak transfer lintas perusahaan → gagal keras saat operator melapor. ARKA sekarang dapat `WH-01/Damaged Assets` + `WH-01/Lost Assets`, dan `custom.asset.condition.log.from_location_id` mencatat asal SEBELUM unit pindah supaya `action_return_to_service` punya tujuan pulang (asset-lifecycle-module).

> **BELUM TERUJI DI PRODUKSI (per 8-Sep-2026).** Modul terpasang dan terkonfigurasi di `prd_arkaaim` tapi jalur kerjanya belum pernah dieksekusi di sana: `custom_asset_condition_log` = 0, aset dengan `condition <> 'ok'` = 0, `rental_order` / `repair_order` = 0 / 0, `stock_move` berdeskripsi `Asset %` = 0. Semua latihan damage/missing/dispatch ada di KLON. Jangan menulis atau berkata "sudah terbukti di lapangan" (asset-lifecycle-module).

### Aset pooled (per jumlah)

`custom_accounting_asset` 19.0.0.7.0 + `custom_asset_from_receipt` 19.0.0.2.0, PR **#203** dan **#204** sudah merge, TERDEPLOY 30-Agu-2026 ke 7 DB termasuk `prd_arkaaim` dan `trn_arkaaim`. Beli 5 unit lewat PO Non-Trade → SATU nomor aset berisi 5 unit; retire 1 unit mem-pro-rata atas unit yang masih dipegang (1/5, lalu 1/4) supaya `unit_acquisition_value` stabil (pooled-quantity-fixed-assets).

> **Report/SQL yang menjumlah baris penyusutan `posted` langsung akan OVERSTATE akumulasi aset pooled** — porsi yang dilepas disimpan di `retired_accumulated_depreciation` dan dikurangkan di compute, bukan dengan mengubah baris posted (pooled-quantity-fixed-assets).

`scripts/consolidate_pooled_assets.py` **belum pernah dijalankan dengan APPLY di DB mana pun**. Dry run di klon prd_arkaaim tanpa penjaga menawarkan menggabungkan 3.170 record jadi 10 — SALAH, karena seluruh register AIM terikat `lot_id`. Model sekarang MENOLAK aset ber-`lot_id`/`rental.asset`, dan dry run di AIM benar-benar menggabungkan 0 (pooled-quantity-fixed-assets).

### Jurnal penyusutan bulanan

`custom_accounting_asset` 19.0.0.5.0 (commit `d1c8952`) menggabungkan posting: satu `account.move` per `(company, journal, akun beban, akun akumulasi, tanggal)` alih-alih satu dokumen per baris per aset (3.320 dokumen untuk Juni saja). Opt out per tenant lewat `custom_accounting_asset.group_depreciation_moves = 0` (asset-depreciation-grouped-monthly-entry).

> **Grouping merusak `action_reverse` kalau lupa.** `_reverse_moves` atas `line.move_id` akan menghapus SELURUH periode untuk setiap aset yang berbagi entri itu. `_reverse_partial` membukukan Dr akum / Cr beban berdiri sendiri hanya sebesar baris itu (asset-depreciation-grouped-monthly-entry).

Baca flag baris sebelum menyentuh apa pun: di `prd_arkaaim` ada **39.840 baris `posted=true, move_id NULL`** (akumulasi saldo awal, sengaja tanpa GL — **memposting ini = dobel**) dan 119.520 baris `posted=false` (jadwal Jun-2026 → Mei-2029). Akar masalah "no document atas depreciation" bukan penomoran: seluruh 159.360 baris punya `move_id IS NULL` dan cron `cron_post_depreciation` `active=f` (asset-depreciation-grouped-monthly-entry).

> **Gotcha:** `odoo shell` rollback saat keluar, jadi uji posting terlihat sukses dan tak meninggalkan apa pun — tapi nomor `ir.sequence` TETAP terpakai. Lakukan satu run ter-commit di produksi (asset-depreciation-grouped-monthly-entry).

## 4. Sales -> deployment & event

### Rantai SO → PO → SO AIM

`custom_arka_show_date` **19.0.1.9.0**, flag `x_custom_event_tracking_enabled` NYALA di kedua company, **TERDEPLOY 8-Sep-2026** ke `prd_arkaaim` dan `trn_arkaaim`, 51 tes hijau di klon kedua DB. **MERGED ke main:** `24005d7` (PR **#221**) + `00a7efb` (PR **#229**) (arkaaim-event-chain-analytic).

- Field event ikut dari SO → `purchase.order` → vendor bill (`_prepare_invoice`) dan → SO mirror di AIM (override `_custom_create_ic_mirror_so`).
- Tombol `sale.order.action_custom_create_ic_purchase_order()` membuat PO **draft** ke sister company, harga dari supplier info — **bukan** harga customer.
- `custom.arka.event.mixin` memetakan `"<event> - <lokasi> - <dd.mm.yy>"` ke satu `account.analytic.account` plan **Event**, dicocokkan lewat `x_custom_event_key` (UNIQUE, uppercase, spasi diciutkan) dan dibuat **`company_id = False`** supaya pendapatan ARKA dan biaya AIM bertemu di satu akun.
- Pemetaan jual→beli (1.8.0): `product.template.x_custom_ic_purchase_product_id` ("Purchased As") memetakan produk "Jasa …" yang dijual ke produk "Sewa …" yang dibeli dari AIM, resolusi **satu lompatan saja**. Hasil: prd 3 pasangan, trn 1. Efek samping bagus: produk "Sewa" punya harga vendor, jadi baris PO tidak lagi berharga 0.

Gate `x_custom_event_tracking_enabled` sengaja **terpisah** dari `x_custom_show_date_enabled`: yang lama membuat Show Date wajib di SO dan menggeser jatuh tempo, jadi menyalakannya di AIM akan memblokir SO AIM tanpa show (arkaaim-event-chain-analytic).

> **Jebakan auto-lock SO.** `prd_arkaaim` menyalakan "Auto Lock Confirmed Sales Orders", jadi menulis ke baris SO SETELAH `super().action_confirm()` kena `UserError` "forbidden to modify ... in a locked order". Stamping analytic harus **sebelum** super(). Ketahuan hanya di klon prd, hijau di klon trn — uji di klon produksi, bukan cuma trn (arkaaim-event-chain-analytic).

Kondisi awal yang jadi alasan pekerjaan ini: event cuma teks bebas di header note PO; 7/7 faktur pelanggan ARKA ber-show-date tapi **1/12** vendor bill ARKA dan **0/11** vendor bill AIM; `analytic_distribution` terisi di **0 dari 709** baris jurnal (arkaaim-event-chain-analytic).

Backfill (`backfill_event_analytic.py`, DIJALANKAN 8-Sep): 6 PO dapat field event, 10 order di-stamp, 10 baris jurnal ditandai (Soekarno Cup pendapatan Rp 1.120.000.000, HUT RI 81 biaya Rp 288.000.000); trn no-op. Dua jebakan: SO terkonfirmasi TERKUNCI (harus `locked=False`, stamp, kunci lagi) dan **baris uang muka DIKECUALIKAN** — tanpa ini 5 baris jadi sampah di neraca (arkaaim-event-chain-analytic).

### Tagging event yang tersisa

Setelah backfill, `prd_arkaaim` menyisakan 648 baris "no evidence" yang dipilah `report_event_tagging_candidates.py` (PR **#236** MERGED `d6f8c643`, READ-ONLY). Yang kemudian di-tag 8-Sep atas persetujuan user: 8 baris `BILL/2026/08/0001` (Rp 129,2 jt) + baris pendapatan Rp 300 jt, semuanya ke event id **11** Danone 07.08.26. Danone kini Rp 420 jt pendapatan vs Rp 129,2 jt biaya; tetap 6 event (arkaaim-event-tagging-leftovers).

Bukti yang penting untuk dipahami: `INV/ARKA/2026/08/004` baris 1371 beruraian "Lokasi Taman Bagawan Bali **07.08.26**" padahal header `x_custom_show_date` = 28.08.26. **Show date di header BUKAN penanda event yang andal di DB ini; uraian baris lebih benar** (arkaaim-event-tagging-leftovers).

> **JANGAN tulis field event ke header FAKTUR PELANGGAN.** Menulis `x_custom_show_date` di `out_invoice` menambatkan ulang termin: di klon, jatuh tempo `INV/ARKA/2026/08/004` (piutang Rp 166,5 jt) melompat 28.08 → 07.08, **21 hari lebih awal**. Menghilangkan show date juga tidak boleh — label event butuh tanggalnya, tanpa itu pemanggil `create=True` bisa membuat akun analytic KEDUA untuk show yang sama. Faktur pelanggan di-tag di BARIS jurnalnya; PO aman (arkaaim-event-tagging-leftovers).

> **Jangan panik melihat "pendapatan tanpa analytic".** Baris uang muka (`is_downpayment=True`) duduk di `2108100001 Advances from customers` (liability_current), BUKAN pendapatan; analytic di situ tak pernah sampai ke P&L per Event. Pengecualiannya di `backfill_event_analytic.py` itu BENAR (arkaaim-event-tagging-leftovers).

Jebakan teknis: `account.move.write` core **memutasi dict `vals`** yang dioper (menyuntik `is_manually_modified`) — memakai ulang satu dict untuk write ke model lain → ValueError. Oper `dict(values)` per write (arkaaim-event-tagging-leftovers).

Yang sengaja DIBIARKAN: `PO/ARKA/2026/08/007` "AKIRA BACK JAKARTA" Rp 85 jt (Rp 70,5 jt sudah diterima dan mengendap di persediaan), tanpa SO/faktur/analytic; dan 3 PO menyebut show yang tak pernah jadi SO. Mengarang event dari note akan memasukkan typo "OPERRATIONAL" ke daftar akun dan memecah satu show jadi dua (arkaaim-event-chain-analytic, arkaaim-event-tagging-leftovers).

Cara bertindak kalau Finance sudah memutuskan: isi field event di PO/SO-nya lalu jalankan ulang `backfill_event_analytic.py` — **jangan menulis analytic lewat SQL** (arkaaim-event-tagging-leftovers).

### Alokasi overhead

`custom.arka.event.allocation` (1.9.0, PR **#229** MERGED `00a7efb`): periode + jurnal/akun mana yang dianggap overhead + basis (revenue / direct cost / equal / manual), Compute → Apply → Reset. Ditulis sebagai `analytic_distribution` berpersentase, jadi **TANPA jurnal**. `x_custom_event_allocation_id` di aml = kunci reversibilitas dan pencegah hasil alokasi jadi basis alokasi berikutnya. TERDEPLOY prd+trn tapi **INERT** — belum ada satu pun run; pilihan basis itu keputusan klien (arkaaim-event-chain-analytic).

> Di data Agustus 2026 hanya 1 event punya pendapatan ter-atribusi dan 1 punya biaya, jadi basis revenue = Soekarno Cup 100%, direct cost = HUT RI 81 100%. **Hanya *equal* yang bermakna** sampai atribusi langsung lebih luas (arkaaim-event-chain-analytic).

> **Jebakan tes:** analytic account event itu shared antar-company, jadi tes yang jalan di klon tenant bisa nyangkut ke event ASLI klien. Fixture dipindah ke Maret 2026 — tetap masa lalu, karena `action_post()` soft dan tanggal masa depan diam-diam tetap draft (arkaaim-event-chain-analytic).

### Charge-out biaya show

`custom_arka_show_date` **19.0.1.10.0**, `models/event_chargeout.py`, PR **#234 MERGED** (squash `483edde9`), TERDEPLOY prd+trn 8-Sep-2026, 65 tes hijau di klon prd (arkaaim-show-cost-chargeout).

Pemicu yang dipilih klien: **saat pendapatan event diakui**. Kuncinya, di ARKA uang muka masuk akun liabilitas dan tidak mengakui pendapatan, jadi entri pertama yang mengkredit akun income untuk sebuah event ITULAH pendapatannya — tak perlu rasio. Jurnal: `Dr COGS / Cr Persediaan`, jurnal STJ, tanggal = tanggal move pemicu, analytic event di KEDUA kaki, ref `ARKA-SHOWCOST:<analytic id>` (arkaaim-show-cost-chargeout).

**TANPA STATE — sengaja.** Tiap eksekusi menghitung ulang saldo yang masih ada di akun persediaan untuk event itu lalu mengkredit akun yang sama → saldo jatuh ke nol sendiri. Jalan dua kali tak menagih dua kali, biaya telat terambil penuh. Hanya saldo POSITIF yang dipindah (saldo negatif kalau "dikembalikan" akan mengarang aset) (arkaaim-show-cost-chargeout).

Akun tidak dikonfigurasi dua kali: akun persediaannya = `property_stock_valuation_account_id` kategori ber-`real_time`, jadi saklar `real_time` yang sama menyalakan GR journal DAN charge-out. Akun beban fallback dari param `custom_arka_show_date.event_chargeout_expense_codes` = `6199000000` (Erajaya) / `51000010` (chart generik trn). Satu-satunya event prd dengan pendapatan diakui saat itu: Soekarno Cup Rp 1,12 M, biayanya nol karena 39 receipt lama tak pernah menjurnal (arkaaim-show-cost-chargeout).

### SO → deployment

`custom_rental_sale` 19.0.1.0.0, branch `feat/rental-sale-deployment` → PR **#227**, di-stack di atas PR **#222** — **bukan** di atas `main`. **TERDEPLOY + AKTIF di `prd_arkaaim` 8-Sep-2026**, `deployment_auto_create=True` untuk KEDUA perusahaan sejak 09:52 WIB (dump `prd_arkaaim-pre-autocreate-20260908-0952.dump`). Mematikan lagi = tulis False, tanpa restart (rental-sale-deployment).

**Pemicunya `deployment_product_id` di sale.order, bukan saklarnya.** Per 8-Sep ada 11 SO dan NOL yang mengisi field itu, jadi menyalakan saklar tidak mengubah apa pun sampai seseorang memilih produk deployment. Deployment lahir **draft** — gudang yang mengkonfirmasi (rental-sale-deployment).

Keputusan inti: **Sales TIDAK dipindah ke modul rental.** ARKA menjual jasa drone show lump-sum per event qty 1, sedangkan `rental.order` menghitung `daily_rate × days × qty` plus denda harian. SO tetap dokumen komersial dan sumber pendapatan; rental hanya menyumbang unit fisik mana yang berangkat dan apa yang pulang. Deployment = `rental.order` mode internal loan (`is_internal_loan=True`, `daily_rate=0`, `sale_order_id` terisi) dengan dua pengaman: tidak boleh membawa uang (constraint) dan `action_create_invoice` menolak (rental-sale-deployment).

Konfigurasi terpasang lewat `scripts/tenants/arkaaim/setup_deployment.py`: AIM on-deployment `WH/On Deployment` sumber `WH/RUKO GUDANG PALEM`; ARKA on-deployment `WH-01/On Deployment` sumber `WH-01/RUKO GUDANG PALEM`. Sumber dibaca dari register (hitungan unit), **bukan `WH/Stock`** (rental-sale-deployment).

Jalan buntu yang dihapus: `_check_returned_serials` dulu melempar UserError berisi saran "resolve via inventory adjustment" — dan inventory adjustment persis cara drone hilang berhenti jadi masalah siapa pun. `action_validate_loan_return` kini membuka wizard rekonsiliasi yang menyerahkan unit hilang/rusak ke `custom_asset_lifecycle`, dan wizard hanya menampilkan **selisih**, bukan 1.500 serial (rental-sale-deployment).

> **BUG BESAR `custom_rental` yang hanya diperbaiki SEBAGIAN.** Modul mengambil sumber internal loan dari `default_location_src_id` tipe picking internal PERTAMA — dock Input, bukan tempat armada berada. Reservasi dari lokasi salah **tidak gagal**: ia membukukan −1 di sumber, +1 di tujuan, dan meninggalkan stok asli utuh → unit ada di dua tempat, diam-diam. Ini mesin yang sama yang menaruh 2.572 unit di gudang salah. `custom_asset_stock_link` memperbaikinya **untuk mode serial saja**; mode bulk (yang dipakai deployment) tidak tersentuh (rental-sale-deployment).

Sudut tumpul yang diketahui: `deployment_product_id` **tidak divalidasi tipenya**. Salah pilih produk jasa tetap membuat deployment, dan konfirmasinya menghasilkan picking berisi move produk jasa. Tidak berbahaya (penjualan aman, GL aman) tapi membingungkan Ops; perbaikan wajar = domain ke produk storable ber-`tracking='serial'` (rental-sale-deployment).

Diverifikasi di klon prd 8-Sep tanpa menyentuh prd: SO biasa tanpa deployment product tidak terpengaruh; SO dengan deployment product melahirkan deployment draft bersumber PALEM; deployment menolak invoice dan menolak `daily_rate`; **konfigurasi rusak di tengah jalan TIDAK memblokir penjualan** — SO tetap `sale`, catatan ditempel di order (rental-sale-deployment).

> **Jalur confirm → dispatch → retur → rekonsiliasi BELUM PERNAH dieksekusi di `prd_arkaaim`** per 8-Sep-2026. Teruji-klon, BUKAN teruji-produksi (rental-sale-deployment).

## 5. GR/IR & intercompany

### Jurnal GR/IR saat receipt

Dibangun di `custom_arka_aim_purchase_type` **19.0.1.2.0**, `models/stock_move.py`: `_action_done` memposting `Dr property_stock_valuation_account_id / Cr GR-IR`, ref `ARKA-GR-VAL:<move id>` (retur: `ARKA-GR-RET-VAL:`), jurnal STJ, idempoten. Saklar `ir.config_parameter custom_arka_aim_purchase_type.suppress_gr_journal` (default "0" = posting). PR **#230 MERGED** (squash `9d1572e6`), TERDEPLOY prd+trn 8-Sep-2026, konfigurasi diterapkan **hanya di `prd_arkaaim`**, 17 tes hijau (arkaaim-gr-journal-grir).

Konfigurasi `prd_arkaaim` (dipilih klien 8-Sep): debit ke `1113100099 Inventory-Others`; kategori **Goods, Expenses, Services / Exhibition** jadi `real_time`; GR/IR Trade `2103109199`, Non-Trade `2103300008` (keduanya liability_current + reconcile). **Fixed Assets (Non-Valuated) sengaja dibiarkan `periodic`** karena drone dikapitalisasi lewat register aset — mengakru sebagai persediaan = dobel (arkaaim-gr-journal-grir).

Temuan Odoo 19 yang penting: core mengambil lawan jurnal receipt dari `stock.location.valuation_account_id`, bukan akun input/output kategori. Lokasi *Vendors* `company_id` NULL alias dipakai bersama dua company → satu field tak bisa memuat GR/IR berbeda per company DAN per stream, makanya jurnal dibuat sendiri. `account_stock_variation_id` ADA di core tapi di `account.account`, **bukan** di `product.category` (arkaaim-gr-journal-grir).

Sisi bill digerbangi "PO line-nya benar-benar diterima" (ada move done dari lokasi supplier), BUKAN `product.type == 'consu'`, karena ARKA menerima produk bertipe *service* lewat `custom_service_receipt` dan receipt itu ikut mengakru (arkaaim-gr-journal-grir).

> **Retur vendor tidak boleh pakai `move.value`.** Move keluar dinilai metode biaya (standard, dan `standard_price` kosong di tenant ini) → akru 1.000 dilepas 400 dan sisanya mengendap selamanya. `_arka_grir_amount()` menilai retur dari porsi `origin_returned_move_id`; stream retur dibaca dari picking asal karena retur tak punya PO (arkaaim-gr-journal-grir).

Backfill 39 receipt lama (`backfill_gr_journal.py`, PR **#236 MERGED** `d6f8c643`): **24 baris Rp 569,2 jt di-akru** (tanggal hari ini, periode terbuka) + 1 charge-out Rp 239,7 jt untuk Soekarno Cup; **15 baris Rp 341 jt SENGAJA DILEWATI** karena `BILL/2026/08/0001` & `/0002` sudah memposting biayanya ke `7101007000 Exhibition` — mengakru ulang = dobel. Backfill ini **WAJIB, bukan opsional**: sisi bill sudah hidup, jadi tagihan susulan akan mendebit GR/IR walau akrualnya tak ada → debit menggantung (arkaaim-gr-journal-grir).

> Atribusinya **tidak hilang**: ke-15 baris itu sudah membawa analytic event dan duduk di akun beban, jadi P&L per Event SUDAH menghitungnya (HUT RI 81 Rp 226 jt, Danone Rp 115 jt). Yang beda cuma akun penampungnya. "Reklas" di sini = perubahan **penyajian** atas bulan terlapor, **BUKAN** koreksi angka salah — jangan dijual sebagai perbaikan (arkaaim-gr-journal-grir).

Sisa persediaan Rp 329,5 jt = Merdeka Run Rp 259 jt (menunggu faktur) + Rp 70,5 jt di `PO/ARKA/2026/08/007` yang TANPA event. Nilai kedua **tidak akan pernah keluar dari persediaan sampai PO-nya diberi event** (arkaaim-gr-journal-grir).

`trn_arkaaim` juga AKTIF sejak 8-Sep: chart generik hanya punya SATU payable dan SATU Interim Stock (`29000000`), jadi kedua stream memakainya bersama — benar untuk chart itu, kliring tetap nol, pemisahan stream hidup di penomoran PO dan pelaporan. Kategori yang dinyalakan di trn: Goods, Expenses, Drone Sparepart; **Drone Unit sengaja periodic** (setara Fixed Assets di prd — dan justru di situ receipt terbesar trn, Rp 10,68 M) (arkaaim-gr-journal-grir).

### PO Trade / Non-Trade

`custom_arka_aim_purchase_type` 19.0.1.0.1 TERDEPLOY prd+trn 8-Sep-2026, PR **#220 MERGED** (squash `e4d5c4c`, +1209/-11 di 25 file, 21 check CI hijau). Port fitur #9 Levi's minus bagian Levi's-only. Penomoran `PO/T/<CO>/YYYY/MM/NNN` + `PO/NT/<CO>/YYYY/MM/NNN`, dua counter terpisah per company, reset bulanan lewat `x_monthly_reset`, digerbangi `res.company.x_doc_code` sehingga inert di luar tenant. 12 PO lama tetap `PO/<CO>/…` dan default ke `trade` (arkaaim-trade-nontrade-purchase-type).

Mapping akun `arka.purchase.account.map` di-seed per company by code: Trade AP `2103100001`, Non-Trade AP `2103300001` + GR/IR `2103300008` + expense fallback **`7799000000`** (bukan `6120010001` seperti Levi's — opex ARKA ada di blok 7xxx). Bill Non-Trade: `Dr expense/COGS / Dr VAT In / Cr 2103300001` (arkaaim-trade-nontrade-purchase-type).

Transfer to Asset: receipt Non-Trade validated menampilkan **Convert to Assets** tanpa produk perlu di-flag di master; semua baris ditawarkan pooled dan sudah tercentang; aset DRAFT tanpa jurnal akuisisi. Fallback group `res.company.x_nontrade_asset_group_id`: AIM → "Office and outlet equipment", ARKA → "Alat Pendukung" (arkaaim-trade-nontrade-purchase-type).

> **Uji rollback di prod TIDAK membakar nomor PO — selama `ir.sequence.date_range` bulan itu belum pernah ada.** `_create_date_range_seq` membuat range + PG sequence-nya di dalam transaksi yang sama, dan DDL PostgreSQL transaksional. Begitu satu PO asli sudah membuat range bulan itu, `nextval` berikutnya **TIDAK** ter-rollback lagi dan uji semacam ini meninggalkan lubang nomor (arkaaim-trade-nontrade-purchase-type).

> **Jebakan view `purchase.order`:** ada DUA search view. Aksi Purchase Orders pakai `purchase.purchase_order_view_search`, aksi RFQ pakai `purchase.view_purchase_order_filter`. Mewarisi salah satu saja = filter tidak kelihatan justru di layar yang dipakai buyer (arkaaim-trade-nontrade-purchase-type).

### Gap Rp 920 jt — bukan penggandaan akrual, tapi rantai IC yang putus

Diperiksa 8-Sep-2026 baca-saja. **TIDAK ADA PENGGANDAAN**: akun GR/IR kredit Rp 569,2 jt, **debit 0** — tak satu pun tagihan menyentuhnya (arkaaim-grir-accrual-gap).

Tapi **Rp 920.000.000 penerimaan TANPA JURNAL SAMA SEKALI**:

| Receipt | Isi | Nilai (DPP) | Status |
| --- | --- | --- | --- |
| `WH-01/IN/00006` | Sewa Drone Show 1500 Unit | 800.000.000 | to invoice, 0 baris jurnal |
| `WH-01/IN/00007` | Sewa Drone Show 250 Unit | 120.000.000 | to invoice, 0 baris jurnal |

**Sebabnya INTERCOMPANY, bukan tanggal.** Hipotesis "cutoff tanggal" SALAH; korelasinya kebetulan. Pembedanya lokasi asal, eksplisit di kode: `_is_arka_goods_receipt()` = `location_id.usage == "supplier"`, dengan docstring menyatakan internal & transit **sengaja dikecualikan**. Move 7240/7241 berasal dari `Inter-company transit` dan berada DI DALAM span id 7224–7250 yang dikelilingi move terakrual. **Modul akrualnya BENAR dan berperilaku persis seperti ditulis** (arkaaim-grir-accrual-gap).

Yang rusak adalah asumsi "penerimaan IC tak perlu akrual karena tagihannya akan datang":

- **Rp 800 jt** — `PO/ARKA/2026/08/001` → `SQ/AIM/2026/09/001` masih **DRAFT QUOTATION**, barang diterima ARKA 09-01, tak pernah jadi SO → tidak diakui KEDUA perusahaan.
- **Rp 120 jt** — `PO/ARKA/2026/08/002` → SO AIM dikonfirmasi, fakturnya **MASIH DRAFT (id 277)** → tidak diakui kedua perusahaan.

> **KOREKSI ATAS PERINGATAN LAMA YANG TERBALIK DAN BERBAHAYA.** Pernah tercatat bahwa faktur draft **id 277** (Rp 120 jt) adalah duplikat `INV/AIM/2026/09/001` dan "harus dibuang". **SALAH.** Keduanya Rp 120 jt ke pelanggan sama tapi dari SO berbeda yang mencerminkan PO ARKA berbeda. **Draft 277 adalah faktur yang HILANG untuk leg itu; MEMPOSTINGNYA adalah obatnya.** Membuangnya akan menghapus satu-satunya dokumen atas barang yang sudah diterima ARKA (arkaaim-grir-accrual-gap).

Jebakan yang sebenarnya: `SO/AIM/2026/09/001` berbunyi `invoice_status = invoiced` padahal satu-satunya fakturnya belum diposting — Odoo menghitung faktur draft ke `qty_invoiced`. SO ini **tidak muncul** di pencarian "SO belum ditagih" MAUPUN "pendapatan terposting". Tak terlihat dari dua arah; itu sebabnya ia menganggur sejak 09-02 dan dua sesi salah membacanya (arkaaim-grir-accrual-gap).

Jenis produk BUKAN pembeda: baris `service` justru ikut terakrual di ketiga penerimaan yang tercakup (70,5 + 239,7 + 259,0 = 569,2 jt persis, termasuk Rp 64,5 jt baris service). Basis nilai adalah **DPP** dan itu diverifikasi terhadap perilaku fiturnya sendiri, jadi Rp 920 jt vs Rp 569,2 jt adalah perbandingan setara. Termasuk PPN 11%: Rp 1.021.200.000. Nol dari 50 baris akrual menyentuh produk aset, jadi jaminan nol-valuasi armada bertahan (arkaaim-grir-accrual-gap).

### Mirror SO intercompany

`custom_intercompany_procurement` memang membuat mirror PO→SO sebagai **quotation draft** (prefix `SQ/`) — desain lama, bukan bug. Keluhan klien 8-Sep "PO ARKA tidak membentuk SO di AIM": mirror-nya ADA (`SQ/AIM/2026/09/007`, id 20, company AIM) tapi masih draft dan tak terlihat kalau company switcher hanya mencentang ARKA. Di `prd_arkaaim` hanya **1 dari 4** mirror yang pernah dikonfirmasi manual (ic-mirror-auto-confirm).

`custom_intercompany_procurement` **19.0.0.3.0** (PR **#233**) menambah `account.intercompany.rule.auto_confirm_mirror_so`. TERDEPLOY 8-Sep ke prd+trn, tiga container odoo di-restart, **tapi flag masih FALSE di rule 1 (ARKA → AIM)** — nol perubahan perilaku di produksi (ic-mirror-auto-confirm).

> **Sebelum menyalakan flag, dua fakta yang mengunci keputusan:** baris mirror dibuat **tanpa pajak** (`tax_ids` sengaja dikosongkan) dan menyalin harga PO apa adanya — auto-confirm mengunci SO AIM **tanpa PPN**. Dan kalau `spawn_rental_loan` ikut nyala, confirm otomatis akan membuat `rental.order` sebagai efek berantai (ic-mirror-auto-confirm).

> **Produk ber-company mematikan IC mirror — data, bukan kode.** Produk yang `company_id`-nya dikunci ke ARKA ditolak sebagai company crossover; error ditangkap dan hanya jadi catatan chatter → user tidak sadar. Di prd hanya 4 dari 12 PO yang punya mirror. SUDAH DIPERBAIKI 8-Sep: prd produk 14 + 15 jadi shared, duplikat 153 diarsipkan; trn produk 18 + 8 jadi shared. "Jasa Drone Show 250 Unit" ada DUA kali (id 14 milik ARKA, id 153 shared) (arkaaim-event-chain-analytic).

> **Jebakan operasional:** `odoo -d ... -u <modul> --stop-after-init` di dalam container yang sedang jalan mati dengan `OSError: Address already in use` **sebelum** upgrade jalan — versi di `ir_module_module` tidak berubah, jadi terlihat seperti sukses diam. Wajib `--no-http` (ic-mirror-auto-confirm).

### Jasa ikut goods receipt

`custom_service_receipt` 19.0.0.2.0 + `custom_asset_from_receipt` 19.0.0.4.0, PR **#219 MERGED** (squash `74dc1ab`), **LIVE di `prd_arkaaim`** 8-Sep-2026 dengan **4 produk di-flag** (tmpl 143 Manpower, 142 Venue & Supporting Tools, 155 Sewa Drone Show 1500, 154 Sewa Drone Show 250), semuanya ikut pindah ke `purchase_method='receive'` (service-receipt-module).

> Catatan memory yang sama masih memuat kalimat lebih tua **"Belum ada satu pun produk yang di-flag, jadi modulnya masih inert"** — itu **BASI** dan bertentangan dengan blok status di paragraf pertamanya. Verifikasi `product.template.receive_on_gr` di DB sebelum mengandalkan salah satu (service-receipt-module).

Masalah asalnya: Odoo memfilter GR di **empat** tempat dengan `product_id.type == 'consu'`, sehingga jasa yang dibeli tak pernah punya dokumen terima; bukti di prd: 14 baris PO jasa semuanya `purchase_method='purchase'`. Solusinya opt-in per produk `product.template.receive_on_gr`. Tipe produk **sengaja TIDAK diubah** karena `custom_coretax_export` membaca `product.type == 'service'` untuk kolom e-Faktur `BARANG_JASA` (service-receipt-module).

## 6. Mata uang & pricelist

### Pricelist USD membajak SO

`sale.order._compute_currency_id` = `pricelist_id.currency_id or company_id.currency_id` — **pricelist menang atas mata uang company**, dan `depends`-nya hanya `('pricelist_id', 'company_id')`, BUKAN `pricelist_id.currency_id`. Jadi mengubah mata uang pricelist tidak otomatis memperbaiki order lama; harus `env.add_to_compute(...)` untuk `currency_id` **dan** `currency_rate` (arkaaim-pricelist-currency-usd).

Di ARKA-AIM `product_pricelist` id 1 (company 1 = AIM) lahir **USD** karena modul `product` membuat `product.list0` dengan base currency saat install, sedangkan `custom_arka_aim_seed/hooks.py` baru menyetel company ke IDR belakangan — dan hook itu hanya menyentuh `base.main_company`. Company 2 (ARKA) aman (arkaaim-pricelist-currency-usd).

| DB | Status 7-Sep-2026 |
| --- | --- |
| `prd_arkaaim` | **SUDAH diperbaiki** (pricelist + 5 SO) |
| `trn_arkaaim` | **MASIH USD** — pricelist 1 + 3 SO + `INV/AIM/2026/07/001` posted |

trn sengaja di luar cakupan; GL trn kebetulan benar karena diposting di kurs 1,0. Alatnya `scripts/tenants/arkaaim/fix_pricelist_currency.py` (3 tahap, idempoten, PREVIEW default); cek paritas permanen di `audit_finance_parity.py` blok [8]/[9] (arkaaim-pricelist-currency-usd).

> **`add_to_compute` TIDAK menandai dependent dirty.** `sale.order.line.currency_id` itu `related='order_id.currency_id'` + `store=True`, jadi setelah memperbaiki header order, BARISNYA tetap USD. Wajib `orders.modified(["currency_id"])` lalu `orders.order_line.flush_recordset()`, dan verifikasi harus mengecek baris, bukan cuma header (arkaaim-pricelist-currency-usd).

Dua jebakan lain di skrip itu: draft move tidak bisa di-`write` sama sekali kalau ada baris di akun **arsip** (bikin seluruh skrip abort), dan untuk menurunkan `balance` faktur draft setelah ganti mata uang panggil `move.line_ids._inverse_amount_currency()` — `account.move.line.currency_rate` bukan field stored-compute (arkaaim-pricelist-currency-usd).

### Popup CNY dan kurs yang hilang

Popup Register Payment yang menampilkan Rp 20.000 untuk bill CN¥ 20.000 **bukan bug konversi**. Jurnal bank 51/53 di `prd_arkaaim` memang ber-`currency_id` IDR sehingga wizard selalu IDR — itu native dan benar. Yang salah: satu-satunya baris `res.currency.rate` untuk CNY (id 2, tanggal 2026-07-29, company 2) baru dibuat 2026-08-04 04:15, dan sebelum itu `res.currency._convert` diam-diam jatuh ke 1,0. Dengan kurs terisi: CN¥ 20.000 → Rp 53.445.926,08 @ 1 CNY = 2.672,2963 IDR (arkaaim-cny-payment-rate).

Company 1 (AIM) per catatan itu masih **tidak punya** kurs CNY sama sekali — dokumen CNY di sana akan kena fallback 1:1 yang sama (arkaaim-cny-payment-rate).

`custom_arka_fx_header` 19.0.1.1.0 menampilkan open amount / rate / ekuivalen CNY di popup dan menaikkan banner merah saat baris kurs hilang (`x_fx_rate_missing`). Display-only, tanpa perubahan schema, dan sengaja **tanpa restriksi `groups`** karena blok native Odoo bersembunyi di belakang `base.group_multi_currency` dan hilang untuk role yang tidak meng-imply grup itu (`addons/_tenants/custom_arka_fx_header/MODULE_KNOWLEDGE.md`).

### Satu baris kurs ber-company membajak semua baris shared

**Odoo 19 `res.currency._get_rates` mengurutkan `order='company_id.id, name DESC'` dengan `limit=1`** (`addons/base/models/res_currency.py:126-129`). Karena `company_id` diurut lebih dulu dan menaik, baris ber-`company_id` **selalu** menang atas baris shared — **tanpa memandang tanggal**. Satu baris company-scoped bertanggal lama membajak seluruh tanggal sesudahnya untuk company itu (odoo19-company-rate-shadows-shared).

Terlihat di `prd_arkaaim` 19-Agu-2026: setelah 26 baris shared KMK dimuat, company 1 membaca 1 CNY = 2.645,08 (KMK 38) tapi company 2 tetap 2.648,42 — nilai baris company-2 tertanggal 29-Jul (odoo19-company-rate-shadows-shared).

> Perbaikannya: **hapus baris company-scoped** itu (aman bila ada baris shared bertanggal sama). **Jangan** "diperbaiki" dengan menduplikasi tiap baris KMK per-company — itu hanya melawan urutan sortir core (odoo19-company-rate-shadows-shared).

Kebijakan kurs `prd_arkaaim` = **Kurs Pajak KMK, shared kedua company** (keputusan user 19-Agu-2026). Loader `scripts/tenants/arkaaim/load_currency_rates.py` menulis `RATES` arah terbaca (IDR per 1 unit) dan skripnya yang membalik ke arah simpan Odoo; COMMIT=False default, idempoten. Terisi 13 minggu KMK 23–38/MK/EF.2/2026, 27-Mei s/d 25-Agu 2026, CNY+USD, 26 baris. Mulai 27-Mei karena saldo awal 31-Mei jatuh di periode itu (odoo19-company-rate-shadows-shared).

**Cron mingguan** `/etc/cron.d/odoo-kmk-rate` menjalankan `scripts/ops/kmk_rate_sync.sh` Rabu + Kamis 07:00 WIB untuk `prd_arkaaim` + `trn_arkaaim` (Kamis = retry), idempoten, membaca ulang 4 KMK terakhir, menulis **HANYA baris shared** dan memperingatkan kalau menemukan baris ber-company. Halaman daftar KMK hanya memuat ~5 dekrit, jadi `BACKFILL_WEEKS` di atas 5 sia-sia. Sumber angka: PDF KMK di `fiskal.kemenkeu.go.id`, di-`pdftotext -layout` sendiri — **jangan pakai ringkasan hasil pencarian**, pernah menyebut "1 CNY = Rp 12,61" (odoo19-company-rate-shadows-shared).

Dokumen yang sudah posted tidak ikut berubah — rate tersimpan di `account.move.invoice_currency_rate` (dua bill CN¥ 27-Jul tetap di 2.672,30) (odoo19-company-rate-shadows-shared).

### Input kurs manual di payment

`custom_payment_fx_rate` 19.0.1.1.0 menambah field **Exchange Rate** di form `account.payment` dan popup Register Payment, ditulis arah **terbaca** (1 USD = 16.200 IDR) — kebalikan dari `res.currency.rate` dan dari `invoice_currency_rate`. Cara kerja: override `res.currency._get_conversion_rate` yang menghormati context `manual_fx_rate` (payment-manual-fx-rate).

> **Jebakan:** mata uang yang dibaca dari baris jurnal (`line.currency_id`) membawa context baris itu, bukan context wizard. Membungkus wizard saja membuat kurs manual **DIABAIKAN tanpa error** — jumlahnya cuma diam (payment-manual-fx-rate).

Status 26-Agu-2026: modul **TERPASANG di `prd_levis_begbal` saja**, bukan di DB ARKA-AIM; di repo ada di `addons/ee_gap/custom_payment_fx_rate` (payment-manual-fx-rate).

## 7. Akun & COA

### Fakta CoA yang paling mudah salah dibaca

Di DB ARKA-AIM `account.account` adalah **single-company** — 0 akun shared; `account_account_res_company_rel` adalah sumber kebenaran, **BUKAN** key `code_store`. Company 1 memakai xmlid `arka_aim.coa_*` (546 akun), company 2 memakai `account.2_erajaya_*` (543 akun). "534 duplicate codes di company 2" yang terlihat via `code_store->>'2'` adalah **metadata basi** pada akun company-1 — menghapus set erajaya akan menghancurkan seluruh chart ARKA (arkaaim-opening-balance-clone).

`account.account.code` di Odoo 19 **company-dependent**, tersimpan di kolom JSONB `code_store`. Membaca `acc.code` tanpa `with_company` untuk akun milik company lain mengembalikan **blank/False** — hanya `code` yang terpengaruh; `name`, `account_type`, `reconcile` shared. Ini yang dulu memunculkan "TB ARKA kosong", diperbaiki lewat helper `custom.report.engine._account_code(account)` (odoo19-company-dependent-account-code).

> **JANGAN PERNAH cari akun hanya lewat `code` di `prd_arkaaim`.** Akun **354** Gross Sales-Others punya `code_store = {"1": "5199000000", "2": "5199000000"}` padahal `company_ids = {1}`; akun company 2 yang benar adalah **1067**. Jadi `search([('code','=','5199000000')])` di context company 2 mengembalikan 354 — akun milik company lain (id lebih kecil menang). Selalu:
> ```python
> search([('code', '=', X), ('company_ids', '=', company.id)], limit=1)
> assert company in acct.company_ids
> ```
> (odoo19-company-dependent-account-code)

Laporan QWeb PDF kena juga: `ir.actions.report` merender di bawah company **user**, bukan `o.company_id`, jadi Journal Voucher atas bill company 2 mencetak semua kode GL kosong untuk admin yang sedang di company 1. Pola perbaikannya `o.with_company(o.company_id).line_ids…` (odoo19-company-dependent-account-code).

Jebakan yang sama menggigit `custom_arka_aim_purchase_type`: satu kode akun punya DUA record, mis. `2103300001` = id **263** (AIM) vs **976** (ARKA). Hook jalan sebagai superuser jadi record rule multi-company tidak berlaku; `_find_account` **WAJIB** filter `company_ids` selain `code`, kalau tidak payable AIM terpasang ke bill ARKA (arkaaim-trade-nontrade-purchase-type).

Default akun lintas-company juga pernah salah: default income/expense company 2 pada kategori Goods/Expenses/Services (id 1,2,3) dan produk "Jasa Drone Show" (tmpl 7) menunjuk akun **company-1** 354 / 360. Diperbaiki 1-Jul-2026 ke akun company-2 yang benar 1067 / 1073 di `prd_arkaaim` dan `trn_arkaaim_begbal`; `trn_arkaaim` sudah bersih (arkaaim-crosscompany-default-accounts-fix).

### Tipe akun terbalik di prd

Akun **id 62** (`arka_aim.coa_1106000001` "Trade Receivables - Third Parties", company 1) `account_type`-nya diubah manual jadi `liability_payable` pada 2026-07-09 oleh `ricad.lingga@erajaya.com` (uid 46), sehingga SEMUA customer invoice company 1 gagal dengan "Account 1106000001 is of payable type, but is used in a sale operation" (constraint core `_check_payable_receivable`). **Dikembalikan ke `asset_receivable` 2-Sep-2026** lewat `odoo shell`, aman karena akun itu 0 move line (arkaaim-receivable-account-type-flipped).

Akun itu adalah default piutang company 1 yang tersimpan di **`ir_default`** (model `res.partner`, field `property_account_receivable_id`, company_id=1 → 62), **bukan** di property partner. Mencari di `res_partner.property_account_receivable_id` hasilnya nol dan menyesatkan. Tiap company punya akun `1106000001` sendiri (company 2 = id 780) (arkaaim-receivable-account-type-flipped).

> **Catatan hak akses:** `ricad.lingga@erajaya.com` adalah tim Accounting dan MEMANG berhak menyunting CoA. **Jangan usulkan mencabut hak edit `account.account` darinya** — sudah ditolak user 2-Sep-2026. Perlakukan sebagai salah klik biasa (arkaaim-receivable-account-type-flipped).

### Akun arsip

Faktur penjualan company 1 membukukan ke akun **arsip** `400000 Product Sales`. Ini fatal, bukan kosmetik: core menolak **setiap `write`** ke move semacam itu ("The account ... is archived"), jadi draft-nya beku total — tak bisa diedit maupun diposting (arkaaim-archived-income-account).

Penyebabnya **bukan kategorinya**: `ir.default` company 1 sudah benar, tapi **30 product template `categ_id` NULL**, sehingga `_get_product_accounts()` kosong di kedua sisi lalu jatuh ke akun generik basi. **SELESAI 7-Sep-2026**, 33 record: 0 produk tanpa kategori, 0 baris di akun 26; 3 template sewa drone (154/155/157) dapat akun eksplisit `5122000000 Gross Sales-Rental Asset`. Akun `6199000000` company 1 juga di-retype ke `expense_direct_cost` dan jurnal BILL diarahkan ke sana, lepas dari akun arsip `600000` (arkaaim-archived-income-account).

Yang masih tersisa: move **272 & 273** (bill draft company 1) masih di akun arsip `600000 Expenses`, beku dengan cara yang sama, menunggu akun beban dari Accounting. Dan company 1 **kekurangan 9 akun** yang dipunyai company 2, termasuk `1103000002 Bank Suspense Account`, `1103000003 Outstanding Receipts`, `1103000004 Outstanding Payments`, `9990000001/2 Cash Difference Gain/Loss` — akibatnya 5 jurnal bank/kas company 1 (BNK1, CSH, BCA1, BCA2, PCPAY) masih memakai `suspense_account_id` = akun ARSIP 6 digit `101402`; **6 pointer tersisa per 7-Sep** (arkaaim-archived-income-account).

> **DITAHAN 8-Sep-2026 atas permintaan user.** JANGAN membuat akun `1103000002` / `9990000001` / `9990000002` di company 1, jangan menyentuh 6 pointer `101402` yang tersisa, dan **jangan merge PR #216** sampai user memberi lampu hijau. Klien harus mengonfirmasi CoA dulu. Perubahan yang SUDAH live (mata uang, kategori produk, retype `6199000000`, jurnal BILL) tetap berlaku (arkaaim-archived-income-account).

`journal.suspense_account_id` **BUKAN** jalur pembayaran — keputusan direct-to-bank 10-Agu ada di `payment_account_id` dan masih utuh. Suspense hanya dipakai saat baris rekening koran tak bisa dicocokkan, dan company 1 punya 0 baris statement. Mengarahkan suspense ke akun bank itu sendiri membuat kedua kaki saling meniadakan → rekonsiliasi bank jadi tak bermakna (arkaaim-archived-income-account).

Beda tipe antar-company yang tersisa: `2103300090` (liability_current vs liability_payable). `6122000000` bertipe `income` di KEDUA company — itu pertanyaan chart-wide, bukan drift; **jangan diutak-atik** (arkaaim-archived-income-account).

### Akun uang muka (down payment)

Di Odoo 19 akun baris invoice uang muka = `company.downpayment_account_id or _get_down_payment_account(product)`. `l10n_id` **tidak** mengisi field itu, jadi kalau kosong DP langsung nyangkut di akun income produk (arkaaim-downpayment-account).

Per 4-Aug-2026 kedua company `prd_arkaaim` sudah punya `downpayment_account_id = 2108100001 Advances from customers - Third parties`, dan `INV/ARKA/2026/07/001` (satu-satunya DP invoice) sudah dikoreksi dari `5123000000 Gross Sales-Media`; rekonsiliasi AR dengan `PBNK1/2026/00001` selamat, `payment_state` tetap `paid`. Pada pelunasan, baris potongan DP mengambil akunnya **dari DP invoice yang sudah ada**, jadi memperbaiki akun di DP invoice cukup — tidak perlu jurnal reklas terpisah (arkaaim-downpayment-account).

Produk jasa (keputusan klien 4-Aug): product 7, 14, 15, 16, 28 di-set `property_account_income_id = 1067` (`5199000000 Gross Sales-Others`, company 2) dan `categ_id = 3` Services dengan fallback expense `6199000000`. "Biaya Luar Kota" sengaja disatukan dengan revenue show, bukan dipisah ke Reimbursement Income (arkaaim-downpayment-account).

### Pembayaran company 1 pernah mati total

"No outstanding account could be found to make the payment" di `prd_arkaaim` berasal dari core `_get_outstanding_account`, yang mencari di **tiga jalur berurutan**: `payment_account_id` baris payment-method, XMLID chart-template, lalu `res_company.transfer_account_id`. Ketiganya kosong untuk **company 1 (AIM)**; company 2 punya XMLID ke Outstanding Receipts/Payments — itu sebabnya hanya AIM yang terblokir (0 payment vs 5 posted) dan gap-nya tak terlihat berbulan-bulan (arkaaim-payment-outstanding-blocker).

Tidak ada jalan keluar "in payment" di platform ini — `account_accountant` tidak terpasang di mana pun, jadi setiap payment wajib punya outstanding account. Perbaikan 10-Aug-2026 (COMMIT) ke `trn_arkaaim` dan `prd_arkaaim`, **company 1 saja**: direct-to-bank. Company 2 sengaja dibiarkan di Outstanding accounts karena sudah punya payment terposting lewat sana. Tiap company juga dapat `transfer_account_id` = akun Bank Suspense-nya sebagai jaring pengaman (arkaaim-payment-outstanding-blocker).

> **Konsekuensi yang harus dijaga:** dengan direct-to-bank, payment sudah memindahkan GL bank. Saat impor rekening koran diaktifkan untuk ARKA, baris statement harus **dicocokkan** ke payment itu, **jangan** diposting baru ke akun yang sama, atau bank jadi dobel. `prd_arkaaim` punya 0 baris statement saat itu; ARKA belum memisah jurnal bank-IN / bank-OUT seperti Levi's (arkaaim-payment-outstanding-blocker).

`prd_arkaaim` company 1 juga di-retype `2103100001` + `2103200001` ke payable (PR **#121**). Itu lebih dari sekadar merapikan: **7 dari 10 vendor aktif company 1 tidak punya `property_account_payable_id`** eksplisit sehingga jatuh ke default chart-template `2103100001` — selama akun itu `liability_current`, tagihan untuk 7 vendor tersebut **akan gagal**. Dua akun *non-trade* sengaja **ditahan**: `2103300001` membawa sepuluh akrual gaji bulanan tanpa partner, dan menariknya ke Aged Payable adalah keputusan Finance. Saldo AP yang tidak disentuh: `2103300001` −42.876.084 dan `2103400001` −16.867.000 (arkaaim-payment-outstanding-blocker).

> **Memasang payment method `mode='multi'` menambah baris ke jurnal bank SETIAP company**, bukan hanya yang sedang diperbaiki. Baris Giro/Transfer baru company 2 berakun kosong dan jatuh ke jalur 2 — terverifikasi masih memposting ke Outstanding Payments (arkaaim-payment-outstanding-blocker).

## 8. Saldo awal (begbal)

Cutover **31-Mei-2026**, dari Google Drive "Beg Balance ARKA AIM.xlsx" (2 trial balance yang masing-masing balance D=C persis) (arkaaim-opening-balance-clone).

| Company | TB 31-Mei-2026 | Sumber |
| --- | --- | --- |
| AIM (1) | Rp 43.264.095.721,50 | docs/projects/arka-aim/BEGBAL_DETAIL.md |
| ARKA (2) | Rp 5.054.276.231 | docs/projects/arka-aim/BEGBAL_DETAIL.md |

Perjalanannya dua tahap. **1-Jul-2026**: dimuat sebagai 2 jurnal agregat (move 15 AIM 27 baris; move 16 ARKA 12 baris) lewat modul `custom_arka_aim_opening_balance`, terpasang di `prd_arkaaim` dan `trn_arkaaim_begbal`; intercompany Rp 6.337.500 tie out (arkaaim-opening-balance-clone). **4-Aug-2026**: diganti agregat → **detail**:

| | Sebelum | Sesudah |
| --- | --- | --- |
| Jurnal AIM | move 15, 27 baris, MISC | move 120, **265 baris**, MISC |
| Jurnal ARKA | move 16, 12 baris, **BILL1** | move 121, **61 baris**, **JM** |
| Ref | `Saldo Awal 31 Mei 2026` | `Saldo Awal Detail 31 Mei 2026` |
| Register aset | 3.329 unit, tanggal seragam | **3.590 unit**, tanggal riil, 3 group |

**Saldo tidak berubah** — yang berubah hanya granularitas. Satu-satunya perbedaan saldo adalah **desimal**: jurnal agregat membulatkan ke rupiah, detail membawa angka TB apa adanya (mis. `1103019270` 2.470.000 → 2.470.000,12). Tanggal transaksi asli, nomor dokumen dan nama lawan transaksi disimpan di **label baris** karena `account.move.line` tidak punya field tanggal sendiri (`docs/projects/arka-aim/BEGBAL_DETAIL.md`, arkaaim-begbal-detail-aug04).

Lima akun `asset_cash` yang benar-benar tidak ada di CoA dan harus dibuat: AIM `1103019270`, `1103019280`; ARKA `1103019290`, `1103019300`, `1105020007` (arkaaim-opening-balance-clone, `addons/_tenants/custom_arka_aim_opening_balance/MODULE_KNOWLEDGE.md`). Perhatikan `post_init_hook` modul itu **tidak memverifikasi debit = kredit** — ia hanya menjumlah sisi debit untuk log.

Tiga kode akun di sheet detail ARKA yang **tidak ada di CoA**, dipetakan berdasarkan nominal yang cocok persis — **masih perlu konfirmasi klien mana yang benar** (`docs/projects/arka-aim/BEGBAL_DETAIL.md`):

| Kode di sheet | Dipetakan ke | Akun |
| --- | --- | --- |
| 1103019870 | 1103019290 | BCA - IDR-268.262.6268 |
| 1103019900 | 1103019300 | BCA - IDR-268.222.9595 |
| 1105020003 | 1105020007 | Time Deposit BRI |

> **Gotcha parsing workbook:** **kolom `Amount`** yang jadi acuan block total, **bukan** Debit/Credit — baris "Accrue Gaji 05-2026" punya Debit bulanan tapi Amount 5 bulan (arkaaim-begbal-detail-aug04).

> **Menghapus register lama:** `action_reset_draft()` MENOLAK aset yang punya baris posted → hapus `custom.fixed.asset.depreciation.line` dulu, baru asetnya (arkaaim-begbal-detail-aug04).

> **Keempat CSV detail WAJIB tetap tracked di git** (`asset_register_registered.csv`, `asset_register_unregistered.csv`, `opening_detail_aim.csv`, `opening_detail_arka.csv`) — keputusan user 6-Ags-2026. Keempatnya dibaca per nama di `post_init_hook` lewat `file_open()` **tanpa penjagaan file-hilang**, jadi meng-untrack = install/`-u` gagal FileNotFoundError di klon mana pun. Ukurannya hanya ~485 KB total (arkaaim-begbal-detail-aug04).

Jalankan skripnya lewat **stdin** (`docker exec -i ... 'odoo shell -d db' < script`) — `/tmp` container hilang tiap restart dan `docker cp` ke /tmp gagal di image ini (arkaaim-begbal-detail-aug04). Runbook lengkap + query verifikasi ada di `docs/projects/arka-aim/BEGBAL_DETAIL.md`.

### Workbook Agustus yang PARKIR

3-Aug-2026 user mengirim `Template_Begbal_Odoo AIM.xlsx` untuk **memperbarui** saldo awal `prd_arkaaim`. Pekerjaan itu **PARKIR menunggu konfirmasi klien — nol eksekusi, nol perubahan DB** — dengan daftar **34 pertanyaan** (grup A–H) di `/root/.claude/plans/https-docs-google-com-spreadsheets-d-1lx-concurrent-brooks.md` (arkaaim-begbal-workbook-aug2026).

Isi workbook itu: dari 9 sheet **hanya `Aset Tetap`** yang memuat data klien; sheet Neraca Saldo Awal / AR / AP / Persediaan / Bank & Kas / Uang Muka / Perpajakan masih berisi baris contoh template ("PT Sumber Makmur", "Meja Kantor Type A"), dan sel "Tanggal Cutover" kosong di mana-mana. Sheet `Aset Tetap` punya 3.443 baris, TOTAL Rp 27.222.424.239, **kolom Akum. Penyusutan / Nilai Buku / Sisa Umur / Metode `-` (kosong) di setiap baris**, dan TOTAL sheet ≠ jumlah baris (beda Rp 1.665.220 = tepat 1 Drone Battery). Tiga angka cost AIM saling bertentangan saat itu: sheet 27.124.465.726 / GL posted 27.110.131.391 / register lama 27.145.108.236 (arkaaim-begbal-workbook-aug2026).

> Sebagian besar pertanyaan itu **sudah dijawab** oleh workbook 4-Aug (D.12, C.6–C.10, D.14, E.16–E.19, G.26/G.27, A.3/B.4) — jangan mengulang tanya. Yang **masih terbuka**: sel "Tanggal Cutover" (diasumsikan 31-Mei-2026), kode aset resmi untuk 410 unit `Unregistered` (F.20), serial/lokasi/custodian per unit (F.22–F.24), kode akun bank ARKA mana yang benar, serta approval Finance + pengaktifan lock date (H.32–H.33) (`docs/projects/arka-aim/BEGBAL_DETAIL.md`).

### Jebakan code_store basi

"534 duplicate codes di company 2" adalah **metadata basi**, bukan duplikat nyata — lihat bagian 7. Turunannya: `code_store` id 62 masih menyimpan key "2" yang basi dan itu tidak apa-apa karena `account_account_res_company_rel` membatasi ke company 1 (arkaaim-receivable-account-type-flipped). "534 dobel" pernah membuat sesi salah menyimpulkan bahwa set akun erajaya harus dihapus — **itu akan menghancurkan seluruh chart ARKA** (arkaaim-opening-balance-clone).

`prd_arkaaim` dan `trn_arkaaim` sama-sama punya lock date **NULL** pada kedua company, jadi Mei-2026 masih bisa diedit (arkaaim-begbal-workbook-aug2026).

## 9. Pajak & BUPOT

Audit 5-Aug-2026 dengan `prd_levis_begbal` sebagai baseline: **`prd_arkaaim` tidak butuh apa pun** — sudah di (atau di atas) paritas Levi's. `custom_tax_id` 19.0.0.5.0, `custom_tax_id.withholding_gl_posting=1`, **107 kategori**, **214 rule (107 × 2 company)** — loader-nya multi-company aware, jadi 214 itu **benar, bukan duplikat**. Rule menunjuk akun per-company yang benar (co1 → 281-286, co2 → 994-999), tanpa kebocoran lintas-company. View picker + 6 menu termasuk "Rekap Bukti Potong PPh" dan identitas coretax (NPWP penandatangan terisi untuk kedua company) semuanya ada. **Pemakaiannya masih nol** — itu operasional, bukan gap konfigurasi (arkaaim-withholding-bupot-parity).

Gap sebenarnya ada di DB training, keduanya dimuat 5-Aug-2026 → 107 kategori / 214 rule:

- `trn_arkaaim_begbal` — jalan biasa `scripts/tenants/levis/70_load_withholding.py`.
- `trn_arkaaim` — chart 8 digit sepenuhnya berbeda (PPh23=21210030, PPh4(2)=21210050, PPh26=21210060, PPh21=21210010). Semua rule ter-SKIP sampai ditambahkan env var opsional `WHT_COA_ALIAS` di skrip 70; **edit itu UNCOMMITTED di /home** per catatan tersebut (arkaaim-withholding-bupot-parity).

Drift `Z5-AG` → `Z5-AJ` (object code 24-104-02 "Jasa Management"): **arkaaim adalah sisi yang BENAR**, `prd_levis_begbal` yang salah. Diperbaiki dengan **rename kategori id=8 in place** lewat ORM — id tidak berubah, jadi kelima tabel yang mereferensikan ikut otomatis; tidak ada yang menyimpan salinan teks kodenya. Kalau skrip 70 dijalankan ulang sebelum rename itu, ia akan MEMBUAT kategori Z5-AJ kedua dan meng-orphan AML yang sudah ditandai (arkaaim-withholding-bupot-parity).

PPh native vs engine: arkaaim hanya punya pajak PPh23-Sewa + PPh22-Impor dan **0 AML** yang memakainya — dan itu **memang keadaan yang diinginkan**. Pasangan PPh 26 DGT/Non-DGT memang sah berbagi object code, jadi kecualikan dari pemeriksaan duplikat (arkaaim-withholding-bupot-parity).

### Deskripsi baris DP di PDF dan Faktur Pajak

Baris uang muka dulu tercetak `Down payment of 50.00%` di **dua** tempat karena keduanya membaca field yang sama: PDF invoice (`custom_report_templates.items_table` mencetak `line.name`) dan Faktur Pajak (`custom_coretax_export._rows_fk()` memakai `line.product_id.name or line.name`, dan baris DP **tidak punya `product_id`**). Karena itu cukup menulis ulang `name` yang tersimpan — template QWeb dan wizard coretax (keduanya addon **shared**) tidak perlu disentuh (arka-dp-line-description).

Hasil di `custom_arka_show_date` 19.0.1.4.0 → 19.0.1.6.0:

```
Jasa Drone Show 250 Unit, Biaya Luar Kota (Uang Muka 50%)

Jasa Drone Show 1000 Unit, Event Soekarno Cup, Lokasi Stadion Gelora Bung
Tomo Surabaya, 24.08.26 (Uang Muka ref: INV/ARKA/2026/08/002 tgl 14/08/2026)
```

**Sengaja SATU baris** tanpa `\n`: string yang sama masuk ke satu sel file impor coretax, dan newline di situ tidak aman. Tanggal ditulis eksplisit `dd/mm/YYYY`, bukan `format_date`, untuk alasan yang sama (arka-dp-line-description).

Kolom *Jenis Barang Jasa* juga diperbaiki: `custom_coretax_export` 19.0.1.1.0 punya `_item_jenis(line)` yang, saat baris tak punya produk, jatuh ke produk-produk SO asal dan menjawab "Jasa" hanya bila **semua** produk yang ditagih adalah service (order campuran → "Barang"). PR **#209 MERGED** 4-Sep-2026 (squash `2546f07`). `custom_coretax_export` terpasang di **5 DB** (prd_arkaaim, trn_arkaaim, tst_admfee, tst_mdm_levis, prd_levis_begbal), semuanya sudah di-`-u` supaya tidak drift (arka-dp-line-description).

> **Temuan penting soal cara kerja user:** dua invoice pelunasan yang sudah ada, `INV/ARKA/2026/08/004` dan `/005`, baris pengurangnya **tidak punya `sale_line_ids`** — user membuat invoice pelunasan **manual**, bukan lewat tombol *Create Invoice → Regular invoice* di SO. Itulah "bingung cara pelunasan" yang dilaporkan; jalur yang benar adalah bikin invoice dari SO, seksi Down Payments + baris pengurang muncul dan dapat label ini otomatis (arka-dp-line-description).

> **GOTCHA tes:** `AccountTestInvoicingCommon.init_invoice()` meledak `AccessError: account.move.withholding.line` di DB yang punya `custom_tax_id` — bikin invoice langsung dengan `.sudo()` (arka-dp-line-description).

Penomoran per company hidup di `custom_arka_aim_purchase_type` + `custom_arka_aim_numbering` (rincian di bagian 5).

> **Dua catatan yang BERTENTANGAN soal coretax:** satu menyatakan wizard coretax belum bisa dijalankan penuh di `prd_arkaaim` karena NPWP Penandatangan belum diisi (arka-dp-line-description, arkaaim-golive-issue-sheet), sementara audit 5-Aug menyatakan NPWP penandatangan **sudah terisi untuk kedua company** (arkaaim-withholding-bupot-parity). Verifikasi di DB sebelum melapor ke klien.

## 10. Petty cash & cash advance

Odoo Enterprise **tidak punya fitur cash advance / uang muka karyawan sama sekali** — Expenses hanya memodelkan "dibayar karyawan, reimburse saya". OCA `hr_expense_advance_clearing` adalah referensi industri tapi **belum diport ke 19.0**, dan tidak bisa apa adanya karena **Odoo 19 menghapus `hr.expense.sheet`** (cash-advance-arkaaim).

Jawaban platform adalah `custom_petty_cash` (ee_gap) — meski namanya petty cash, ia modul cash advance penuh. Dinaikkan ke **19.0.0.5.0** dan **TERDEPLOY 5-Aug-2026** (PR **#104** merged `1560bc1`) ke semua 6 DB yang membawanya; `prd_arkaaim` + `trn_arkaaim` di-`-u`, dan **`prd_arkaaim` dikonfigurasi penuh** (cash-advance-arkaaim).

Konfigurasi ARKA-AIM (`scripts/tenants/arkaaim/setup_cash_advance.py`, PREVIEW default; `verify_cash_advance.py` menjalankan siklus penuh lalu rollback): CA → `1109000002` Non Trade Receivables-cash advance; PC → `1115200001` Advance for operational expenses; keduanya reconcilable, keduanya company; analytic plan param = **"Project"** karena ARKA tidak punya plan "Operating Unit" (cash-advance-arkaaim).

Jurnal baru di `prd_arkaaim`: `PCPAY` (kedua company) dan `CSH` di company 2 — akun likuiditas auto-nya `1102000003 Kas`, **masih harus dikonfirmasi Accounting**. `prd_arkaaim` punya 4 type (CA/PC × 2 company) pada `warn`; **naikkan ke `block` hanya setelah Accounting mengonfirmasi angka plafon**. `FINANCE_LOGINS` dibiarkan kosong, jadi belum ada pemegang `Petty Cash / Finance` di luar admin (cash-advance-arkaaim).

> **Jurnal Payment harus DEDICATED (`PCPAY`).** `_configure_payment_journal` menulis ulang `payment_account_id` di **setiap** baris payment-method jurnal yang diberikan kepadanya. Skrip konfigurasi harus membuat jurnal kas operasional **sebelum** PCPAY, kalau tidak pencarian kas menemukan PCPAY (juga bertipe cash) dan menyerahkannya sebagai Bank-Out (cash-advance-arkaaim).

> **`trn_arkaaim` TIDAK dikonfigurasi** — chart-nya sepenuhnya berbeda (316 akun, 8 digit, tanpa akun aset advance dan tanpa jurnal `JM`), jadi skrip setup **dengan benar menolak dan rollback**. Mengonfigurasinya butuh keputusan akun lebih dulu (cash-advance-arkaaim).

`custom_petty_cash` 19.0.0.6.0 (PR **#194**, TERDEPLOY 26-Agu-2026 ke 5 DB termasuk `prd_arkaaim` + `trn_arkaaim`) menambah float bergulir per Operating Unit dengan tiga `kind` baru (`pc_initial` / `pc_realization` / `pc_claim`). **Hanya `prd_levis_begbal` yang dikonfigurasi** — empat DB lain, termasuk kedua DB ARKA, HANYA naik schema tanpa type baru, jadi perilakunya tidak berubah sama sekali (petty-cash-store-float).

> **`amount_available` ≠ `amount_gl_balance` dan itu DISENGAJA.** Available = ledger kontrol (mengasumsikan replenishment); GL = saldo akun uang muka. Setelah realisasi 250rb, available 950rb sementara GL 750rb. **Jangan "rekonsiliasi" dengan mengubah salah satunya** (petty-cash-store-float).

Topologi menu (0.6.2): aplikasi Cash Advance menyisakan Requests + Realizations saja; Finance Review / Dashboard / Reporting / Configuration pindah ke **Invoicing ▸ Cash Advance**. Konsekuensinya Invoicing digerbangi grup akuntansi, jadi pemegang `group_petty_cash_finance` saja tidak melihat apa pun di sana (petty-cash-store-float).

Tes yang **memang gagal sejak sebelumnya** di klon ARKA: `test_third_party_requires_attachment` (hr_expense minta due date di baris payable) — **pre-existing**, identik di 0.4.0 yang belum diubah. Jalankan baseline pada kode yang belum diubah sebelum menyalahkan perubahan sendiri (cash-advance-arkaaim, payment-admin-fee-module).

> **CodeQL menolak skrip yang mencetak konstanta yang namanya memuat kata *employee*** (`py/clear-text-logging-sensitive-data`). Suppression inline tidak bekerja pada CodeQL — ganti nama konstantanya; skrip setup memakai `ADVANCE_SLICE_PLAN_NAME` (cash-advance-arkaaim).

Fitur pembayaran pendukung lain di `prd_arkaaim`: `custom_payment_admin_fee` **19.0.1.1.0** (biaya admin bank di Register Payment, PR #83 & #85 merged), plus `custom_payment_methods_id` (Giro + Bank Transfer) dan `custom_payment_voucher` (Payment Voucher/Receipt PDF) dari PR **#117** (payment-admin-fee-module, arkaaim-payment-outstanding-blocker).

Multi-bill di admin fee: core `_compute_group_payment` menyetel `group_payment = len(...) == 1`, jadi **pilihan multi-bill default False** = satu payment per bill, dan di jalur itu tidak ada payment tunggal untuk ditempeli fee. Sejak 4-Aug-2026 menambahkan baris fee otomatis menyetel `group_payment = True`. Bill dari **partner berbeda** membentuk >1 batch → `can_edit_wizard` False → seksi tetap tersembunyi **by design**; register per partner (payment-admin-fee-module).

## 11. Sheet isu go-live

Ada **dua** sheet klien yang harus dibedakan.

### Sheet Juli 2026 — "[ARKA AIM] List Issue After Go Live", 7 item

Direview terhadap `prd_arkaaim` 21-Jul-2026, diperbaiki lewat commit `745825f` dan `2b1b096` di `feat/industry-packs` (arkaaim-golive-issue-sheet):

| Item | Klaim sheet | Kenyataan DB / tindakan |
| --- | --- | --- |
| #7 | user tidak bisa login | Odoo 19 cocokkan login **case-SENSITIVE**; 3 login di-lowercase |
| #5/#6 | event & lokasi tak tercetak | `custom_arka_show_date` 19.0.1.3.0 + `custom_report_templates` 19.0.0.3.0 |
| #4 | nomor rekening tak muncul | template sudah siap; **`res.partner.bank` belum ada isinya** |
| #2 | e-Faktur | `custom_coretax_export` dipasang; NPWP di-backfill dari `res.partner.vat` (7 partner) |
| #3 | menu TB/GL/Uang Muka diblokir | **BUKAN bug akses** — menu ada, tak dibatasi, dan export jalan |

`trn_arkaaim` disinkronkan ke prd 24-Jul-2026. **`custom_arka_aim_asset_register` sengaja TIDAK dipasang di `trn_arkaaim`** — akun begbal drone `1205104000`/`1205203000` tidak ada di sana, dan `post_init`-nya akan menyemai 3.329 aset tanpa akun (arkaaim-golive-issue-sheet).

### Sheet Agustus 2026 — PR #171, masih OPEN

PR **#171** (`docs/arkaaim-issue-sheet-aug2026`, base `main`) mereview sheet 25 item + tab "List Feedback User Odoo (EO)" 15 item terhadap `prd_arkaaim` **dan terhadap kode yang benar-benar jalan dari `/opt`, bukan `/home`**. Docs-only; tidak menyentuh addon, skrip, atau konfigurasi. Isinya `docs/projects/arka-aim/ISSUE_SHEET_AUG2026_STATUS.md` + dua TSV siap-tempel (PR #171).

Sembilan gap yang bertahan, masing-masing dengan bukti query (PR #171):

| Item | Klaim sheet vs kenyataan DB |
| --- | --- |
| 25 / EO#4 | payment ARKA masih mendarat di `1103000004 Outstanding Payments`; AIM sudah direct-to-bank |
| 8 / EO#9 | penyusutan Juli-2026 ke depan **tanpa satu pun jurnal**; jumlah aset sendiri cocok (3.180 running) |
| 20 / EO#1 | opening AR/AP masuk agregat — 8 dan 18 baris, hampir tak ada yang berpartner |
| 23 | user `syafiqo.zhafran@erajaya.com` **tidak pernah dibuat** |
| 4 / 21 | `res_partner_bank` kosong untuk kedua company; ARKA cetak lewat teks bebas, AIM tak cetak apa pun |
| 22 | blok di bawah BALANCE DUE itu tanda tangan + footer "If you have any questions…" |
| EO#10 | Sales Report AIM kosong karena AIM punya **nol** faktur pelanggan — pendapatan lewat jurnal MISC |
| EO#12 | tidak ada partner berpayment term default; jatuh tempo diketik tangan (bill April, due Agustus) |
| 2 | template Excel "Invoice PPN" masih harus dibangun |

**Sebelas item yang sheet catat sebagai terbuka sebenarnya SUDAH live** dan hanya perlu dilihat klien: aging export, drilldown neraca, payment voucher, cash advance, wizard lock date, Giro, KAS NEGARA (PR #171).

> Juga tercatat di PR #171: `custom_accounting_reports` ada di **19.0.0.19.0 di `/opt`** tapi **19.0.0.18.0 di `/home`**. **Deploy dari `/home` akan diam-diam membatalkan perbaikan purchase report (EO#5).**

### Akses & onboarding

Gap grup akses yang sempat menyembunyikan **SEMUA** laporan custom: `account.group_account_user` tidak meng-imply `custom_accounting_asset.group_asset_user` maupun `custom_accounting_reports.group_report_user`. Di `prd_arkaaim` hanya **3 dari 15** user akuntansi punya grup asset dan **2 dari 15** punya grup report — sebagian besar tim finance literally tidak bisa melihat laporannya. Diperbaiki lewat `scripts/tenants/arkaaim/grant_asset_and_reports.py` (commit `9e83d8b`): **23 assignment / 14 user** (arkaaim-report-gap-build).

> **Onboarding ARKA belum selesai — 6 staf nyata TIDAK BISA LOGIN, dan itu keputusan ARKA.** mei.mey, sumida.01, tania.01, yosephine.melisa, rizki.assagaf.01, eko.rahardja semuanya `password IS NULL` dan Keycloak SSO tidak terpasang. **NOL undangan dikirim** — mengirim invite berarti mengemail staf Erajaya sungguhan dan butuh sign-off eksplisit (arkaaim-report-gap-build, arkaaim-golive-issue-sheet).

Login Tania sempat membawa **karakter tak terlihat** (WORD JOINER sebelum alamat): tak mungkin diketik, jadi tak pernah cocok. Diperbaiki lewat `scripts/tenants/arkaaim/fix_invisible_login_chars.py` (`96a762f`) — layak dijalankan di DB tenant lain karena asal copy-paste-nya sama. Catatan query: `res_users.login_date` **bukan** kolom di Odoo 19 (ORM-only), dan `password` hanya bisa dilihat lewat SQL (arkaaim-report-gap-build).

Akun `User` (id=57) di `prd_arkaaim` = artefak "klik New lalu simpan sebelum diisi", **BUKAN** system admin (`base.group_system` / `group_erp_manager` keduanya False — jangan salah baca label "Accounting Administrator"). Nol jejak data. **DIBIARKAN atas keputusan user** (arkaaim-report-gap-build).

### Laporan

Gap analysis 16-Jul-2026 atas 25 laporan yang diminta klien: ~19 dari 25 sudah ada lewat engine shared `custom.report.engine`. **8 laporan SHIPPED + LIVE di `prd_arkaaim` 16-Jul-2026**, semua 8/8 terverifikasi live (arkaaim-report-gap-build):

- A1 Purchase register (#12) `custom.report.purchase`; A3 Credit Limit (#23) `custom.report.credit.limit`.
- A2 Per-Show P&L (#13/#14) — **TENANT-SCOPED** di `custom_arka_show_date`, bukan engine shared, karena ia mengquery kolom ARKA-only `account_move.x_custom_show_date`. Draf pertama di modul shared akan meng-crash tenant non-ARKA.
- A4 Asset Register Excel (#3) — sudah ada; "hilang"-nya murni soal keanggotaan grup.
- Phase B: 5 laporan `custom_ops_reports` (#15 Asset Opname, #16 Event Movement, #17 Spareparts, #18 Maintenance Health, #19 Repair History).

> **LAYERING RULE (pernah dilanggar, diperbaiki di `7b0b15d`):** modul `ee_gap/` **TIDAK BOLEH** bergantung pada modul `_tenants/`. `custom_ops_reports` sempat depend ke `custom_arka_aim_asset_register` hanya untuk satu field — dan `post_init_hook` modul tenant itu **menyemai 3.329 aset drone**, jadi memasang laporan di mana pun akan menarik seluruh seed (arkaaim-report-gap-build).

> **`-u` TIDAK cukup, container odoo WAJIB di-restart.** Container jalan `workers=4` tanpa auto-reload; Python cache modul di `sys.modules`, jadi registry reload membaca DB tapi **tidak** membaca ulang `.py` yang berubah. Modul **baru** ikut load saat reload; modul yang **dimodifikasi** tidak. Restart menyentuh **SEMUA tenant** karena container-nya bersama (arkaaim-report-gap-build).

Dua bug pre-existing yang ditemukan sambil jalan dan sudah diperbaiki: drift schema `repair_order` di **ketiga** DB ARKA (kolom `x_*` hilang padahal modul `installed`; **menghitung jumlah kolom `x_` adalah drift-check yang TIDAK berguna** — cek kolom spesifik `x_equipment_id`), dan `custom_rental` yang rusak total di Odoo 19 karena menulis `stock.move.name` yang sudah dihapus (ganti `description_picking`), plus sequence `rental.order` yang kosong sehingga setiap order bernama "RNT-???" dan picking yang tak pernah dikonfirmasi sehingga **stok tak pernah bergerak** (arkaaim-report-gap-build).

Lock Dates: `custom_accounting_full` 19.0.0.5.0 mengirim `custom.account.lock.date.wizard` di Accounting → Configuration → Lock Dates. Klien **eksplisit menolak** lock date diset dari shell: "buatkan fiturnya dan bukan diset di backend". `hard_lock_date` sengaja dikecualikan karena core menolak menurunkannya. **Lock date kedua company ARKA masih kosong dengan sengaja — jangan diisi** (arkaaim-eegap-lockdate-reports).

Kebocoran laporan yang sudah ditutup: menu `Sales Detail (XStore X24DN)` tampil di `prd_arkaaim` yang tidak punya `point_of_sale` sama sekali; sekarang diarsipkan oleh `custom_accounting_reports.hooks.sync_pos_only_menus`. **Mengarsipkan record dari data file lewat hook butuh `noupdate` di baris `ir.model.data`-nya** — kalau tidak, setiap `-u` memuat ulang XML dan meng-unarchive menu itu; sebuah migration BUKAN obatnya karena `-u` versi-sama tidak menjalankan migration (arkaaim-eegap-lockdate-reports).

> **Menyentuh `custom_accounting_full` = sapuan seluruh fleet, bukan satu DB.** TransientModel baru akan merusak autovacuum di DB yang belum di-upgrade, jadi 11 DB pembawa modul itu harus ikut naik — dan karena `custom_accounting_reports` depend padanya, Odoo meng-upgrade itu juga di mana-mana (arkaaim-eegap-lockdate-reports, arkaaim-report-gap-build).

## 12. Yang MASIH TERBUKA

Prioritas 1 — uang yang belum diakui:

1. **Rp 920.000.000 penerimaan tanpa jurnal di `prd_arkaaim`** (arkaaim-grir-accrual-gap). Obatnya bukan mengubah modul akrual: Rp 120 jt = **posting faktur draft id 277** lalu catat vendor bill di ARKA; Rp 800 jt = `SQ/AIM/2026/09/001` harus dijadikan SO dan difakturkan. `count(*)=0` vendor bill company 2 terhadap PT Aero Inovasi Media. Kalau ARKA tutup buku sekarang, Rp 920 jt kewajiban tidak muncul sementara Rp 569,2 jt sejenis muncul — **perlakuan tak seragam dalam satu periode**.
2. **Backlog penyusutan Juni-2026 Rp 565,5 jt di `prd_arkaaim` belum diposting dan cron masih mati** (asset-depreciation-grouped-monthly-entry); PR #171 menegaskan Juli ke depan pun nol jurnal. Selisih terpisah yang belum terjelaskan: baris akumulasi seeded 6.786.277.002,84 vs GL `1205203000` 7.341.288.299, beda ~Rp 555 jt.
3. **Rp 329,5 jt biaya show mengendap di persediaan** — Merdeka Run Rp 259 jt (menunggu faktur) + Rp 70,5 jt `PO/ARKA/2026/08/007` TANPA event. Yang kedua **tidak akan pernah keluar dari persediaan sampai PO-nya diberi event** (arkaaim-gr-journal-grir).

Prioritas 2 — keputusan klien/Finance yang memblokir:

1. **CoA company 1 — DITAHAN.** 9 akun hilang, 6 pointer `101402` (akun ARSIP) masih dipakai jurnal bank/kas company 1, move 272 & 273 beku di akun arsip `600000`. **PR #216 tidak boleh di-merge** sampai user memberi lampu hijau (arkaaim-archived-income-account).
2. **Nomor rekening + "atas nama" per company belum diberikan** → `setup_invoice_bank.py` (arkaaim-golive-issue-sheet, PR #171). Akibatnya AIM tidak mencetak apa pun di invoice.
3. **Basis alokasi overhead per event belum dipilih klien** — `custom.arka.event.allocation` TERDEPLOY tapi INERT, nol run. Dengan data Agustus hanya *equal* yang bermakna (arkaaim-event-chain-analytic).
4. **Angka plafon cash advance belum dikonfirmasi Accounting**, jadi 4 type di `prd_arkaaim` tetap `warn` bukan `block`; akun likuiditas `1102000003 Kas` (jurnal CSH company 2) juga menunggu konfirmasi (cash-advance-arkaaim).
5. **Kode akun bank ARKA mana yang benar** (1103019870 vs 1103019290, dst.) dan **kode aset resmi untuk 410 unit `Unregistered`**, serial/lokasi/custodian per unit (`docs/projects/arka-aim/BEGBAL_DETAIL.md`).
6. **Approval Finance + pengaktifan lock date** (H.32–H.33); lock date masih kosong dengan sengaja (arkaaim-eegap-lockdate-reports).
7. **Workbook begbal Agustus PARKIR** dengan 34 pertanyaan; sebagian sudah dijawab workbook 4-Aug, sisanya belum (arkaaim-begbal-workbook-aug2026).
8. **Akun beban untuk move 272 & 273** belum ditunjuk Accounting (arkaaim-archived-income-account).

Prioritas 3 — teknis yang belum tuntas:

1. **`trn_arkaaim` masih USD** — pricelist 1 + 3 SO + `INV/AIM/2026/07/001` posted. Sengaja di luar cakupan, tapi tetap salah (arkaaim-pricelist-currency-usd).
2. **Company 1 (AIM) tidak punya kurs CNY** — dokumen CNY di sana kena fallback 1:1 (arkaaim-cny-payment-rate).
3. **Bug sumber lokasi `custom_rental` mode bulk BELUM diperbaiki.** Hanya mode serial yang diperbaiki `custom_asset_stock_link`; deployment memakai mode bulk (rental-sale-deployment).
4. **`deployment_product_id` belum divalidasi tipenya** — perbaikan wajar = domain ke produk storable ber-`tracking='serial'` (rental-sale-deployment).
5. **`consolidate_pooled_assets.py` belum pernah dijalankan dengan APPLY di DB mana pun** (pooled-quantity-fixed-assets).
6. **Jalur lifecycle & deployment belum pernah dieksekusi di produksi** — teruji-klon, bukan teruji-produksi (asset-lifecycle-module, rental-sale-deployment).
7. **`1106000001 Trade Receivables` masih bertipe `liability_payable`** menurut catatan 10-Aug (arkaaim-payment-outstanding-blocker), tapi catatan 2-Sep menyatakan sudah dikembalikan ke `asset_receivable` (arkaaim-receivable-account-type-flipped). **Catatan 10-Aug yang lebih tua — verifikasi di DB**, jangan mengulang perbaikan.
8. **Edit `WHT_COA_ALIAS` di `scripts/tenants/levis/70_load_withholding.py` UNCOMMITTED di /home** per catatan 5-Aug (arkaaim-withholding-bupot-parity).

PR yang menggantung:

| PR | Isi | Status |
| --- | --- | --- |
| #171 | review sheet go-live Agustus (docs-only) | **OPEN** |
| #216 | langkah CoA company 1 | **DITAHAN atas permintaan user** |
| #227 | `custom_rental_sale` (SO → deployment) | di-stack di atas #222, sudah LIVE di prd |
| #232 | scoping lintas-company `custom_asset_lifecycle` | per catatan "belum merge", skripnya sudah jalan di prd |
| #233 | `auto_confirm_mirror_so` | terdeploy, **flag masih FALSE** |

> Soal #227 dan #232: keduanya sudah **berjalan di produksi** sementara status git-nya belum tuntas. Jangan menyamakan "belum merge" dengan "belum jalan" di vertikal ini.

## 13. JANGAN - khusus ARKA-AIM

> **JANGAN memposting register aset sebagai jurnal perolehan.** Armada sudah dikapitalisasi di GL saldo awal; `custom.fixed.asset.create()` sengaja tidak menyentuh GL, sisi stoknya wajib bernilai nol, dan skrip materialisasi menghentikan diri kalau ada satu jurnal stok muncul (aim-drone-asset-register, `docs/projects/arka-aim/BEGBAL_DETAIL.md`).

> **JANGAN memposting 39.840 baris penyusutan `posted=true, move_id NULL`** — itu akumulasi saldo awal dan memposting = dobel (asset-depreciation-grouped-monthly-entry, aim-drone-asset-register).

> **JANGAN menyalakan `real_time` untuk kategori aset drone.** Fixed Assets (Non-Valuated) sengaja `periodic`; mengakru drone sebagai persediaan = dobel terhadap register aset (arkaaim-gr-journal-grir).

> **JANGAN menulis field event ke header faktur pelanggan.** `x_custom_show_date` di `out_invoice` menambatkan ulang termin — satu kasus nyata memindahkan jatuh tempo 21 hari lebih awal. Tag di baris jurnalnya (arkaaim-event-tagging-leftovers).

> **JANGAN menulis analytic event lewat SQL.** Isi field event di PO/SO-nya lalu jalankan ulang `backfill_event_analytic.py` (arkaaim-event-tagging-leftovers).

> **JANGAN membuang faktur draft id 277.** Peringatan lama yang menyebutnya duplikat SALAH dan berbahaya — draft itu satu-satunya dokumen atas barang Rp 120 jt yang sudah diterima ARKA; memposting-nya adalah obatnya (arkaaim-grir-accrual-gap).

> **JANGAN mencari akun hanya lewat `code`.** `code_store` menyimpan key untuk company yang akunnya bukan miliknya, dan id lebih kecil menang; Anda dapat akun perusahaan lain. Selalu tambahkan filter `company_ids` (odoo19-company-dependent-account-code, arkaaim-trade-nontrade-purchase-type).

> **JANGAN mencari gudang hanya lewat `code`.** Kode gudang TIDAK unik antar perusahaan, dan gudang bernama `ARKA` justru **milik AIM**. Kalau gudang harus ditebak, tanya register: lokasi mana yang menampung unit terbanyak milik perusahaan itu (arkaaim-drone-asset-in-stock, asset-lifecycle-module).

> **JANGAN menghapus set akun `account.2_erajaya_*`** dengan alasan "534 duplicate codes" — itu metadata basi pada akun company-1, dan menghapusnya menghancurkan seluruh chart ARKA (arkaaim-opening-balance-clone).

> **JANGAN memperbaiki kurs dengan menduplikasi baris KMK per-company.** Satu baris company-scoped mengalahkan SEMUA baris shared tanpa memandang tanggal; obatnya menghapus baris company-scoped itu (odoo19-company-rate-shadows-shared).

> **JANGAN mengisi lock date dari backend.** Klien eksplisit meminta fitur, bukan set dari shell; lock date kedua company ARKA kosong dengan sengaja (arkaaim-eegap-lockdate-reports).

> **JANGAN mencabut hak edit `account.account` dari `ricad.lingga@erajaya.com`** — sudah ditolak user 2-Sep-2026; perlakukan insiden tipe akun terbalik sebagai salah klik (arkaaim-receivable-account-type-flipped).

> **JANGAN mengirim undangan/reset password ke 6 user tanpa password** — itu mengemail staf Erajaya sungguhan dan butuh sign-off eksplisit. Juga jangan menghapus akun `User` id=57, dibiarkan atas keputusan user (arkaaim-report-gap-build).

> **JANGAN meng-untrack keempat CSV begbal/register** — dibaca per nama di `post_init_hook` tanpa penjagaan file-hilang; install/`-u` akan gagal FileNotFoundError (arkaaim-begbal-detail-aug04).

> **JANGAN memasang `custom_arka_aim_asset_register` di `trn_arkaaim`** — akun begbal drone tidak ada di sana dan `post_init` akan menyemai 3.329 aset tanpa akun (arkaaim-golive-issue-sheet).

> **JANGAN membuat modul `ee_gap/` bergantung pada modul `_tenants/`.** Pelanggaran satu kali membuat instalasi laporan menarik seed 3.329 aset drone (arkaaim-report-gap-build).

> **JANGAN deploy `custom_accounting_reports` dari `/home`** — `/opt` ada di 19.0.0.19.0 sementara `/home` 19.0.0.18.0, dan deploy dari `/home` diam-diam membatalkan perbaikan purchase report (PR #171).

> **JANGAN menyalakan `auto_confirm_mirror_so` sebelum sisi pajak diputuskan.** Baris mirror dibuat tanpa pajak, jadi auto-confirm mengunci SO AIM tanpa PPN; dan kalau `spawn_rental_loan` ikut nyala, confirm otomatis akan melahirkan `rental.order` (ic-mirror-auto-confirm).

> **JANGAN mengandalkan `-u` saja.** Restart `odoo` + `odoo-mgmt` + `odoo-front` sesudah setiap perubahan kode, dan untuk perbaikan posisi stok: resync DULU, restart SESUDAH (arkaaim-report-gap-build, asset-lifecycle-module).

> **JANGAN memakai `move.value` untuk retur vendor.** Move keluar dinilai metode biaya dan `standard_price` kosong di tenant ini → akru mengendap selamanya. Nilai retur dari porsi `origin_returned_move_id` (arkaaim-gr-journal-grir).

> **JANGAN menjual backfill GR sebagai "koreksi angka salah".** 15 baris Rp 341 jt yang dilewati sudah membawa analytic event dan sudah masuk P&L per Event; yang berbeda hanya akun penampung — itu perubahan **penyajian** atas bulan terlapor (arkaaim-gr-journal-grir).

> **JANGAN menulis "sudah terbukti di produksi"** untuk lifecycle aset maupun jalur deployment — semuanya teruji-klon (asset-lifecycle-module, rental-sale-deployment).

> **JANGAN menjalankan perbaikan data tanpa DUA pre-flight: dump, DAN "ada yang sedang bekerja di sistem?"** Perbaikan quant 8-Sep berjalan saat user sungguhan membuat SO dan aman hanya secara kebetulan (arkaaim-duplicate-quant-rows, always-dump-before-touching-prod).
