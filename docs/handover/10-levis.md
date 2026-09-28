# Handover — Levi's (PT ERA Busana Retailindo)

Dokumen ini ditulis sebagai serah-terima. Setiap angka dan tanggal diberi sumber dalam tanda kurung: nama file memory (tanpa `.md`), path repo, nomor PR, atau nama DB. Setelah memory dihapus, dokumen ini harus tetap bisa diaudit.

Posisi pengetahuan: **28 September 2026**. Apa pun yang terjadi sesudah itu tidak ada di sini.

> Memory yang menandai dirinya BASI/SALAH ditulis di dokumen ini sebagai **peringatan**,
> bukan sebagai fakta. Bagian 14 mengumpulkan larangan yang khusus berlaku di vertikal ini.

## 1. Ringkasan vertikal

**Tenant.** PT ERA Busana Retailindo (disingkat **EBR**) = pemegang lisensi retail Levi's. Di Odoo ia `res.company` **id 1**, nama "PT. ERA Busana Retailindo", mata uang IDR, `rounding` 0,01 (`levis-ebr-tb-gl-load`). Operasi tokonya di bawah PT Sinar Eka Selaras (SES) — itulah sebabnya setiap Operating Unit bernama `OLS SES - <NAMA MALL>` (`levis-operating-unit-normalization`). NPWP perusahaan pada template pajak klien = `1000000006199490` (`levis-tax-import-templates`).

**DB yang benar-benar hidup: `prd_levis_begbal`.** Dibuat 8-Jul-2026 sebagai klon blank-ledger dari `rnd_levis` (`retail-import-dataquality-fix`), lalu diisi begbal + penjualan. Semua pekerjaan nyata ada di sini: impor retail, clearing, impor bank, COGS, GR/IR, pajak, aset.

**Peringatan nama DB.** `prd_levis` **bernama prd tetapi hanyalah environment testing** — dikonfirmasi user 8-Sep-2026 (`retail-feed-shared-dropfolder-race`). DB itu praktis mati: `cogs_catchup_enabled=0`, 88 kategori tanpa akun COGS/persediaan, `account_move` terakhir dibuat 5-Agu-2026 (`levis-cogs-open-items-sep25`). Jangan pakai angkanya untuk laporan klien.

Daftar DB yang pernah/masih dipakai:

| DB | Peran | Catatan |
| --- | --- | --- |
| `prd_levis_begbal` | PRODUKSI sebenarnya | seluruh operasi; 73 user aktif (`levis-admin-rights-cleanup`) |
| `prd_levis` | testing meski bernama prd | `retail-feed-shared-dropfolder-race` |
| `prd_detail_levis` | klon paritas Juli | `levis-gl-2026-detail-load` |
| `prd_levis_AP` | UAT purchase/AP user | `levis-uat-review-jul24` |
| `rnd_levis` | master/rnd, sumber klon | `levis-txn-reset` |
| `demo_updated_levis` | DB uji berkonfigurasi | `demo-updated-levis-setup` |
| `demo_levis` | demo lama | `demo-levis-coa-stray-categ` |

DB `tst_*` / `scratch_*` / `demo_levis_wms` adalah DB kerja sesi lain dan sering di-drop; `demo_levis_wms` sempat merusak feed produksi (bagian 3).

**Garis waktu go-live.** Begbal dikunci per 31-Mei-2026 lalu ditambah penjualan X24 Juni (`levis-begbal-may-plus-june-sales`). `fiscalyear_lock_date` bergerak 30-Jun → 31-Jul (12-Agu, `levis-clearing-narrative-gotchas`) → 31-Agu-2026 (`levis-cogs-open-items-sep25`). Sejak Juli feed malam berjalan otomatis (`levis-mail-ingest-infra-fix-jul24`).

**Cakupan toko.** 24 OU aktif per 24-Jul-2026 (`levis-operating-unit-normalization`), naik jadi **33 OU aktif (HO + 32 toko)** setelah 9 toko Sulawesi/Kalimantan ditambahkan 16-Sep-2026 (`levis-new-stores-sept2026`).

**Pengguna & PIC klien** (dari `levis-golive-client-answers-sep16`, `levis-user-testing-gap-review`, `levis-categ-change-governance`, `levis-t20-closure-evidence`):

- Accounting — **Devina Himelda** (juga tier-2 approver kategori, bersama **Hermawan**)
- Finance-AP — **Hermawan**
- Tim Tax — **Azis**, **Stephani** (gate G7–G10, K-2 semuanya masih nol jawaban)
- IT BA — **Pak Ade** (pemilik catatan "COA Tampungan", isu #22)
- **Fiqo** (gate G15, akun advance), **InaL** (gate G11, MDR)
- Admin utama Odoo: `am.ademaryadi@gmail.com` (`levis-admin-rights-cleanup`)

**Keamanan akses.** 6-Aug-2026 seluruh 73 user `prd_levis_begbal` memegang `base.group_system`; dicabut dari 71 lewat `scripts/tenants/levis/84_tidy_admin_rights.py` (commit `11013e7`). `prd_levis` 28→1, `prd_detail_levis` 27→1, `rnd_levis` 43→2. `prd_levis_AP` **sengaja dilewati** — 4 user di sana tanpa grup fungsional sama sekali (`levis-admin-rights-cleanup`). Backup rollback di `/opt/odoo-platform/data/rights-backup/`.

## 2. Modul yang dimiliki

🔴 **Versi di checkout git `/home` TERTINGGAL JAUH dari produksi.** Per 27-Agu-2026 `origin/main` di 19.0.1.34.0 sementara 7 DB Levi's menjalankan 19.0.1.38.0 (`levis-module-versions-lag-git`); per 25-Sep-2026 produksi sudah **19.0.1.63.0** sementara `/home` masih 19.0.1.41.0 (`levis-cogs-automation-deploy-sep25`). Kolom "git /home" di bawah adalah yang terbaca di repo saat dokumen ini ditulis.

Modul tenant (`addons/_tenants/`):

| Modul | git /home | Produksi terakhir tercatat | Fungsi |
| --- | --- | --- | --- |
| `custom_levis_localization` | 19.0.1.41.0 | **19.0.1.63.0** | inti vertikal: Trade/Non-Trade, OU, GR journal, clearing POS, COGS, store-day |
| `custom_levis_bank_reconcile` | 19.0.1.2.0 | 1.3.0 (PR #250) | matcher bank per toko, gross vs MDR |
| `custom_levis_asset_accounts` | 19.0.2.0.0 | 2.3.0 | seed 13 grup aset EBR + ROU + revaluasi IAS 16 |
| `custom_levis_categ_approval` | 19.0.1.0.0 | 19.0.1.0.0 | gerbang persetujuan 2-tier perubahan kategori produk |
| `custom_levis_mdr` | **tidak di `main`**; ada di branch PR #264 | 19.0.1.0.0 di `/opt` | 39 tarif MDR per payment type + view `levis.mdr.txn` |

🔴 `custom_levis_mdr` **tidak ada di `main` maupun di pohon kerja `/home`**, tapi ia berjalan di produksi dari `/opt`. Diverifikasi 28-Sep-2026: kodenya ADA di git, pada commit `1280256a` (18-Sep) yang hanya terjangkau dari branch `feat/levis-store-tender-mdr` dan `feat/levis-x70t-settlement` — keduanya sudah di-push ke origin, dan yang terakhir adalah **PR #264 yang masih terbuka**. Konsekuensinya: `-u` dari worktree GAGAL untuk `prd_levis_begbal` (`levis-cogs-automation-deploy-sep25`), dan **kalau PR #264 ditutup tanpa di-merge, kode produksi ini kehilangan rumahnya di `main`**. Lihat bagian 14.

Modul ee_gap / core yang kritis untuk vertikal ini:

| Modul | git /home | Produksi terakhir tercatat | Fungsi |
| --- | --- | --- | --- |
| `custom_retail_import` | 19.0.0.24.0 | **19.0.0.27.0** | X101/X20/X24DN/X70D/X70T/X31/X48 + mailbox IMAP + feed |
| `custom_retail_import_pos` | 19.0.0.5.0 | 19.0.0.6.0 | jembatan POS: gross-up diskon, retur, pajak verbatim |
| `custom_retail_import_recon` | 19.0.1.0.0 | terpasang 2 DB | laporan rekon X-Store vs Odoo per transaksi |
| `custom_retail_import_api` | 19.0.1.0.0 | hanya DB tst | REST MDM HUB product-master |
| `custom_accounting_reports` | 19.0.0.27.0 | **19.0.0.32.0** | TB/GL/Aging/Purchase/PPN digunggung/laporan stok |
| `custom_accounting_asset` | 19.0.0.7.0 | 19.0.0.11.0 | register aset, depresiasi, revaluasi, disposal |
| `custom_accounting_full` | 19.0.0.7.0 | 0.7.0 | wizard Lock Date + guard duplikat ref bill |
| `custom_account_reconcile` | 19.0.3.0.0 | 3.1.0 | wizard rekonsiliasi + 4 guard anti-hilang-rekonsiliasi |
| `custom_bank_import` | 19.0.0.6.0 | 19.0.0.6.0 | parser CSV/XLS BCA/BRI/BNI/Mandiri + dedup |
| `custom_tax_id` | 19.0.0.6.0 | **19.0.0.9.0** | PPh (107 kode objek), DPP Nilai Lain, guard akun |
| `custom_coretax_export` | 19.0.1.8.0 | 19.0.1.9.0 | FK/OF + Retur, layout Coretax & Mitra Pajakku |
| `custom_petty_cash` | 19.0.0.6.2 | 0.6.3 | Cash Advance / Petty Cash / store float |
| `custom_po_return` | 19.0.0.1.0 | terpasang | RTV vendor return, seq `RTV/%(year)s/` |
| `custom_wms_reports` | 19.0.0.2.0 | terpasang | Purchase Return Report + Stock Summary (menu Inventory) |
| `custom_web_layout_memory` | 19.0.1.3.0 | 1.4.0 | memori layout list (isu #11) |

Catatan penamaan yang menipu: modul bernama `custom_coretax_export` sesungguhnya menulis layout **Mitra Pajakku**, bukan Coretax (`levis-tax-import-templates`).

## 3. Retail import X-file

### Peta berkas

| Berkas | Isi | Status pipeline |
| --- | --- | --- |
| X101 | material master, 214.305 baris | manual/SFTP, **tidak pernah dikirim email** |
| X20 | snapshot on-hand | di-ingest |
| X24DN | detail penjualan per transaksi | di-ingest + posting GL |
| X70D | detail tender | di-ingest + RIREC |
| X70T | settlement tender (cross-tab) | di-ingest sejak 26-Sep-2026 |
| X31 | discount journal | staging saja (`x31_post_enabled=0`) |
| X32P | stock movement with price | backup saja |
| X48 | retur | `x48_post_enabled=0`, ada bug |

Sumber: `levis-mail-ingest`, `levis-x70t-acquirer-tenders`, `docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md`.

### X101 — material master

- **Dua kode per item, keduanya sah.** `PROD SKU` (`000A900050OS`) = `default_code` Odoo & XStore; `PRODUCT CODE + ITEM SIZE` (`000A9-0005OS`) dipakai untuk order ke supplier. Relasinya eksak di seluruh 214.305 baris: `PROD SKU = PRODUCT CODE tanpa tanda hubung + "0" + ITEM SIZE + INSEAM` (`levis-x101-dual-code-po-import`).
- Upload PO memakai bentuk ber-hubung sehingga importer mati. Perbaikannya **override `name_search`, bukan menulis ulang `default_code`** (`levis-x101-dual-code-po-import`).
- **`udf2` adalah PROD SKU, bukan `skuCode`** — kunci API MDM (`levis-mdm-product-api`).
- **Multi-GTIN**: tiap varian punya beberapa GTIN; yang ekstra disimpan sebagai `product.barcode`. Setelah perbaikan, unmatched 15.356 → **100**, resolusi EAN X24 45% → 88% di `prd_levis_begbal` (`retail-import-x101-multigtin-variant-fix`).
- **Odoo menghilangkan atribut bernilai tunggal dari kombinasi varian** — itu sebab ~15rb SKU tidak pernah cocok (`retail-import-x101-multigtin-variant-fix`).
- **X101 penuh TIDAK BISA lewat queue_job** — `limit_time_cpu=600` membunuhnya, requeuer mengulang dari nol sampai `max_retries=5` lalu `failed`. Jalankan lewat `odoo shell`; satu run penuh ±22 menit (`x101-import-queue-limits-and-price-gap`).
- **Impor ulang TIDAK pernah memperbarui harga.** Butuh `retail_import.x101_update_price` (default MATI). 8 template yang lahir 31-Jul-2026 tetap `list_price = 0` (`x101-import-queue-limits-and-price-gap`).
- Sel numerik: satu ukuran `10.5` membuat Excel menaip seluruh kolom ITEM SIZE sebagai angka → crash; kini di-coerce lewat allowlist `TEXT_FIELDS` (PR #119, 8 DB, 19.0.0.23.0) (`retail-import-numeric-cell-coercion`).
- **375 baris X101 ditolak "invalid/zero price"** = 8 style garmen nyata dengan `retail_price` kosong (`004CA-0000`, `004CK-0000`, `0057N-0000`, `009NP-0000`, `00ACJ-0009`, `00ACJ-0012`, `A4750-0134`, `A4750-0160`) — butuh master terkoreksi (`levis-july-sales-gap-aug03`).
- **16.324 template berharga nol di `rnd_levis`/`prd_levis_begbal` adalah populasi NON-SUMBER** (0% cocok dengan X101 by code/SKU). Keputusan user 8-Jul-2026: **dibiarkan apa adanya**, tidak bisa di-backfill (`retail-import-dataquality-fix`).
- Performa: 3 penyebab load produk lambat sudah diperbaiki (index list varian, chatter per varian, index `product_value`) — 280 ms → 10,7 ms per halaman (`levis-product-load-perf`).

### X24DN — sumber kebenaran penjualan

- **Satu POS session (dan satu jurnal penutup) per (toko, hari dagang)**, dan jurnal itu sekaligus membawa reklas diskon. Tidak ada lagi RIADJ untuk X24 (RIADJ = X31 saja). Semua baris — termasuk PPN dan Suspense — membawa `analytic_distribution` OU toko (`retail-import-x24dn-daily-journals`).
- Verifikasi Juni-2026 di `prd_levis_begbal`: 4.387 order, 239 sesi semua `closed`, 239 jurnal INV, **Rp 0 selisih** vs workbook — PPN 619.692.565, Suspense 6.253.197.087, Sales Discount 1.234.678.813, Gross Sales kredit 6.868.183.335 (`retail-import-x24dn-daily-journals`).
- **Decouple mode**: X24 posting ke POS Suspense Clearing `1106000112` lewat satu metode sintetis SUSPENSE; X70D lalu memposting RIREC (Dr piutang per tender / Cr Suspense) dan merekonsiliasinya. Syarat `x24_close_sessions=1` (`retail-import-decouple-suspense`).
- 🔴 Bug historis decouple: `journal_id` metode SUSPENSE **harus kosong** agar `type='pay_later'`. Kalau diisi, POS close menerbitkan `account.payment` yang langsung menguras suspense dan bertanggal hari impor (`retail-import-decouple-suspense`).
- **Strict-product** (`retail_import.x24_strict_product=1`): satu SKU tak dikenal memarkir **SELURUH transaksi**. Keputusan user: "strict murni", tanpa whitelist (`retail-import-strict-product`). Baris kategori **NP** dikecualikan agar paper bag/jasa tailoring tidak meledakkan ~3.900 transaksi (`retail-import-x24-composite-match-npmerch`).
- **ITEM CODE X24 adalah kode dasar**, WAIST/INSEAM di kolom terpisah — matcher harus merangkai `code+waist+inseam`. Line match 36,4% → 64,9% (`retail-import-x24-composite-match-npmerch`).
- Produk NP yang lazy-create dulu tanpa `categ_id` sehingga pendapatannya jatuh ke `5199000000 Gross Sales-Others` — Rp 94.360.361 penjualan Juni salah rute di `prd_levis_begbal`; diperbaiki 19.0.0.5.0 + `34_coa_categ_tree.py` (`retail-import-x24-np-category-fix`).
- Paper bag `BGNM*` dipindahkan ke **Miscellaneous** lewat `retail_import.x24_np_category_id = 501`; `5199000000` jadi 0 baris di `prd_levis_begbal` (`levis-others-to-miscellaneous`).
- 🔴 **`x24_np_category_id` adalah ID yang BERBEDA antar DB** (begbal 501, prd_levis 360, dua-duanya "Miscellaneous") — cocokkan by NAMA, jangan salin angkanya (`levis-gl-2026-detail-load`).
- 🔴 **SATU sesi POS yang dibuka manual mematikan seluruh impor X24 semalam.** Sesi 2041 (KELAPA GADING, dibuka 10-Agu oleh `martha.ritonga@erajaya.com`) memblokir **8 malam** penjualan di `prd_levis_begbal` sampai diperbaiki 18-Agu. Gejalanya senyap: log `state='running'`, feed `last_status=ok`, file diarsipkan karena hash duplikat (`x24-import-blocked-by-open-pos-session`).
- Impor multi-hari (backfill) menabrak guard "satu-per-satu": setiap selesai satu berkas, log-nya harus dibalik `imported` → `partial`, dan urutan wajib X24 → X70D (`levis-july-import-prd-begbal`).

### X70D / X70T — tender & settlement

- Juli 2026 `prd_levis_begbal`: 9.975 order, Rp 13.281.038.471 setelah pemulihan (`levis-july-import-prd-begbal`).
- Residual X70D Juli ±Rp 39,25 juta (0,30%) **tuntas didiagnosis** — dua gap master data: toko 80448 PASKAL BANDUNG tanpa `pos.config`, dan SKU `0057O00010` "BAGGY BARREL MAX VOLUME" tanpa barcode/default_code. Keduanya selesai 24-Jul (`levis-july-import-prd-begbal`).
- 🔴 **Sejak 16-Sep-2026 X70D BERHENTI memuat tender ber-acquirer** (14 kode: `BCA_QRIS`, `BCA_DEBIT_GPN`, `BCA_CARD`, `BRI_QRIS`, `MANDIRI_QRIS`, `OFFLINE_BANK_TRANSFER`, dst). Dibuktikan atas 87 pasang file malam X70T/X70D: X70D kurang **persis** sebesar total kode acquirer — Rp 389.478.201 untuk 16–24 Sep (`levis-x70t-acquirer-tenders`).
- **X70T adalah laporan yang memuatnya.** Bentuknya cross-tab, set kolom berubah tiap malam, header di baris 10, kolom terakhir `NON CASH(Total)` adalah **subtotal bukan tender**. Dibangun `profile.read_wide_records` + `_post_x70t_settlement` yang memposting **SELISIH** (PR #264, `custom_retail_import` 19.0.0.27.0).
- **SELESAI 26-Sep-2026 di `prd_levis_begbal`**: susulan 13–25 Sep memposting Rp 1.307.639.151; **POS Suspense Clearing = 0 untuk SETIAP hari September**. Sekarang ada 24 akun `POS Receivable - <tender>`. Feed live id 17 (`feed_levis_x70t`, sequence 60, SESUDAH X70D seq 20); feed lama id 9 dipensiunkan (`levis-x70t-acquirer-tenders`).
- **Lubang feed X-center September**: 13-Sep X70D tidak dikirim (5 dari 6 laporan datang); **15-Sep tidak ada satu pun laporan** — satu hari dagang 22 toko hilang total, ±Rp 300 juta, `pos_order` 15-Sep = 0 baris. Odoo terbukti bersih (cron jalan, Trash/Junk kosong, purge hanya >30 hari). 13-Sep bisa dipulihkan dari X70T (total Rp 707.801.650, persis = total pos.order); **15-Sep tidak ada sumber apa pun, harus ditagih ulang ke X-center** (`levis-x70d-feed-gaps-sep2026`).

### Feed drop-folder, mail ingest, MDM API

- 🔴 **Semua feed menunjuk `/mnt/data_levis/data` tanpa penguncian per DB.** Per 8-Sep-2026 ada 8 DB berebut folder yang sama; yang kalah kehilangan file **tanpa error** dan melaporkan `ok — Imported 0 new file(s)`. Akibat nyata: 22 & 23-Agu `prd_levis_begbal` kehilangan X70D+X31 → Rp 1.558.706.480 menggantung di POS Suspense Clearing (`retail-feed-shared-dropfolder-race`).
- 8-Sep sore balapan **DITUTUP**: 71 feed dinonaktifkan; kini hanya `prd_levis_begbal` mengambil file (`retail-feed-shared-dropfolder-race`).
- 🔴 **TERULANG 26-Sep-2026 lewat `demo_levis_wms`** — klon `prd_levis_begbal` yang dibuat ±20-Sep membawa 13 feed + 2 mailbox IMAP aktif; ia menang balapan X70D/X31 tiap malam sejak 21-Sep → suspense prd menganggur Rp 1.413.245.899. Mailbox klonnya bahkan `purge_enabled=t, dry_run=f` sehingga menghapus surat dari INBOX bersama (`retail-feed-shared-dropfolder-race`).
- Mail ingest: `retail.import.mailbox` menarik dari `mail.erajaya.com:993` (`levis.data@erajaya.com`, pengirim `XcenterAdmin@levi.com`), 6 lampiran/malam 03:30 +0800, ±10,4 MB/hari. **Invarian penghapusan: surat dihapus atas kekuatan BACKUP-nya, bukan kesuksesan impor** (`levis-mail-ingest`).
- Kredensial: `LEVIS_MAIL_PASSWORD` disimpan di `/opt/odoo-platform/.env` (mode 0600), backup `/opt/odoo-platform/.env.bak.20260724-mailpw`. Nilai yang benar pernah hanya ada di env container `odoo19-platform-odoo`. **Verifikasi dengan hash, jangan pernah dicetak**, dan password itu pernah tertempel di transkrip chat sehingga **harus dirotasi** (`levis-mail-ingest-infra-fix-jul24`, `levis-mail-ingest`).
- Orkestrator produksi: cron id **46** "Levi's nightly full-auto (mail→import→post)" (per jam) dan cron id **47** monitor residual suspense (harian, alert in-app saja karena DB tanpa SMTP) (`levis-mail-ingest-infra-fix-jul24`).
- Ekspor X70D kiriman toko: dari 25 lampiran satu sore, **20 benar-benar X70D** tapi hanya 10 lolos glob `X70D*.xlsx`; judul kolom bahkan berbeda ANTAR-SHEET di berkas yang sama. Keputusan staging pindah dari **nama ke isi** (`ingest_signature = TRANSNUM,TENDER AMOUNT`), `custom_retail_import` 19.0.0.26.0, 5 DB (`levis-store-export-variants`).
- MDM product API: modul `custom_retail_import_api`, route `/api/mdm/*`, auth `api_key` + CIDR allow-list wajib. CIDR Mulesoft yang sebenarnya **tidak terdokumentasi di mana pun**; sementara disempitkan ke `172.18.0.0/16` (`retail-import-20-deploy-aug03`, `levis-mdm-product-api`).

## 4. POS, clearing & store-day

### Clearing bulanan — status per bulan

| Bulan | Status | Bukti |
| --- | --- | --- |
| Juni 2026 (AR) | **SELESAI** 4-Aug + lanjutan 7-Aug | `levis-june-ar-fico-final-rekon`, `levis-june-ar-clearing-completed` |
| Juli 2026 | **SELESAI & DIPOSTING** 11-Aug | `levis-july-clearing-completed` |
| Agustus 2026 | **SELESAI & DIPOSTING** 9-Sep | `levis-august-clearing-prep` |
| September 2026 | **BELUM** | MDR Rp 30,2 jt sudah di bank, GL 7104000001 masih NOL (`levis-wave3-decisions-sep18`) |

**Juni 2026.** Rekon FICO cocok ke rupiah (AR 1.025.747.288 / deposit −671.710.641 / MDR 25.971.461,73). Tiga jurnal adjustment diposting 4-Aug **bertanggal 01-JUL**, bukan 30-Jun: REALOKASI 9.612.964, MDR 527.265, CLEARING 667.523.715 (`levis-june-ar-fico-final-rekon`). Lanjutannya 7-Aug: `GLJV/2026/07/0026` SALESMANUAL 14.608.080, `/0027` TOPUP 4.186.925, `/0028` ADJ 264.842 (`levis-june-ar-clearing-completed`). 🔴 Kunci yang sempat salah diasumsikan: **entry sales manual Rp 14.608.080 BUKAN pendapatan baru** — uangnya masuk Juni tapi toko menginput ulang penjualannya di X24DN Juli, jadi yang benar adalah **reklas** Dr `1106000001` / Cr POS Receivable, bukan Dr AR / Cr Sales. Membukukan sebagai pendapatan akan **mendobel pendapatan dan PPN Keluaran Juli** (`levis-june-ar-clearing-completed`).

**Juli 2026.** 63 jurnal `EBR-CLR-JULI-2026-*` (`GLJV/2026/07/0034..0096`) diposting via `scripts/tenants/levis/90_post_clearing_juli.py` dengan `CLR_POST=1`; total debit Rp 32.055.956.081. Hasil akhir: Bank Suspense `1103000002` 1.530.199.113,09; MDR `7104000001` 94.186.098,68; AR EBR `1106000001` 2.949.900; POS receivable Juli terbuka 490.494.449 pada 85 baris (`levis-july-clearing-completed`). Dokumen lengkap: `docs/projects/levis/CLEARING_JULI2026.md`. Sisa 490.494.449 ditelusuri tuntas 19-Aug: timing 31-Jul 412.665.600 + KOL Grand Indonesia 76.926.875 + AEON 1.400.875 + selisih antar tender −498.901 (`levis-july-clearing-completed`). 🔴 Fitur `levis.pos.clearing` **sengaja TIDAK dipakai untuk Juli** — memakai keduanya akan menjanjikan kolam piutang yang sama dua kali.

**Agustus 2026.** 32 jurnal (`GLJV/2026/08/0075..0106`, ref `EBR-CLR-AGUSTUS-2026-A/B-<tgl>`), total debit **15.416.516.180**. Blok A settlement 15.003.850.580 bruto (MDR 61.065.767,34, 30 jurnal); blok B collection AR Juli 412.665.600 bruto (MDR 1.539.811,15, 2 jurnal). MDR Agustus terbentuk 62.605.578,49; Bank Suspense per 31-Agu **−0,17**. Blok C dilewati karena Finance melengkapi jurnal ATS 7–8 Sep (35 move, Rp 13.918.328.412,70) (`levis-august-clearing-prep`). Skrip: `104_prep_clearing_agustus.py` + `105_clearing_agustus.py`. 🔴 **Clearing tidak merekonsiliasi kaki Bank Suspense** — GL benar tapi widget rekonsiliasi bank menahan 2.348 baris. Obatnya `scripts/tenants/levis/107_reconcile_bank_suspense.py` (`REC_MONTH=YYYY-MM`, PREVIEW default, `REC_COMMIT=1`). **Ini akan terulang tiap bulan — jalankan 107 sesudah setiap run clearing** (`levis-august-clearing-prep`).

### Selisih yang sudah terurai

- **Rp 901.974** (Juli, terbawa utuh ke Agustus). GL `1106000101..110` per 31-Jul = 490.494.449 vs sheet AR JULI 489.592.475. Biang keroknya satu jurnal `GLJV/2026/07/0047` yang mengalokasi lebih kecil dari piutang harinya (kurang bayar 06-Jul total 2.700.775). Per OU: AEON +1.400.875, CENTRAL PARK −499.900, PIM 1 +1.000, PVJ −1 (`levis-july-901974-gap`). ⚠️ Angka "belum tertelusur 599.726" di memory clearing Agustus adalah **artefak** — selalu bandingkan `balance ≤ 31-Jul`, bukan `amount_residual`.
- **Rp 1.980.248,29** — "selisih closing Juli" ternyata **plug suspense** `GLJV/2026/07/0118` (Dr `1103000002` / Cr `2103100003`). Dekomposisi eksak: 5 baris BCA `unknown` −2.791.009 + over-debit blok A/B +810.760,71 = −1.980.248,29 (`levis-july-suspense-plug-1980248`).
- **Rp 76.926.875 "KOL"** — 32 transaksi Grand Indonesia 15-Jul, tender CASH, kolom approval `KOL <nama influencer>`. Barang diberikan **GRATIS** tapi POS mencatat penjualan tunai harga penuh → menggantung permanen di `1106000101`. Butuh keputusan: reklas ke beban promosi, atau batalkan di X-Store dan impor ulang sebagai free goods (implikasi PPN cuma-cuma) (`levis-july-clearing-prd-begbal`).

### Fitur clearing in-app

`levis.pos.clearing` (+ `.line`/`.alloc`/`.diag`), `levis.clearing.config`, `levis.bank.mid.map`, `levis.bank.narrative` — dibangun 11-Aug-2026, PR #130/#131 (`levis-pos-clearing-feature`). Tiga tahap keras-terpisah atas permintaan user: `action_compute` (nol perubahan) → `action_generate_moves` (DRAFT) → `action_post`. Tanpa cron, tanpa auto-post.

- **Temuan yang membuat fitur ini mungkin tanpa upload:** narasi statement bank sudah memuat gross dan MDR per settlement — BCA `TGH`/`DDR`/`ADM`, QRIS `QR`/`DDR`, BRI `AMT`/`MDR`. Diukur di 2.535 baris Juli: `gross - mdr == amount` pada **seluruh** 2.073 settlement, 0 selisih (`levis-pos-clearing-feature`).
- **Desain pembukuan berubah total di 19.0.1.30.0** (PR #167): kaki jurnal ditulis **ke move baris rekening koran itu sendiri**, menggantikan kaki suspense-nya. Sebabnya: membukukan lawan di jurnal terpisah membuat kaki suspense berdiri selamanya sehingga lock date terblokir (`levis-pos-clearing-feature`).
- Pola `NFC:` ditambahkan ke parser di 19.0.1.31.0 (PR #168).
- **Defect alokasi setoran tunai SUDAH DIPERBAIKI** (PR #140, `_pool_accounts_for_channel`): dulu Rp 11,94 jt dari Rp 15,59 jt alokasi `cash_deposit` mendarat di akun BUKAN-CASH. Tidak ada kerusakan buku karena Juli diselesaikan lewat jalur skrip (`levis-pos-clearing-feature`).
- 🔴 **MASIH TERBUKA: 377 settlement teridentifikasi menunjuk tender BERBEDA dari akun yang dikredit alokasi** (280 exact + 97 batch, `x24_tender_mismatch`). Total per toko benar, akun per-tender salah saji. Belum ada kerusakan buku; perbaikannya perubahan perilaku akuntansi, **menunggu keputusan user** (`levis-pos-clearing-feature`).
- Hari dagang dijangkar ke tanggal mutasi sejak 19.0.1.51.0: `_resolve_target` = `statement_line.date - settlement_lag_days`, SELALU. Tanggal narasi jadi pemeriksa silang saja (`levis-pos-clearing-feature`).
- 🔴 **`action_compute` menghapus `line_ids` dan membangun ulang receipt** — keputusan manual TIDAK BOLEH disimpan di run. Itu persis insiden 9-Sep (44 centang hilang). Semua jawaban manusia hidup di `levis.clearing.manual.map` berkunci `statement_line_id` (`levis-clearing-ebr-roundtrip`, `levis-pos-clearing-feature`).

### Store-day, autoclearing, cash split

- **Store Settlement Reconcile** (`levis.pos.clearing.store.day` + view SQL `levis.pos.x70d.txn`), 19.0.1.48.0, deploy 31-Agu ke 12 DB. Satu baris per Store OU per tanggal settlement: statement hari H vs tender X70D hari H-1 (`levis-store-settlement-reconcile`).
- **Autoclearing per store-day** PR #258 merged 18-Sep, deploy **`prd_levis_begbal` saja**, modul 19.0.1.56.0, **saklar mati semua, cron `active=false`**. Pencocokan per (toko × hari dagang) — per baris mentok 27%, per store-day terbukti 226 store-day / 570 baris / Rp 3.887.852.400 pada klon September, shortfall nol (`levis-store-day-autoclearing`). ⚠️ 289 store-day adalah plafon aritmetika SQL; 226 yang benar-benar dibuktikan.
- **Cash split** (19.0.1.61.0/62.0, 21–22-Sep, 6 DB): `variance_bank` dulu menjumlahkan MDR + kas belum disetor dalam satu kolom. Sekarang dipisah: `statement_card_total`, `variance_bank` (**pada hari yang cocok = MDR saja**), `cash_deposit_total`, `cash_variance` (`levis-store-day-cash-split-and-matching`).
- Pencocokan setoran tunai: otomatis `cash_auto_match` **default MATI**; manual lewat tombol **Cocokkan Setoran Tunai**. Dry-run run 17: switch ON menempatkan 11 setoran Rp 17.009.300, 5 ambigu Rp 2.749.700, 51 (Rp 75.445.200) tetap tanpa toko (`levis-store-day-cash-split-and-matching`).
- 🔴 **BUG produksi 22-Sep sudah diperbaiki**: wizard memakai `store_day_id` ber-`ondelete= "cascade"` sementara `action_compute` menghapus seluruh store-day → wizard menghapus dirinya sendiri di tengah method ("record deleted", padahal pekerjaannya BERHASIL). Pelajaran umum: **sebuah layar tidak boleh menggantung pada record yang akan dihancurkan oleh aksi layar itu sendiri** (`levis-store-day-cash-split-and-matching`).
- **Workbook EBR round-trip** PR #260, deploy 18-Sep ke 10 DB, 19.0.1.58.0/59.0: `levis.clearing.ebr` (pembangkit xlsx), `levis.clearing.recon.upload`, `levis.clearing.manual.map`, `levis.clearing.match`. Run POSCLR/2026/0001 (Agustus): 2.348 baris → workbook 1,0 MB dalam 17 detik. Kolom `AMOUNT PAYMENT` vs file klien: BCA 13.969.794.486 vs 13.969.830.691,67 (selisih 36.205,67 = SATU baris ATS yang klien ikutkan), BRI 1.446.723.819 vs 1.446.724.196 (selisih 377) — **yang menghitung dobel adalah workbook klien** (`levis-clearing-ebr-roundtrip`). Panduan Finance (Bahasa Indonesia, 5 langkah): `https://claude.ai/code/artifact/f335009f-b48f-4f20-b581-69406c291a9c`.
- 🔴 **HANYA `prd_levis_begbal` yang ter-provision**: `prd_levis`, `rnd_levis`, `demo_updated_levis` punya 0 `levis_clearing_config`, 0 `levis_bank_mid_map`, 0 run. Kalau ada yang bilang "modulnya belum bisa dipakai", tanya DB-nya dulu (`levis-clearing-ebr-roundtrip`).
- Biaya ekspor diukur di produksi (run September, 567 baris): `COMPILE SALES` **62 detik**, sisanya ≤1,4 detik. `limit_time_real` 1200s, Caddy 720s — **jangan "memperbaiki" ekspor 90 detik yang tidak rusak** (`levis-clearing-ebr-roundtrip`).

## 5. Bank & rekonsiliasi

### Impor statement

`custom_bank_import` 19.0.0.6.0 mengenali **enam** bentuk lewat auto-detect (bukan konfigurasi template):

| Bank / bentuk | Ciri | Sumber |
| --- | --- | --- |
| BCA corporate CSV (KlikBCA Bisnis) | preamble `Informasi Rekening`, `DD/MM` tanpa tahun | `bank-import-bca-corp-csv` |
| BCA corporate CSV varian 2 | tanggal `DD/MM/YYYY` penuh | `bank-import-bca-corp-csv` |
| BRI "BRISIM" xlsx | kolom geser, angka tertanam di Uraian | `bank-import-multiformat-accounting-date` |
| BRI "MUTASI" 6 kolom | header 6 sel: Tanggal / Uraian Transaksi / Teller ID / Debet / Kredit / Saldo | `bri-mutasi-vs-brisim-export` |
| BNI "TRANSACTION INQUIRY" xls | kolom dicari lewat label header | `bank-import-multiformat-accounting-date` |
| Mandiri "Acc_Statement" xls | `dd/mm/YYYY HH:MM:SS` | `bank-import-multiformat-accounting-date` |

- **Accounting date = bank transaction date.** Akar "tanggal jadi hari impor" adalah core `_post()` yang menggeser move ≤ `fiscalyear_lock_date` ke hari ini. Wizard menulis tanggal parse balik dengan `bypass_lock_check` (`bank-import-multiformat-accounting-date`).
- Statement `prd_levis_begbal` yang sudah beres: #12 IBCA Juni diperbaiki (735 baris, tanggal 06-01..06-30), #17 IBCA Juli 1.442 baris netto −84.065,62, #18 IBRI BRISIM 172 baris, #19 IBNI 4 baris netto −274.997, #20 IMand 4 baris netto −274.968. Template: BCA01, BRI01, BNI01, MDR01 (`bank-import-multiformat-accounting-date`).
- 🔴 **BRI punya TIGA bentuk ekspor, dan "sabuk pengaman" indeks kolom yang MENGGIGIT.** `Mutasi_01-31_Agustus_2026.xlsx` datang **tanpa** kolom Teller ID (5 kolom), auto-detect meleset, parser generik membaca kol-4=Kredit sebagai debit dan **kol-5=Saldo sebagai credit**. Tanpa error: 306 baris masuk dengan total **Rp 170.868.400.902** (seharusnya kredit 1.436.278.456 / debet 1.436.607.680). Diperbaiki 8-Sep dengan menghapus 306 baris + statement 44, menandai log #60 `failed`, dan impor ulang dari file yang dinormalkan ke 6 kolom → log #63, netto −329.224. **Kode agar `_parse_bri_mutasi` menerima varian 5 kolom BELUM dibuat** (`bri-mutasi-vs-brisim-export`).
- Impor BRI hidup di `prd_levis_begbal` jurnal **IBRI (id 74)**, BUKAN `prd_arkaaim` (`bri-mutasi-vs-brisim-export`).
- Drift versi 5.0 → 6.0 **kosmetik, bukan bahaya** — isinya murni Python (parser) dan field `file` bertipe `Binary` (attachment, tanpa kolom). Pelajaran: **cek dulu APA isi kenaikan versinya sebelum panik** (`bank-import-multiformat-accounting-date`).

### Statement berulang / duplikat

- 🔴 **Impor kumulatif itu DISENGAJA** (user, 30-Agu): klien mengimpor 1–7, lalu 1–14, lalu 1–31. Permintaannya: yang duplikat cukup tidak diproses ke jurnal — **bukan memblokir bulannya** (`levis-bank-statement-duplicate-imports`).
- ⚠️ Angka "3.145 baris / 1.943 duplikat" untuk IBCA Agustus **SUDAH BASI**; per 30-Agu tinggal 1.205 baris / 1.202 unik (dibersihkan sesi lain). **Semua angka run POSCLR/2026/0010 adalah artefak dan jangan dipakai** ("short Rp 10,3 M", "2.479 gap terbuka", dst) (`levis-bank-statement-duplicate-imports`).
- Guard pintu clearing: 19.0.1.47.0 → salinan jadi `state='skipped'`, nol alokasi. **Harus dibuang SEBELUM alokasi** — salinan yang memakan piutang hari itu membuat baris aslinya terbaca *short* (`levis-pos-clearing-feature`).
- Guard pintu **upload**: `custom_bank_import` 19.0.0.5.0, `custom.bank.import.dedup` (AbstractModel) diwarisi wizard CSV **dan** `custom.bank.h2h.connection` (yang sebelumnya tanpa pemeriksaan sama sekali). Kuncinya **selisih hitungan**, bukan "kunci ada → lewati": dua penjualan asli boleh identik. 🔴 Jebakan yang membuat guard diam-diam tidak bekerja: tipe tanggal beda per jalur (H2H str vs CSV `date`) — dinormalkan lewat `fields.Date.to_date` (`levis-bank-statement-duplicate-imports`).

### Pemetaan MID/TID → toko

- Metode yang dipakai, dari yang terkuat (`levis-mid-mapping-by-evidence`):
  1. **Pencocokan angka** — gross settlement vs debit persis piutang tender terbuka ±2 hari; terima kunci hanya bila suaranya bulat dan ≥3 baris setuju.
  2. **Eliminasi lewat sisa per toko** — contoh: TID `001999632289` Rp 557,0 jt; PIM 2 menyisakan Rp 551,8 jt. **Validasi lewat prediksi**: sesudah dipetakan sisa PIM 2 runtuh 551.823.858 → −1.000. Kalau sisa TIDAK runtuh, pemetaannya salah.
  3. **Cek-silang singkatan** — untuk MEMBENARKAN, bukan menyimpulkan.
- 🔴 **Nama toko di narasi bank adalah SINGKATAN, bukan pemotongan**: `LEVIS BIP` = Bandung Indah Plaza, `LEVIS GANCIT` = Gandaria City. Nol tumpang-tindih kata dengan nama analytic `OLS SES - ...`, jadi fuzzy matching tidak bisa (`levis-clearing-narrative-gotchas`).
- Skrip: `97_setup_mid_map.py` (38 baris) + `98_setup_mid_map_cash.py` (41 baris) = 79 aturan (PR #133/#135/#136). Keduanya resolve toko lewat **nama**, bukan id (`levis-mid-mapping-by-evidence`).
- 🔴 **Constraint unik SQL tidak menjaga apa pun** (semua `journal_id` NULL + Postgres `NULLS DISTINCT` + perbandingan string mentah). Diganti `@api.constrains` `_check_no_colliding_rule` + urutan preferensi `(sequence, -panjang_kunci, kunci)` di `_resolve` — **PR #138, live sejak 11-Aug-2026**. Escape hatch: context `levis_skip_mid_map_guard=True`, meninggalkan warning di log (`levis-mid-mapping-by-evidence`).
- MID list klien (`ALL_MID_EBR.xlsx`, 31 toko × 4 bank) dimuat 16-Sep lewat `109_load_bank_mid_map.py`: 80 rule baru → total 180. Hasil: 205 baris / Rp 821.286.058 ter-atribusi; coverage IBCA 91,1→94,8%, IBRI 97,2→99,1%. **Sesudahnya WAJIB `action_levis_reread_narrative`** (`levis-new-stores-sept2026`).
- 🔴 **Mandiri & BNI INERT**: `_parse_mandiri` dan `_parse_bni` masih stub `_parse_minor` — tidak pernah mengembalikan `mid`. 59 rule-nya benar dan sudah distage, tapi baru bekerja kalau grammar kedua feed itu ditulis (`levis-new-stores-sept2026`).
- Setoran tunai (tanpa MID) dipetakan dari narasi. Tiga sinyal, holdout 70/30 ×5: 87,9% benar, 0,8% salah, 11,3% abstain (akurasi saat berani menebak **99,0%**). Kuncinya: **singkatan toko ditulis DENGAN SPASI SISIPAN** (`TH E PARK KENDARI`, `c ibubur`) — buang SELURUH spasi lalu cari substring. `WS#####` **TIDAK berguna** (kode cabang BCA). 🔴 Boilerplate BCA `.../FTSCY/WS...` mengandung `TSC` = inisial TRANS STUDIO CIBUBUR → akurasi anjlok ke 64% kalau boilerplate tidak dibuang dulu (`levis-cash-deposit-ou-patterns`). Terdeploy 18-Sep: 43 aturan dimuat → 219 total; **53 dari 193 setoran tanpa OU terselesaikan (27%)**.
- 83 baris kanal `transfer` bernilai negatif (`TRSF E-BANKING DB .../SWBCA/WS...`) adalah **sweep kas ke pusat, bukan setoran toko** — jangan diberi OU (`levis-cash-deposit-ou-patterns`).

### MDR per payment type

- 🔴 **Detail acquirer HANYA ada di X70D yang diekspor toko** — kolom `AUTH NUMBER` / `VOUCHER NUMBER` feed malam **selalu kosong** (79 file, 25.414 baris, 0 terisi sejak 29-Jun-2026). `tender_type` tidak bisa menggantikannya: satu `OFFLINE_OTHER_CREDITCARD` memuat QRIS 42 / DEBIT OTHER 14 / DEBIT-GPN 20 / BCA Card 1 (`levis-store-mdr-recon-source`).
- 🔴 **JANGAN parse "LAPORAN HARIAN LEVIS - <toko>.xlsx"** — itu ketikan ulang manual dari X70D; dalam 1 bulan (206 baris) ada **13 baris meleset** (No Tiket salah ketik, nominal meleset Rp 100, payment method salah, satu baris tertukar total) (`levis-store-mdr-recon-source`).
- Tarif dikonfirmasi 18-Sep dari `LIST_MDR.xlsx` (17 bank × 18 kolom produk), 39 label `PAYMENT` terpetakan tanpa sisa. **User menegaskan QRIS BCA/BNI/BRI memang 0%** (MANDIRI & CIMB 0,7%) — **jangan "perbaiki" jadi 0,7%**. Uji MKG Sep-2026: 208 trx, Rp 346.630.200 gross → MDR Rp 1.309.664 (0,378%) (`levis-store-mdr-recon-source`).
- Modul `custom_levis_mdr` 19.0.1.0.0: `levis.mdr.rate` (39 tarif effective-dated) + view `levis.mdr.txn`. Terpasang di `rnd_levis` + `prd_levis_begbal`. 🔴 Keputusan desain yang jangan dibongkar: transaksi tanpa label/tarif bernilai **NULL, bukan 0** — nol adalah klaim (QRIS memang gratis) (`levis-store-mdr-recon-source`).
- **Kesimpulan lama diperbarui:** setelah X70T live 26-Sep, ke-14 kode acquirer cocok 1:1 dengan label tarif `levis.mdr.rate`, jadi MDR **tidak lagi bergantung ekspor toko mingguan** (`levis-x70t-acquirer-tenders`).
- 3 toko mengekspor X70D **tanpa kolom acquirer**: PLAZA SENAYAN, METROPOLITAN MALL BEKASI, BALIKPAPAN SUPERBLOCK — MDR toko itu tidak bisa dihitung dari ekspor mereka (`levis-store-export-variants`).
- Laporan MDR penuh (skrip 121, `Laporan_MDR.xlsx`, 6 sheet): 3.259 baris ber-MDR; Juli selisih −Rp 471.725, Agustus +Rp 1.316.611 (`levis-wave3-decisions-sep18`).
- `levis.mdr.bin` (berkunci BIN kartu) masih **0 baris** di semua DB; BIN tidak ada di X70D sehingga model itu tidak bisa dipakai untuk MDR X70D (`docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md`, `levis-store-mdr-recon-source`).

### Guard rekonsiliasi & laporan

- `custom_account_reconcile` 19.0.3.0.0, PR #127 (PR #116 **DITUTUP, jangan dibuka lagi**), deploy 11-Aug ke 10 DB: `button_draft()` melepas rekonsiliasi dulu + catatan chatter; `write()` menolak ubah `account_id`/`partner_id` pada baris ber-partial di **semua** state; `action_post()` menolak payment kembar kecuali `duplicate_checked`; menu **Unapplied Payments** (`reconciliation-guards-module`).
- **GL Open Items** wajib netting FIFO 2 pass karena clearing account di Levi's hampir tak pernah direkonsiliasi. Di GR/IR `2103109121` `prd_levis_begbal`: 28.348 baris kredit tanpa partner vs 26.618 baris debit berpartner. Netting per akun+partner saja hanya 54.966 → 53.406; pass kedua (baris tanpa partner boleh saling hapus lintas partner) → **1.665**, grand total tidak berubah. Netting FIFO **selalu aktif, bukan opsi wizard** (keputusan user 27-Agu-2026) (`gl-open-items-netting`).
- **Aged Payable/Receivable as-of** — lihat bagian 12 (T01). Basis lama menyembunyikan Rp 4,34 miliar utang terbuka (`levis-t01-aged-as-of-done`).
- **AR Aging Export** (15 bucket hari lewat jatuh tempo), menu Invoicing → Reporting → Reports. Tanpa wizard sendiri — memakai context key di wizard Aged Receivable agar tidak memaksa `-u` seluruh tenant (`ar-aging-export-report`).
- ⚠️ `tst_agedpay` adalah DB scratch yang **mendahului `/opt`** dan memblok `-u` apa pun (view `duplicate_checked`); disarankan di-drop. Masalahnya selesai sendiri saat PR #116/#127 merge (`tst-agedpay-ahead-of-opt`, `levis-aged-payable-as-of-fix`).

## 6. Begbal, TB & GL

### Apa yang dimuat

- **EBR = company id 1.** Workbook bulanan klien: `YYYY-MM - EBR - TB and GL For Upload to Odoo.xlsx`. Sheet: `CoA EBR` (645 akun), `Trial Balance EBR 2026` (101 akun, 12 blok bulanan), `GL EBR 2026`, subledger Aging AP/AR, Advance, Deposit, Accrued, MDR Bank (`levis-ebr-tb-gl-load`).
- 🔴 **Sheet GL versi pertama SINGLE-SIDED** (tiap baris satu kaki, Amount = D−C, tanpa akun lawan; ΣD 80 miliar vs ΣC 13 juta) — tidak bisa diposting sebagai `account.move` balance. Spesifikasi export 2-sisi yang diminta ke tim EBR/SAP: `docs/projects/levis/EBR_GL_2SIDED_SPEC.md` (`levis-ebr-tb-gl-load`).
- GL 2-sisi akhirnya datang: `2026 - EBR - TB and GL - BegBal Odoo.xlsx`, dimuat ke `prd_levis_begbal` 10-Jul-2026 lewat `62_load_gl_2026.py` — **1.185 voucher / 3.199 baris, 0 skipped** (`levis-gl-2026-detail-load`).
- 🔴 **Kunci voucher adalah kolom "No" (filled down), BUKAN Document No** — hanya 150 dari 3.199 baris punya Document No; dikelompokkan per "No", semua 1.185 voucher balance ke nol (`levis-gl-2026-detail-load`).
- **GL memuat MUTASI SAJA**, bukan saldo awal: TB beginning (31-Des-2025) + GL(Jan–Jun) = TB ending (Jun) untuk **semua 105 akun**, nol pengecualian. Saldo awal dimuat terpisah oleh `63_load_tb_opening.py` (12 akun, D=C=Rp 106.522.488,75) (`levis-gl-2026-detail-load`).
- **GL tidak memuat pendapatan sama sekali** (nol akun 4xxx); sisi penjualan hidup di jurnal POS/retail-import dengan cabang COA yang disjoint. Jadi GL dan POS **tidak** saling mendobel (`levis-gl-2026-detail-load`).
- Hasil akhir: **nol deviasi terhadap TB-ending-Juni pada seluruh 39 akun EBR**; 9 akun POS netto persis 0,00 terhadap `1106000112` (`levis-gl-2026-detail-load`).
- Paritas dibawa ke `prd_levis` (11-Jul) dan `prd_detail_levis` (11-Jul) lewat skrip 62/63/64/65 → ketiganya **1.425 move / 6.706 baris / Rp 71.293.028.285,76 / 4.387 order** (`levis-gl-2026-detail-load`).

### Apa yang sengaja TIDAK dimuat

- **Kolom Juni TB EBR (`m6_*`) sengaja TIDAK dimuat** — isinya siklus penjualan Juni, dan kredit Trade Receivables Juni-nya persis 6.253.197.087 = penjualan yang sudah diimpor incl. PPN. Memuatnya = dobel. Begbal dikunci di 31-Mei (`levis-begbal-may-plus-june-sales`).
- Begbal s/d 31-Mei kecil sekali: Rp 106.950.181,07 tiap sisi. Pembentukan neraca sebenarnya (right-of-use 20 miliar, lease payable 13 miliar, deposit) semua ada di kolom Juni yang tidak dimuat (`levis-begbal-may-plus-june-sales`).
- **Finance masih berutang jurnal non-penjualan Juni** (`levis-begbal-may-plus-june-sales`).

### Selisih yang diketahui

- ⚠️ Keluhan "masih ada selisih nilai jurnal" 13-Jul dan 14-Jul **dua-duanya sebab yang sama: export TB klien BASI** (diambil sebelum reload GL 10–11 Jul). Sweep penuh 105 akun workbook terhadap DB hidup: **nol selisih nyata**. Jawaban baku: minta accounting **re-export TB dari Odoo bertanggal hari ini** sebelum melaporkan selisih (`levis-tb-selisih-jul13-stale-export`).
- Bucket yang memang nyata dulu: (1) struktur, netto 0 — diselesaikan `66_reclass_sales_structure.py` (GLJV/2026/06/0012–0030); (2) **11 akun yang tidak ada di berkas GL klien, netto Rp 24,9 juta** — butuh GL Juli / GL revisi dari EBR (`levis-tb-selisih-jul13-stale-export`).
- **Gap Rp 7.153.500 / 3 transaksi Juli** — X101 datang SETELAH penjualan (SKU `0057O00010` baru dapat `default_code` pada 31-Jul 02:58, sementara terjual 25 & 29-Jul) dan strict-product memarkir seluruh transaksi. Selesai lewat re-import `X24_FORCE=1` (`levis-july-sales-gap-aug03`). 🔴 **65.815 produk baru dapat `default_code` pada 31-Jul** — kelas kegagalan ini akan terulang setiap X101 tertinggal dari berkas penjualan.
- 🔴 **Persediaan awal TIDAK PERNAH masuk GL.** Mutasi `1113100021` baru mulai Juli 2026, saldo awal nol. Gap GL vs nilai fisik: Rp 17,53 M (Agu) → **Rp 18,12 M** (27-Agu) → **Rp 25,31 M** (25-Sep, GL 51.329.305.834 vs fisik 76.641.311.637) → **Rp 25.312.005.806,49** (27-Sep, GL 55.147.538.511,64 vs fisik 80.459.544.318,13). **Tiap posting COGS melebarkannya** — posting Rp 7,62 M akan membuatnya ±Rp 32,93 M. Butuh jurnal pembukaan persediaan tersendiri (`levis-cogs-june-gap-july-posted`, `levis-cogs-open-items-sep25`).
- `1113100022` Inventories-footwear pernah **negatif Rp −29.104.185** (Juli membebankan COGS footwear tanpa satu pun penerimaan footwear) (`levis-cogs-june-gap-july-posted`).
- Cash Advance `prd_levis_begbal`: Dr `1102000099` Petty Cash clearing / Cr `1102000001` Cash on hand IDR lewat jurnal CSH1, dipasang `106_setup_cash_advance_cash_accounts.py` (`levis-begbal-cash-advance-cash-accounts`). Sisa: draft yatim `OBCA/2026/00001`.

### Gotcha SQL Odoo 19 yang selalu kena di sini

- `account_account.code` **tidak ada** — pakai `code_store->>'1'` (`levis-cogs-june-gap-july-posted`, `levis-july-clearing-completed`).
- `product_product.standard_price` adalah **jsonb** berkunci company id (`->>'1'`).
- `ir_property` sudah tidak ada; pakai `ir.default`.
- `account.bank.statement.line` **tidak punya kolom SQL `date`** — delegated ke `account.move`, jadi raw SQL wajib join `move_id` (`levis-clearing-narrative-gotchas`, `levis-t18-bank-mid`).
- `account_journal.name` dan `account_analytic_account.name` bertipe **jsonb**; `stock_warehouse.name` **varchar** (`levis-july-sales-gap-aug03`, `levis-t18-bank-mid`).
- `retail_import_line.raw_data_json` bertipe **text**, bukan jsonb — cast `(raw_data_json::json)->>'k'`, dan untuk >1 field pakai `json_to_record` (8,8 s → **1,5 s**) (`levis-july-sales-gap-aug03`, `retail-recon-report`).
- Kredensial Postgres: `docker exec odoo19-platform-postgres env` atau `db_password` di `/etc/odoo/odoo.conf`. **`.env` di repo/`/home` sudah BASI** (`levis-purchase-gr-basis-and-ppn-masukan`, `levis-gl-2026-detail-load`).

## 7. COGS

### Basis harga

🔴 **Basis yang benar = harga PO netto PPN** (`purchase_order_line.price_unit / 1.11`). **JANGAN** pakai `stock_move.value` maupun `standard_price` sebagai basis: 3.592 move penerimaan Agustus ber-`value` NULL membuat rata-rata `sum(value)/sum(qty)` anjlok ke pecahan bersih dan melahirkan klaim palsu "harga Agustus beda 11% dari Juli" — padahal harga PO per produk **identik** Juli vs Agustus (2.712 produk dicek) (`levis-cogs-june-gap-july-posted`).

### Status per bulan (`prd_levis_begbal`)

| Periode | Nilai | Status |
| --- | --- | --- |
| Juni 2026 | Rp 4.227.985.550,39 | `COGS/2026/0001`, **posted** |
| Juli 2026 | Rp 12.034.701.508 | `GLJV/2026/07/0032`+`0033`, **posted manual** |
| Agustus 2026 | Rp 8,466 M | `COGS/2026/0003`, **posted** |
| paper bag delta | Rp 52,43 jt | `0004/0005/0006`, posted 30-Sep |
| September 2026 | Rp 3.035.234.426 | `COGS/2026/0007` **computed, belum di-generate** |

Sumber: `levis-cogs-june-gap-july-posted`, `levis-cogs-open-items-sep25`.

🔴 **Juli dibukukan TANGAN, bukan lewat modul.** Bentuknya persis `levis.cogs.run` (Dr `6120010001/2/3` / Cr `1113100021/2/3`, analytic OU di kedua sisi) tapi `levis_cogs_run` 0 baris. **Jangan pernah membukukan ulang Juli.** Hitung ulang meleset Rp 1.116.818 (0,009%), seluruhnya = **3 pcs RIBCAGE SHORT ZIP** (`005DS0005026/27/28`) di Grand Indonesia yang tidak punya baris PO sendiri — artinya **jurnal Juli yang terposting justru LEBIH benar daripada hitung ulang** (`levis-cogs-june-gap-july-posted`).

Margin yang dilaporkan ke FA: Juni GM 24,95% (Rp 1.405.518.975), Juli GM 21,15% (Rp 3.228.050.048), gabungan 22,17%. Beberapa toko <12% (AEON BSD, Summarecon Bandung, Bandung Indah Plaza) — perlu konfirmasi apakah harga PO = harga pokok riil (`levis-cogs-june-gap-july-posted`).

### Catch-up saat penerimaan

`levis.cogs.catchup` (fitur 16, 19.0.1.50.0, deploy 4-Sep ke 7 DB, **AKTIF hanya di `prd_levis_begbal`**) — hook di `stock.move._action_done` untuk penerimaan vendor. Kontraknya sengaja sempit: hanya produk di penerimaan itu; seluruh sisa qty terjual dibebankan; basis harga PO netto pajak dengan fallback `standard_price`; jurnal **DRAFT** digabung per tanggal buku; gagal di sini **tidak pernah memblokir penerimaan** (`levis-cogs-catchup-on-receipt`).

Output sebenarnya adalah **`levis.cogs.charge`** — buku besar biaya yang sudah diakui per (produk, gudang, bulan penjualan). `levis.cogs.run._detail()` menguranginya sebelum membukukan, sehingga satu unit tidak mungkin dibebankan dua kali oleh dua mekanisme itu (`levis-cogs-catchup-on-receipt`).

🔴 **Jendela default hanya bulan berjalan — jangan dilebarkan sembarangan.** COGS Juni dan Juli dibukukan **tanpa** meninggalkan baris `levis.cogs.charge`; melebarkan `cogs_catchup_start` ke bulan itu akan membebankan biayanya untuk kedua kalinya (`levis-cogs-catchup-on-receipt`).

### Bahaya dobel Agustus — SUDAH LEWAT

🔴 8 jurnal catch-up draft Rp 3.007.522.761,26 memuat porsi Agustus Rp 528.443.940,74 (897 unit) yang **SUDAH dibukukan manual** oleh FA di `GLJV/2026/08/0021` (Rp 531.048.759). Per toko cocok sampai rupiah untuk 13 dari 14 toko; satu-satunya selisih (Grand Indonesia Rp 2.604.639) tepat = 7 unit RIBCAGE tanpa PO × Rp 372.082 (`levis-cogs-open-items-sep25`).

**PRASYARAT TUNTAS 27-Sep-2026**: `126_seed_cogs_charge_manual.py` sudah di-APPLY di `prd_levis_begbal`. `levis.cogs.charge` kini punya `source='manual'` 595 baris / 907 unit / Rp 532.164.760,56; porsi Agustus **hilang dari draft**; 9 draft catch-up turun dari Rp 3.562.845.844,22 → **Rp 3.034.401.903,48** (September murni). **Bahaya dobel Rp 528 jt sudah lewat.** Dump: `/opt/odoo-platform/backups/prd_levis_begbal-pre-seed126-20260927.dump` (`levis-cogs-automation-deploy-sep25`).

🔴 Skrip 126 **tidak ada di `main` maupun di pohon kerja `/home`**. Diverifikasi 28-Sep-2026: ia ada di riwayat git pada commit `ba80583b` dan `8b434ce7`, terjangkau dari branch **PR #263** (`feat/levis-cogs-autopost`) yang masih terbuka — bukan hilang, tapi belum mendarat (`levis-cogs-automation-deploy-sep25`).

### Status saklar (27-Sep-2026) dan hold FA

**KEPUTUSAN USER 27-Sep-2026: NOL saklar dinyalakan selama hold FA masih berlaku.**

| Saklar / objek | Nilai sekarang | Arti |
| --- | --- | --- |
| `cogs_catchup_enabled` | **1** | perhitungan jalan |
| `cogs_catchup_autopost` | **0** | posting manual (autopost menembus hold) |
| cron id 51 `cron_levis_cogs_catchup` | `active=false` | nextcall 2026-10-01 19:00 UTC |
| `cogs_session_start` | **KOSONG** | isu #16 (COGS melekat jurnal sesi POS) MATI |
| `l10n_cogs_reported_through` | 2026-08-31 | belum dimajukan |
| 9 draft catch-up | Rp 3.034.401.903,48 | **posting di-HOLD FA** |

Sumber: `levis-cogs-open-items-sep25`, `levis-cogs-automation-deploy-sep25`.

**FA SETUJU otomatisasi COGS mulai 1-Okt-2026**, tetapi **posting draft September di-HOLD** sampai penjualan toko yang belum ter-record (terutama toko baru ex-AMP) selesai masuk, dan **harga 3 SKU RIBCAGE masih jadi pertanyaan tim M&P** (`levis-cogs-automation-deploy-sep25`).

Dampak kalau saklar dinyalakan, disimulasikan SQL 27-Sep (read-only): `_post_due` memposting ke-9 draft Rp 3.034.401.903,48 sekaligus; `_sweep` September menghasilkan 13.312 unit → Rp 4.588.510.550,49 dalam SATU jurnal (±2.046 baris GL); Agustus 0 unit storable (bukti skrip 126 + isu #79 tuntas); warning tiap malam menyebut 9.218 unit **non-storable** (paper bag) karena `_outstanding` tidak memfilter `is_storable` — berisik, tidak dibebankan (`levis-cogs-open-items-sep25`).

🔴 **JEBAKAN URUTAN**: kalau `l10n_cogs_reported_through` dimajukan ke 30-Sep **SEBELUM** sweep pertama jalan, September jadi tertutup dan COGS-nya dilempar ke **Oktober**. Majukan `reported_through` hanya SETELAH COGS bulan itu lengkap (`levis-cogs-open-items-sep25`).

### Sisa data COGS

- **10–14 unit tanpa PO sama sekali**: 3 SKU satu style `005DS0005026/27/28` RIBCAGE ukuran 26/27/28, semua di Grand Indonesia (Jul 3 · Agu 7 · Sep 4). Di GL sudah dibebankan manual; yang kosong hanya `standard_price` di master — usul isi **Rp 372.081,98** dari PO ukuran 25 (`PO/T/EBR/2026/08/00340`, Rp 413.011 incl ÷ 1,11) **sekaligus seed charge-nya** (`levis-cogs-open-items-sep25`).
- 150 produk / 272 unit terjual September masih tanpa `standard_price` (menunggu GR).
- ⚠️ Sheet menandai **#16 "Done" padahal check 16/09 klien sendiri masih mengeluh** COGS belum melekat ke jurnal sales harian — **jangan percaya kolom Status** (`levis-cogs-open-items-sep25`).

## 8. Purchase & GR/IR

### Arsitektur GR journal

Platform ini **membuang field interim stock input/output standar**, jadi valuasi real-time core tidak memposting apa pun. `custom_levis_localization` membukukan langsung lewat pasangan kategori `property_stock_valuation_account_id` + `account_stock_variation_id` (`levis-gr-journal-opt-in-behavior`).

- Saklar `custom_levis_localization.suppress_gr_journal`, **default MATI = memposting**. MATI → penerimaan vendor posting `Dr Stock Valuation / Cr Stock Variation` ref `GR-VAL:<move id>`; retur vendor posting kebalikannya ref `GR-RET-VAL:<move id>`. ON → keduanya ditekan dan GL diluruskan lewat `levis.inventory.reconciliation` (`levis-gr-journal-opt-in-behavior`, `addons/_tenants/custom_levis_localization/MODULE_KNOWLEDGE.md`).
- `prd_levis`/`rnd_levis`/`demo_levis` di-set `suppress_gr_journal=1`; `demo_updated_levis` = `0` (`levis-gr-journal-opt-in-behavior`).
- 🔴 **Jurnal GR TIDAK tertaut lewat `stock_move.account_move_id`** (NULL untuk semua move). Satu-satunya tautan adalah `account_move.ref = 'GR-VAL:<stock_move_id>'` di jurnal *Inventory Valuation*. Mencari `ref LIKE '<picking>%'` memberi nol baris dan kesimpulan palsu "GL bersih" (`levis-po-ppn-included-correction`, `levis-po-qty-price-swap`).
- Odoo 19 **tidak punya `stock.valuation.layer`**; FIFO dihitung on-the-fly dari `stock_move.value / quantity` (`levis-po-ppn-included-correction`).

### GR/IR bill-clearing

- Akar keluhan "Jurnal terbentuk saat Vendor Bill masih COGS pada AP": baris produk bill tidak pernah dirutekan ke akun GR/IR yang dikredit penerimaan. Diperbaiki di `account_move_line._compute_account_id` (`levis-grir-bill-clearing-fix`).
- 🔴 **Akun GR/IR WAJIB `liability_current`**, bukan `liability_payable`/`asset_receivable`. Merutekan baris produk (tanpa due date) ke akun payable/receivable menabrak aturan Odoo "any journal item on a payable account must have a due date" → bill tidak bisa diposting (`levis-grir-bill-clearing-fix`).
- 🔴 Asumsi "no-op untuk trade" **SALAH**. Dua cacat nyata: (1) gate memakai `is_storable` padahal **seluruh katalog Levi's `type='consu', is_storable=False`** (344.268/344.268) meski tetap real-time valued → gate NEVER fired; diperbaiki jadi `type == 'consu'`. (2) Setiap `account_stock_variation_id` kategori real-time diimpor sebagai `liability_payable`; `_ensure_grir_current` menormalkannya (`levis-grir-bill-clearing-fix`).
- Baris **Trade** pada `levis.purchase.account.map` memang `grir_account_id = NULL` dan **memang seharusnya begitu** — GR/IR trade diambil per kategori; mengisi baris map akan meng-override pemetaan per kategori. ⚠️ `docs/projects/levis/CONFIG_FOLLOWUPS.md` menyatakan sebaliknya dan **SALAH**; pakai `CONFIG_FOLLOWUPS_STATUS.md` (`levis-config-followups-status`).
- Pemetaan GR/IR per kategori: Textile `1113100021`→`2103109121`, Footwear `…022`→`…122`, Accessories `…023`→`…123`, Miscellaneous `…024`→`…124`, semuanya `liability_current` (`docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md`).

### Auto-reconcile & backfill

- **T02a (PR #247, merged+deploy 17-Sep, 1.52.0, TANPA `-u`)**: GR/IR di-netting saat bill post. 🔴 **Netting per `(account, purchase_line_id)`, BUKAN per pasangan** — terukur: dari 42.922 baris GR/IR bill terposting hanya **41%** cocok dalam Rp 0,02; 15.198 meleset >Rp 1.000, total Rp 2,52 miliar. Dua sebab struktural: penerimaan parsial (satu bill 200 baris / 200 baris PO / **600 stock move**) dan basis beda (penerimaan neto pajak, bill tidak). Saklar `grir_auto_reconcile` default 1; **0 = rollback seketika** (`levis-t02a-grir-autoreconcile`).
- 🔴 Setengah bagian kedua: `_compute_account_id` adalah **precompute tanpa `@api.depends`**, jadi `create()` yang mengirim `account_id` melewati routing — persis yang dilakukan importer bill, dan sebab bill impor mendarat di COGS (`levis-t02a-grir-autoreconcile`).
- **T02b (PR #253, DIJALANKAN DI PRODUKSI 17-Sep)**: `114_grir_backfill_reconcile.py` menjalankan ulang `_levis_reconcile_grir()` — tidak mengarang pencocokan kedua. Hasil `prd_levis_begbal`: 408 bill, 0 gagal, 63.756 partial + 27 full; `2103109121` 65.779→6.659 baris, `2103109123` 5.224→567. **Saldo buku keempat akun IDENTIK sebelum/sesudah** — itu ujiannya (`levis-grir-backfill-t02b`).
- 🔴 Rollback harus mencatat `account.partial.reconcile`, **bukan** `account.full.reconcile` (di klon: 408 bill → 63.758 partial tapi hanya 27 full) (`levis-grir-backfill-t02b`).
- Sisa sesudah backfill (JANGAN salah baca netto −36,04 sebagai "sudah cocok"): (A) 202 jurnal STJ "Koreksi PPN Masukan atas GR" Rp 2.135.691.535 tanpa `purchase_line_id`; (B) 2.681 penerimaan September Rp 4.278.052.042 **tanpa bill sama sekali** — posisi terbuka yang sah; (C) 312 baris netto Rp −14,87 (`levis-grir-backfill-t02b`).
- Efek gabungan T02a + T02b: baris GR/IR terbuka **68.345 → 7.978**, seluruh baris reconcilable **71.273 → 12.316**. Sisa Rp 5,1 miliar di `2103109121` adalah posisi belum tertagih yang sah (`levis-wave1-deploy-sep18`).

### Gap Agustus Rp 6,08 M — SUDAH DIBACKFILL

Kredit GR/IR Agustus kurang **Rp 6.084.177.039** dibanding debit tagihan. **Bukan selisih harga PO** — 43 receipt terisi `owner_id` (konsinyasi) sehingga `stock_move.value` NULL dan `_levis_book_valuation_entry()` berhenti di guard `if not amount`; perbaikan 27-Agu memakai `_set_value()` yang tidak memanggil `_create_account_move()`, jadi value terisi tapi GL tidak menyusul. Sebaran: Grand Indonesia Rp 3.904.410.909 (21 receipt), Gandaria City Rp 2.003.077.997 (20 receipt, nol GR sepanjang Agustus), Trans Studio Cibubur Rp 176.688.132 (`levis-august-grir-gap`).

**SELESAI 9-Sep-2026**: `100_backfill_gr_journal_owner_receipts.py` membukukan 3.592 entri Rp 6.084.177.042,48 bertanggal receipt masing-masing. **Selisih GR/IR Agustus kini Rp 46,64** pembulatan di 22 toko. Dump `/var/backups/odoo/prd_levis_begbal-pre-grbackfill-20260909.dump` (`levis-august-grir-gap`).

Akar `owner_id`-nya sendiri: 43 receipt (`14703/IN/*`, `33595/IN/*`, `27917/IN/*`) terisi owner partner 36 Agus Kurniawan. **Berbahaya, bukan kosmetik**: quant ber-owner = stok konsinyasi sehingga tidak bisa direservasi. 🔴 **JANGAN perbaiki lewat ORM/UI** — `owner_id` adalah valuation trigger. Dipakai SQL satu transaksi dengan `BEGIN ISOLATION LEVEL REPEATABLE READ` + backfill `_set_value()` (`levis-receipt-owner-consignment-fix`).

### Jebakan PO

- **PPN included tapi `tax_ids` kosong** (6-Agu-2026). PO dibuat lewat import Excel, dan import melewati `onchange_product_id()` — di Odoo 19 `purchase.order.line.tax_ids` **bukan** stored-compute. Akibatnya GR menilai persediaan **bruto**. Koreksi SELESAI 6-Agu: 243 dokumen GR, **Rp 3.322.153.130,21** dikeluarkan dari harga pokok, 6/6 verifikasi lulus. Bentuk: satu jurnal per dokumen GR, ref `PPN-INC-KOREKSI:<nama GR>`, bertanggal akhir bulan periode GR-nya sendiri (`levis-po-ppn-included-correction`). 🔴 **JANGAN satu transaksi besar** — versi pertama menahan row lock **22 menit** di prod. 🔴 Jebakan `_post(soft=True)`: tanggal akhir bulan yang jatuh di masa depan tidak diposting, hanya ditandai `auto_post='at_date'` — 74 jurnal sempat menggantung; pakai `min(akhir_bulan, hari_ini)`.
- **Qty ⇄ Unit Price tertukar** (6-Agu). 18 PO (`PO/T/EBR/2026/08/00132..00149`) masuk lewat `base_import` dengan kolom tertukar (413.011 pcs @ Rp 1). 🔴 **Total rupiahnya justru BENAR** — swap mempertahankan qty × harga, jadi anomali tidak terlihat dari angka total mana pun. 🔴 **Retur biasa MENGGANDAKAN kerusakan**: kategori FIFO, receipt @ Rp 1 menggerus `standard_price` → retur over-reverse GL ±Rp 1,23 miliar. SELESAI: 15 PO direset ke draft, qty/harga ditukar balik, confirm ulang — 948.681.379 pcs → **3.046 pcs** untuk nilai yang sama persis Rp 1.796.549.453. Guard `_check_levis_qty_price_swap` (`@api.constrains`, PR #111) — **harus constrains, bukan onchange**, karena `base_import` tidak pernah menjalankan onchange. Laporan: `docs/projects/levis/INSIDEN_PO_SWAP_QTY_HARGA_06AGU2026.md` (`levis-po-qty-price-swap`). Sisa: `27917/IN/00001` sengaja dibiarkan atas keputusan user — retur tanpa jurnal, GL masih menanggung Rp 191,29 jt (`levis-po-ppn-included-correction`).
- **Salah size di receiving lahir di PO, bukan di gudang.** `_check_levis_receipt_line_from_po` menolak baris receipt tanpa `purchase_line_id`, jadi produk pada receipt selalu diwarisi dari PO. Kasus "4 baris size 25 padahal fisiknya 25/26/27/28" berasal dari **file upload PO yang kolom produknya tersalin turun**. Guard SKU-ganda + wizard konfirmasi (PR #211 merged 4-Sep, main 19.0.1.41.0); diagnosis `103_report_po_duplicate_sku.py`. Hasil 4-Sep: **8 pasang (PO, SKU) di 5 PO Agustus, semuanya sudah GR done + bill posted** → koreksi harus jalur retur (`levis-po-duplicate-sku-guard`).
- Menggeser GR antar periode: `button_draft()` → `write({'name':'/','date':target})` → `action_post()`. Tanpa `name='/'`, `_check_sequence_mixin` menolak perubahan tanggal lintas periode. Skrip `94_shift_po_gr_to_july31.py` (`shift-posted-gr-journal-period`).
- Menghapus permanen dokumen stok `done` **harus SQL, bukan ORM** — `stock.move.line.unlink()` mendorong `reserved_quantity` quant jadi negatif (`purge-done-stock-docs-odoo19`).
- PO Return (`custom_po_return`): return picking tetap draft/ready (gudang validasi manual); RTV valuation journal `GR-RET-VAL:`; bug admin-fee `account.account.deprecated` (field dihapus di Odoo 19) yang memblokir SELURUH modul sudah diperbaiki (`levis-po-return-fixes`).
- **Vendor segrup jatuh ke AP Third Party.** 439 bill posted PT SINAR EKA SELARAS mendarat di `2103100001` padahal master menunjuk `2103200001`. Fix PR #193 pakai **flag** `res.partner.l10n_related_party`, bukan "master vendor selalu menang" (aturan itu akan membajak PO trade 68 dari 74 vendor). GR/IR **sengaja tidak dibelah**. **Reklas saldo lama TIDAK dikerjakan** atas permintaan user (`levis-related-party-payable`).
- Purchase Report Trade/Non-Trade: `custom_accounting_reports` 19.0.0.21.0, PR #183 merged 19-Agu, 9 DB. Smoke test prd_levis_begbal: trade 44.373.987.923,53 + non-trade 10.108.847.001,67 = 54.482.834.925,20, unclassified 0. Panduan: `docs/projects/levis/PURCHASE_REPORT_TRADE_NONTRADE.md` (`purchase-report-trade-split`).
- Purchase Report basis GR (#25/#30, PR #192, reports 19.0.0.23.0, 10 DB): wizard dapat `date_basis` (`gr` default / `bill`). Di `prd_levis_begbal` basis GR vs Bill menghasilkan **angka IDENTIK** — fiturnya tersedia, bukan mengoreksi angka (`levis-purchase-gr-basis-and-ppn-masukan`).

## 9. Operating Unit & master data

- **Dimensi OU** = analytic plan "Operating Unit" (plan_id=2) berisi `EBR - HEAD OFFICE` + toko bernama `OLS SES - <MALL>`. Head Office OU = perusahaan itu sendiri (`res.company.l10n_ho_analytic_id`) (`levis-operating-unit-normalization`, `levis-manual-bill-payment-ou-batch`).
- Tooling (semua idempoten, `RUN_DRY=1` default): `40_setup_trade_ou.py`, `41_normalize_ou.py`, `42_backfill_ou_analytic.py`, `43_align_pos_naming.py`, `44_fix_cash_journal_accounts.py` (`scripts/tenants/levis/README.md`).
- 🔴 **`stock.warehouse.code` adalah kunci join retail-import — JANGAN pernah diubah.** Satu nama toko hidup di 4 tempat: warehouse, OU analytic, purchase journal (`Pembelian - <name>`), `pos.config` (`levis-operating-unit-normalization`).
- 🔴 **JANGAN rename dengan `LIKE '%OLS %'`** — nama produk nyata memuatnya (`GRAPHIC CREWNECK TEE TOOLS PEWTER`, `Original Cut OLS TS SCU`). Bangun map eksplisit old→new dari `pos.config` (`levis-pos-naming-alignment`).
- 🔴 **Mengarsipkan warehouse yang punya `pos.config` ditolak core** walau config-nya sudah diarsipkan — `_archive_warehouse()` memarkir operation type config di Head Office selama penulisan (`levis-operating-unit-normalization`).
- GRAND INDONESIA ternyata **berdagang harian** (70–110 baris X24DN/hari); daftar "resmi" yang mengarsipkannya sudah basi, dan `_ri_assert_stores_postable` hard-fail setiap impor yang memuat toko terarsip. `ARCHIVED_STORES` kini kosong (`levis-operating-unit-normalization`).
- Cash journal per toko: EBR CoA tidak punya akun kas per toko, jadi `point_of_sale` memilih sendiri dengan menyusuri blok kode `1102` dan **menabrak 6 akun EBR asli**. Diperbaiki `44_fix_cash_journal_accounts.py`. ⚠️ **Kode baru BERBEDA per DB** — jangan asumsikan sama (`levis-pos-naming-alignment`).

### 9 toko baru September 2026

- `prd_levis_begbal`, 16-Sep-2026, `108_add_stores.py`. Hasil: **33 OU aktif**, 33 warehouse, 32 pos.config, **nol jurnal** tercipta. Dump `/opt/db-backups/manual/prd_levis_begbal-pre-newstores-20260916.dump` (`levis-new-stores-sept2026`).
- 🔴 **DUA sistem kode toko — jangan tertukar.** `STORE CODE` 5 digit (80741) vs `SAP STORE CODE` ship-to 10 digit (0020080741). Importer join ke `STORE CODE` lewat xid `posconfig_<STORE CODE>`. Sheet klien hanya memberi ship-to → STORE CODE = 5 digit setelah "00200". 23 toko lama memakai nomor XStore LEGACY (14696, 33267) sebagai `stock.warehouse.code`; 9 toko baru memakai STORE CODE (80680, 80741–80748) (`levis-new-stores-sept2026`).
- Satu "toko" = **9 record**, urutannya penting: warehouse → akun kas (`1102000034`–`42`) + jurnal kas → `pos.payment.method` CASH → `pos.config` (clone dari Paskal cfg 21, 12 tender termasuk SUSPENSE) → analytic OU → jurnal pembelian → `operating.unit` → xid `posconfig_<code>` → `petty.cash.float`. **Kas dibuat SEBELUM pembelian** (`levis-new-stores-sept2026`).
- 🔴 BUG upstream yang menggigit: `setup._unique_journal_code` menyimpan `base[:4]` lalu menempel counter → **loop tak berhingga** sejak n=10. Diperbaiki 16-Sep di /home DAN /opt **tanpa bump versi manifest** (murni Python); test regresi memakai `SIGALRM` supaya loop jadi FAIL bukan hang CI (`levis-new-stores-sept2026`).
- 🔴 `l10n_store_code` sempat kelewat — itulah field yang dibaca `_levis_store_code_index` (matcher setoran tunai, matcher bank, laporan closing harian), BUKAN xid `posconfig_`. PACIFIC PLACE (27648) masih kosong (`levis-new-stores-sept2026`).
- 🔴 **Feed X24DN/X70D BELUM memuat 9 toko baru** — nol baris untuk 9 kode itu sepanjang sejarah, nol pos.order. Uang banknya sudah mengalir sejak 29-Agu tapi datanya belum. **Ini pekerjaan XStore/klien, bukan Odoo** (`levis-new-stores-sept2026`).
- Menunggu klien: Mandiri `72223624331` tercantum untuk DUA toko (80680 DR RATULANGI dan 80748 MALL PANAKKUKANG) — 2 rule diblokir guard; DR RATULANGI tidak punya nomor BNI; 2 settlement BCA ber-MID di luar sheet: `004632694` (Rp 3.468.355) dan `004776753` (Rp 1.329.905) (`levis-new-stores-sept2026`).
- 8 toko Sulawesi/Kalimantan baru **belum punya label EBR pendek** (`BIP`, `SENCY`, `PVJ`) — kolom REMARKS workbook jatuh ke kode toko sampai Finance menyebut nama pendeknya (`levis-clearing-ebr-roundtrip`).

### Kategori produk & governance

- `levis.categ.reclass` (19.0.1.22.0): UI memindahkan produk ke kategori lain **dan** membukukan koreksi GL. 🔴 Harus menghitung ulang dari POS karena di `prd_levis_begbal` **nol** `account_move_line` punya `product_id` — jurnal penutup POS per akun saja. Periode tertutup membukukan dua entri di bulan berjalan lewat clearing account (REVERSAL + RE-BOOKING) (`levis-categ-reclass-feature`).
- `custom_levis_categ_approval` 19.0.1.0.0 (6 DB): `write()` menolak ubah `categ_id` hanya bila TIGA hal benar sekaligus (categ berubah, produk punya movement, pemetaan akun berbeda). Dua tier: `account.group_account_manager` → grup Finance Manager (Devina + Hermawan). Clearing account `2300000000` (`levis-categ-change-governance`). 🔴 Tier 1 besar (27–73 user), jadi fan-out aktivitas dibatasi `activity_fanout_max` default 8; di atasnya hanya catatan chatter.
- Gotcha keras: `approval.matrix` **wajib** `company_id eval="False"` atau diam-diam membebaskan setiap company lain; tier `on_overdue` harus `none` atau tier 1 lapse ke tier 2 dan perubahan GL cuma bawa satu tanda tangan (`levis-categ-change-governance`).
- Master kategori: 174 kategori setelah `32_clean_stray_categ.py` + `33_map_categ.py` di `demo_levis` (`demo-levis-coa-stray-categ`); 285–297 kategori di DB besar. Bagan akun hanya punya **4 pasang akun COGS/persediaan** (textile/footwear/accessories/misc) untuk 297 kategori — "per kategori" hanya bisa nyata di baris run, bukan di akun (`levis-cogs-june-gap-july-posted`).
- ⚠️ **GOTCHA pajak default**: tax id 28 (sale) / 21 (purchase) bernama "12% (Non-Luxury Good)" tetapi `amount`-nya **11,0** (PPN DPP Nilai Lain 12% × 11/12). Ada pajak "12%" lain (id 29/22, amount 12,0). **Resolve by name `ilike 'Non-Luxury'`, jangan by `amount==12`** (`demo-updated-levis-setup`).
- Template import PO memakai nama pajak **`PPN 12% (Included)` (tax 37)**, bukan `12% (Non-Luxury Good)` — nama itu dimiliki dua pajak sekaligus sehingga ambigu saat import (`levis-po-ppn-included-correction`).
- Reset transaksi: `20_reset_txn.py` (FK-closure + `session_replication_role='replica'`). 🔴 **LANDMINE: jangan pernah `TRUNCATE ... CASCADE`** — `res_company.account_opening_move_id` menjembatani CASCADE ke SELURUH DB (pernah terjadi di `rnd_levis`) (`levis-txn-reset`). 🔴 FK-closure adalah heuristik: `custom_po_return` dan `account_full_reconcile` **selamat dari setiap reset** sampai di-seed ke `CORE` (`levis-reset-orphan-tables-bug`). Di `prd_levis_begbal` **wajib** `RESET_KEEP_JOURNALS=EBRTB`.

## 10. Pajak

### PPh

- **107 kode objek** dimuat ke `tax.withholding.category` + `.rule` di 6 DB lewat `70_load_withholding.py` + `withholding_codes.csv` (PR #60). Distribusi: pph_23=70, pph_26=26, pph_4_2=10, pph_21=1. Akun: PPh 23 `2104100005`, PPh 4(2) `2104100001`, PPh 26 `2104100008`, PPh 21 `2104100003` (`levis-withholding-codes-load`). 🔴 Loader **menulis ulang `bupot_object_code` setiap run**, jadi koreksi lewat UI akan regresi kecuali CSV-nya ikut diedit. Belum terdaftar: kode objek untuk PPh 22 (`2104100004`) dan PPh 15 (`2104100002`).
- **PPh di Levi's dibukukan sebagai pajak pembelian bernilai NEGATIF** pada baris bill (PPh 23 −2%, PPh 21 −2,5%, PPh 22 −2,5%, PPh 4(2) −10%) (`levis-reset-to-draft-tax-lines`).
- 🔴 **PPh pernah DOBEL**: engine `custom_tax_id` memposting MISC "Pemotongan PPh" sendiri; kalau operator JUGA memasang native tax "PPh 23%" di kolom Taxes, PPh terbukukan dua kali (plus rounding mismatch 412.305 vs 412.305,60). Guard di `_custom_apply_withholding` melewati baris yang punya tax bernilai negatif (19.0.0.4.1, 5 DB Levi's). **Aturannya either/or** (`custom-tax-id-double-pph-booking`).
- **TERBUKTI tidak dobel lagi** (T20, 17-Sep): Rekap PPh Pemotongan = GL sampai rupiah — Juni 278.157.397, Juli 473.339.553, Agustus 293.790.391,59, total **1.045.287.341,59**. 🔴 DUA jebakan pengukurannya: `_build_lines()` memancarkan **baris subtotal per kode objek**, jadi menjumlahkan "semua kecuali grand_total" memberi **tepat 2×** (terlihat persis seperti bug dobel); dan basis GL harus **jurnal BILL**, bukan `move_type in (in_invoice,in_refund)` — Juni memuat 10 jurnal manual `entry` Rp 136.799.195 yang sah (`levis-t20-closure-evidence`).
- **Kode Objek di Rekap PPh dibaca dari base line (expense), bukan tax line** — operator mengisi picker di baris expense sementara PPh turun ke baris tax. Helper `_tax_base_splits()` menelusuri balik dan membagi DPP/PPh proporsional. Hasil Jan–Sep 2026: 277 baris, total tetap Rp 1.067.641.588,59, yang tadinya semua kosong kini **254 berisi**. PR #238, reports 19.0.0.27.0, **hanya `prd_levis_begbal`** (`rekap-pph-kode-objek-from-base-line`).
- 🔴 **"Rekap Bukti Potong PPh" KOSONG di `prd_levis_begbal`, dan menambah kolom tidak akan mengubahnya.** `custom_coretax_bukti_potong` = 0 baris; bupot hanya di-materialisasi oleh jalur engine, sementara Levi's hampir selalu memotong lewat native PPh tax. **Gap pipeline, bukan kolom report — perlu keputusan** (`rekap-pph-kode-objek-from-base-line`).
- `x_custom_withholding_category_id` pada `account.move.line` = picker PPh per baris bill, 19.0.0.3.0 (`custom-tax-id-aml-field-drift`). ⚠️ 19.0.0.4.0 pernah membawa **WIP sesi lain (NITKU/TIN)** ke skema seluruh 17 DB — lihat bagian 14.
- Guard akun PPh (T17, PR #257, `custom_tax_id` 0.9.0): `_custom_check_withholding_accounts` bersifat **read-only** karena me-repoint `account_id` sebelum `_post()` tidak mungkin (posting me-resync dynamic lines). **Audit produksi: 947 bill, 0 selisih**. Memperbaiki selisih = arahkan repartition line tax, **BUKAN** menyalakan engine withholding (dobel) (`levis-wave3-decisions-sep18`).
- Reset to draft: `_sync_tax_lines` mengambil snapshot pra-write hanya untuk move yang **sudah** draft, jadi `button_draft` menimpa keterangan (#7, sudah live di `custom_tax_id`) **dan** nominal pajak (#8, PR #178, `custom_tax_id` 19.0.0.7.0, merged+deploy 19-Agu ke 6 DB) (`levis-reset-to-draft-tax-lines`).

### e-Faktur & PPN

- 🔴 **Levi's adalah PKP Pedagang Eceran — PPN keluaran dilaporkan DIGUNGGUNG, bukan per faktur.** `prd_levis_begbal` punya **0 `out_invoice`**; PPN Keluaran Jun–Agu 2026 Rp 3.230.593.942 (DPP Rp 29.368.721.056) dari 22.207 POS order, semuanya `move_type='entry'`. Jadi `custom.report.faktur.pajak` dan ekspor FK keluar **KOSONG** — itu bukan bug, itu jalur yang salah (`ppn-digunggung-retail-report`).
- Jalur yang benar: `custom.report.ppn.digunggung` (PR #190, reports 19.0.0.22.0, deploy 20-Agu). **Melebarkan salah satu sisi = masa terhitung dua kali** (`ppn-digunggung-retail-report`).
- Rincian per transaksi: `custom.report.ppn.digunggung.detail` (PR #195, reports 19.0.0.24.0, 11 DB, 26-Agu). 🔴 Odoo memposting **satu jurnal per sesi POS** (1.454 jurnal untuk 24.218 order), jadi nomor struk **hanya ada di `pos.order`**. Verifikasi Agu-2026: rincian = rekap = Rp 1.249.052.143 dari 7.632 transaksi (`ppn-digunggung-detail-report`).
- e-Faktur "need at least one PPN or STLG tax group" = **XMLID tax-group per company hilang**. Semua 9 DB Levi's adalah klon turunan erajaya dengan `1_erajaya_tg_*` xmlid dan tanpa yang standar; diperbaiki 17-Jul dengan alias `ir_model_data`. "SLTG" adalah ejaan erajaya untuk STLG — **cocokkan by xmlid, bukan nama** (`efaktur-taxgroup-xmlid-fix`).
- 🔴 **Grid uang FK adalah 1.0 (rupiah bulat), di-hardcode `FK_AMOUNT_ROUNDING`, BUKAN `move.currency_id.rounding`** (Odoo mengirim IDR dengan rounding 0,01) (`efaktur-fk-of-export-entry-points`).
- `custom_coretax_export` 19.0.1.8.0 (8-Sep): faktur DP dan faktur pelunasan **berdiri sendiri** — `UANG_MUKA_*` selalu kosong, `_coretax_fk_net_factor()` menyekala harga. Ini **PEMBALIKAN** dari 19.0.1.7.0 (`efaktur-uang-muka-settlement`). Levi's tanpa efek (0 faktur keluaran) tetapi tetap di-`-u` agar tidak meninggalkan drift.
- Guard signer Coretax: `NPWP Penandatangan` hanya kolom bupot (`BPPU`/`BP21`/`BPNR`); `FK_COLUMNS`/`OF_COLUMNS` tidak punya kolom itu. Guard lama memblokir e-Faktur atas field yang tidak pernah dicetak — diperbaiki `require_signer` (`coretax-signer-guard-scoped`).
- **Prasyarat config yang menghentikan ekspor dengan `UserError`**: **NPWP company kosong di `prd_levis_begbal`**, dan **0 dari 30 UoM membawa kode Coretax** sehingga setiap baris OF jatuh ke `UM.0018` (`efaktur-fk-of-export-entry-points`).
- Import PPN Masukan: `custom.report.ppn.masukan.import`, **10 kolom** di produksi termasuk Tanggal & Nomor Faktur Pajak (#33/PT-2 **BISA DITUTUP**) (`levis-t20-closure-evidence`, `levis-purchase-gr-basis-and-ppn-masukan`).

### Template Coretax / Mitra Pajakku

Empat template klien kini di repo: `docs/projects/levis/tax-templates/` (PR #248).

| Template | Bentuk | Status |
| --- | --- | --- |
| FK Keluaran — Mitra Pajakku | `Import FK`: FK 35 kol + OF 16 kol | sudah ada, **byte-identik** |
| Retur PM — Coretax | `Retur` 12 + `DetailRetur` 15 | sudah ada, cocok |
| FK Keluaran — Coretax | `Faktur` 18 + `DetailFaktur` 14 | **BARU** (PR #249) |
| Retur PM — Mitra Pajakku | `Import RM`: RM 24 + OF 23 | **BARU** (PR #249) |

Sumber: `levis-tax-import-templates`, `levis-t16-fk-digunggung`.

- 🔴 **Berkas impor dibaca BERDASARKAN POSISI.** Header `OF` retur Mitra Pajakku sengaja mengulang empat nama (kolom 9–16 = angka faktur, 17–23 = angka retur). Merapikannya merusak upload (`levis-t16-fk-digunggung`).
- 🔴 Sheet `DetailRetur` di berkas sample berhenti di 14 header sementara kode menulis 15 — **kode yang BENAR** (sheet `Keterangan` mencantumkan `PPNBM Retur` sebagai wajib). **Jangan "memperbaiki" kode agar cocok dengan sample** (`levis-tax-import-templates`).
- `fk_source` (invoice / digunggung / both, default `invoice`): digunggung mengambil angka dari `custom.report.ppn.digunggung` — **satu FK per hari per toko**, bukan menurunkan ulang, sehingga ekspor dan SPT tidak bisa berbeda. Field pembeli non-TIN: NPWP `0000000000000000`, ID TKU `000000`, kode transaksi **04**, satuan `UM.0018` (`levis-t16-fk-digunggung`).
- Verifikasi masa 08/2026: 679 faktur di kedua format; rekap DPP **13.782.351.923,00** / PPN **1.516.072.957,00** — kedua export sama persis. Berkas jadi di `/srv/sftp-share/files/FakturPajakKeluaran_{CORETAX,MITRA_PAJAKKU}_2026-{07,08}.xlsx` (`levis-t16-fk-digunggung`).
- 🔴 **Retur masih 0 baris — terhalang ALUR, bukan format**: 784 dari 911 vendor bill punya NSFP (86%), tapi hanya 3 `in_refund` dan **0 ber-NSFP**, tanpa baris pajak, padahal 200 stock move ke lokasi supplier menunjukkan retur fisik terjadi → wilayah **#26 / T10** (`levis-tax-import-templates`).
- Field NSFP di `account_move`: `x_custom_nsfp`, `x_custom_tanggal_faktur_pajak`, `x_custom_has_faktur_pajak`. Akun: PPN Keluaran **2104300001**, PPN Masukan **1117200001** (`levis-tax-import-templates`).

## 11. Sheet After Go Live

Sheet klien `1Lgx1tBAq8-vPLAHgwE9Bn96d6Kpf8LSGnFP2svX_YhM`, per 18-Sep-2026 **78 baris** (dulu 61) + tab "meeting candance"; tab "Pending Tax" menyusut jadi 1 baris. **Sheet-nya PUBLIK** — `curl -sL ".../export?format=xlsx"` berhasil tanpa auth (`levis-golive-new-issues-sep18`).

⚠️ **Kolom Status di sheet klien BUKAN sumber kebenaran.** Audit 19-Agu membuktikan mayoritas baris "Open" sebenarnya sudah live (`levis-sheet-after-golive-status-aug19`), dan sebaliknya #16 ditandai "Done" padahal klien sendiri masih mengeluh (`levis-cogs-open-items-sep25`).

Klien menandai **tiga** baris *High Priority in Accounting*: **#67, #74, #77** (`levis-golive-new-issues-sep18`).

| # | Isi | Status | Bukti |
| --- | --- | --- | --- |
| 62 | 9 toko baru | **OPEN** (toko sudah dibuat di prd; PR #243 masih terbuka) | `levis-new-stores-sept2026` |
| 63 | OU saat akuisisi aset | **DONE** (klien tandai Done 17-Sep) | `levis-golive-new-issues-sep18` |
| 64 | Movement Inventory Detail | **SEBAGIAN** — sumber dibangun, template klien tidak ada | `levis-golive-new-issues-sep18` |
| 65 | paper bag COGS | **DONE** PR #257 (`is_storable=True`, skrip 124 lalu 123) | `levis-wave3-decisions-sep18` |
| 66 | prefix DSPFA | **DONE** PR #255 | `levis-wave1-deploy-sep18` |
| 67 | Purchase Report GR belum di-bill | **DONE** PR #255 (High Priority) | `levis-wave1-deploy-sep18` |
| 68 | penomoran `GR/<wh>/YYYY/MM/NNNNN` | **DONE** PR #257, 33 picking type | `levis-wave3-decisions-sep18` |
| 69 | penomoran `INTF/<wh>/…` | **DONE** PR #257, 33 picking type | `levis-wave3-decisions-sep18` |
| 70 | penomoran `STADJ/` + `STSCP/` | **DONE** PR #257 | `levis-wave3-decisions-sep18` |
| 71 | COA write-off `7218000001` | **DONE** PR #257 (di `stock.location`, bukan kategori) | `levis-wave3-decisions-sep18` |
| 72 | panduan clearing plus-minus `2103400001` | **OPEN** | `levis-golive-new-issues-sep18` |
| 73 | Aged Receivable vs GL Open Items | **TERJAWAB, bukan bug** (selisih uang NOL) | `levis-point-a-stock-reports-sep18` |
| 74 | COGS re-run | **DONE** PR #255 (High Priority) | `levis-wave1-deploy-sep18` |
| 75 | kolom "BILL TYPE" di upload | **DONE** PR #257 (template skrip 122) | `levis-wave3-decisions-sep18` |
| 76 | reset to draft bulky | **DONE** PR #255; "#76-lanjut" masih ada | `levis-golive-new-issues-sep18` |
| 77 | jurnal depresiasi per aset | **DONE** PR #255 (High Priority) | `levis-wave1-deploy-sep18` |
| 78 | confirm bulky | **DONE** PR #255 | `levis-wave1-deploy-sep18` |
| 79 | 904 unit COGS-0 Agustus | **TERJAWAB**; posting di-HOLD FA | `levis-cogs-open-items-sep25` |

Baris lama yang penting dan masih bergerak:

- **#11 lebar kolom per user** — GH issue **#182**. Akar: `list_controller.js` tidak mendaftarkan `getContext` di `useSetupAction` (pivot/graph punya), jadi layout tidak pernah ikut ke `ir.filters`. Diperbaiki sebagian di PR #259 (`createViewKey()` mencampur daftar field ke hash sehingga tiap modul yang menambah satu field membuang seluruh lebar tersimpan; kunci kini `resModel|viewId|nestedModel.field`). **Dikonfirmasi klien: yang diminta LEBAR kolom**, bukan pilihan kolom. Estimasi 2–3 hari; biaya sebenarnya memelihara patch core lintas rilis (`levis-sheet-after-golive-status-aug19`, `levis-point-a-stock-reports-sep18`).
- **#16 COGS di jurnal sesi POS** — kode LIVE tapi MATI (`cogs_session_start` kosong). 🔴 **Tanggal cutover WAJIB dan default KOSONG** karena Jun–Agu 2026 sudah dibukukan `COGS/2026/0001..0003`. 1-Okt-2026 aman; 517 entri sesi September semuanya `posted` (`levis-point-a-stock-reports-sep18`, `levis-cogs-open-items-sep25`).
- **#36 gerbang OU wajib di baris P&L** — PR #256 merged+deploy 18-Sep, saklar `ou_required_pl` default **0** (inert) (`levis-wave1-deploy-sep18`).
- **#23/#48** — `1116100007` dan `1116200001` **sudah** `reconcile = true` di produksi; sisanya pertanyaan "apakah fungsi clearing sudah proper" (`levis-golive-new-issues-sep18`).
- **#44 akun advance** — domain picker diperluas menerima `asset_cash` (PR #257). 🔴 Menandai akun kas `reconcile=true` akan membuat SETIAP penyelesaian advance merekonsiliasi kas — itu yang dihindari (`levis-wave3-decisions-sep18`, `levis-t20-closure-evidence`).
- **#50 MDR** — laporan penuh skrip 121 (bukan hanya Juli). Temuan: September Rp 30,2 jt MDR sudah di bank tetapi GL `7104000001` masih NOL (`levis-wave3-decisions-sep18`).
- **#61 wizard clearing massal** — dua hal berbeda: `action_open_lines` membuka daftar **tanpa limit** (63.240 baris satu akun GR/IR), dan wizard lama memuat setiap baris ke `line_ids` sebagai `Command.set`. Sekarang action ber-`limit` dan wizard batch tidak memuat baris. Setelah T02a + T02b, urgensinya turun drastis (`levis-point-a-stock-reports-sep18`, `levis-wave1-deploy-sep18`).
- **#59 "berat untuk ditarik"** — browse record 22,6s/23,3s/17,6s → SQL **3,0s/2,3s/1,3s** (`levis-point-a-stock-reports-sep18`).

🔴 **Berkas template klien yang diklaim "sudah dikirim" TETAPI TIDAK ADA di share maupun repo** — pola berulang: `Template Movement Inventory Detail.xlsx` (#64), `Template Internal Transfer Stock Detail.xlsx` (#69), `Template Adjustment Stock Report.xlsx` (#70), `Template Purchase Return Report.xlsx` (#26), `Template Summary Inventory.xlsx` (#27/#28) (`levis-golive-new-issues-sep18`, `levis-golive-client-answers-sep16`). **Arahnya sudah dibalik 18-Sep**: kami yang mengirim template — `117_build_report_templates.py` membangun enam workbook di `/srv/sftp-share/files/Template_*.xlsx`, tiap berkas punya sheet **Petunjuk** dengan asumsi bertanda `[ASUMSI]` (`levis-golive-new-issues-sep18`).

Tiga fakta tenant yang membentuk semua laporan stok (`levis-point-a-stock-reports-sep18`, `levis-golive-new-issues-sep18`):

1. 🔴 **Penjualan POS TIDAK PERNAH membuat `stock.move`** — 82.482 `pos.order.line` (91.008 unit) vs **NOL** move ke lokasi customer. Laporan movement dari `stock.move` saja menampilkan penerimaan dan retur tanpa satu pun penjualan; sumber wajib `stock.move` UNION `pos.order.line`.
2. **On-hand ditulis snapshot X20**, jadi "saldo awal ± pergerakan" tidak rekonsiliasi ke `stock_quant`; Summary menurunkan Beginning dari Ending secara mundur dan membawa selisihnya di kolom **Adjustment**.
3. 🔴 **`default_code` ada di `product_product`, bukan `product_template`** — 290.707 varian vs 10.479 template.

Enam laporan stok dibangun di `custom_accounting_reports`, **BUKAN** `custom_wms_reports`: menaruh menuitem ke action WMS akan memaksa modul ini depend ke WMS dan menyeret cycle count, barcode, stock_account ke **delapan DB akuntansi tanpa gudang**. **Modul jembatan yang dirancang di plan T11 tidak diperlukan** (`levis-point-a-stock-reports-sep18`).

## 12. Plan After Go Live T00–T21

Plan lengkap ada di `/root/.claude/plans/https-docs-google-com-spreadsheets-d-1lg-silly-pretzel.md` (10-Sep-2026). ⚠️ **REVISI 3 (16-Sep-2026) adalah versi berlaku; revisi 1 memuat 42 pernyataan salah dan jangan dipakai.** Jalur kritis 9 → **10 hari kerja** (`levis-after-golive-plan-sep2026`).

| Task | Isi | Status | PR |
| --- | --- | --- | --- |
| T00 | rekonsiliasi tiga arah `custom_levis_localization` | **SELESAI** 16-Sep oleh pihak lain | #193 |
| T01 | Aged as-of + AP Aging Export | **SELESAI & TERDEPLOY** 13 DB | #241 |
| T02a | GR/IR auto-reconcile saat bill post | **SELESAI & TERDEPLOY** 17-Sep | #247 |
| T02b | backfill GR/IR bill lama | **DIJALANKAN DI PRODUKSI** 17-Sep | #253 |
| T05 | analytic OU pada 5 penulis jurnal aset | **SELESAI & TERDEPLOY** 16-Sep | #244 |
| T05b | penetapan OU 148 aset | **belum di produksi** — keputusan Accounting | #245 |
| T07 | Asset Register: kolom akun/lokasi/OU, basis posted | **SELESAI & TERDEPLOY** 17-Sep | #246 |
| T09 | Purchase Report (Vendor Ref = SO SES, No. PO, warehouse) | lingkup terkunci; #67/#25 terdeploy | #255, #192 |
| T10 | Purchase Return Report | **TERBLOKIR** template klien | — |
| T11 | Summary Inventory + jembatan menu | **SEBAGIAN** (6 laporan stok live) | #259 |
| T12 | COGS melekat jurnal sales harian per store (lane S) | kode LIVE tapi **MATI** | #259 |
| T13 | ekualisasi peredaran usaha | **TERBLOKIR** gate G7 Tax | — |
| T14 | laporan PPh withholding | `test_pph_withholding_report` merah sejak lama | #238 |
| T15 | retur pajak masukan | format SELESAI, **alur 0 baris** | #249 |
| T16 | FK Keluaran Mitra Pajakku + digunggung | **SELESAI & TERDEPLOY** 17-Sep, 6 DB | #249, #248 |
| T17 | mapping COA PPh (guard read-only) | **SELESAI**; audit 947 bill 0 selisih | #257 |
| T18 | MID tampil + filter + tombol pemetaan | **belum merge/deploy** | #250 |
| T19 | MDR | gate G11 (InaL); laporan #50 selesai | #257 |
| T20 | bukti penutupan 6 baris sheet | **SELESAI** 17-Sep | — |
| T21 | (sisa, belum dikerjakan) | **OPEN** | — |

T03, T04, T06, T08 tidak tercatat di memory — hanya ada di plan file di atas.

**Jawaban klien 16-Sep-2026** yang mengubah lingkup (`levis-golive-client-answers-sep16`):

- **G6 / T12 — klien MENOLAK penyempitan lingkup.** COGS harus melekat ke jurnal sales per hari per store. Item ber-COGS 0: auto-recalculate selama periode OPEN; kalau CLOSED → COGS Catch Up di periode berjalan. **T12 keluar dari lane R jadi lane S sendiri (0,5 → 3 hari).**
- **G1 / T05 — alur LVA BENAR, bukan salah konfigurasi.** Akuisisi ke `1116100009` Prepaid-Office supplies lalu depresiasi FULL AMOUNT di bulan akuisisi. FA-LVA justru **masuk seed** (kini 13 baris).
- **G2 / T05 — ROU ke-7 'Others' DIBATALKAN.** Cukup 6 kategori.
- **G5 / T11 — harus ikut Template Summary Inventory dari user**, dan menu tarik report pindah ke **Invoicing ▸ Reporting**.
- **G4 / T10 — referensi Purchase Return Report "sudah diberikan"** — berkasnya TIDAK ikut terlampir.
- **K-1 / T09 — dikonfirmasi**: kolom Vendor Reference memang diisi nomor SO SES oleh tim MnP; tampilkan juga nomor PO dan nama warehouse.
- **G14 / #22 — dialihkan**: catatan "COA Tampungan" ditulis tim IT BA (Pak Ade), bukan Accounting.

🔴 **MASIH KOSONG — semua gate Tax nol jawaban**: G7 (T13), G8 (T15), G9 (T16), G10 (T17), K-2 (#58 Stephani), plus G11 (InaL, T19 MDR) dan G15 (Fiqo, #44). **Jangan mulai T13/T15/T16/T17 sebelum Tax menjawab** (`levis-golive-client-answers-sep16`). ⚠️ Catatan: G9 ternyata **BUKAN celah kode** — exporter FK Keluaran Mitra Pajakku sudah dibangun dan benar; yang hilang cuma berkasnya (`levis-tax-import-templates`).

Temuan verifikasi rev2 yang paling mahal kalau dilupakan (`levis-after-golive-plan-sep2026`):

- 🔴 **PR #177 dan #197 MEREVERT kode live** kalau di-merge apa adanya (entri `REPORT_MODEL_MAP` dua laporan digunggung; drill-down GL Open Items). **8 PR juga menurunkan versi di bawah yang terpasang.**
- **Perintah backup lama tidak pernah autentikasi** — `$PGPASSWORD` harus diekspansi DI DALAM container.
- Semua hitungan DB pemasang terlalu kecil (asset 7→13, reports 11→13, layout_memory 16→18).
- **Container ada EMPAT** yang me-mount `/opt` addons (odoo, odoo-mgmt, odoo-front, odoo-vaspmo).
- **Pencocokan GR/IR per baris mustahil** — cuma 41% cocok.
- **Nilai Selection baru TIDAK butuh `-u`**; sebaliknya menambah kolom laporan SELALU butuh `-u` (template QWeb menulis `<th>` literal).

## 13. Yang MASIH TERBUKA

Prioritas menurun. Angka rupiah disebutkan kalau ada.

### Keuangan / butuh keputusan klien

1. **9 draft COGS catch-up Rp 3.034.401.903,48 (September murni)** — posting **di-HOLD FA** sampai penjualan toko ex-AMP masuk. Nol saklar dinyalakan atas keputusan user 27-Sep (`levis-cogs-open-items-sep25`, `levis-cogs-automation-deploy-sep25`).
2. **Persediaan awal tidak pernah masuk GL — gap Rp 25.312.005.806,49** (GL 55.147.538.511,64 vs fisik 80.459.544.318,13 per 27-Sep). Butuh jurnal pembukaan persediaan tersendiri, dan **tiap posting COGS melebarkannya** (`levis-cogs-open-items-sep25`).
3. **Clearing September 2026 belum dijalankan** — MDR Rp 30,2 jt sudah di bank tetapi GL `7104000001` masih NOL; sisa suspense September −Rp 193.219.638,96 (ekor BRI) menunggu (`levis-wave3-decisions-sep18`, `levis-august-clearing-prep`).
4. **KOL Rp 76.926.875** — 32 transaksi Grand Indonesia 15-Jul, barang gratis tercatat penjualan tunai. Menggantung permanen di `1106000101`. Butuh keputusan: reklas ke beban promosi, atau batalkan di X-Store + impor ulang sebagai free goods (implikasi PPN cuma-cuma) (`levis-july-clearing-prd-begbal`).
5. **Selisih Juli Rp 901.974** terbawa utuh ke Agustus, nol jurnal koreksi sepanjang Agustus/September. Rp 2.700.775 adalah kurang-terima bank 06-Jul yang harus ditagih/di-write-off (`levis-july-901974-gap`).
6. **Plug suspense Rp 1.980.248,29** (`GLJV/2026/07/0118`) — hanya Rp 2.791.009 yang bisa dijelaskan; sisa Rp 810.760,71 adalah over-clearing blok A/B (`levis-july-suspense-plug-1980248`).
7. **`27917/IN/00001` sengaja dibiarkan** — GR qty/harga tertukar yang returnya tidak berjurnal; GL masih menanggung **Rp 191,29 juta** persediaan yang barangnya tidak ada (`levis-po-ppn-included-correction`).
8. **377 settlement dengan `x24_tender_mismatch`** — total per toko benar, akun per-tender salah saji. Perubahan perilaku akuntansi, menunggu keputusan user (`levis-pos-clearing-feature`).
9. **8 pasang (PO, SKU) duplikat di 5 PO Agustus**, semuanya sudah GR done + bill posted → koreksi harus jalur retur (`levis-po-duplicate-sku-guard`).
10. **Satu payment menggantung** `8282/2026/07/074` 17-Jul PT ARTISAN WAHYU, residual **Rp 1.500** (`levis-t01-aged-as-of-done`).
11. **Reklas AP related party saldo lama TIDAK dikerjakan** atas permintaan user — Rp 44,58 M masih terbuka di `2103100001` (`levis-related-party-payable`).
12. **11 akun, netto Rp 24,9 juta** yang tidak ada di berkas GL klien — butuh GL Juli / GL revisi dari EBR (`levis-tb-selisih-jul13-stale-export`).
13. **Jurnal non-penjualan Juni masih diutang Finance** (`levis-begbal-may-plus-june-sales`).
14. **Draft yatim `OBCA/2026/00001`** (9-Sep, Dr `1102000099` / Cr `2103300001`) milik request PCA yang sudah dihapus — tanya Finance (`levis-begbal-cash-advance-cash-accounts`).

### Data / sumber

15. **Data 15-Sep-2026 HILANG TOTAL** — satu hari dagang 22 toko, ±Rp 300 juta, nol sumber di mana pun. **Harus ditagih kirim ulang ke X-center** (`levis-x70d-feed-gaps-sep2026`).
16. **Feed X24DN/X70D belum memuat 9 toko baru** — nol baris sepanjang sejarah, sementara uang banknya sudah mengalir sejak 29-Agu. Pekerjaan XStore/klien (`levis-new-stores-sept2026`).
17. **375 baris X101 ditolak zero-price** (8 style garmen nyata) — butuh master terkoreksi + `retail_import.x101_update_price=1` (`levis-july-sales-gap-aug03`, `x101-import-queue-limits-and-price-gap`).
18. **10–14 unit RIBCAGE tanpa PO** dan **150 produk / 272 unit September tanpa `standard_price`** (`levis-cogs-open-items-sep25`).
19. **Harga 3 SKU RIBCAGE jadi pertanyaan tim M&P**, belum diputuskan (`levis-cogs-automation-deploy-sep25`).
20. **5 template klien yang diklaim terkirim tapi tidak ada** (#64, #69, #70, #26, #27/#28) (`levis-golive-new-issues-sep18`).
21. **Mandiri `72223624331` tercantum untuk DUA toko**; DR RATULANGI tanpa nomor BNI; 2 settlement BCA ber-MID di luar sheet klien (`levis-new-stores-sept2026`).
22. **8 toko baru belum punya label EBR pendek** untuk kolom REMARKS workbook (`levis-clearing-ebr-roundtrip`).

### Kode / teknis

23. 🔴 **`custom_levis_mdr` dan skrip 126 berjalan di produksi tapi tidak ada di `main`.** Keduanya ada di git, hanya pada branch PR yang masih terbuka: modul MDR di PR #264 (commit `1280256a`), skrip 126 di PR #263 (commit `ba80583b`/`8b434ce7`) — diverifikasi 28-Sep-2026. Itu membuat `-u` dari worktree GAGAL untuk `prd_levis_begbal`, dan menutup salah satu PR tanpa merge akan meninggalkan kode produksi tanpa rumah di `main` (`levis-cogs-automation-deploy-sep25`).
24. **Parser BRI varian 5 kolom belum dibuat** — sementara file bentuk itu harus dinormalkan manual ke 6 kolom sebelum diimpor (`bri-mutasi-vs-brisim-export`).
25. **`_parse_mandiri` / `_parse_bni` masih stub** — 59 rule MID sudah distage tapi inert (`levis-new-stores-sept2026`).
26. **PR #243** (9 toko, 14 insertion di `41_normalize_ou.py`) masih OPEN (`levis-new-stores-sept2026`).
27. **PR #250 (T18)** belum merge/deploy — deploy nanti hanya `-u custom_levis_bank_reconcile` di `prd_levis_begbal` (satu-satunya pemasang) (`levis-t18-bank-mid`).
28. **Isu #72** (panduan clearing plus-minus `2103400001`) dan **#76-lanjut** masih OPEN (`levis-golive-new-issues-sep18`).
29. **#11 lebar kolom** — GH #182, estimasi 2–3 hari; biaya sebenarnya memelihara patch core (`levis-sheet-after-golive-status-aug19`).
30. **`x48_post_enabled=0` karena bug belum diperbaiki**: refund X48 di-tender ke metode CASH toko dan nilainya mendarat di akun *Cash Difference* (Rp 19.798.400 pada file Juni), bukan mengurangi kas (`docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md`, `retail-import-x24dn-source-of-truth`).
31. **Cron depresiasi aset NONAKTIF** — depresiasi **tidak** jalan otomatis, harus diposting manual. ⚠️ Dokumen FD/Manual versi awal menyebut cron ini **aktif**; itu **SALAH** (`docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md`, `levis-config-followups-status`).
32. **`levis.mdr.bin` 0 baris** dan **COA biaya audit** menunggu arahan Finance (`docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md`).
33. **"Rekap Bukti Potong PPh" kosong** — gap pipeline (bupot hanya lahir dari jalur engine), perlu keputusan (`rekap-pph-kode-objek-from-base-line`).
34. **NPWP company kosong di `prd_levis_begbal`** dan **0 dari 30 UoM punya kode Coretax** — kedua-duanya menghentikan ekspor e-Faktur dengan `UserError` (`efaktur-fk-of-export-entry-points`).
35. **`x24_autoregister_from_sales` masih OFF di setiap DB** — diblokir keputusan Finance soal akun income/COGS kategori "MDM Pending"; **map kategorinya SEBELUM membalik flag** (`retail-import-20-deploy-aug03`).
36. **CIDR egress Mulesoft tidak terdokumentasi di mana pun** — sementara `172.18.0.0/16` (`retail-import-20-deploy-aug03`).
37. **Port 18069 listen di `0.0.0.0` dan `ufw` host inactive** — seluruh instance Odoo terjangkau dari interface host mana pun (`retail-import-20-deploy-aug03`).
38. **`auth_totp` terpasang di semua DB tapi 0 user enroll**; Odoo 19 CE tak punya `res_company.totp_policy` sehingga penegakan 2FA butuh modul kecil (`levis-admin-rights-cleanup`).
39. **`prd_levis_AP` belum dirapikan hak aksesnya** — terblokir 4 user tanpa grup fungsional (`levis-admin-rights-cleanup`).
40. **Alarm WhatsApp DIMATIKAN** (`ALERT_WHATSAPP_DISABLED=1` di `/opt/odoo-platform/.env`, cadangan `backups/.env.bak-20260908`) — sesi baileys perlu pairing QR ulang. Peringatan tetap ditulis ke log (`retail-feed-shared-dropfolder-race`).
41. **`LEVIS_MAIL_PASSWORD` harus dirotasi** — nilainya pernah tertempel di transkrip chat (`levis-mail-ingest`).

## 14. JANGAN — khusus Levi's

Larangan di bawah **hanya** berlaku/khas di vertikal ini. Aturan platform umum (dump sebelum sentuh prod, dua checkout, pre-commit bukan hook, bump versi addon shared) ada di `CLAUDE.md` repo.

### Tentang DB dan versi

- **JANGAN mengira `prd_levis` adalah produksi.** Ia environment testing; produksi sebenarnya `prd_levis_begbal` (`retail-feed-shared-dropfolder-race`).
- **JANGAN commit dari working tree `/home`.** Versi produksi jauh di depan dan commit naif justru **MEREVERT** fitur main. Buat worktree di atas `origin/main`, port hanya file fitur yang dimaksud (`levis-module-versions-lag-git`, `levis-po-duplicate-sku-guard`).
- **JANGAN menilai keberadaan kode dari `git ls-files` di `/home`** — bandingkan dengan `origin/main` (`levis-store-day-cash-split-and-matching`).
- **JANGAN merge PR #177 atau #197 apa adanya** — keduanya MEREVERT kode live (`levis-after-golive-plan-sep2026`).
- **JANGAN membuka lagi PR #116** (custom_account_reconcile) — sudah ditutup dan digantikan PR #127 (`reconciliation-guards-module`).
- **JANGAN `-u` modul Levi's dari worktree `docker run`** untuk `prd_levis_begbal`: worktree tidak punya `custom_levis_mdr`/`custom_report_inline_assets`, dan Odoo lalu mencoba `ALTER TABLE stock_warehouse ALTER COLUMN wms_mode DROP NOT NULL` lalu kena lock timeout. Pakai `docker exec` pada container yang mount `/opt` (`levis-cogs-automation-deploy-sep25`).
- **JANGAN jalankan suite penuh `custom_levis_localization` di DB Levi's mana pun** — ±345rb produk, `TestClearingStoreDay` menggantung berjam-jam. Jalankan per kelas (`levis-t02a-grir-autoreconcile`).
- **JANGAN `-u custom_account_reconcile` di `tst_agedpay`** — DB itu menyimpan view PR #116 yang merujuk field yang tidak ada di `/opt` (`tst-agedpay-ahead-of-opt`).

### Tentang akuntansi

- **JANGAN backdate jurnal adjustment ke periode yang angkanya sudah dilaporkan ke klien**, walaupun `fiscalyear_lock_date` bisa dibuka sementara dan walaupun secara akuntansi jurnalnya "milik" periode itu. Bukukan di periode terbuka berikutnya. Kalau terlanjur ter-posting dan jurnalnya masih baru: **hapus, jangan reverse** — reversal mengembalikan saldo tapi tetap menambah mutasi dan baris GL di periode itu (`levis-closed-period-no-backdate`).
- **JANGAN membukukan ulang COGS Juli 2026.** Sudah diposting tangan (`GLJV/2026/07/0032`+`0033`), dan hitung ulang justru LEBIH salah (`levis-cogs-june-gap-july-posted`).
- **JANGAN melebarkan `cogs_catchup_start` ke Juni/Juli** tanpa seed `levis.cogs.charge` dulu — biayanya akan dibebankan kedua kali (`levis-cogs-catchup-on-receipt`).
- **JANGAN majukan `l10n_cogs_reported_through` sebelum COGS bulan itu lengkap** — September akan tertutup dan COGS-nya dilempar ke Oktober (`levis-cogs-open-items-sep25`).
- **JANGAN posting 8/9 draft catch-up apa adanya** sebelum porsi periode yang sudah dibukukan manual dibuang (skrip 126 sudah menyelesaikan Agustus) (`levis-cogs-open-items-sep25`).
- **JANGAN pakai fitur `levis.pos.clearing` untuk Juli 2026** — kolam piutang yang sama akan dijanjikan dua kali (`levis-july-clearing-completed`).
- **JANGAN mengisi baris Trade `grir_account_id` di `levis.purchase.account.map`** — itu akan meng-override pemetaan GR/IR per kategori (`levis-config-followups-status`).
- **JANGAN memakai `stock_move.value` atau `standard_price` sebagai basis COGS** — pakai harga PO netto PPN (`levis-cogs-june-gap-july-posted`).
- **JANGAN mengaktifkan `x31_post_enabled` bersama `x24_discount_reclass`** — saling eksklusif, Gross Sales menggelembung dua kali (`docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md`).
- **JANGAN menyalakan engine withholding untuk memperbaiki selisih akun PPh** — itu membuat PPh dobel; arahkan repartition line tax (`levis-wave3-decisions-sep18`).
- **JANGAN memasang PPh sebagai native tax di kolom Taxes kalau engine withholding aktif** — either/or (`custom-tax-id-double-pph-booking`).
- **JANGAN menandai akun kas `reconcile=true`** hanya supaya muncul di picker advance — setiap penyelesaian advance akan merekonsiliasi kas (`levis-wave3-decisions-sep18`).
- **JANGAN taruh akun clearing di outstanding PCPAY** — `_configure_payment_journal` menimpa setelan itu setiap kali bill pihak ketiga dibayar (`levis-begbal-cash-advance-cash-accounts`).
- **JANGAN mengandalkan `button_draft` sebagai rollback clearing** — Odoo 19 tidak melepas rekonsiliasi; rollback HANYA lewat restore dump (`levis-july-clearing-completed`, `levis-august-clearing-prep`).

### Tentang data & import

- **JANGAN menulis ulang `default_code` ke bentuk ber-hubung X101.** X24/X48/X70D matching, X32P, HHT dan setiap dokumen terposting berkunci PROD SKU. Satu user pernah melakukannya manual pada produk 386191 (31-Jul) — **revert** (`levis-x101-dual-code-po-import`).
- **JANGAN menjalankan X101 penuh lewat queue_job** — pakai `odoo shell` (`x101-import-queue-limits-and-price-gap`).
- **JANGAN `TRUNCATE ... CASCADE` tabel transaksi** — CASCADE menjembatani lewat `res_company.account_opening_move_id` dan menghapus SELURUH DB (`levis-txn-reset`).
- **JANGAN reset transaksi `prd_levis_begbal` tanpa `RESET_KEEP_JOURNALS=EBRTB`** — 6 move EBRTB yang menjadi alasan DB itu ada akan hilang (`levis-reset-orphan-tables-bug`).
- **JANGAN rename apa pun dengan `LIKE '%OLS %'`** (`levis-pos-naming-alignment`).
- **JANGAN mengubah `stock.warehouse.code`** — kunci join retail-import (`levis-operating-unit-normalization`).
- **JANGAN memakai `x24_np_category_id` (atau id kategori apa pun) lintas DB** — cocokkan by nama (`levis-gl-2026-detail-load`).
- **JANGAN memperbaiki `owner_id` receipt lewat ORM/UI** — ia valuation trigger dan akan mengubah nilai stok; pakai SQL `REPEATABLE READ` + `_set_value()` (`levis-receipt-owner-consignment-fix`).
- **JANGAN menghapus dokumen stok `done` lewat ORM** — `reserved_quantity` quant jadi negatif (`purge-done-stock-docs-odoo19`).
- **JANGAN mengklon DB Levi's produksi tanpa mematikan feed + mailbox-nya tepat setelah restore** — klon mewarisi 13 feed + 2 mailbox aktif dan akan mencuri file dari drop folder bersama serta menghapus surat dari INBOX bersama. Cek cepat: `select count(*) from retail_import_feed where active` (`retail-feed-shared-dropfolder-race`).
- **JANGAN centang Track Inventory (`is_storable`) produk mana pun tanpa mengukur dampaknya dulu** — Odoo **langsung** membuat `stock.move` `is_inventory` dan mengeluarkan SELURUH stok ke lokasi adjustment, **tanpa jurnal** kalau lokasi itu belum punya `valuation_account_id`. Hasilnya buku stok NOL sementara GL tetap terisi (kasus paper bag: 48.500 unit, GL Rp 141,7 juta). Urutan mengikat: **skrip 124 dulu, baru 123** (`levis-wave3-decisions-sep18`).
- **JANGAN memarkir seluruh transaksi karena baris NP** — kategori NP harus jatuh ke jalur lazy-create (`retail-import-x24-composite-match-npmerch`).
- **JANGAN mengisi `journal_id` pada metode pembayaran SUSPENSE** — ia harus `pay_later` (`retail-import-decouple-suspense`).
- **JANGAN parse "LAPORAN HARIAN LEVIS - <toko>.xlsx"** — ketikan ulang manual yang salah (`levis-store-mdr-recon-source`).
- **JANGAN memutuskan apakah sebuah berkas X70D dari nama berkasnya** — putuskan dari isi (header memuat `TRANSNUM` dan `TENDER AMOUNT`) (`levis-store-export-variants`).
- **JANGAN "memperbaiki" tarif QRIS BCA/BNI/BRI jadi 0,7%** — user menegaskan memang 0% (`levis-store-mdr-recon-source`).
- **JANGAN memberi OU pada 83 baris kanal `transfer`** — itu sweep kas ke pusat (`levis-cash-deposit-ou-patterns`).
- **JANGAN melewatkan kode terminal `Z####` ke `match_type='tid'`** — `_normalise_key` hanya menyisakan angka sehingga `Z6FK1` jadi `61` lalu suffix-match ke merchant id lain (`levis-cash-deposit-ou-patterns`).

### Tentang pengukuran dan pelaporan

- **JANGAN ukur sisa POS receivable dengan `amount_residual`** untuk membandingkan ke sheet — pakai `balance ≤ tanggal` (`levis-july-901974-gap`).
- **JANGAN masukkan `1106000112` ke pola `11060001%`** — itu POS suspense contra dan akan **melipatduakan** debit Juli tiap toko. Pakai `code between '1106000101' and '1106000110'` (`levis-july-clearing-completed`).
- **JANGAN nilai rekonsiliasi dari `sum(amount_residual)` per move** — nol baik saat settled maupun saat kedua kaki masih terbuka dan saling menghapus. Group by account dan hitung `reconciled` (`x24-import-blocked-by-open-pos-session`).
- **JANGAN jumlahkan "semua baris kecuali grand_total" pada Rekap PPh** — ada baris subtotal per kode objek, hasilnya tepat 2× (`levis-t20-closure-evidence`).
- **JANGAN cocokkan clearing per TRANSNUM** — EBR sering salah ketik transnum; kunci transnum melaporkan 17 "selisih" palsu (`levis-july-clearing-prd-begbal`).
- **JANGAN baca laporan raw-SQL langsung sesudah `reconcile()`** — `amount_residual` basi, wajib `env.flush_all()` dulu (`levis-august-clearing-prep`).
- **JANGAN percaya kolom Status di sheet klien**, dan **jangan mengutip angka plan rev1 atau angka T18 lama (73 baris / Rp 368 jt; yang benar 2 baris / Rp 5.050.800) ke klien** (`levis-sheet-after-golive-status-aug19`, `levis-after-golive-plan-sep2026`, `levis-t18-bank-mid`).
- **JANGAN memakai angka run POSCLR/2026/0010** — semuanya artefak duplikat statement (`levis-bank-statement-duplicate-imports`).
- **JANGAN jalankan ulang `84_report_ppn_included_correction.py` setelah koreksi** — ia menghitung DPP dari nilai GR yang kini sudah DPP (`levis-po-ppn-included-correction`).
- **JANGAN jalankan ulang skrip 69** untuk entry SALESMANUAL — ref-guard sudah `SystemExit` (`levis-june-ar-fico-final-rekon`).
- **JANGAN menjadikan kasus yang kebetulan benar sebagai tes.** `SMB SOPIAN PERMANA` lulus hanya karena alfabet ('M' < 'O'); tesnya harus memakai varian yang alfabetnya melawan (`levis-mid-mapping-by-evidence`).
