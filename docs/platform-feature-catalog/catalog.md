<!-- GENERATED FILE — do not edit by hand.
     Source: catalog.json + narrative/*.md
     Rebuild: python3 docs/platform-feature-catalog/build.sh -->

# Katalog Fitur Platform Odoo — Erajaya Group

Dihasilkan 2026-08-11 dari commit `4896fdf` (ada perubahan belum ter-commit) pada branch `docs/catalog-rebuild-162`. Odoo 19.0, 162 modul custom.

# Ringkasan Eksekutif

Dokumen ini adalah katalog lengkap fitur yang sudah dibangun di atas platform Odoo Erajaya Group: **162 modul custom**, dikelompokkan ke dalam 8 brand dan tiga belas domain fungsional. Dokumen ini menjawab tiga pertanyaan yang selama ini tersebar di banyak berkas dan tidak pernah dijawab di satu tempat:

- Apa saja yang sudah tersedia?
- Mana yang berlaku umum untuk tenant mana pun, dan mana yang khusus satu brand?
- Sejauh mana platform ini benar-benar berjalan sebagai layanan, dan apa yang belum ada?

## Angka yang perlu diketahui

|  |  |
| --- | --- |
| Modul custom | **162** |
| Berlaku umum untuk semua tenant | 140 |
| Khusus satu brand (`addons/_tenants/`) | 11 |
| Lapisan kendali platform | 7 |
| Komponen pihak ketiga (OCA) | 4 |
| Brand / tenant terdaftar | 8 |
| Kesenjangan tercatat (prioritas tinggi) | 10 (3) |

Sekitar **140 dari 162 modul berlaku umum**. Hanya 11 modul yang benar-benar terikat pada satu brand. Itulah angka yang menopang klaim reuse lintas vertikal: sebuah tenant baru mewarisi hampir seluruh kapabilitas platform tanpa pengembangan ulang, dan yang tersisa adalah konfigurasi serta data.

## Apa yang membedakan dokumen ini

Setiap angka di sini **dipindai langsung dari repositori**, bukan diketik. Sebuah skrip membaca seluruh direktori `addons/`, mengurai setiap manifest dan kode model, lalu menghasilkan berkas data yang menjadi sumber tunggal bagi versi Markdown, PDF, dan Excel dokumen ini. Menambahkan modul baru membuat proses build gagal sampai modul itu diklasifikasikan.

Alasannya sederhana: sebelum dokumen ini dibuat, tabel jumlah modul di dokumen arsitektur internal salah pada lima dari delapan barisnya. Satu grup tertulis 78 modul padahal berisi 105. Angka yang dipelihara manual selalu tertinggal.

Dokumen ini juga **menandai tingkat keyakinannya sendiri**. Dari 162 modul, 110 memiliki dokumen pengetahuan hasil generator yang belum diperiksa manusia, dan 27 belum memiliki dokumen sama sekali. Isinya tetap dipakai — tetapi setiap baris membawa kolom **Keyakinan Info**, dan sebuah gerbang otomatis membandingkan setiap klaim dengan kode sebelum dokumen ini terbit. Klaim yang menyebut model yang tidak ada di kode diturunkan keyakinannya dan daftar modelnya dibuang.

## Struktur dokumen

- **Bab 1–2** — arsitektur platform dan model layanan: bagaimana satu basis kode melayani banyak brand, dan apa arti "umum" versus "khusus brand".
- **Bab 3–15** — tiga belas domain fungsional. Setiap bab menutup dengan subbagian *Yang bersifat khusus per-brand*, sehingga pemisahan umum versus khusus terlihat di setiap domain, bukan hanya di ringkasan.
- **Bab 15** — administrasi platform dan Odoo sebagai layanan, termasuk analisis kesenjangan **Kondisi Saat Ini versus Sasaran** yang jujur.
- **Lampiran** — rincian teknis per modul dalam Bahasa Inggris, untuk tim pengembang dan arsitek. Istilah antarmuka Odoo sengaja dipertahankan dalam Bahasa Inggris di seluruh dokumen.

## Yang tidak dokumen ini janjikan

Katalog ini mencatat **apa yang ada di dalam basis kode**, bukan apa yang aktif di setiap basis data. Sebuah modul yang tercatat di sini belum tentu terpasang pada tenant tertentu; kolom **Brand Terkait** menunjukkan di mana sebuah modul sudah membawa data atau konfigurasi, bukan daftar instalasi. Untuk pertanyaan "apakah fitur X aktif di basis data Y", jawabannya ada di basis data itu sendiri, bukan di dokumen ini.

# 1. Arsitektur Platform

## 1.1 Satu basis kode, banyak brand

Platform ini adalah **satu repositori Odoo 19 yang melayani seluruh brand Erajaya Group sekaligus beberapa tenant di luar grup**. Setiap tenant mendapat basis datanya sendiri di dalam satu klaster PostgreSQL; kode, modul, dan pembaruan dibagi bersama.

Konsekuensinya berlaku dua arah, dan keduanya perlu dipahami sebelum membaca bab mana pun setelah ini:

- Sebuah perbaikan yang dikerjakan untuk satu brand langsung tersedia untuk semua brand lain. Ini sumber penghematan terbesar platform.
- Sebuah perubahan pada modul bersama **menyentuh semua tenant**, termasuk yang tidak meminta perubahan itu. Karena itu ada aturan tegas tentang di mana sebuah modul boleh diletakkan.

| Brand | Entitas | Afiliasi | Industri | Basis data | Status |
| --- | --- | --- | --- | --- | --- |
| ARKA-AIM | PT Arka Mandiri Nusantara / PT AIM | Erajaya Group | Sewa & pertunjukan drone | `prd_arkaaim`, `trn_arkaaim` | live |
| Levi's | PT Era Busana Retailindo (EBR) | Erajaya Group | Retail fashion | `prd_levis_begbal`, `rnd_levis` | live |
| Eraspace / PPOB-VAS | PT Erajaya Swasembada Tbk | Erajaya Group | Value-added services / bill payment | `rnd_ppob` | development |
| EFN (Erajaya F&B) | Erajaya Food & Nourishment | Erajaya Group | Food & beverage | `rnd_esb` | pre-pilot |
| Finance Portal | Erajaya Group Shared Services | Erajaya Group | Corporate finance over SAP | — | development |
| VAS PMO | Erajaya Value-Added Services | Erajaya Group | Delivery management | `rnd_vas_pmo` | live |
| GentleWoman | GentleWoman AP | Di luar grup | Retail fashion / eCommerce | — | pre-implementation |
| JDS Warehouse | JDS | Di luar grup | Warehouse management | `rnd_wms` | poc |

## 1.2 Tingkatan modul

Tingkat sebuah modul ditentukan **semata-mata oleh direktori tempat ia berada** di bawah `addons/`. Kategori di dalam manifest bukan penentu tingkat: modul `ee_gap` sengaja memakai kategori bawaan Odoo agar muncul berdampingan dengan aplikasi Enterprise yang digantikannya.

| Grup | Modul |
| --- | --- |
| `addons/_tenants/` | 11 |
| `addons/_vendor/` | 4 |
| `addons/compliance/` | 9 |
| `addons/control_plane/` | 4 |
| `addons/core/` | 11 |
| `addons/ee_gap/` | 106 |
| `addons/operations/` | 3 |
| `addons/verticals/` | 14 |
| **Total** | **162** |

Tiga aturan mengatur penempatan:

- **Mesin integrasi bersama selalu masuk `ee_gap/` atau `core/`, tidak pernah `_tenants/`.** Data awalnya boleh milik satu pelanggan; mesinnya tidak. Contoh kanoniknya adalah `custom_retail_import`, yang generik, sementara profil `levis_*` di dalam datanya milik satu tenant.
- **Promosi.** Sebuah pola yang muncul untuk pelanggan kedua naik dari `_tenants/` ke `ee_gap/`.
- **Kedalaman direktori tetap** `addons/<grup>/<modul>/`. Satu pengecualian yang sudah ada — modul template di `verticals/_template/` — berada satu tingkat lebih dalam, dan itulah sebabnya perhitungan modul yang berbatas kedalaman menghasilkan satu modul lebih sedikit dari 162.

Grup `ee_gap` adalah yang terbesar dengan 106 modul. Isinya adalah **selisih antara Odoo Community dan Odoo Enterprise**, ditambah lokalisasi Indonesia: akuntansi, payroll, gudang, portal keuangan, retail, dan e-commerce. Ini bagian dari platform yang paling bernilai secara komersial, karena menghilangkan ketergantungan lisensi Enterprise per pengguna untuk kapabilitas yang dibutuhkan Erajaya.

![Tingkatan modul: semakin ke atas, semakin sedikit tenant yang tersentuh](svg/D02-tingkatan-modul.svg)

## 1.3 Lapisan teknis

Seluruh tumpukan berjalan sebagai kontainer Docker di satu host, di belakang satu reverse proxy:

- **Pintu depan** — Caddy dengan Web Application Firewall (OWASP CRS), TLS, dan pembatasan laju per alamat IP. Nama sub-domain tenant diterjemahkan menjadi nama basis data lewat header, sehingga satu instans Odoo melayani banyak tenant tanpa saling melihat.
- **Gerbang login** — halaman `/signin` tersendiri menggantikan pemilih basis data bawaan Odoo, yang secara bawaan membocorkan daftar seluruh tenant.
- **Aplikasi** — Odoo 19 Community dengan 162 modul custom di atasnya, ditambah beberapa aplikasi pendamping (konsol admin, storefront, aplikasi PMO) yang berbicara ke Odoo lewat API bertanda tangan.
- **Data** — satu klaster PostgreSQL dengan satu basis data per tenant, Redis untuk pencegahan replay dan cache, MinIO untuk objek dan salinan cadangan.
- **Integrasi** — satu kontrak HMAC dipakai untuk kedua arah: setiap panggilan masuk dan keluar ditandatangani dengan stempel waktu, dibatasi selisih waktu 300 detik, dan dijaga terhadap pengulangan lewat Redis.

![Arsitektur platform: dari pengguna sampai basis data](svg/D01-arsitektur.svg)

Rincian operasional lapisan ini — siklus hidup tenant, hak akses, cadangan, dan apa yang **belum** dibangun — ada di Bab 15.

## 1.4 Domain fungsional dalam dokumen ini

Tiga belas domain di bawah ini adalah cara dokumen ini membaca 162 modul tersebut. Pengelompokan ini dibuat untuk pembaca bisnis dan tidak selalu sama dengan struktur direktori: sebuah modul akuntansi tetap masuk domain Keuangan meskipun ia berada di `addons/_tenants/`.

| Domain | Modul | Cakupan isi |
| --- | --- | --- |
| Keuangan & Akuntansi | 30 | Buku besar, laporan keuangan, aset tetap, kas & bank, dan portal keuangan yang menutup selisih antara Odoo Community dan Enterprise. |
| Perpajakan Indonesia | 6 | Coretax DJP, e-Faktur, Bukti Potong Unifikasi, dan mesin pemotongan PPh — mengikuti PER-11/PJ/2025 dan PMK 131/2024. |
| SDM & Payroll | 13 | Payroll PPh 21 TER dan BPJS, absensi geofence, cuti UU Cipta Kerja, rekrutmen, penilaian kinerja, dan reimbursement. |
| Gudang & Inventori | 17 | Putaway, cycle count, QC inbound, transfer order, handheld terminal, barcode, dan retur pembelian. |
| Penjualan, Retail & POS | 11 | CRM, POS Indonesia, eCommerce dan storefront headless, langganan, serta jalur impor data retail dari XStore. |
| Layanan, Proyek & Sewa | 15 | Manajemen proyek dan change request, helpdesk ber-SLA, field service, timesheet, dan siklus penyewaan aset dengan BAST. |
| Manufaktur, Kualitas & Pemeliharaan | 5 | Quality point dan CAPA, PLM/ECO, pemeliharaan prediktif dengan MTBF/MTTR, perbaikan aset, dan ingest sensor IoT. |
| Produktivitas & AI | 10 | Jembatan AI ke Claude/OpenAI/Ollama, dokumen, knowledge base, spreadsheet, dashboard, tanda tangan elektronik, dan Studio Lite. |
| Pemasaran & Komunikasi | 12 | WhatsApp Cloud API, SMS Indonesia, email marketing, marketing automation, event, survei, dan kanal komunikasi pelanggan. |
| Kepatuhan Data (UU PDP) & Audit | 6 | Klasifikasi data pribadi, audit log berantai-hash, consent, DSAR, masking PII, dan kebijakan retensi — UU 27/2022. |
| Integrasi & Fondasi Platform | 16 | Fondasi bersama: HMAC endpoint, adapter framework, mesin persetujuan, SSO Keycloak, konektor ESB, dan komponen OCA. |
| Vertikal Industri | 14 | Paket khusus industri: PPOB/VAS (dompet mitra, provider, switching H2H) dan operasi stok F&B di atas ESB Core. |
| Administrasi Platform & Odoo-as-a-Service | 7 | Lapisan kendali multi-tenant: registry tenant, provisioning, deploy modul, monitoring kapasitas, onboarding journey, dan pelacakan siklus dev. |
| **Total** | **162** |  |

![Modul per domain fungsional](svg/D04-peta-domain.svg)

# 2. Model Layanan — Umum versus Khusus Brand

Pertanyaan "fitur ini bisa dipakai brand lain atau tidak" tidak punya jawaban biner. Katalog ini membedakan **tiga tingkat**, dan perbedaannya menentukan berapa biaya membawa sebuah kapabilitas ke tenant berikutnya.

## 2.1 Tiga tingkat cakupan

**Umum** — 140 modul. Tersedia untuk tenant mana pun tanpa utang konfigurasi berarti. Pasang, aktifkan, pakai. Mayoritas kapabilitas akuntansi, SDM, gudang, dan produktivitas berada di tingkat ini.

**Umum, dikonfigurasi untuk brand tertentu** — mesin generik yang **sudah membawa profil, data, atau pemetaan satu brand**. Tenant kedua bisa memakainya, tetapi harus menyediakan profilnya sendiri. Dua contoh yang paling menjelaskan:

- `custom_retail_import` adalah mesin ingest Excel/CSV/SFTP yang sepenuhnya generik. Yang khusus Levi's adalah profil format berkas XStore di dalam datanya. Retailer lain memerlukan profilnya sendiri, bukan modul baru.
- `l10n_erajaya` menyediakan bagan akun 10 digit standar grup. Ia dipakai bersama oleh dua tenant live — ARKA-AIM dan Levi's — dan siap dipakai tenant Erajaya berikutnya tanpa perubahan kode.

**Khusus brand** — 11 modul di `addons/_tenants/`. Terikat pada satu entitas dan **tidak dapat dipakai ulang apa adanya**. Isinya adalah aturan yang benar-benar hanya berlaku di sana: saldo awal per tanggal tertentu, format penomoran dokumen satu perusahaan, akun revaluasi aset satu entitas.

Dua tingkat sisanya melengkapi gambaran: **Platform** (7 modul) adalah lapisan kendali yang melayani operator, bukan tenant; **Pihak ketiga** (4 modul) adalah komponen OCA yang di-vendor dan tidak diubah.

## 2.2 Mengapa modul khusus brand sedikit

Angka 11 dari 162 bukan kebetulan. Ada aturan tertulis yang mencegahnya membesar: **mesin bersama tidak boleh masuk `_tenants/`**, seberapa pun jelas ia diminta oleh satu pelanggan. Yang boleh masuk ke sana hanyalah data dan aturan yang secara definisi tidak berlaku di tempat lain.

Ketika sebuah pola muncul untuk pelanggan kedua, ia dipromosikan naik ke `ee_gap/`. Jadi tekanan sistemnya mengarah ke pengurangan modul khusus brand seiring waktu, bukan penambahan.

Konsekuensi praktisnya untuk perencanaan: **biaya menambah brand baru terutama adalah konfigurasi dan migrasi data, bukan pengembangan.** Yang perlu dibangun biasanya hanya bagan akun, penomoran dokumen, saldo awal, dan aturan lokal yang tidak dimiliki entitas lain.

## 2.3 Cara membaca kolom Brand Terkait

Di setiap tabel domain, kolom **Brand** menunjukkan brand yang modul tersebut **sudah membawa data atau konfigurasinya**. Kolom ini bukan daftar instalasi:

- Untuk modul **khusus brand**, kolom ini adalah pemiliknya.
- Untuk modul **umum**, kolom ini adalah brand yang profilnya sudah dikirim — petunjuk bahwa jalur itu sudah terbukti jalan, dan bahwa tenant lain akan memerlukan profilnya sendiri.
- Kolom kosong berarti modul berlaku umum tanpa data brand apa pun.

Pemetaan lengkap modul terhadap brand tersedia sebagai matriks di lembar **Peta Brand** pada berkas Excel pendamping dokumen ini. Ringkasannya per domain:

![Domain terhadap brand](svg/D05-peta-brand.svg)

## 2.4 Kematangan dan keyakinan informasi

Dua kolom lain muncul di setiap tabel, dan keduanya adalah penilaian, bukan fakta mentah:

**Kematangan** diturunkan dari kode. Modul dengan suite pengujian dinilai *Produksi*; modul dengan model, endpoint, atau data tetapi tanpa pengujian dinilai *Beta*; modul kosong dinilai *Kerangka*. Sebelas modul dikoreksi manual karena mereka berjalan di produksi tanpa membawa pengujian — penilaian otomatis akan salah menurunkannya.

**Keyakinan Info** menyatakan seberapa dipercaya deskripsi di dokumen ini, bukan seberapa baik modulnya. *Tinggi* berarti deskripsi ditulis atau diperiksa manusia. *Sedang* berarti berasal dari dokumen pengetahuan hasil generator yang belum diperiksa. *Rendah* berarti tidak ada dokumen pengetahuan, atau gerbang audit menemukan klaim yang tidak didukung kode.

Membedakan keduanya penting. Sebuah modul bisa berstatus Produksi dengan Keyakinan Rendah — artinya ia berjalan baik, tetapi katalog ini belum bisa menjamin deskripsinya lengkap.

# 3. Keuangan & Akuntansi

Domain terbesar di platform: **30 modul**. Isinya adalah kapabilitas akuntansi yang tidak ada di Odoo Community dan biasanya menjadi alasan utama membeli lisensi Enterprise — dibangun sendiri, sehingga tidak ada biaya lisensi per pengguna untuknya.

## 3.1 Yang menutup selisih Community versus Enterprise

**Mesin laporan keuangan** (`custom_accounting_reports`) adalah modul dengan churn tertinggi kedua di seluruh platform, dan itu bukan kebetulan: laporan adalah tempat kebenaran akuntansi diuji. Ia menyediakan Laba Rugi, Neraca, Buku Besar, Neraca Saldo, Arus Kas, Aging Piutang dan Utang, Buku Kas dan Bank, Partner Ledger, serta laporan pajak — semuanya dengan penelusuran ke jurnal asal.

**Rekonsiliasi manual** (`custom_account_reconcile`) mengembalikan menu dan wizard rekonsiliasi bergaya Enterprise ke Community. Tanpa modul ini, mencocokkan pembayaran dengan faktur di Community adalah pekerjaan satu per satu.

**Aset tetap** (`custom_accounting_asset`) membawa register aset, jadwal penyusutan, cron posting bulanan, dan alur pelepasan aset — dipakai oleh dua tenant live.

**Konsolidasi dan antar-perusahaan** (`custom_accounting_full`) menangani otomasi transaksi antar-perusahaan, eliminasi, laporan konsolidasi, batas kredit, tahun fiskal, dan tingkat follow-up penagihan.

Melengkapinya: jurnal dan pembayaran berulang, pendapatan/beban ditangguhkan, pembayaran batch dengan ekspor file transfer bank Indonesia, impor rekening koran multi-format, serta pelaporan keberlanjutan ESG untuk POJK 51/2017.

## 3.2 Kas, bank, dan pembayaran

Sekelompok modul kecil menutup hal-hal yang tampak sepele tetapi menghentikan pekerjaan harian bila tidak ada: metode pembayaran **GIRO** dan **Bank Transfer** pada jurnal bank, **voucher pembayaran dan kuitansi** yang bisa dicetak lengkap dengan terbilang, dan **biaya admin bank multi-COA** pada wizard Register Payment.

**Uang muka dan kas kecil** (`custom_petty_cash`) adalah kapabilitas yang tidak dimiliki Odoo Enterprise sekalipun: permintaan bertipe, persetujuan Finance, pencairan lewat bank, realisasi, penyelesaian, dan Kartu Uang Muka per karyawan, termasuk penanganan multi-mata uang. Sudah terpasang di dua tenant live.

## 3.3 Finance Portal — Odoo di depan SAP

Empat modul membentuk **Finance Portal**, sebuah pola yang berbeda dari sisa domain ini dan layak dipahami tersendiri.

Di sini Odoo berperan sebagai **sistem interaksi** di depan SAP S/4HANA yang tetap menjadi **sistem pencatatan**. Odoo menjalankan formulir pengajuan, persetujuan dua tahap Tax Review → Finance Review, dan validasi anggaran. Dokumen yang disetujui didorong ke SAP, yang membukukan GL atau MIRO dan membayar.

Keputusan desain yang penting bagi Finance: **Odoo tidak pernah membukukan jurnal sendiri di jalur ini.** Ia hanya mencerminkan status dari SAP. Tidak ada mekanisme di sini yang bisa menciptakan versi kedua dari kebenaran di buku besar.

Empat jenis dokumen ditangani: uang muka beserta realisasinya, reimbursement, tagihan vendor (dengan portal vendor), dan penyelesaian perjalanan dinas sebagai cerminan data HRIS. Integrasi SAP-nya **menurun dengan anggun**: tanpa konfigurasi adapter yang aktif, dorongan ke SAP jatuh ke stub lokal dan penjadwal tidak melakukan apa-apa — portal tetap dapat dipakai sebelum konektor SAP siap.

## 3.4 Bagan akun

Dua template bagan akun tersedia. **Bagan Akun Erajaya** (`l10n_erajaya`) menyediakan standar grup 10 digit — 534 akun, 29 grup akun, 78 pajak — dan dipakai bersama oleh ARKA-AIM dan Levi's. **Bagan Akun PSAK** (`l10n_id_psak_custom`) menyediakan alternatif 5 digit untuk tenant di luar standar grup.

Keduanya muncul sebagai pilihan di Settings → Accounting → Chart Template, dan dipilih sekali saat perusahaan dibuat. Keduanya dinilai *Kerangka* pada kolom Kematangan karena tidak memuat model Python dan tidak membawa pengujian; secara operasional keduanya sudah dipakai di basis data produksi.

## 3.5 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Pembayaran Batch | `custom_account_batch_payment` | Umum | — | Produksi | Pembayaran massal dengan ekspor file transfer bank Indonesia. |
| Pendapatan & Beban Ditangguhkan | `custom_account_deferred` | Umum | — | Produksi | Menyebar baris faktur/tagihan ke rentang periode lewat akun tangguhan. |
| Rekonsiliasi Akun | `custom_account_reconcile` | Umum | — | Produksi | Menu dan wizard rekonsiliasi manual bergaya Enterprise untuk Odoo Community. |
| Aset Tetap & Penyusutan | `custom_accounting_asset` | Umum, dikonfigurasi | ARKA-AIM, Levi's | Produksi | Register aset, jadwal penyusutan, cron posting bulanan, dan alur pelepasan aset. |
| Akuntansi Lengkap & Konsolidasi | `custom_accounting_full` | Umum | — | Produksi | Otomasi antar-perusahaan, eliminasi, konsolidasi, batas kredit, tahun fiskal, dan follow-up. |
| Jurnal & Pembayaran Berulang | `custom_accounting_recurring` | Umum | — | Produksi | Template jurnal dan pembayaran berulang dengan penjadwalan otomatis. |
| Mesin Laporan Keuangan | `custom_accounting_reports` | Umum, dikonfigurasi | ARKA-AIM, Levi's | Produksi | P&L, Neraca, Buku Besar, Neraca Saldo, Arus Kas, Aging, Buku Kas/Bank, dan laporan pajak. |
| Aset dari Penerimaan Barang | `custom_asset_from_receipt` | Umum, dikonfigurasi | ARKA-AIM | Beta | Mengubah massal produk ber-serial yang diterima menjadi Aset Tetap dan Aset Sewa. |
| Impor Rekening Koran | `custom_bank_import` | Umum, dikonfigurasi | Levi's, ARKA-AIM | Produksi | Impor mutasi bank berbasis template CSV dan kerangka adapter API H2H bank. |
| Pelaporan ESG | `custom_esg` | Umum | — | Beta | Metrik lingkungan, sosial, dan tata kelola untuk POJK 51/2017. |
| Anggaran Biaya Divisi | `custom_finance_budget` | Umum, dikonfigurasi | Finance Portal | Beta | Anggaran biaya per divisi/periode yang disinkronkan dari SAP. |
| Finance Portal | `custom_finance_portal` | Umum, dikonfigurasi | Finance Portal | Produksi | Uang muka, reimbursement, tagihan vendor, dan perjalanan dinas di atas SAP — tanpa posting GL sendiri. |
| Integrasi Finance Portal ↔ SAP | `custom_finance_portal_sap` | Umum, dikonfigurasi | Finance Portal | Beta | Adapter jembatan, push asinkron, sinkronisasi master data, webhook status, dan log sinkronisasi. |
| SSO Finance Portal | `custom_finance_portal_sso` | Umum, dikonfigurasi | Finance Portal | Produksi | Login Keycloak dan pemetaan peran ke grup, memisahkan karyawan dari vendor. |
| Laporan per Unit Operasional | `custom_operating_unit_reports` | Umum | — | Produksi | Membatasi laporan keuangan pada unit yang boleh dibaca pengguna — laporan menyusun SQL sendiri sehingga aturan akses Odoo tidak berlaku di sana. |
| Biaya Admin Pembayaran | `custom_payment_admin_fee` | Umum, dikonfigurasi | Levi's | Produksi | Baris biaya admin/bank multi-COA pada wizard Register Payment. |
| Payment Gateway Indonesia | `custom_payment_id` | Umum | — | Beta | Adapter Midtrans, Xendit, dan DOKU untuk payment.provider. |
| Metode Pembayaran GIRO & Transfer | `custom_payment_methods_id` | Umum, dikonfigurasi | Levi's | Kerangka | Menambahkan GIRO dan BANK TRANSFER sebagai metode pembayaran pada jurnal bank. |
| Voucher & Kuitansi Pembayaran | `custom_payment_voucher` | Umum, dikonfigurasi | Levi's | Produksi | Cetak bukti kas keluar dan kuitansi pada pembayaran, lengkap dengan terbilang. |
| Uang Muka & Kas Kecil | `custom_petty_cash` | Umum, dikonfigurasi | ARKA-AIM, Levi's | Produksi | Permintaan bertipe, persetujuan Finance, pencairan bank, realisasi, dan Kartu Uang Muka. |
| Bagan Akun Erajaya | `l10n_erajaya` | Umum, dikonfigurasi | ARKA-AIM, Levi's | Kerangka | CoA Indonesia 10 digit khas Erajaya beserta pajak PPN/PPh, jurnal, dan posisi fiskal. |
| Bagan Akun PSAK | `l10n_id_psak_custom` | Umum | — | Kerangka | CoA 5 digit selaras PSAK dengan pajak PPN dan posisi fiskal Indonesia. |
| Register Aset Drone ARKA-AIM | `custom_arka_aim_asset_register` | Khusus brand | ARKA-AIM | Beta | Subledger aset tetap per unit drone, direkonsiliasi ke saldo awal GL 31 Mei 2026. |
| Saldo Awal ARKA-AIM | `custom_arka_aim_opening_balance` | Khusus brand | ARKA-AIM | Produksi | Saldo awal perusahaan AIM dan ARKA per 31 Mei 2026. |
| Seed CoA ARKA-AIM | `custom_arka_aim_seed` | Khusus brand | ARKA-AIM | Produksi | Bagan akun, pajak, dan posisi fiskal awal untuk basis data pengembangan ARKA-AIM. |
| Header Valuta Asing ARKA-AIM | `custom_arka_fx_header` | Khusus brand | ARKA-AIM | Beta | Menampilkan total mata uang asing dan kurs yang dipakai di header faktur serta popup pembayaran. |
| Akun Revaluasi Aset Levi's | `custom_levis_asset_accounts` | Khusus brand | Levi's | Beta | Enam kategori aset tetap EBR beserta akun revaluasi IAS 16, resolusi kode akun per perusahaan. |
| Rekonsiliasi Bank POS Levi's | `custom_levis_bank_reconcile` | Khusus brand | Levi's | Produksi | Mencocokkan settlement bank dengan piutang tender POS per toko, bersih dari MDR. |
| Persetujuan Perubahan Kategori Produk | `custom_levis_categ_approval` | Khusus brand | Levi's | Produksi | Perubahan kategori produk tidak lagi diam-diam — harus lewat persetujuan Finance, dengan koreksi GL. |
| Migrasi Unit Operasional Levi's | `custom_levis_operating_unit` | Khusus brand | Levi's | Produksi | Mengangkat dimensi Operating Unit Levi's yang sudah ada menjadi master unit platform — tanpa mengubah kode gudang, nama akun analitik, jurnal, maupun POS. |

### Yang bersifat khusus per-brand

Modul berikut berada di `addons/_tenants/` dan **tidak dapat dipakai ulang apa adanya** oleh tenant lain:

- **Register Aset Drone ARKA-AIM** (`custom_arka_aim_asset_register`) — ARKA-AIM. Subledger aset tetap per unit drone, direkonsiliasi ke saldo awal GL 31 Mei 2026.
- **Saldo Awal ARKA-AIM** (`custom_arka_aim_opening_balance`) — ARKA-AIM. Saldo awal perusahaan AIM dan ARKA per 31 Mei 2026.
- **Seed CoA ARKA-AIM** (`custom_arka_aim_seed`) — ARKA-AIM. Bagan akun, pajak, dan posisi fiskal awal untuk basis data pengembangan ARKA-AIM.
- **Header Valuta Asing ARKA-AIM** (`custom_arka_fx_header`) — ARKA-AIM. Menampilkan total mata uang asing dan kurs yang dipakai di header faktur serta popup pembayaran.
- **Akun Revaluasi Aset Levi's** (`custom_levis_asset_accounts`) — Levi's. Enam kategori aset tetap EBR beserta akun revaluasi IAS 16, resolusi kode akun per perusahaan.
- **Rekonsiliasi Bank POS Levi's** (`custom_levis_bank_reconcile`) — Levi's. Mencocokkan settlement bank dengan piutang tender POS per toko, bersih dari MDR.
- **Persetujuan Perubahan Kategori Produk** (`custom_levis_categ_approval`) — Levi's. Perubahan kategori produk tidak lagi diam-diam — harus lewat persetujuan Finance, dengan koreksi GL.
- **Migrasi Unit Operasional Levi's** (`custom_levis_operating_unit`) — Levi's. Mengangkat dimensi Operating Unit Levi's yang sudah ada menjadi master unit platform — tanpa mengubah kode gudang, nama akun analitik, jurnal, maupun POS.

Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan data sendiri:

- **Aset Tetap & Penyusutan** (`custom_accounting_asset`) — sudah membawa data atau profil untuk ARKA-AIM, Levi's.
- **Mesin Laporan Keuangan** (`custom_accounting_reports`) — sudah membawa data atau profil untuk ARKA-AIM, Levi's.
- **Aset dari Penerimaan Barang** (`custom_asset_from_receipt`) — sudah membawa data atau profil untuk ARKA-AIM.
- **Impor Rekening Koran** (`custom_bank_import`) — sudah membawa data atau profil untuk Levi's, ARKA-AIM.
- **Anggaran Biaya Divisi** (`custom_finance_budget`) — sudah membawa data atau profil untuk Finance Portal.
- **Finance Portal** (`custom_finance_portal`) — sudah membawa data atau profil untuk Finance Portal.
- **Integrasi Finance Portal ↔ SAP** (`custom_finance_portal_sap`) — sudah membawa data atau profil untuk Finance Portal.
- **SSO Finance Portal** (`custom_finance_portal_sso`) — sudah membawa data atau profil untuk Finance Portal.
- **Biaya Admin Pembayaran** (`custom_payment_admin_fee`) — sudah membawa data atau profil untuk Levi's.
- **Metode Pembayaran GIRO & Transfer** (`custom_payment_methods_id`) — sudah membawa data atau profil untuk Levi's.
- **Voucher & Kuitansi Pembayaran** (`custom_payment_voucher`) — sudah membawa data atau profil untuk Levi's.
- **Uang Muka & Kas Kecil** (`custom_petty_cash`) — sudah membawa data atau profil untuk ARKA-AIM, Levi's.
- **Bagan Akun Erajaya** (`l10n_erajaya`) — sudah membawa data atau profil untuk ARKA-AIM, Levi's.

# 4. Perpajakan Indonesia

6 modul menangani kewajiban perpajakan Indonesia, seluruhnya dinilai *Produksi* kecuali satu jembatan kecil. Ini domain dengan kepadatan regulasi tertinggi di platform, dan karena itu paling sering menyentuh peraturan yang berubah.

## 4.1 Coretax DJP

`custom_coretax` mengimplementasikan permukaan kepatuhan Coretax sesuai PER-11/PJ/2025: siklus **NSFP** pada jurnal, ekspor dan impor XML untuk tujuh jenis dokumen utama, catatan **Bukti Potong**, serta penyimpanan **Sertifikat Elektronik** (.p12) terenkripsi. Kata sandi sertifikat tidak pernah disimpan; setiap akses sertifikat menulis baris audit.

Alur kerjanya mengikuti kenyataan operasional: operator menghasilkan XML, mengunggahnya ke portal Coretax, lalu mengimpor kembali XML tanggapan DJP. Sebuah abstraksi adapter memungkinkan jalur host-to-host menggantikan unggah manual di kemudian hari tanpa mengubah alur penggunanya — `custom_coretax_pajakku` sudah mengisi jalur itu untuk Pajakku sebagai ASPP.

**Bukti Potong Unifikasi** (`custom_coretax_bupot`) menangani PPh 22, 23, 4(2), 15, dan 26 dengan ekspor XML dan pembaruan nomor dari DJP.

**Ekspor template Coretax** (`custom_coretax_export`) menghasilkan workbook yang sesuai format impor DJP: e-Faktur Keluaran (FK/OF), Retur Masukan, serta Bupot Unifikasi dan PPh 21. Ini yang dipakai sehari-hari oleh dua tenant live.

## 4.2 Pemotongan PPh

Dua modul menangani PPh, dan pembagian tugasnya perlu dipahami karena keduanya pernah membukukan hal yang sama dua kali.

`custom_tax_id` adalah mesin utama: pemotongan PPh 23, 4(2), dan 26, PPN **DPP Nilai Lain** sesuai PMK 131/2024, serta Faktur Pengganti. Ia menyimpan kategori dan aturan pemotongan, dan menghasilkan jurnal pemotongan saat tagihan dibukukan. Registri kode objek pajak berisi 107 kategori yang dapat dipetakan ke akun per tenant.

`custom_pph_witholding` adalah mesin generik yang lebih tua — registri tarif, perhitungan, dan log penerapan — yang juga terpakai oleh payroll untuk PPh 21.

> Peringatan operasional yang layak diketahui: ketika pajak PPh dikonfigurasi sebagai pajak native Odoo **dan** dijalankan lewat mesin pemotongan sekaligus, jurnal terbentuk dua kali. Ini pernah terjadi di produksi dan sudah diperbaiki; konfigurasi tenant baru harus memilih salah satu jalur, bukan keduanya.

Satu jembatan kecil, `custom_accounting_recurring_tax_id`, membawa kode objek PPh dari template tagihan berulang ke tagihan yang dihasilkannya. Ia terpasang otomatis hanya ketika kedua modul induknya ada.

## 4.3 Hubungan dengan bagan akun

Modul perpajakan tidak membawa akun sendiri. Akun PPh dan PPN berasal dari template bagan akun yang dipilih tenant — `l10n_erajaya` untuk tenant grup, `l10n_id_psak_custom` untuk yang lain — dan dipetakan lewat konfigurasi. Itulah sebabnya kedua template itu tercatat di Bab 3 dengan rujukan silang ke bab ini, bukan sebaliknya.

## 4.4 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Coretax DJP | `custom_coretax` | Umum | — | Produksi | NSFP, ekspor/impor XML e-Faktur, Bukti Potong, dan penyimpanan Sertifikat Elektronik terenkripsi. |
| Bukti Potong Unifikasi | `custom_coretax_bupot` | Umum | — | Produksi | Bupot PPh 22/23/4(2)/15/26 dengan ekspor XML dan pembaruan nomor DJP. |
| Ekspor Template Coretax | `custom_coretax_export` | Umum, dikonfigurasi | ARKA-AIM, Levi's | Produksi | Workbook sesuai format DJP: e-Faktur FK/OF, Retur Masukan, Bupot Unifikasi dan PPh 21. |
| Adapter Pajakku (ASPP) | `custom_coretax_pajakku` | Umum | — | Produksi | Adapter host-to-host ke Pajakku sebagai Penyedia Jasa Aplikasi Perpajakan. |
| Mesin Pemotongan PPh | `custom_pph_witholding` | Umum | — | Produksi | Registry tarif, perhitungan, dan log penerapan pemotongan PPh. |
| Pajak Indonesia (PPh & DPP Nilai Lain) | `custom_tax_id` | Umum, dikonfigurasi | ARKA-AIM, Levi's | Produksi | Pemotongan PPh 23/4(2)/26, PPN DPP Nilai Lain (PMK 131/2024), dan Faktur Pengganti. |

### Yang bersifat khusus per-brand

Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan data sendiri:

- **Ekspor Template Coretax** (`custom_coretax_export`) — sudah membawa data atau profil untuk ARKA-AIM, Levi's.
- **Pajak Indonesia (PPh & DPP Nilai Lain)** (`custom_tax_id`) — sudah membawa data atau profil untuk ARKA-AIM, Levi's.

# 5. SDM & Payroll

13 modul, seluruhnya berlaku **umum** — tidak ada satu pun yang terikat pada satu brand. Domain ini adalah contoh paling murni dari klaim reuse platform: apa pun brandnya, aturan ketenagakerjaan Indonesia sama.

## 5.1 Payroll Indonesia

`custom_hr_payroll_id` adalah inti domain ini: **PPh 21 dengan skema TER** dan perhitungan progresif tahunan, **BPJS Kesehatan dan Ketenagakerjaan**, PTKP, THR, serta **SPT 1721 A1**. Perhitungan pajaknya berbagi registri tarif dengan mesin pemotongan PPh di domain perpajakan, sehingga tarif tidak dipelihara di dua tempat.

## 5.2 Kehadiran, cuti, dan waktu

**Absensi** (`custom_attendance`) menyediakan check-in dengan **geofence**, portal kiosk untuk lokasi tanpa perangkat pribadi, alur persetujuan, dan lembur yang mengalir langsung ke payroll sebagai komponen upah — bukan sebagai catatan terpisah yang harus dimasukkan ulang.

**Cuti Indonesia** (`custom_hr_leave_id`) mengikuti UU Cipta Kerja, termasuk cuti haid, kalender hari libur nasional, dan kebijakan carry-over saldo antar tahun.

**Perencanaan shift** (`custom_planning`) menutup penjadwalan sumber daya untuk tim yang bekerja bergilir.

## 5.3 Biaya, rekrutmen, dan pengembangan

**Klaim biaya** (`custom_expenses`) memakai OCR berbantuan AI untuk membaca struk, mendukung kartu korporat dan klaim kilometer, dan berjalan di atas mesin persetujuan bersama.

**Rekrutmen** (`custom_recruitment_id`) menerima lamaran dari job board lewat webhook, dengan retensi data pelamar yang sadar UU PDP — sebuah kewajiban yang sering terlewat, karena berkas lamaran adalah data pribadi yang tidak boleh disimpan tanpa batas.

Melengkapinya: **program referral** dengan buku besar imbalan, **penilaian kinerja** dengan template dan umpan balik 360 derajat, serta **pembelajaran daring** dengan sertifikat berbahasa Indonesia dan kohort peserta.

## 5.4 Fasilitas dan operasional kantor

Tiga modul menangani hal-hal yang bukan HR inti tetapi jatuh ke meja HR: **armada kendaraan** dengan pengingat STNK dan KIR serta pencatatan BBM, **katering** dengan tautan ke layanan pesan-antar dan potongan payroll yang benar-benar terbukukan, dan **manajemen tamu** di lobi dengan notifikasi ke host.

## 5.5 Identitas

`custom_hr_sso_keycloak` menghubungkan login karyawan ke Keycloak dan menyinkronkan data `hr.employee` dari klaim token serta HC API. Ia bekerja berpasangan dengan `authenticate_keycloak` di domain Integrasi, yang menyediakan alur OAuth2-nya.

## 5.6 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Absensi & Lembur | `custom_attendance` | Umum | — | Produksi | Check-in geofence, portal kiosk, alur persetujuan, dan lembur yang mengalir ke payroll. |
| Pembelajaran Daring | `custom_elearning` | Umum | — | Beta | Sertifikat berbahasa Indonesia, kohort peserta, dan integrasi penilaian kinerja. |
| Klaim Biaya Karyawan | `custom_expenses` | Umum | — | Produksi | Ekstraksi struk dengan OCR AI, persetujuan, kartu korporat, dan klaim kilometer. |
| Armada Kendaraan | `custom_fleet_id` | Umum | — | Produksi | Pengingat STNK dan KIR, pencatatan BBM, dan penugasan pengemudi. |
| Front Desk & Tamu | `custom_frontdesk` | Umum | — | Beta | Manajemen kunjungan tamu dengan notifikasi ke host dan jejak audit PDP. |
| Penilaian Kinerja | `custom_hr_appraisal` | Umum | — | Beta | Review berbasis template, umpan balik 360 derajat, dan penilaian kompetensi. |
| Cuti Indonesia | `custom_hr_leave_id` | Umum | — | Produksi | Cuti sesuai UU Cipta Kerja, cuti haid, hari libur nasional, dan carry-over saldo. |
| Payroll Indonesia | `custom_hr_payroll_id` | Umum | — | Produksi | PPh 21 TER dan progresif tahunan, BPJS Kesehatan/Ketenagakerjaan, PTKP, THR, SPT 1721 A1. |
| Program Referral Karyawan | `custom_hr_referral` | Umum | — | Beta | Pelacakan kandidat rujukan beserta buku besar imbalannya. |
| SSO Karyawan (Keycloak) | `custom_hr_sso_keycloak` | Umum | — | Produksi | SSO Keycloak yang menautkan dan menyinkronkan data karyawan dari klaim token dan HC API. |
| Katering & Makan Siang | `custom_lunch` | Umum | — | Beta | Tautan GoFood/GrabFood/ShopeeFood, potongan payroll nyata, dan penanda halal. |
| Perencanaan Shift | `custom_planning` | Umum | — | Beta | Perencanaan sumber daya dan penjadwalan shift tim. |
| Rekrutmen Indonesia | `custom_recruitment_id` | Umum | — | Produksi | Ingest lowongan dari job board via webhook dan retensi data pelamar sadar-PDP. |

### Yang bersifat khusus per-brand

Tidak ada. Seluruh modul di domain ini berlaku umum untuk tenant mana pun, tanpa data atau konfigurasi khusus brand.

# 6. Gudang & Inventori

17 modul membentuk sebuah **Warehouse Management System lengkap** di atas Odoo Community. Ini kelompok modul paling matang di platform: hampir seluruhnya dinilai *Produksi*, dan sebagian besar sudah diuji dalam skenario proof-of-concept ujung ke ujung.

## 6.1 Mesin gudang

**Putaway** (`custom_wms_putaway`) adalah mesin penempatan bertingkat yang dapat dikonfigurasi: aturan berjenjang memutuskan bin mana yang diusulkan untuk setiap baris penerimaan, dan usulannya diberi peringkat, bukan sekadar diambil yang pertama cocok.

**Slotting bergaya SAP** (`custom_wms_sap_slotting`) menambahkan dua dimensi yang tidak dimodelkan mesin dasar: Storage Type (*Lagertyp*) dan Storage Section (*Lagerbereich*), masing-masing dengan urutan pencarian sendiri. Gudang yang bermigrasi dari SAP WM mengharapkan pencarian berjalan dalam urutan itu. Seluruhnya ditambahkan lewat pewarisan, sehingga tenant yang tidak memakai slotting SAP tidak perlu ikut memutakhirkan modul putaway bersama.

**QC penerimaan** (`custom_wms_inbound_qc`) memasang gerbang karantina: barang masuk tidak dapat direservasi sampai lolos QC, dan barang tak dikenal diregistrasi alih-alih ditolak diam-diam.

**Cycle count** (`custom_wms_cycle_count`) menjalankan stock opname berbasis rencana dengan persetujuan selisih. **Transfer Order Engine** (`custom_wms_to_engine`) memicu perpindahan internal berdasarkan aturan: batas stok minimum, kedaluwarsa, dan konsolidasi.

## 6.2 Perangkat genggam

`custom_wms_hht` adalah aplikasi handheld yang benar-benar memindahkan stok — menggantikan shell demo yang hanya *mencatat* pemindaian. Antarmukanya berbasis tugas dengan lencana antrean kerja per modul: terima, putaway, pick dan pack, package, count, bin-to-bin, dan pemeriksaan stok baca-saja.

Ia sengaja dipisahkan dari `custom_hht_bridge` yang menyediakan shell PWA, API REST ber-HMAC per perangkat, dan antrean offline. Alasannya operasional: jembatan itu terpasang di basis data produksi ARKA yang tidak memiliki satu pun model WMS, dan tidak boleh ikut dipaksa naik versi untuk fitur khusus gudang.

Antrean offline bersifat idempoten pada pasangan `(device_id, client_id)`, sehingga pemindaian yang terkirim ulang setelah koneksi pulih tidak menggandakan pergerakan stok.

## 6.3 Barcode dan penerimaan

**Barcode** (`custom_barcode`) menyediakan pemindaian scan-in dan scan-out setara Enterprise, termasuk nomenklatur GS1. **Barcode produk ganda** (`custom_product_barcode`) mengizinkan beberapa barcode alternatif untuk satu varian — satu varian, satu stok, semuanya dapat dipindai.

**Kelengkapan penerimaan** (`custom_wms_receiving_ext`) menutup celah yang halus tetapi mahal: tanggal kedaluwarsa GS1 yang sebelumnya diurai lalu dibuang kini benar-benar ditulis ke lot, nomor batch pemasok disimpan sehingga penarikan produk dapat ditelusuri ke batch pemasoknya, dan pemindaian IMEI polos tidak lagi jatuh sebagai "tidak ditemukan". Ditambah wizard impor penerimaan massal dari CSV/XLSX dengan template kosong yang bisa diunduh.

## 6.4 Dokumen dan laporan

**Dokumen dan label** (`custom_wms_docs`) menghasilkan picking list, packing list, lembar scan, dan label harga.

**Paket laporan** (`custom_wms_reports`) menyediakan enam analisis — retur pembelian, ringkasan stok dengan nilai, stock take, spot check, transfer, dan scrap. Seluruh model analisisnya adalah **SQL view baca-saja**, sehingga tidak mungkin menyimpang dari data operasional yang diringkasnya. Setiap laporan mengekspor ke **XLSX dengan barcode Code128 tertanam** di dua tingkat — satu untuk dokumen, satu untuk baris — sehingga lembar kerjanya tetap dapat dipindai di luar Odoo.

## 6.5 Pembelian dan antar-perusahaan

**Retur pembelian** (`custom_po_return`) menangani retur ke vendor berbasis kuantitas dengan alokasi FIFO lintas PO dan penerimaan, beserta nota kredit otomatis. **Pengadaan antar-perusahaan** (`custom_intercompany_procurement`) mencerminkan purchase order dan pengiriman antar perusahaan sekelompok secara otomatis — pola yang lahir dari kebutuhan grup Erajaya, tetapi ditulis generik.

**Validasi penerimaan asinkron** (`custom_receipt_async`) memindahkan validasi penerimaan berukuran besar ke antrean latar belakang, sehingga operator tidak menunggu.

> Satu modul di domain ini, `custom_stock_delivery_report_fix`, **sengaja dinonaktifkan**. Ia adalah tambalan untuk template surat jalan bawaan Odoo dan hanya diaktifkan bila cacat itu muncul kembali. Ia tetap dihitung agar total modul dapat direkonsiliasi.

## 6.6 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Pemindaian Barcode Gudang | `custom_barcode` | Umum | — | Produksi | Scan-in dan scan-out mobile untuk pengiriman dan penerimaan, setara Enterprise. |
| Jembatan Handheld Terminal | `custom_hht_bridge` | Umum | — | Produksi | Shell PWA, REST API ber-HMAC per perangkat, dan sinkronisasi offline idempoten. |
| Pengadaan Antar-Perusahaan | `custom_intercompany_procurement` | Umum | — | Beta | Cerminan otomatis purchase order dan pengiriman antar perusahaan sekelompok. |
| Retur Pembelian | `custom_po_return` | Umum, dikonfigurasi | Levi's | Produksi | Retur ke vendor berbasis kuantitas dengan alokasi FIFO lintas PO dan nota kredit otomatis. |
| Barcode Produk Ganda | `custom_product_barcode` | Umum | — | Beta | Beberapa barcode alternatif per varian produk — satu varian, satu stok, semua terpindai. |
| Validasi Penerimaan Asinkron | `custom_receipt_async` | Umum | — | Beta | Validasi penerimaan barang berukuran besar di latar belakang lewat antrean pekerjaan. |
| Perbaikan Surat Jalan | `custom_stock_delivery_report_fix` | Umum | — | Nonaktif | Tambalan template surat jalan bawaan. Sengaja dinonaktifkan. |
| Stock Opname Berkala | `custom_wms_cycle_count` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Cycle count berbasis rencana dengan alur persetujuan selisih. |
| Dokumen & Label Gudang | `custom_wms_docs` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Picking list, packing list, lembar scan barcode, dan label harga produk. |
| Aplikasi Handheld Gudang | `custom_wms_hht` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Antarmuka handheld berbasis tugas: terima, putaway, pick, pack, count, bin-to-bin. |
| QC Penerimaan Barang | `custom_wms_inbound_qc` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Karantina inbound, gerbang QC, stok belum bisa direservasi, dan registrasi item tak dikenal. |
| Integrasi WMS Eksternal | `custom_wms_integration` | Umum | — | Produksi | REST masuk, adapter keluar, dan outbox event untuk host WMS/SAP. |
| Mesin Putaway | `custom_wms_putaway` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Mesin penempatan bertingkat yang dapat dikonfigurasi, bergaya ZWME001. |
| Kelengkapan Penerimaan Barang | `custom_wms_receiving_ext` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Kedaluwarsa GS1, nomor batch pemasok pada lot, dan impor penerimaan dari CSV/XLSX. |
| Paket Laporan Gudang | `custom_wms_reports` | Umum, dikonfigurasi | JDS Warehouse, Levi's | Produksi | Retur pembelian, ringkasan stok (qty dan nilai), stock take, spot check, dan transfer. |
| Slotting Bergaya SAP | `custom_wms_sap_slotting` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Pencarian lokasi dua dimensi ala SAP (Lagertyp × Lagerbereich). |
| Mesin Transfer Order | `custom_wms_to_engine` | Umum, dikonfigurasi | JDS Warehouse | Produksi | Transfer internal berbasis aturan: batas stok minimum, kedaluwarsa, dan konsolidasi. |

### Yang bersifat khusus per-brand

Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan data sendiri:

- **Retur Pembelian** (`custom_po_return`) — sudah membawa data atau profil untuk Levi's.
- **Stock Opname Berkala** (`custom_wms_cycle_count`) — sudah membawa data atau profil untuk JDS Warehouse.
- **Dokumen & Label Gudang** (`custom_wms_docs`) — sudah membawa data atau profil untuk JDS Warehouse.
- **Aplikasi Handheld Gudang** (`custom_wms_hht`) — sudah membawa data atau profil untuk JDS Warehouse.
- **QC Penerimaan Barang** (`custom_wms_inbound_qc`) — sudah membawa data atau profil untuk JDS Warehouse.
- **Mesin Putaway** (`custom_wms_putaway`) — sudah membawa data atau profil untuk JDS Warehouse.
- **Kelengkapan Penerimaan Barang** (`custom_wms_receiving_ext`) — sudah membawa data atau profil untuk JDS Warehouse.
- **Paket Laporan Gudang** (`custom_wms_reports`) — sudah membawa data atau profil untuk JDS Warehouse, Levi's.
- **Slotting Bergaya SAP** (`custom_wms_sap_slotting`) — sudah membawa data atau profil untuk JDS Warehouse.
- **Mesin Transfer Order** (`custom_wms_to_engine`) — sudah membawa data atau profil untuk JDS Warehouse.

# 7. Penjualan, Retail & POS

11 modul. Domain ini menopang tenant retail yang sudah **live** — Levi's / PT Era Busana Retailindo — dan karena itu berisi jalur data dengan volume terbesar di platform.

## 7.1 Jalur impor data retail

Toko Levi's berjalan di atas **XStore**, yang tidak memiliki konektor. Yang ada adalah ekspor laporan berformat XLSX dan CSV: master material, on-hand, detail penjualan, dan settlement tender.

`custom_retail_import` adalah mesin ingest untuk itu — **sepenuhnya generik**. Sebuah profil impor mendeklarasikan format, baris header, pemetaan kolom, dan namespace; wizard melakukan pratinjau kering dan menyaring duplikat lewat SHA256; eksekutor memuat secara idempoten lewat external ID. Yang khusus Levi's hanyalah profil-profil di dalam datanya. Modul ini punya nomor versi tertinggi di seluruh platform, yang mencerminkan berapa banyak kasus tepi data retail nyata yang sudah ditemui dan ditangani.

Tiga modul melengkapinya:

- **API master produk** (`custom_retail_import_api`) menerima dorongan JSON dari MDM HUB alih-alih menarik laporan terjadwal. Ia dipisahkan dari mesin utama karena Odoo membangun peta rute per basis data: menaruh controller di modul bersama akan mengekspos `/api/mdm/*` di semua basis data Levi's sekaligus. Memasangnya hanya di tempat yang diinginkan membuat rute itu **tidak ada** di tempat lain — jaminan yang lebih kuat daripada flag runtime.
- **Jembatan POS** (`custom_retail_import_pos`) membukukan penjualan dan retur POS hasil impor dengan akun pajak, diskon, dan retur yang diambil dari berkas sumbernya, bukan dari default.
- **Rekonsiliasi** (`custom_retail_import_recon`) mencocokkan per transaksi antara berkas penjualan dan apa yang benar-benar terbukukan di Odoo.

> Pembukuan hasil impor dikendalikan **per parameter, per basis data** dan mati secara bawaan. Ini disengaja: sebuah basis data pengembangan yang menerima berkas produksi tidak boleh ikut membukukan jurnal. Mengaktifkannya adalah keputusan sadar per lingkungan.

## 7.2 POS, e-commerce, dan langganan

**POS Indonesia** (`custom_pos_id`) menambahkan QRIS, pembulatan rupiah, dan struk elektronik lewat WhatsApp atau SMS.

**eCommerce Indonesia** (`custom_ecommerce`) menyediakan registri kurir lokal — JNE, JNT, SiCepat, AnterAja, Pos — dan checkout Midtrans/Xendit, ditambah pelacakan keranjang terbengkalai. **Storefront API** (`custom_storefront_api`) mengekspos REST JSON headless untuk storefront Next.js: katalog, keranjang, autentikasi JWT, checkout, bukti pembayaran, dan wishlist. Keduanya sudah membawa konfigurasi untuk GentleWoman, tenant di luar grup Erajaya.

**CRM** (`custom_crm`) menutup selisih Enterprise dengan penambangan prospek, skoring prediktif, pengayaan data, formulir web, dan otomasi. **Langganan** (`custom_subscription`) menangani penagihan berulang dengan analitik MRR/LTV dan prediksi churn.

## 7.3 Lokalisasi Levi's

`custom_levis_localization` adalah modul khusus brand terbesar di platform, dengan 26 berkas model. Isinya adalah kumpulan aturan yang benar-benar hanya berlaku di EBR: HS Code pada produk, batas kuantitas penerimaan, keputusan untuk **tidak membukukan jurnal persediaan saat penerimaan barang**, jurnal billing, voucher pembayaran, pemetaan MID bank, dan mesin kliring piutang POS per toko.

Ia tidak dapat dipakai ulang apa adanya — dan memang tidak dimaksudkan demikian. Yang generik dari pekerjaan Levi's sudah dipromosikan keluar: mesin impor retail, retur pembelian, biaya admin pembayaran, dan voucher pembayaran semuanya hidup di `ee_gap/` dan tersedia untuk tenant lain.

## 7.4 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| CRM & Prospek | `custom_crm` | Umum | — | Produksi | Penambangan prospek, skoring prediktif, pengayaan data, formulir web, dan otomasi. |
| eCommerce Indonesia | `custom_ecommerce` | Umum, dikonfigurasi | GentleWoman | Beta | Registry kurir (JNE, JNT, SiCepat, AnterAja, Pos) dan checkout Midtrans/Xendit. |
| Unit Operasional di Kasir | `custom_operating_unit_pos` | Umum | — | Produksi | Membatasi POS, sesi, dan pesanan per toko, serta membubuhkan unit pada setiap baris jurnal penutupan sesi. |
| POS Indonesia | `custom_pos_id` | Umum | — | Beta | QRIS, pembulatan rupiah, dan struk elektronik via WhatsApp/SMS. |
| Impor Data Retail | `custom_retail_import` | Umum, dikonfigurasi | Levi's | Produksi | Ingest Excel/CSV dan SFTP untuk master serta transaksi retail dari XStore. |
| API Master Produk (MDM) | `custom_retail_import_api` | Umum, dikonfigurasi | Levi's | Produksi | REST masuk untuk feed master produk mendekati real-time dari MDM HUB. |
| Jembatan POS Impor Retail | `custom_retail_import_pos` | Umum, dikonfigurasi | Levi's | Kerangka | Membukukan penjualan dan retur POS hasil impor dengan akun pajak, diskon, dan retur dari sumbernya. |
| Rekonsiliasi X-Store vs Odoo | `custom_retail_import_recon` | Umum, dikonfigurasi | Levi's | Beta | Pencocokan per transaksi antara berkas penjualan X24DN dan yang benar-benar terbukukan. |
| API Storefront Headless | `custom_storefront_api` | Umum, dikonfigurasi | GentleWoman | Beta | REST JSON untuk storefront Next.js: katalog, keranjang, autentikasi JWT, checkout. |
| Langganan Berulang | `custom_subscription` | Umum | — | Beta | Penagihan berulang, analitik MRR/LTV, dan prediksi churn berbasis AI. |
| Lokalisasi Levi's | `custom_levis_localization` | Khusus brand | Levi's | Produksi | Kustomisasi tenant Levi's: HS Code, batas qty terima, jurnal billing, voucher pembayaran, kliring POS. |

### Yang bersifat khusus per-brand

Modul berikut berada di `addons/_tenants/` dan **tidak dapat dipakai ulang apa adanya** oleh tenant lain:

- **Lokalisasi Levi's** (`custom_levis_localization`) — Levi's. Kustomisasi tenant Levi's: HS Code, batas qty terima, jurnal billing, voucher pembayaran, kliring POS.

Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan data sendiri:

- **eCommerce Indonesia** (`custom_ecommerce`) — sudah membawa data atau profil untuk GentleWoman.
- **Impor Data Retail** (`custom_retail_import`) — sudah membawa data atau profil untuk Levi's.
- **API Master Produk (MDM)** (`custom_retail_import_api`) — sudah membawa data atau profil untuk Levi's.
- **Jembatan POS Impor Retail** (`custom_retail_import_pos`) — sudah membawa data atau profil untuk Levi's.
- **Rekonsiliasi X-Store vs Odoo** (`custom_retail_import_recon`) — sudah membawa data atau profil untuk Levi's.
- **API Storefront Headless** (`custom_storefront_api`) — sudah membawa data atau profil untuk GentleWoman.

# 8. Layanan, Proyek & Sewa

15 modul yang menopang dua lini berbeda: **penyewaan aset** untuk ARKA-AIM, dan **manajemen delivery** untuk tim VAS PMO Erajaya sendiri.

## 8.1 Penyewaan aset

`custom_rental` menangani siklus sewa penuh: tarif bertingkat, jadwal, BAST, denda keterlambatan, portal pelanggan, dan pengiriman stok. Ia dibangun untuk bisnis sewa dan pertunjukan drone ARKA-AIM, tetapi ditulis generik.

Tiga modul memperluasnya:

- **Paket sewa via BOM** membundel drone beserta perangkat pendukungnya sebagai kit, dan mengisi baris BAST otomatis saat pickup dan pengembalian.
- **Penagihan sewa** membuat faktur saat barang kembali — biaya sewa, denda keterlambatan, dan kerusakan dalam satu dokumen.
- **Pemeriksaan kualitas sewa** membuat quality check otomatis saat pengembalian dan menautkan aset sewa ke equipment pemeliharaan, sehingga riwayat kerusakan satu unit terbaca sebagai satu garis waktu.

**Laporan operasional armada** (`custom_ops_reports`) melengkapinya dengan opname aset, pergerakan per event, suku cadang, kesehatan pemeliharaan, dan riwayat perbaikan.

**BAST** sendiri adalah modul inti (`custom_bast`): dokumen serah terima generik dengan tanda tangan ganda dan jejak audit, dapat dibuat langsung dari Sales Order lewat `custom_sale_bast`.

## 8.2 Manajemen delivery — VAS PMO

Empat modul membentuk aplikasi PMO yang dipakai tim Value-Added Services Erajaya untuk mengelola pekerjaannya sendiri:

- **Portofolio proyek** (`custom_project_portfolio`) memodelkan **vertikal brand** sebagai sumbu utama — setiap pekerjaan menggantung pada satu brand Erajaya — ditambah portofolio, sprint mingguan, dan tahap Hold serta Waiting-User-Verification yang menghentikan jam SLA.
- **Change Request** (`custom_project_cr`) memperlakukan CR sebagai record tersendiri, bukan sebagai task biasa: triase, analisis dampak, persetujuan berjenjang, dan penomoran resmi.
- **Notifikasi** (`custom_project_notify`) mengirim pemberitahuan berbasis aturan ke WhatsApp, email, dan Odoo lewat antrean outbox.
- **API PMO** (`custom_project_api`) menyediakan permukaan REST ber-JWT dan HMAC untuk aplikasi Next.js di depannya.

Keempatnya adalah satu-satunya modul di platform yang dokumen pengetahuannya sudah berstatus **reviewed**.

## 8.3 Layanan pelanggan dan lapangan

**Helpdesk** (`custom_helpdesk`) menyediakan alur tiket dengan SLA, eskalasi, dan portal pelanggan. **Field service** (`custom_field_service`) menangani penugasan teknisi, work order di lokasi, pemakaian material, dan tanda tangan pelanggan. **Timesheet** (`custom_timesheet`) menghubungkan pencatatan waktu billable ke penagihan dan ke komponen lembur payroll.

## 8.4 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Berita Acara Serah Terima | `custom_bast` | Umum | — | Produksi | Dokumen serah terima generik dengan tanda tangan ganda dan jejak audit. |
| Layanan Lapangan | `custom_field_service` | Umum | — | Beta | Penugasan teknisi, work order di lokasi, pemakaian material, dan tanda tangan pelanggan. |
| Helpdesk & SLA | `custom_helpdesk` | Umum | — | Beta | Alur tiket dengan SLA, eskalasi, dan portal pelanggan. |
| Laporan Operasional Armada | `custom_ops_reports` | Umum, dikonfigurasi | ARKA-AIM | Beta | Opname aset, pergerakan per event, suku cadang, kesehatan pemeliharaan, dan riwayat perbaikan. |
| API PMO | `custom_project_api` | Umum, dikonfigurasi | VAS PMO | Produksi | Permukaan REST ber-JWT dan HMAC untuk aplikasi VAS PMO. |
| Change Request Proyek | `custom_project_cr` | Umum, dikonfigurasi | VAS PMO | Produksi | Change Request sebagai record tersendiri: triase, analisis dampak, persetujuan berjenjang. |
| Notifikasi Proyek | `custom_project_notify` | Umum, dikonfigurasi | VAS PMO | Produksi | Notifikasi berbasis aturan untuk proyek, CR, task, dan progres mingguan. |
| Portofolio Proyek & SLA | `custom_project_portfolio` | Umum, dikonfigurasi | VAS PMO | Produksi | Vertikal brand, portofolio, sprint mingguan, dan tahap Hold/WUV dengan jam SLA. |
| Penyewaan Aset | `custom_rental` | Umum, dikonfigurasi | ARKA-AIM | Produksi | Siklus sewa: tarif bertingkat, jadwal, BAST, denda keterlambatan, portal, dan pengiriman stok. |
| Paket Sewa via BOM | `custom_rental_bom_explosion` | Umum, dikonfigurasi | ARKA-AIM | Beta | Membundel drone dan perangkat lewat BOM kit, mengisi baris BAST otomatis. |
| Penagihan Sewa | `custom_rental_invoicing` | Umum, dikonfigurasi | ARKA-AIM | Beta | Membuat faktur saat barang sewa kembali: biaya sewa, denda, dan kerusakan. |
| Pemeriksaan Kualitas Sewa | `custom_rental_quality_hook` | Umum, dikonfigurasi | ARKA-AIM | Beta | Quality check otomatis saat pengembalian, menautkan aset sewa ke equipment pemeliharaan. |
| BAST dari Sales Order | `custom_sale_bast` | Umum | — | Beta | Membuat dan mengakses dokumen BAST langsung dari Sales Order. |
| Timesheet & Penagihan Jasa | `custom_timesheet` | Umum | — | Produksi | Timesheet billable dengan integrasi lembur ke payroll. |
| Tanggal Pertunjukan ARKA | `custom_arka_show_date` | Khusus brand | ARKA-AIM | Produksi | Field tanggal show, event, dan uang muka di penawaran/SO/faktur, dengan termin pembayaran berpatokan tanggal show. |

### Yang bersifat khusus per-brand

Modul berikut berada di `addons/_tenants/` dan **tidak dapat dipakai ulang apa adanya** oleh tenant lain:

- **Tanggal Pertunjukan ARKA** (`custom_arka_show_date`) — ARKA-AIM. Field tanggal show, event, dan uang muka di penawaran/SO/faktur, dengan termin pembayaran berpatokan tanggal show.

Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan data sendiri:

- **Laporan Operasional Armada** (`custom_ops_reports`) — sudah membawa data atau profil untuk ARKA-AIM.
- **API PMO** (`custom_project_api`) — sudah membawa data atau profil untuk VAS PMO.
- **Change Request Proyek** (`custom_project_cr`) — sudah membawa data atau profil untuk VAS PMO.
- **Notifikasi Proyek** (`custom_project_notify`) — sudah membawa data atau profil untuk VAS PMO.
- **Portofolio Proyek & SLA** (`custom_project_portfolio`) — sudah membawa data atau profil untuk VAS PMO.
- **Penyewaan Aset** (`custom_rental`) — sudah membawa data atau profil untuk ARKA-AIM.
- **Paket Sewa via BOM** (`custom_rental_bom_explosion`) — sudah membawa data atau profil untuk ARKA-AIM.
- **Penagihan Sewa** (`custom_rental_invoicing`) — sudah membawa data atau profil untuk ARKA-AIM.
- **Pemeriksaan Kualitas Sewa** (`custom_rental_quality_hook`) — sudah membawa data atau profil untuk ARKA-AIM.

# 9. Manufaktur, Kualitas & Pemeliharaan

5 modul — domain terkecil di platform, dan itu mencerminkan bauran bisnis Erajaya: distribusi dan retail, bukan manufaktur. Kapabilitasnya tetap dibangun karena tiga alasan nyata: pemeliharaan armada drone, kontrol kualitas penerimaan gudang, dan perbaikan aset internal.

## 9.1 Kualitas

`custom_quality_full` menyediakan quality point dan pemeriksaan, alert Non-Conformance Report, baris inspeksi, tanda tangan, **CAPA** (Corrective and Preventive Action), serta template uji yang dapat dipakai ulang. Ia menjadi titik sambung bagi dua modul lain: pemeriksaan kualitas otomatis saat aset sewa dikembalikan, dan gerbang QC pada penerimaan gudang.

## 9.2 Pemeliharaan

`custom_maintenance` melampaui modul maintenance bawaan Odoo dengan alert dari sensor IoT, metrik **MTBF/MTTR**, penjadwalan prediktif, SLA per tim, pelacakan suku cadang, dan biaya pemeliharaan. Untuk armada drone ARKA-AIM, ini yang menghubungkan jam terbang dengan jadwal servis.

`custom_repairs` menangani perbaikan aset internal dan menjembatani ke equipment serta permintaan pemeliharaan, sehingga satu unit memiliki satu riwayat, bukan dua catatan terpisah.

## 9.3 PLM dan IoT

`custom_mrp_plm` membawa Product Lifecycle Management: alur **ECO** (Engineering Change Order), versi Bill of Materials, dan perubahan yang dikunci persetujuan.

`custom_iot_bridge` menerima pembacaan sensor lewat webhook, menampilkannya di dashboard, dan memicu alert saat melewati ambang batas. Ia adalah sumber data bagi pemeliharaan prediktif di atas.

## 9.4 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Jembatan IoT | `custom_iot_bridge` | Umum | — | Beta | Menerima pembacaan sensor via webhook, menampilkannya di dashboard dengan alert ambang batas. |
| Pemeliharaan Prediktif | `custom_maintenance` | Umum | — | Produksi | Alert IoT, MTBF/MTTR, penjadwalan prediktif, SLA, suku cadang, dan biaya. |
| Manajemen Siklus Produk (PLM) | `custom_mrp_plm` | Umum | — | Beta | Alur ECO, versi BoM, dan perubahan yang dikunci persetujuan. |
| Manajemen Kualitas | `custom_quality_full` | Umum | — | Produksi | Quality point, pemeriksaan, alert NCR, tanda tangan, CAPA, dan template uji. |
| Perbaikan Aset | `custom_repairs` | Umum | — | Produksi | Perbaikan aset internal yang terhubung ke equipment dan permintaan pemeliharaan. |

### Yang bersifat khusus per-brand

Tidak ada. Seluruh modul di domain ini berlaku umum untuk tenant mana pun, tanpa data atau konfigurasi khusus brand.

# 10. Produktivitas & AI

10 modul, seluruhnya berlaku umum. Domain ini menggantikan sekelompok aplikasi Odoo Enterprise yang biasanya dibeli terpisah — Documents, Knowledge, Spreadsheet, Sign, Studio — dan menambahkan lapisan AI di atasnya.

## 10.1 Lapisan AI

`custom_ai_bridge` adalah satu-satunya jalan keluar menuju model bahasa. Ia menandatangani permintaan dengan HMAC dan mengirimkannya ke sebuah gateway terpisah, yang kemudian memilih penyedia: **Claude (Anthropic), OpenAI, atau Ollama lokal**. Abstraksi ini penting secara komersial dan kepatuhan sekaligus: mengganti penyedia adalah perubahan konfigurasi, dan sebuah tenant dengan kebutuhan kedaulatan data dapat diarahkan ke model lokal tanpa mengubah satu pun modul di atasnya.

`custom_ai_features` memakai jembatan itu untuk fitur yang terlihat pengguna: **Ask AI** di mana saja, **inbox anomali** yang menyoroti transaksi menyimpang, **chat bahasa alami ke data**, dan klasifikasi dokumen otomatis.

## 10.2 Dokumen dan pengetahuan

**Manajemen dokumen** (`custom_documents`) menyediakan workspace, penandaan, versi, dan akses yang menghormati klasifikasi data pribadi dari domain kepatuhan. **Basis pengetahuan** (`custom_knowledge`) adalah wiki internal ringan dengan template dan versi artikel. **Tanda tangan elektronik** (`custom_sign`) menangani alur multi-penandatangan lewat portal bertoken.

**Spreadsheet** (`custom_spreadsheet`) menambahkan lapisan workbook dengan impor dan ekspor CSV, bantuan AI, versi, dan berbagi.

## 10.3 Kustomisasi tanpa kode

`custom_studio_lite` adalah pengganti ringan Odoo Studio: pengelola field kustom dan ekstensi tampilan secara **deklaratif**. Perbedaannya dengan Studio asli penting bagi tim yang memelihara platform ini — perubahan disimpan sebagai record yang dapat ditinjau dan dipindahkan antar basis data, bukan sebagai modifikasi tampilan yang menyebar dan sulit dilacak.

## 10.4 Dashboard dan kerapian data

**Dashboard KPI** (`custom_dashboards`) menyusun ubin metrik dengan kueri bahasa alami. **Pembersihan data** (`custom_data_cleaning`) menjalankan aturan deduplikasi dan normalisasi format Indonesia — nomor telepon dan NIK — yang merupakan sumber duplikasi partner paling umum di basis data lokal. **Daftar tugas pribadi** (`custom_todo`) melengkapi dengan timer pomodoro, pemecahan tugas berbantuan AI, dan template berulang.

## 10.5 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Jembatan AI | `custom_ai_bridge` | Umum | — | Beta | Menghubungkan Odoo ke gateway AI platform (Claude / OpenAI / Ollama). |
| Fitur AI Terpadu | `custom_ai_features` | Umum | — | Beta | Ask AI di mana saja, inbox anomali, chat bahasa alami ke data, dan klasifikasi dokumen otomatis. |
| Dashboard KPI | `custom_dashboards` | Umum | — | Produksi | Dashboard berbasis ubin dengan kueri bahasa alami. |
| Pembersihan Data | `custom_data_cleaning` | Umum | — | Produksi | Aturan deduplikasi dan normalisasi format Indonesia (nomor telepon, NIK). |
| Manajemen Dokumen | `custom_documents` | Umum | — | Beta | Workspace, penandaan, versi, dan akses yang sadar klasifikasi PDP. |
| Basis Pengetahuan | `custom_knowledge` | Umum | — | Produksi | Wiki internal ringan dengan template dan versi artikel. |
| Tanda Tangan Elektronik | `custom_sign` | Umum | — | Beta | Alur tanda tangan multi-penandatangan dengan portal bertoken. |
| Spreadsheet Terintegrasi | `custom_spreadsheet` | Umum | — | Produksi | Lapisan workbook dengan impor/ekspor CSV, bantuan AI, versi, dan berbagi. |
| Studio Lite | `custom_studio_lite` | Umum | — | Produksi | Pengelola field kustom dan ekstensi tampilan secara deklaratif. |
| Daftar Tugas Pribadi | `custom_todo` | Umum | — | Beta | Timer pomodoro, pemecahan tugas oleh AI, dan template berulang. |

### Yang bersifat khusus per-brand

Tidak ada. Seluruh modul di domain ini berlaku umum untuk tenant mana pun, tanpa data atau konfigurasi khusus brand.

# 11. Pemasaran & Komunikasi

12 modul, seluruhnya berlaku umum. Ciri khas domain ini: **setiap kanal keluar melewati gerbang persetujuan UU PDP**. Ini bukan tambahan opsional — mengirim pesan pemasaran ke seseorang yang menarik persetujuannya adalah pelanggaran, dan platform ini menutup jalurnya di tingkat kode, bukan prosedur.

## 11.1 WhatsApp

`custom_whatsapp` adalah adapter Meta WhatsApp Cloud API dengan manajemen template dan **antrean keluar bergerbang PDP**. Ia terintegrasi ke penjualan, akuntansi, dan helpdesk, sehingga konfirmasi pesanan, pengingat tagihan, dan pembaruan tiket berjalan lewat kanal yang benar-benar dibaca pelanggan di Indonesia.

## 11.2 Kanal lain

**SMS Indonesia** (`custom_sms_id`) menyediakan adapter Zenziva untuk penyedia lokal dan Twilio untuk global. **Email marketing** (`custom_email_marketing`) menambahkan galeri template, uji A/B, dan mekanisme berhenti berlangganan yang patuh. **Marketing automation** menjalankan kampanye multi-langkah, rangkaian drip, dan segmentasi audiens.

**Live chat** (`custom_livechat`) menambahkan eskalasi ke helpdesk, jawaban siap pakai, skrip chatbot, routing berdasarkan keahlian, dan saran balasan dari AI. **VoIP** (`custom_voip`) menyediakan click-to-call dan pencatatan panggilan dengan beberapa adapter SIP/PBX.

## 11.3 Event, survei, dan komunitas

**Manajemen event** (`custom_events`) mengirim tiket lewat WhatsApp dengan kode QR, menangani check-in QR di lokasi, sponsor, track sesi, survei pasca-acara, dan daftar tunggu. **Survei** (`custom_survey`) menangani pulse karyawan, NPS pelanggan, sertifikasi, dan survei yang terhubung ke penilaian kinerja.

**Reservasi janji temu** (`custom_appointments`) menyediakan pemesanan publik dengan ketersediaan sumber daya. **Forum** (`custom_forum`) menambahkan moderasi AI, gamifikasi, dan penyamaran identitas penulis sesuai PDP. **Media sosial** (`custom_social`) mengelola akun dan penjadwalan unggahan.

**Program afiliasi** (`custom_affiliate`) melacak tautan, menangkap klik, mengatribusikan pesanan, dan menghitung komisi beserta pembayarannya.

## 11.4 Catatan kematangan

Sebagian besar modul di domain ini dinilai *Beta* karena tidak membawa suite pengujian, bukan karena tidak berfungsi. Empat yang dinilai *Produksi* — WhatsApp, email marketing, live chat, dan survei — adalah yang paling banyak dipakai dan karenanya paling banyak diuji.

## 11.5 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Program Afiliasi | `custom_affiliate` | Umum | — | Beta | Tautan terlacak, penangkapan klik, atribusi pesanan, komisi, dan pembayaran. |
| Reservasi Janji Temu | `custom_appointments` | Umum | — | Beta | Pemesanan publik dan kalender internal dengan ketersediaan sumber daya. |
| Email Marketing | `custom_email_marketing` | Umum | — | Produksi | Galeri template, uji A/B, dan berhenti berlangganan yang patuh UU PDP. |
| Manajemen Event | `custom_events` | Umum | — | Beta | Tiket WhatsApp ber-QR, check-in QR, sponsor, track, survei pasca-acara, dan waiting list. |
| Forum Komunitas | `custom_forum` | Umum | — | Beta | Moderasi AI, gamifikasi, dan penyamaran identitas penulis sesuai PDP. |
| Live Chat | `custom_livechat` | Umum | — | Produksi | Eskalasi ke helpdesk, jawaban siap pakai, chatbot, routing keahlian, dan saran balasan AI. |
| Marketing Automation | `custom_marketing_automation` | Umum | — | Beta | Kampanye multi-langkah, rangkaian drip, dan segmentasi audiens. |
| SMS Indonesia | `custom_sms_id` | Umum | — | Beta | Adapter Zenziva dan Twilio dengan gerbang persetujuan PDP untuk pesan pemasaran. |
| Media Sosial | `custom_social` | Umum | — | Beta | Pengelolaan akun dan penjadwalan unggahan media sosial. |
| Survei & NPS | `custom_survey` | Umum | — | Produksi | Pulse karyawan, NPS pelanggan, sertifikasi, dan survei terkait penilaian kinerja. |
| Telepon & VoIP | `custom_voip` | Umum | — | Beta | Click-to-call dan pencatatan panggilan dengan beberapa adapter SIP/PBX. |
| WhatsApp Bisnis | `custom_whatsapp` | Umum | — | Produksi | Adapter Meta WhatsApp Cloud API dengan manajemen template dan antrean keluar bergerbang PDP. |

### Yang bersifat khusus per-brand

Tidak ada. Seluruh modul di domain ini berlaku umum untuk tenant mana pun, tanpa data atau konfigurasi khusus brand.

# 12. Kepatuhan Data (UU PDP) & Audit

6 modul mengimplementasikan kewajiban **UU 27/2022 tentang Pelindungan Data Pribadi**. Domain ini kecil dalam jumlah tetapi menyentuh hampir seluruh platform: puluhan modul lain mewarisi mixin audit dan klasifikasinya.

## 12.1 Rantai lapisan

Empat lapisan dibangun berurutan, dan urutannya menentukan:

**Klasifikasi** (`custom_pdp_core`) menyediakan taksonomi: field mana pada model mana yang merupakan data pribadi, dan pada tingkat sensitivitas apa. Tanpa ini, tiga lapisan di atasnya tidak punya sesuatu untuk dijaga.

**Audit** (`custom_pdp_audit`) adalah log **append-only berantai-hash**. Setiap baris menyimpan hash baris sebelumnya, sehingga penghapusan atau penyuntingan di tengah rantai terdeteksi. Perlindungannya tidak berhenti di tingkat aplikasi: sebuah trigger PostgreSQL menolak UPDATE dan DELETE pada tabel itu, dan sebuah cron malam menelusuri rantai serta memberi alert bila ada mata rantai putus. Modul mana pun dapat ikut dengan mewarisi mixin-nya.

**Consent** (`custom_pdp_consent`) mencatat pemberian dan penarikan persetujuan per tujuan pemrosesan. Inilah yang dibaca gerbang PDP di kanal pemasaran.

**DSAR** (`custom_pdp_dsar`) menangani permintaan subjek data — akses, koreksi, penghapusan — sebagai alur kerja dengan tenggat, bukan permintaan email yang hilang di kotak masuk.

## 12.2 Masking dan retensi

**Masking PII** (`custom_pdp_masking`) menyamarkan data pribadi lewat hook pada pembacaan ORM, sehingga pengguna tanpa hak melihat data tersamar di layar yang sama — bukan layar terpisah yang harus dibangun dua kali.

**Retensi** (`custom_pdp_retention`) menjalankan kebijakan penyimpanan dan otomasi siklus hidup. Ini yang membuat data pelamar kerja tidak tersimpan tanpa batas, sebuah kewajiban yang paling sering terlewat dalam praktik.

## 12.3 Jangkauan sesungguhnya

Nilai domain ini tidak terletak pada enam modulnya, melainkan pada seberapa jauh ia menjangkau. Tag `audit-trail` muncul pada 78 manifest dan tag `pdp` pada 37 dari 162 modul. Artinya jejak audit dan kesadaran data pribadi bukan fitur yang dinyalakan di satu tempat, melainkan properti yang diwarisi sebagian besar platform.

> Catatan kematangan: lima dari enam modul PDP dinilai *Beta* karena tidak membawa suite pengujian sendiri. Perilaku append-only-nya ditegakkan di tingkat basis data lewat trigger, yang berlaku terlepas dari ada tidaknya pengujian di tingkat aplikasi.

## 12.4 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Audit Log UU PDP | `custom_pdp_audit` | Umum | — | Beta | Log audit append-only berantai-hash, dilindungi trigger Postgres. |
| Manajemen Consent | `custom_pdp_consent` | Umum | — | Beta | Pencatatan pemberian dan penarikan persetujuan subjek data, teraudit. |
| Klasifikasi Data Pribadi | `custom_pdp_core` | Umum | — | Beta | Taksonomi klasifikasi data pribadi sesuai UU 27/2022. |
| Permintaan Subjek Data (DSAR) | `custom_pdp_dsar` | Umum | — | Beta | Alur permintaan akses/koreksi/penghapusan data pribadi. |
| Masking PII | `custom_pdp_masking` | Umum | — | Produksi | Layanan penyamaran data pribadi dengan hook pada pembacaan ORM. |
| Kebijakan Retensi Data | `custom_pdp_retention` | Umum | — | Beta | Kebijakan retensi dan otomasi siklus hidup data pribadi. |

### Yang bersifat khusus per-brand

Tidak ada. Seluruh modul di domain ini berlaku umum untuk tenant mana pun, tanpa data atau konfigurasi khusus brand.

# 13. Integrasi & Fondasi Platform

16 modul. Domain ini jarang terlihat pengguna akhir, tetapi hampir setiap fitur di bab-bab sebelumnya berdiri di atasnya.

## 13.1 Fondasi

`custom_core` adalah akar dependensi hampir seluruh platform: utilitas bersama, mixin, helper kebijakan, penyimpanan konfigurasi terenkripsi, dan **dekorator `secure_endpoint`** yang menjaga setiap endpoint masuk.

Satu kontrak HMAC dipakai untuk kedua arah, dengan bentuk kanonik yang sama: stempel waktu digabung dengan badan permintaan mentah, batas selisih waktu 300 detik, penjagaan pengulangan lewat Redis, dan daftar izin CIDR. Endpoint masuk memakai `@secure_endpoint('<scope>')`; scope yang dipakai saat ini adalah `hht`, `finance_sap`, `storefront`, `mdm`, dan `ops_alertmanager`.

`custom_adapter_framework` menangani arah keluar: registri adapter, klien HTTP dengan **retry berjenjang dan circuit breaker**, kredensial lewat rujukan ke parameter konfigurasi alih-alih disimpan pada record, dan log panggilan append-only yang menyimpan **hash** badan permintaan, bukan isinya. Kesalahan 4xx diperlakukan permanen dan tidak diulang — perilaku yang membedakan adapter yang matang dari yang membanjiri mitra dengan permintaan gagal.

> Utang teknis yang layak dicatat: empat modul (`custom_ai_bridge`, `custom_payment_id`, `custom_sms_id`, `custom_voip`) menulis adapternya sendiri alih-alih memakai kerangka ini. Itu adalah warisan, bukan preseden — integrasi keluar yang baru harus memakai kerangka bersama.

## 13.2 Mesin persetujuan

`custom_approval_engine` menyediakan persetujuan berjenjang generik dengan delegasi, mode di luar kantor, dan eskalasi SLA. Ia dipakai oleh klaim biaya, cuti, purchase order, sales order, Finance Portal, uang muka, dan perubahan kategori produk. Membangun tujuh alur persetujuan terpisah adalah kesalahan yang dihindari platform ini sejak awal.

## 13.3 Identitas

`authenticate_keycloak` menambahkan alur OAuth2 authorization code dengan confidential client di atas `auth_oauth` bawaan Odoo. Ia menjadi fondasi bagi SSO karyawan (`custom_hr_sso_keycloak`) dan SSO Finance Portal (`custom_finance_portal_sso`).

## 13.4 Konektor ESB

`custom_esb_connector` adalah mesin integrasi ke **ESB Core dan ESB OMS**, sistem ERP food & beverage yang dipakai EFN. Ia menyediakan adapter REST bersesi, mirror master data, snapshot stok, dan outbox dokumen yang idempoten. Mesinnya generik; yang khusus EFN adalah vertikal `custom_fnb_stock_ops` di Bab 14.

## 13.5 Presentasi dan kenyamanan

`custom_report_templates` menyediakan tata letak PDF faktur, penawaran, dan purchase order dengan branding per tenant. `custom_home_console` menggantikan halaman depan Odoo dengan kartu aplikasi terkelompok dan pencarian.

`custom_currency_nbsp` menyelesaikan masalah kecil yang berbiaya besar: Odoo menyisipkan **non-breaking space** pada nominal mata uang, yang membuat ekspor CSV terbaca sebagai teks rusak di Excel. Modul ini menghapusnya dan menambahkan BOM UTF-8 pada ekspor. Setiap tim keuangan yang pernah melihat karakter "Â" di lembar kerjanya tahu mengapa ini ada.

## 13.6 Komponen pihak ketiga

Empat modul OCA di-vendor apa adanya dan tidak diubah: **queue_job** (eksekusi pekerjaan latar belakang berbasis basis data, dipakai enam modul dan dimuat sebagai server-wide module), **auth_jwt**, **partner_firstname**, dan **base_rest** — yang terakhir masih pada seri 18.0 dan ditandai tidak dapat dipasang.

> Perlu ditegaskan: Redis di platform ini **bukan** broker pekerjaan. Ia dipakai untuk penjagaan replay dan cache. Antrean pekerjaan berjalan di PostgreSQL lewat `queue_job`. Tidak ada RabbitMQ maupun Celery, dan Kafka hanya muncul sebagai mock di jembatan SAP — tidak ada broker Kafka di berkas Compose mana pun.

## 13.7 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Autentikasi Keycloak | `authenticate_keycloak` | Umum | — | Beta | Alur OAuth2 authorization code (confidential client) di atas auth_oauth Odoo. |
| Kerangka Adapter Integrasi | `custom_adapter_framework` | Umum | — | Produksi | Registry adapter, klien HTTP dengan retry dan circuit breaker, serta log panggilan append-only. |
| Mesin Persetujuan | `custom_approval_engine` | Umum | — | Produksi | Persetujuan berjenjang generik dengan delegasi, mode cuti, dan eskalasi SLA. |
| Fondasi Platform | `custom_core` | Umum | — | Produksi | Utilitas bersama, mixin, helper kebijakan, dan endpoint ber-HMAC. |
| Perbaikan Format Mata Uang & CSV | `custom_currency_nbsp` | Umum | — | Beta | Menghapus non-breaking space pada nominal dan menambahkan BOM UTF-8 pada ekspor CSV. |
| Konektor ESB Core | `custom_esb_connector` | Umum, dikonfigurasi | EFN (Erajaya F&B) | Produksi | Adapter REST bersesi ke ESB Core/OMS, mirror master data, snapshot stok, dan outbox dokumen. |
| Konsol Beranda | `custom_home_console` | Umum | — | Beta | Halaman depan bergaya spotlight: kartu aplikasi terkelompok, pencarian, branding. |
| Manajemen Unit Operasional | `custom_operating_unit` | Umum | — | Produksi | Master unit operasional berjenjang Kantor Pusat → Area → Toko, dan pemetaan pengguna ke unit yang menjadi dasar pembatasan data. |
| Pembatasan Data per Unit Operasional | `custom_operating_unit_docs` | Umum | — | Produksi | Menempelkan unit operasional pada dokumen akuntansi, gudang, pembelian dan penjualan, lalu membatasi baca maupun tulisnya per unit. |
| Template Laporan Berbranding | `custom_report_templates` | Umum | — | Beta | Tata letak PDF faktur, penawaran, dan PO dengan branding per tenant. |
| Manajemen Peran Pengguna | `custom_role_manager` | Umum | — | Produksi | Pilih peran jabatan alih-alih mencentang puluhan grup akses; 18 peran standar Kantor Pusat dan retail, dengan pencabutan yang hanya menyentuh pemberian peran. |
| Autentikasi JWT (OCA) | `auth_jwt` | Pihak ketiga | — | Vendor | Autentikasi bearer token JWT untuk API keluar-masuk. |
| Base REST (OCA) | `base_rest` | Pihak ketiga | — | Vendor | Kerangka membangun REST API tingkat tinggi di Odoo. Tidak dipasang. |
| Penomoran Dokumen ARKA-AIM | `custom_arka_aim_numbering` | Khusus brand | ARKA-AIM | Produksi | Nomor SQ/SO/PO/INV/DO/BAST per perusahaan dengan reset bulanan. |
| Nama Depan/Belakang Partner (OCA) | `partner_firstname` | Pihak ketiga | — | Vendor | Memisahkan nama depan dan nama belakang untuk partner perorangan. |
| Antrean Pekerjaan (OCA) | `queue_job` | Pihak ketiga | — | Vendor | Eksekusi pekerjaan latar belakang berbasis basis data — dipakai 6 modul. |

### Yang bersifat khusus per-brand

Modul berikut berada di `addons/_tenants/` dan **tidak dapat dipakai ulang apa adanya** oleh tenant lain:

- **Penomoran Dokumen ARKA-AIM** (`custom_arka_aim_numbering`) — ARKA-AIM. Nomor SQ/SO/PO/INV/DO/BAST per perusahaan dengan reset bulanan.

Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan data sendiri:

- **Konektor ESB Core** (`custom_esb_connector`) — sudah membawa data atau profil untuk EFN (Erajaya F&B).

# 14. Vertikal Industri

14 modul membentuk dua paket khusus industri: **PPOB / Value-Added Services** untuk Eraspace, dan **operasi stok F&B** untuk EFN. Berbeda dengan domain lain, modul di sini dirancang sebagai satu suite yang dipasang bersama, bukan sebagai fitur yang dipilih satu per satu.

## 14.1 PPOB — Payment Point Online Bank

Dua belas modul menopang bisnis value-added services Erajaya: pulsa, paket data, token listrik, dan pembayaran tagihan yang dijual lewat jaringan **mitra** (reseller B2B) dengan model prabayar.

**Fondasi** (`custom_ppob_core`) menyediakan partner mitra dan provider, katalog produk dengan denominasi, tingkatan harga per mitra, dan kerangka pemetaan bagan akun. Satu field di sini menentukan perlakuan pajak seluruh kelas produk: mode PPN — margin, DPP nilai lain, gross, atau bebas — sesuai PMK-63/2022 untuk distributor pulsa dan voucher.

**Dompet** (`custom_ppob_wallet`) adalah fondasi kebenarannya. Satu dompet per pasangan (mitra, kelas produk), dengan operasi debit dan kredit yang **atomik**: kunci baris `SELECT ... FOR UPDATE`, jurnal berpasangan, baris sub-ledger, dan pembaruan saldo — semuanya dalam satu transaksi PostgreSQL. Tidak ada celah di mana saldo dan buku besar berbeda. Dalam bisnis prabayar, dua penjualan simultan yang keduanya berhasil terhadap saldo terakhir yang sama adalah kerugian langsung.

**Transaksi** (`custom_ppob_sale`) menjalankan state machine `pending → inquiry_ok → in_progress → success / failed / timeout / refunded`, menarik dompet mitra dan deposit provider secara atomik, lalu memanggil adapter provider. Sebuah cron reaper menyelesaikan transaksi yang tergantung dengan **menanyakan status ke provider terlebih dahulu, tidak pernah langsung mengembalikan dana** — penjagaan agar pelanggan tidak dibayar dua kali ketika provider hanya lambat.

**Virtual Account** (`custom_ppob_va`) menangani top-up dompet lewat VA bank (BCA, BNI, BRI, Mandiri, Permata). Jaminan idempotensinya bukan penjagaan replay berbasis waktu, melainkan **indeks unik pada referensi bank**: callback ganda mengkredit dompet tepat satu kali dan mengembalikan tanda terima yang sama.

Sisanya melengkapi rantai: **provider** dengan inventori bucket atomik dan topup deposit, **komisi** dua arah dengan pemotongan PPh 23, **rollup harian** yang mengagregasi transaksi menjadi satu faktur ringkas per mitra untuk e-Faktur, **target SLA** per provider dengan pengambilan sampel per jam, dan tiga jembatan: Digiflazz sebagai biller H2H, **ERASPACE** untuk mencerminkan feed POS, serta **Oracle EVShop** untuk pipeline lama.

`custom_ppob_pps_gateway` membalik arahnya: ia mengekspos API H2H sehingga POS ERASPACE dapat bertransaksi ke Odoo, menjadikan Odoo sebagai switcher — tahap kedua dari rencana menggantikan sistem lama sebagai sumber kebenaran dompet.

Seluruh suite PPOB saat ini berjalan di basis data pengembangan `rnd_ppob`.

## 14.2 F&B di atas ESB Core

`custom_fnb_stock_ops` menyediakan tiga kapabilitas yang dibutuhkan vertikal EFN di atas ESB Core: **stock opname**, **prakiraan permintaan**, dan **replenishment otomatis** untuk outlet. Mesin integrasinya sendiri (`custom_esb_connector`) tinggal di domain Integrasi, sesuai aturan bahwa mesin bersama tidak boleh masuk vertikal.

Status: pembangunan selesai dan teruji, menunggu kredensial staging ESB.

## 14.3 Template vertikal

`custom_vertical_example` adalah modul rujukan — titik awal untuk membangun vertikal baru. Ia tidak pernah dipasang di mana pun dan dihitung hanya agar totalnya dapat direkonsiliasi. Ia juga satu-satunya modul yang berada satu tingkat lebih dalam dari standar direktori, di `verticals/_template/`.

## 14.4 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Operasi Stok F&B | `custom_fnb_stock_ops` | Umum, dikonfigurasi | EFN (Erajaya F&B) | Produksi | Stock opname, prakiraan permintaan, dan replenishment otomatis untuk outlet F&B di atas ESB Core. |
| Biller Digiflazz | `custom_ppob_biller_digiflazz` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | Adapter H2H Digiflazz untuk topup prabayar dan pembayaran tagihan, idempoten lewat ref_id. |
| Komisi PPOB | `custom_ppob_commission` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Beta | Komisi dua arah: pendapatan dari provider dan rebate ke mitra, dengan pemotongan PPh 23. |
| Fondasi PPOB | `custom_ppob_core` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Beta | Partner mitra dan provider, katalog produk, tingkatan harga, dan kerangka pemetaan CoA. |
| Jembatan ERASPACE | `custom_ppob_eraspace_bridge` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | Mencerminkan feed POS dan H2H ERASPACE ke Odoo Finance lewat dua kanal ingest ber-HMAC. |
| Jembatan Oracle EVShop | `custom_ppob_oracle_bridge` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | Menghubungkan suite PPOB ke pipeline Oracle EVShop lama lewat stored procedure dan polling status. |
| Gateway PPS (H2H Masuk) | `custom_ppob_pps_gateway` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | Mengekspos API H2H PPS/EVShop sehingga POS ERASPACE bertransaksi ke Odoo sebagai switcher. |
| Provider & Stok Denom | `custom_ppob_provider` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | Master provider, inventori bucket atomik, pemetaan SKU, dan topup deposit DP 100%. |
| Rollup Harian PPOB | `custom_ppob_rollup` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Beta | Agregasi transaksi sukses menjadi satu sales order dan faktur ringkas per mitra untuk e-Faktur. |
| Transaksi PPOB | `custom_ppob_sale` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | State machine transaksi, penarikan dompet dan bucket secara atomik, dispatch provider, PPN margin PMK-63. |
| SLA & Throughput PPOB | `custom_ppob_sla` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | Target throughput dan latensi per provider, dengan pengambilan sampel tiap jam. |
| Virtual Account Mitra | `custom_ppob_va` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Produksi | Virtual account mitra dan topup dompet lewat callback H2H bank serta rekonsiliasi CSV. |
| Dompet Prabayar Mitra | `custom_ppob_wallet` | Umum, dikonfigurasi | Eraspace / PPOB-VAS | Beta | Dompet mitra dengan primitif debit/kredit atomik terkunci baris dan buku besar GL berpasangan. |
| Template Vertikal | `custom_vertical_example` | Umum | — | Kerangka | Modul rujukan sebagai titik awal membangun vertikal baru. |

### Yang bersifat khusus per-brand

Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan data sendiri:

- **Operasi Stok F&B** (`custom_fnb_stock_ops`) — sudah membawa data atau profil untuk EFN (Erajaya F&B).
- **Biller Digiflazz** (`custom_ppob_biller_digiflazz`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Komisi PPOB** (`custom_ppob_commission`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Fondasi PPOB** (`custom_ppob_core`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Jembatan ERASPACE** (`custom_ppob_eraspace_bridge`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Jembatan Oracle EVShop** (`custom_ppob_oracle_bridge`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Gateway PPS (H2H Masuk)** (`custom_ppob_pps_gateway`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Provider & Stok Denom** (`custom_ppob_provider`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Rollup Harian PPOB** (`custom_ppob_rollup`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Transaksi PPOB** (`custom_ppob_sale`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **SLA & Throughput PPOB** (`custom_ppob_sla`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Virtual Account Mitra** (`custom_ppob_va`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.
- **Dompet Prabayar Mitra** (`custom_ppob_wallet`) — sudah membawa data atau profil untuk Eraspace / PPOB-VAS.

# 15. Administrasi Platform & Odoo-as-a-Service

Bab ini menjawab kebutuhan kedua dari dokumen ini: bagaimana platform ini dikelola sebagai layanan, siapa yang bisa melakukan apa, dan — bagian yang paling perlu dibaca — **apa yang belum dibangun**.

Bab ini memakai konvensi yang sama dengan dokumen arsitektur internal: setiap pernyataan ditandai sebagai **KONDISI SAAT INI (NOW)** atau **SASARAN (TARGET)**. Tidak ada yang dideskripsikan sebagai ada sampai ia benar-benar ada. Versi sebelumnya dari dokumen arsitektur itu pernah menggambarkan Kafka, Postgres warm-standby, dan struktur direktori infra yang tidak pernah dibangun, dan perencanaan sempat berangkat dari asumsi tersebut. Bab ini tidak mengulanginya.

## 15.1 Mengapa multi-tenant

Satu basis kode Odoo 19 melayani 8 brand terdaftar. Setiap tenant memiliki **basis datanya sendiri** di dalam satu klaster PostgreSQL — bukan satu basis data bersama dengan kolom perusahaan. Pilihan ini menentukan hampir semua hal lain di bab ini:

- Data satu brand tidak dapat bocor ke brand lain lewat kesalahan kueri, karena tidak berada dalam basis data yang sama.
- Sebuah tenant dapat dicadangkan, dipulihkan, atau dihentikan sendiri tanpa menyentuh yang lain.
- Sebaliknya, **pemutakhiran modul bersama menyentuh semua basis data** dan harus dijalankan pada semuanya. Ini sumber insiden operasional yang nyata dan ditangani sebagai prosedur, bukan sebagai hal yang diingat.

## 15.2 Peta lapisan kendali

**NOW.** Enam lapisan, dari luar ke dalam:

**Pintu depan** — Caddy dengan Web Application Firewall berbasis Coraza dan OWASP Core Rule Set, TLS, penekanan header build, dan pembatasan laju per IP. Nama sub-domain tenant diekstrak lewat ekspresi reguler pada header dan diteruskan sebagai `X-Tenant-Slug`, yang dipakai Odoo sebagai `dbfilter`. Satu instans melayani banyak tenant tanpa satu pun melihat yang lain.

**Gerbang login** — aplikasi `/signin` tersendiri menggantikan pemilih basis data bawaan Odoo, yang secara bawaan menampilkan daftar seluruh basis data kepada siapa pun yang membuka halamannya. Daftar tenant yang boleh muncul dikurasi tangan dalam sebuah berkas konfigurasi dengan penanda publik atau internal.

**Konsol admin** — sebuah aplikasi satu halaman (React) dengan lapisan backend-for-frontend yang menandatangani permintaan ber-HMAC ke orkestrator. Dua belas halaman: Dashboard, Onboarding Pipeline, Tenants & Verticals, VPS Console, Module Deployments, Dev Cycles, Services Monitoring, Audit Trail, Documents, **Users & RBAC**, dan Cost & Licenses.

**Orkestrator** — layanan FastAPI yang menjadi mesin siklus hidup tenant. Setiap endpoint `/v1/*` menuntut tanda tangan HMAC-SHA256 dengan jendela replay lima menit. Ia menjalankan penjadwal cadangan, enkripsi kunci data dengan skema envelope, dan bootstrap VPS jarak jauh lewat SSH.

**Registry** — sebuah skema PostgreSQL tersendiri, `tenant_registry`, berisi empat tabel: `tenants`, `action_log`, `backups`, dan `coretax_usage`. `action_log` adalah **log append-only berantai-hash** — setiap baris menyimpan hash baris sebelumnya, dan sebuah trigger menghitungnya saat penyisipan. Hak akses dipisah: orkestrator boleh menulis, peran pembaca hanya boleh membaca.

**Di dalam Odoo** — empat modul lapisan kendali, yang juga merupakan isi domain ini: konsol hub terpadu, super admin, infrastruktur tenant, dan perjalanan onboarding. Ditambah tiga modul operasi internal: analisis kesenjangan BRD, pelacakan siklus pengembangan, dan monitor kapasitas.

![Lapisan kendali: siapa memanggil siapa](svg/D03-control-plane.svg)

## 15.3 Siklus hidup tenant

**NOW.** Enam fase, masing-masing dengan prosedur tertulis dan perintah yang dapat dijalankan:

**Onboarding** — `custom_onboarding_journey` menjalankan state machine intake → BRD → Go/No-Go → provisioning → handover, dengan transisi tahap yang **tidak dapat diubah setelah tercatat** dan sinkronisasi dua arah ke modul Project. Formulir intake publik tersedia lewat controller tersendiri. Prosedur manualnya ada di `docs/sops/tenant-onboarding.md`.

**Provisioning** — orkestrator membuat basis data lewat CLI Odoo di dalam kontainer manajemen, bukan lewat endpoint pembuatan basis data bawaan. Alasannya tercatat sebagai komentar di berkas Compose: endpoint bawaan mengembalikan HTTP 200 meskipun pembuatan gagal. Perintah operator: `make tenant-provision`.

**Operasi** — deploy modul per tenant lewat halaman Module Deployments, dengan peta vertikal → modul yang didefinisikan di dalam kode konsol hub, bukan di manifest.

**Cadangan dan pemulihan** — `make tenant-backup`, `tenant-list-backups`, `tenant-restore`. Penjadwal per tenant berjalan di orkestrator; sebuah cron host terpisah menjalankan dump seluruh basis data pukul 02.30 dengan rotasi harian, mingguan, dan bulanan, ditambah pekerjaan verifikasi pukul 07.05 yang sengaja dipisah agar kegagalan verifikasi tidak tertutupi oleh keberhasilan dump.

**Suspend dan resume** — `make tenant-suspend` dan `tenant-resume` menghentikan akses tanpa menghapus data.

**Offboarding** — `make tenant-archive`, dengan prosedur di `docs/sops/tenant-offboarding.md`.

Integritas seluruh jejak tindakan dapat diperiksa kapan saja dengan `make tenant-verify-chain`, yang menelusuri rantai hash `action_log` dan gagal bila ada mata rantai yang putus.

## 15.4 Pengelolaan pengguna dan hak akses

**NOW.** Tiga lapisan identitas berjalan bersamaan:

**Di dalam Odoo**, hak akses memakai model *privilege* Odoo 19. Platform mendefinisikan kategori dan privilege `custom_platform` sendiri, dan setiap modul vertikal maupun kepatuhan menggantungkan grup keamanannya pada kategori itu.

> Jebakan yang penting diketahui saat memberi hak: pada Odoo 19, satu dropdown privilege memetakan ke **satu grup**. Memberi seseorang akses lewat dropdown tidak menambahkan grup — ia menggantikan. Pencabutan hak administrator harus mencabut pasangan grup yang benar lewat ORM, bukan lewat layar pengguna.

**Lewat SSO**, tiga modul menghubungkan Odoo ke Keycloak: `authenticate_keycloak` menyediakan alur OAuth2, `custom_hr_sso_keycloak` menyinkronkan data karyawan dari klaim token, dan `custom_finance_portal_sso` memetakan peran ke grup serta memisahkan karyawan dari vendor.

**Di konsol admin**, halaman Users & RBAC menampilkan pengguna lintas tenant lewat JSON-RPC ke Odoo.

## 15.5 Isolasi dan keamanan

**NOW.**

- **Isolasi data**: satu basis data per tenant dalam satu klaster.
- **Antar layanan**: satu kontrak HMAC untuk semua arah, dengan penjagaan pengulangan berbasis Redis dan daftar izin CIDR.
- **Pintu masuk**: WAF Coraza dengan OWASP CRS di Caddy, pembatasan laju per IP, dan penguncian origin agar hanya lewat CDN.
- **Jejak audit**: `action_log` berantai-hash di sisi platform, dan `pdp.audit_log` berantai-hash di dalam setiap basis data tenant — yang terakhir dilindungi trigger PostgreSQL yang menolak UPDATE dan DELETE.
- **Kredensial**: kunci data dienkripsi dengan skema envelope di orkestrator; kredensial VPS disimpan sebagai rujukan vault, tidak pernah sebagai nilai di dalam Odoo; kredensial adapter disimpan sebagai rujukan ke parameter konfigurasi terenkripsi.

Prosedur pemulihan tersedia sebagai 13 runbook, termasuk pemulihan bencana, pemulihan data tenant, Postgres mati, Odoo kehabisan memori, dan pengerasan pintu depan.

## 15.6 Observability

**NOW.** Overlay observability menyediakan Prometheus, Alertmanager, Loki, Promtail, Grafana, exporter untuk node/Postgres/Redis/Odoo, dan sebuah layanan prakiraan kapasitas. Di dalam Odoo, `custom_ops_monitor` menampilkan kesehatan server dan prakiraan kapasitas, serta menerima alert lewat endpoint ber-HMAC.

Perlu ditegaskan: ini **metrik operasional, bukan business intelligence**. Pelaporan bisnis berjalan di dalam Odoo lewat mesin laporan akuntansi.

## 15.7 Analisis kesenjangan — Kondisi Saat Ini vs Sasaran

Daftar lengkap kesenjangan yang tercatat: 10 butir, 3 di antaranya berprioritas tinggi. Ringkasannya lebih dulu, lalu satu blok rincian per butir. Setiap butir menyertakan **rujukan berkas** yang dapat dibuka sendiri untuk memeriksa klaimnya — seluruhnya sudah diverifikasi ulang terhadap repositori saat dokumen ini dihasilkan.

| ID | Area | Kesenjangan | Prioritas | Horizon (bulan) |
| --- | --- | --- | --- | --- |
| GAP-BACKUP-01 | Ketahanan Data | RPO nyata 24 jam, bukan 1 jam | Tinggi | 0-3 |
| GAP-BACKUP-02 | Ketahanan Data | Backup off-site belum benar-benar off-site | Tinggi | 0-3 |
| GAP-HA-01 | Ketersediaan | Seluruh platform berjalan di satu host | Tinggi | 6-12 |
| GAP-ADMIN-01 | Konsol Admin | Dua endpoint konsol masih mengembalikan data contoh | Sedang | 0-3 |
| GAP-ADMIN-02 | Provisioning VPS | Jalur provisioning VPS masih dapat berjalan dalam mode demo | Sedang | 0-3 |
| GAP-BI-01 | Pelaporan & BI | Belum ada permukaan Business Intelligence | Sedang | 6-12 |
| GAP-KNOW-01 | Pengetahuan Modul | Dokumentasi modul sebagian besar masih berstatus draft | Sedang | 3-6 |
| GAP-SEC-01 | Keamanan | Orkestrator memegang soket Docker host | Sedang | 3-6 |
| GAP-DOC-01 | Dokumentasi | Konsol admin tidak punya referensi endpoint | Rendah | 0-3 |
| GAP-DOC-02 | Dokumentasi | Angka modul di dokumen arsitektur pernah menyimpang jauh | Rendah | 0-3 |

### GAP-BACKUP-01 · RPO nyata 24 jam, bukan 1 jam

|  |  |
| --- | --- |
| Area | Ketahanan Data |
| Prioritas | Tinggi · upaya M — 1 sampai 4 minggu · horizon 0-3 bulan |
| Kondisi saat ini (NOW) | WAL archiving belum tersambung. Backup penuh berjalan harian pukul 02.30 lewat cron, sehingga kehilangan data maksimum yang mungkin terjadi adalah satu hari kerja penuh. Runbook pemulihan bencana menuliskan RPO 1 jam di kepala dokumen, dan baru mengoreksinya sendiri di catatan tengah dokumen. |
| Sasaran (TARGET) | WAL archiving aktif ke object storage terpisah, RPO terukur maksimal 1 jam, dan angka di kepala runbook disamakan dengan kenyataan. |
| Dampak bisnis | Kegagalan penyimpanan pada sore hari menghapus seluruh transaksi hari itu. Untuk tenant retail yang live, itu berarti penjualan satu hari harus dimasukkan ulang dari sumber POS. |
| Rujukan | `docs/runbooks/disaster-recovery.md:4 (klaim 1 jam)` · `docs/runbooks/disaster-recovery.md:152-154 (koreksi ke 24 jam)` · `scripts/ops/pg_backup_all.sh, scripts/ops/odoo-pg-backup.cron` · `postgres/ — tidak ada archive_mode / archive_command` |

### GAP-BACKUP-02 · Backup off-site belum benar-benar off-site

|  |  |
| --- | --- |
| Area | Ketahanan Data |
| Prioritas | Tinggi · upaya M — 1 sampai 4 minggu · horizon 0-3 bulan |
| Kondisi saat ini (NOW) | Layanan pg-backup-s3 dikunci di balik profil Compose `s3-backup` dan mati secara bawaan. MinIO berjalan di host yang sama dan menulis ke disk yang sama dengan Postgres, sehingga salinan yang ada tidak selamat dari kegagalan disk atau host. |
| Sasaran (TARGET) | Salinan harian terkirim ke object storage di luar host, dengan uji restore terjadwal yang hasilnya tercatat. |
| Dampak bisnis | Kehilangan satu host berarti kehilangan basis data dan seluruh salinannya sekaligus. |
| Rujukan | `docker-compose.prod.yml:125-130 (profiles: [s3-backup])` · `docker-compose.yml — minio bind-mount pada disk yang sama` |

### GAP-HA-01 · Seluruh platform berjalan di satu host

|  |  |
| --- | --- |
| Area | Ketersediaan |
| Prioritas | Tinggi · upaya L — lebih dari 1 bulan · horizon 6-12 bulan |
| Kondisi saat ini (NOW) | Sekitar 15 kontainer berbagi satu VPS dan satu Docker network; semua jalur data adalah bind-mount di bawah ./data/. Host basis data, host pelaporan, dan host redundan yang direncanakan belum dibangun. Nama host `postgres` masih ditulis langsung di berkas Compose untuk layanan odoo, sehingga memisahkan basis data ke host lain bukan sekadar mengubah environment. |
| Sasaran (TARGET) | Pemisahan host basis data, replika baca untuk pelaporan, dan host redundan untuk failover. |
| Dampak bisnis | Tidak ada failover. Pemeliharaan yang memerlukan reboot menghentikan semua tenant sekaligus, termasuk yang sudah live. |
| Rujukan | `docker-compose.yml:130 dan :606, docker-compose.multitenant.yml:137 (HOST: postgres)` · `docs/architecture.md — tabel Deployment topology` · `.env.example — HOST_CPU_CORES / HOST_RAM_GB / HOST_DISK_GB tunggal` |

### GAP-ADMIN-01 · Dua endpoint konsol masih mengembalikan data contoh

|  |  |
| --- | --- |
| Area | Konsol Admin |
| Prioritas | Sedang · upaya S — di bawah 1 minggu · horizon 0-3 bulan |
| Kondisi saat ini (NOW) | Pada BFF hub-portal, /api/costs dan /api/monitoring mengembalikan angka tetap dengan penanda `demo: true`, yang di antarmuka muncul sebagai lencana Demo. Endpoint lain sudah membaca data nyata lewat JSON-RPC ke Odoo. |
| Sasaran (TARGET) | Biaya dibaca dari sumber penagihan yang sebenarnya; status layanan dibaca dari Prometheus, bukan dari daftar tetap. |
| Dampak bisnis | Halaman Cost dan Monitoring tidak boleh dipakai mengambil keputusan. Penanda Demo memang tampil, tetapi mudah terlewat saat presentasi. |
| Rujukan | `hub-portal/server/index.mjs:104 (/api/costs)` · `hub-portal/server/index.mjs:116 (/api/monitoring)` |

### GAP-ADMIN-02 · Jalur provisioning VPS masih dapat berjalan dalam mode demo

|  |  |
| --- | --- |
| Area | Provisioning VPS |
| Prioritas | Sedang · upaya S — di bawah 1 minggu · horizon 0-3 bulan |
| Kondisi saat ini (NOW) | Router /v1/vps/* sudah terdaftar di aplikasi (app/main.py:63) dan bukan kode mati. Namun tiga handler yang bergantung SSH memeriksa PLATFORM_DEMO_MODE dan mengembalikan jawaban stub ketika variabel itu bernilai true, sehingga hasil "berhasil" belum tentu berarti ada perubahan di VPS tujuan. |
| Sasaran (TARGET) | Jalur SSH nyata diuji ujung ke ujung pada lingkungan produksi, dan PLATFORM_DEMO_MODE dipastikan false di sana. |
| Dampak bisnis | Operator bisa menyimpulkan sebuah VPS telah disiapkan padahal belum, karena keluaran API terlihat sama. |
| Rujukan | `tenant-orchestrator/app/main.py:63 (router terdaftar)` · `tenant-orchestrator/app/routers/vps.py:30-33, :153 (stub demo mode)` |

### GAP-BI-01 · Belum ada permukaan Business Intelligence

|  |  |
| --- | --- |
| Area | Pelaporan & BI |
| Prioritas | Sedang · upaya L — lebih dari 1 bulan · horizon 6-12 bulan |
| Kondisi saat ini (NOW) | Peran basis data odoo_readonly ada tetapi berstatus NOLOGIN dan hanya diberi hak pada skema pdp. Tidak ada replika baca, tidak ada permukaan ODBC, tidak ada gudang data, tidak ada ETL. Pelaporan seluruhnya berjalan di dalam Odoo lewat custom_accounting_reports. |
| Sasaran (TARGET) | Replika baca khusus pelaporan dengan peran read-only yang benar-benar bisa login, sebagai target untuk perangkat BI. |
| Dampak bisnis | Kueri analitik berat berjalan di basis data yang sama dengan transaksi. |
| Rujukan | `postgres/init/03-roles.sql (odoo_readonly NOLOGIN, hanya skema pdp)` |

### GAP-KNOW-01 · Dokumentasi modul sebagian besar masih berstatus draft

|  |  |
| --- | --- |
| Area | Pengetahuan Modul |
| Prioritas | Sedang · upaya L — lebih dari 1 bulan · horizon 3-6 bulan |
| Kondisi saat ini (NOW) | Dari 162 modul, 135 memiliki dokumen pengetahuan — sebagian berkas MODULE_KNOWLEDGE.md di dalam addons dan 15 override yang ditulis untuk katalog ini. Hanya 10 di antaranya berstatus `reviewed`; 110 masih `draft` hasil generator. 27 modul belum terdokumentasi sama sekali dan diringkas otomatis dari manifest. |
| Sasaran (TARGET) | Semua modul yang menghadap klien berstatus reviewed, dengan pemeriksaan ulang saat versi manifest berubah. |
| Dampak bisnis | Klaim kapabilitas dari berkas draft tidak boleh dikutip tanpa pemeriksaan. Katalog ini menandainya lewat kolom Keyakinan Info, bukan menyembunyikannya. |
| Rujukan | `docs/platform-feature-catalog/catalog-audit.md` · `scripts/generate_module_knowledge.py, scripts/check_knowledge_drift.py` |

### GAP-SEC-01 · Orkestrator memegang soket Docker host

|  |  |
| --- | --- |
| Area | Keamanan |
| Prioritas | Sedang · upaya M — 1 sampai 4 minggu · horizon 3-6 bulan |
| Kondisi saat ini (NOW) | Overlay multitenant memasang /var/run/docker.sock ke tenant-orchestrator dalam mode read-only dan mematikan read_only pada filesystem kontainernya. Akses ke soket Docker setara akses root di host. Pilihan ini diambil sadar dan alasannya tercatat sebagai komentar di berkas Compose, karena provisioning menjalankan CLI Odoo di dalam kontainer odoo-mgmt. |
| Sasaran (TARGET) | Provisioning lewat perantara berhak terbatas (socket proxy dengan daftar perintah yang diizinkan), bukan soket penuh. |
| Dampak bisnis | Satu kerentanan eksekusi kode pada orkestrator berubah menjadi penguasaan host beserta seluruh basis data tenant. |
| Rujukan | `docker-compose.multitenant.yml — blok tenant-orchestrator, mount docker.sock:ro` |

### GAP-DOC-01 · Konsol admin tidak punya referensi endpoint

|  |  |
| --- | --- |
| Area | Dokumentasi |
| Prioritas | Rendah · upaya S — di bawah 1 minggu · horizon 0-3 bulan |
| Kondisi saat ini (NOW) | hub-portal/README.md hanya berisi 24 baris perintah pengembangan dan enam variabel environment. Sekitar 20 endpoint BFF, perilaku stub demo, dan 12 halaman admin tidak terdokumentasi di mana pun selain kodenya. |
| Sasaran (TARGET) | Referensi endpoint dan peta halaman admin, diperiksa CI agar tidak tertinggal. |
| Dampak bisnis | Serah terima operasional bergantung pada membaca kode. |
| Rujukan | `hub-portal/README.md (24 baris)` · `hub-portal/server/index.mjs` |

### GAP-DOC-02 · Angka modul di dokumen arsitektur pernah menyimpang jauh

|  |  |
| --- | --- |
| Area | Dokumentasi |
| Prioritas | Rendah · upaya S — di bawah 1 minggu · horizon 0-3 bulan |
| Kondisi saat ini (NOW) | Sebelum 11 Agustus 2026, lima dari delapan baris tabel Module tiers di docs/architecture.md salah — ee_gap tertulis 78 padahal 105, _tenants tertulis 5 padahal 10. Angka itu sudah dikoreksi, dan verify.py kini membandingkan tabel tersebut dengan hasil pemindaian repo. |
| Sasaran (TARGET) | Pemeriksaan tersebut berjalan di CI bersama check_knowledge_drift.py, sehingga dua dokumen tidak bisa menyimpang lagi tanpa ketahuan. |
| Dampak bisnis | Angka yang salah di dokumen rujukan internal menular ke setiap dokumen turunan, termasuk yang dikirim ke klien. |
| Rujukan | `docs/architecture.md — tabel Module tiers` · `docs/platform-feature-catalog/verify.py — pemeriksaan #12` |

## 15.8 Peta jalan yang diusulkan

Pengelompokan di bawah ini mengikuti kolom Horizon pada tabel di atas, dan diurutkan berdasarkan risiko, bukan kemudahan.

**0–3 bulan — tutup risiko kehilangan data lebih dulu.** WAL archiving dan backup off-site yang benar-benar terpisah (GAP-BACKUP-01, GAP-BACKUP-02) adalah dua butir prioritas tinggi yang dapat diselesaikan tanpa perubahan arsitektur. Bersamaan dengan itu, sambungkan dua endpoint konsol yang masih mengembalikan data contoh, pastikan mode demo mati di lingkungan produksi, dan lengkapi referensi endpoint konsol admin.

**3–6 bulan — kurangi luas serangan dan tutup utang pengetahuan.** Ganti akses soket Docker penuh pada orkestrator dengan perantara berhak terbatas (GAP-SEC-01), dan naikkan status dokumen pengetahuan modul yang menghadap klien dari draft ke reviewed (GAP-KNOW-01).

**6–12 bulan — pisahkan lapisan.** Pemisahan host basis data, replika baca untuk pelaporan, dan host redundan (GAP-HA-01) adalah pekerjaan arsitektur, dan membuka jalan bagi permukaan business intelligence (GAP-BI-01) yang saat ini tidak ada sama sekali.

Empat kendala teknis yang harus dihormati saat pemisahan itu dikerjakan, dan sebaiknya diperiksa ulang sebelum perencanaan dimulai:

- Instans Odoo utama dan instans manajemen **harus berbagi satu klaster PostgreSQL dan satu mount filestore yang sama**. Memisahkannya membuat aset gagal dimuat.
- Nama host basis data masih ditulis langsung di berkas Compose untuk layanan Odoo; tidak ada variabel environment untuk menggantinya.
- Jalur bootstrap VPS jarak jauh mengkloning tumpukan monolit per tenant — ia tidak memisahkan lapisan.
- Model kapasitas mengasumsikan satu mesin: variabel CPU, RAM, dan disk di berkas environment bersifat tunggal.

## 15.9 Daftar modul

| Fitur | Modul | Cakupan | Brand | Kematangan | Ringkasan |
| --- | --- | --- | --- | --- | --- |
| Analisis Kesenjangan BRD | `custom_brd_analyzer` | Platform | — | Produksi | Analisis dokumen kebutuhan bisnis berbantuan AI terhadap katalog kapabilitas modul. |
| Pelacakan Siklus Pengembangan | `custom_dev_cycle` | Platform | — | Produksi | Pelacakan siklus dev penuh dengan webhook pull request dan CI dari GitHub/GitLab. |
| Konsol Hub Terpadu | `custom_hub_console` | Platform | — | Produksi | Satu pintu: tenant, katalog & deploy modul, monitoring, BRD, HHT, AI, audit. |
| Perjalanan Onboarding Tenant | `custom_onboarding_journey` | Platform | — | Produksi | Orkestrasi intake → BRD → Go/No-Go → provisioning → handover, sinkron dua arah dengan Project. |
| Monitor Operasi & Kapasitas | `custom_ops_monitor` | Platform | — | Produksi | Kesehatan server dan prakiraan kapasitas untuk operasi multi-tenant. |
| Super Admin Platform | `custom_super_admin` | Platform | — | Produksi | Kendali multi-tenant khusus ops: provision, suspend, backup, restore. |
| Infrastruktur Tenant (VPS) | `custom_tenant_infra` | Platform | — | Produksi | Siklus hidup VPS dan auto-deploy: bootstrap SSH, Docker, Caddy, stack Odoo. |

### Yang bersifat khusus per-brand

Tidak ada. Seluruh modul di domain ini berlaku umum untuk tenant mana pun, tanpa data atau konfigurasi khusus brand.

# Lampiran — Rincian Teknis per Modul

Bagian ini ditulis dalam **Bahasa Inggris**, ditujukan untuk tim pengembang dan arsitek. Isinya adalah satu entri untuk setiap dari 162 modul, diurutkan menurut domain fungsional yang sama dengan badan dokumen.

Cara membaca entri:

- **Path, Version, Depends** diambil langsung dari `__manifest__.py`.
- **Scope** memakai tiga tingkat yang dijelaskan di Bab 2.
- **Maturity / confidence** — kematangan diturunkan dari kode; keyakinan menyatakan seberapa dipercaya deskripsi di bawahnya, bukan kualitas modulnya.
- **Models / routes / tests** dihitung dengan analisis statis. Modul yang seluruhnya berupa controller sah bernilai nol model.
- Sebuah **catatan** muncul di atas deskripsi bila dokumen pengetahuan modul belum diperiksa manusia, atau bila ia ditulis terhadap versi manifest yang lebih lama. Perlakukan entri semacam itu sebagai indeks, bukan spesifikasi.

Prosa di setiap entri berasal dari tiga sumber, dengan urutan prioritas: override yang ditulis tangan untuk katalog ini, lalu `MODULE_KNOWLEDGE.md` di dalam modul, lalu ringkasan otomatis dari manifest. Setiap klaim sudah melewati gerbang audit yang membandingkannya dengan kode; model yang disebut tetapi tidak ditemukan di mana pun menyebabkan daftar model entri itu dibuang dan keyakinannya diturunkan.

## Finance & Accounting (Keuangan & Akuntansi)

### custom_account_batch_payment — Custom Batch Payments

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_account_batch_payment` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `account` |
| Models / routes / tests | 2 / 0 / 1 |

> Knowledge file is generator output, not human-reviewed.

Closes the Enterprise `account_batch_payment` gap for Community: groups posted payments of one bank journal into a batch with a draft→validated→sent→reconciled lifecycle and exports a bank transfer file using pluggable, per-bank Indonesian format records (BCA, Mandiri, BNI, BRI + generic).

**How it works**

- From the payments list, the server action `action_payments_create_batch` ("Add to Batch", bound to `account.payment`) calls `action_create_batch_from_selection()` → creates a `custom.account.batch.payment` and opens it. (Or create a batch directly via `menu_custom_batch_payment` → `action_custom_batch_payment`.)
- `action_validate()`: checks payments exist, are posted (`in_process`/`paid`), share the batch journal and direction; assigns a sequence name; sets state `validated`.
- `action_generate_export_file()`: renders the transfer file via `export_format_id.render(self)`, stores `export_file`/`export_filename`, sets state `sent`, and calls `mark_as_sent()` on the payments.
- State auto-advances to `reconciled` (computed) once every payment is `paid` and `is_matched`.
- `action_draft()` resets to draft (unmarks sent); `action_open_payments()` smart button; `unlink()` only for draft batches.

**Key models**

- `custom.account.batch.payment` (`_name`, `_inherit=["mail.thread"]`) — the batch: one bank journal, lifecycle + export.
- `custom.batch.payment.format` (`_name`) — pluggable export-file layout with per-bank renderers.
- `account.payment` (`_inherit`) — adds batch link + batch-creation action.

**Important fields**

- `custom.account.batch.payment`: `name` (Char, readonly, default "New", from sequence), `journal_id` (required, domain bank/cash, check_company, tracked), `company_id`/`currency_id` (related), `date` (required), `batch_type` (`outbound`/`inbound`, default outbound, tracked), `payment_ids` (O2m account.payment via `batch_payment_id`), `payment_count`/`amount_total` (computed), `export_format_id` (M2o format), `export_file` (Binary, attachment), `export_filename` (Char), `state` (draft/validated/sent/reconciled — computed+stored, `readonly=False`, tracked).
- `custom.batch.payment.format`: `name`, `code` (Char, required, indexed, unique `_code_uniq`), `bank_label`, `active`, `encoding` (default utf-8), `delimiter` (default ","), `date_format` (default `%d/%m/%Y`), `file_extension` (default csv), `include_header` (default True), `corporate_id`, `debit_account`, `note` (Text).
- `account.payment`: `batch_payment_id` (M2o custom.account.batch.payment, `index="btree_not_null"`, copy=False).

### custom_account_deferred — Custom Deferred Revenue & Expense

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_account_deferred` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `account` |
| Models / routes / tests | 0 / 0 / 1 |

> Knowledge file is generator output, not human-reviewed.

Closes the Enterprise deferred-revenue/expense gap for Community: users set a start/end date on invoice/bill product lines, and on posting the module books a deferral entry to a configured deferred account plus monthly, day-count-prorated recognition entries back to P&L.

**How it works**

- User sets `deferred_start_date` / `deferred_end_date` on invoice/bill product lines.
- On post, `account.move._post()` calls `_generate_deferred_entries()` for each invoice/receipt that doesn't already carry a `deferred_entry_type`.
- Per deferrable line: one **deferral** move (`entry`, `deferred_entry_type='deferral'`) reclasses the full P&L balance to the company's deferred account and is posted immediately; then one **recognition** move per month-end (`_month_ends`), day-count prorated (rounding remainder absorbed by the last month). Recognition moves dated ≤ today post now; future ones stay draft with `auto_post='at_date'` and are posted by the core autopost cron.
- Smart button `action_open_deferred_entries` on the origin lists the generated entries.
- `button_draft()` on the origin resets and unlinks all generated entries (drafting posted ones first).

**Key models**

- `account.move` (`_inherit`) — generation + cleanup logic and links.
- `account.move.line` (`_inherit`) — deferred date fields + deferrability test.
- `res.company` (`_inherit`) — deferred account/journal config.
- `res.config.settings` (`_inherit`) — settings proxies.

**Important fields**

- `account.move`: `deferred_origin_move_id` (M2o self, readonly, `index="btree_not_null"`), `deferred_entry_type` (`deferral`/`recognition`), `deferred_generated_ids` (O2m self via origin), `deferred_generated_count` (Integer computed).
- `account.move.line`: `deferred_start_date`, `deferred_end_date` (Date, both `copy=False`).
- `res.company`: `deferred_expense_account_id` (domain `asset_current`/`asset_prepayments`), `deferred_revenue_account_id` (domain `liability_current`/`liability_non_current`), `deferred_journal_id` (journal type `general`); all `check_company=True`.
- `res.config.settings`: related read-write proxies for the three company fields.

### custom_account_reconcile — Custom Account Reconciliation

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_account_reconcile` |
| Version | 19.0.3.0.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `account` |
| Models / routes / tests | 4 / 0 / 2 |

> Knowledge file is generator output, not human-reviewed.

Supplies the manual-reconciliation UI that Odoo Community lacks: an overview dashboard of reconcilable accounts with open items, a "Reconcile" wizard for selected journal items, and a bank-statement-line matching wizard. The reconciliation itself is delegated to core CE `account.move.line.reconcile()` / `account.bank.statement.line._reconcile_with_amls()` — this module is UI + candidate scoring, not a new engine.

**How it works**

- **Overview**: `Accounting → Reconciliation → Reconcile` opens `action_custom_reconcile_overview` (list of `custom.reconcile.account`). Row button `action_open_lines` drills into that account's posted, unreconciled `account.move.line`s.
- **Journal-items reconcile**: the `account.move.line` list contextual action `action_custom_reconcile_lines` ("Reconcile") opens `custom.account.reconcile.wizard`. `default_get` validates the selection; `action_reconcile` reconciles directly when balanced, or in `writeoff` mode calls `_create_writeoff_line()` (posts a balancing entry) then `reconcile()`.
- **Bank matching**: `action_custom_bank_reconciliation` lists posted `account.bank.statement.line`s; per-row `action_open_match_wizard` opens `custom.bank.reconcile.wizard`; `action_reconcile` calls `st_line._reconcile_with_amls(...)`. The "Auto-match" server action `action_st_lines_auto_match` calls `records.action_auto_match()`.

**Key models**

- `custom.reconcile.account` (`_auto=False` SQL view) — one row per reconcilable account carrying posted unreconciled lines; `id = account.id`. Aggregates span ALL companies sharing the account.
- `custom.account.reconcile.wizard` (TransientModel) — manual reconcile of selected journal items.
- `custom.bank.reconcile.wizard` + `custom.bank.reconcile.wizard.line` (TransientModel) — bank-statement-line matching + candidate rows.
- `account.bank.statement.line` (`_inherit`) — candidate search + reconcile mechanics.
- `account.move` (`_inherit`) — `button_draft` unreconciles before resetting.
- `account.move.line` (`_inherit`) — refuses structural edits on a matched line.
- `account.payment` (`_inherit`) — duplicate guard at posting + the Unapplied flag.

**Important fields**

- `custom.reconcile.account`: `account_id` (M2o account.account), `line_count` (Integer), `debit`/`credit`/`residual` (Monetary), `oldest_date` (Date), `currency_id` (computed from `env.company`, `@api.depends_context("company")`).
- `custom.account.reconcile.wizard`: `line_ids` (M2m account.move.line, readonly), `account_id`, `company_id`, `debit`/`credit`/`residual` (Monetary), `is_balanced` (Boolean), `mode` (`partial`/`writeoff`, default `partial`), `writeoff_account_id`/`writeoff_journal_id` (check_company, domain-restricted), `writeoff_date`, `writeoff_label` (default "Write-Off").
- `custom.bank.reconcile.wizard`: `st_line_id` (required), `candidate_ids` (O2m wizard.line), `selected_total`/`remainder` (Monetary computed), `writeoff` (Boolean), `writeoff_account_id` (domain excludes receivable/payable), `writeoff_label`.
- `custom.bank.reconcile.wizard.line`: `selected` (Boolean), `aml_id` (M2o account.move.line), `amount_residual` (related), plus related move/date/account/partner.
- `account.payment`: `duplicate_checked` (Boolean, `copy=False`) — the explicit override that lets a genuine second payment post; `is_unapplied` (Boolean, stored compute on `state`/`is_reconciled`) — posted (`in_process`/`paid`) but settling nothing.

### custom_accounting_asset — Custom Accounting - Fixed Assets

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_accounting_asset` |
| Version | 19.0.0.5.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM, Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `custom_accounting_reports`, `account` |
| Models / routes / tests | 11 / 0 / 1 |
| Tags | accounting, fixed-assets, depreciation, audit-trail |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.2.0, module is now 19.0.0.5.0.

Fixed-asset register for Odoo CE — closes the EE `account_asset` gap. Maintains a per-company asset master file with hierarchical locations and groups (each with default useful life + default G/L accounts), generates straight-line or double-declining depreciation schedules, and runs a monthly cron that posts `DR depreciation_expense / CR accumulated_depreciation` journal entries for due lines. A disposal wizard captures sale value, computes gain/(loss) vs NBV, and books the retirement entry.

This is the canonical FA module. Anything BRD-related to "aset tetap", "penyusutan", "depreciation schedule", "disposal", "NBV" lives here.

**How it works**

- Set up a `custom.fixed.asset.group` (default useful life, default asset/accum/expense accounts, default journal).
- Set up a `custom.fixed.asset.location` tree (`_parent_store=True`, recursive `complete_name`).
- Create a `custom.fixed.asset` in `draft`; `code` auto-assigned from `ir.sequence("custom.fixed.asset")`. `_onchange_group_id` copies group defaults into asset.
- `action_confirm()` requires expense + accumulated + journal accounts when `depreciation_method != "none"`; calls `_build_schedule()` then transitions `draft`→`running`. The schedule generator writes `custom.fixed.asset.depreciation.line` rows dated via `_depreciation_date_for(seq)` for `useful_life_months` periods. Straight-line uses `round(remaining/months_left, 2)` per month with rounding residual absorbed in the last line; declining uses `factor/total_months * NBV` with straight-line residual on the final period.
- **Depreciation dates are anchored on `posting_date`** (falls back to `acquisition_date` when empty) and shaped by `depreciation_date_mode`: `specific` (line 1 == posting date), `next_month` (default; line 1 == posting date + 1 month, the legacy behavior), `end_following_month` (last day of the month `seq` months after the anchor). `posting_date` defaults to `acquisition_date` on create.
- Monthly cron `_cron_post_due_depreciation` (calls `_post_due_depreciation()`): walks all `state='running'` assets, posts each unposted line whose `date <= today` as one `account.move` per line (DR expense / CR accumulated), flips `line.posted=True` and `line.move_id`.
- **Bulk manual posting**: the `custom.fixed.asset.post.wizard` (menu *Assets → Post Depreciation*) posts every running asset's due lines up to a chosen `cutoff_date` (optional group/location/company filters); the `action_post_due_depreciation_server` server action (list *Action* menu) calls `action_post_selected()` on the selected assets as of today. Both delegate to `_post_due_depreciation`.
- `action_open_dispose_wizard()` (running-only) opens `custom.fixed.asset.disposal.wizard`. The wizard computes `gain_loss = disposal_value - net_book_value` and, on `action_dispose()`, creates a balanced retirement move: DR accum + DR proceeds + DR loss / CR asset cost + CR gain. **Asset cost released = `acquisition_value + revaluation_value`** (full carrying). **If `revaluation_surplus_balance > 0` the move also transfers it DR revaluation surplus / CR retained earnings (IAS 16.41, equity-to-equity, not through P&L) and the balance is cleared.** Asset is written to `disposed` with `disposal_date`, `disposal_value`, `disposal_gain_loss`, `disposal_move_id`.
- **Revaluation** (running-only): `action_open_revaluation_wizard()` opens `custom.fixed.asset.revaluation.wizard`. The user enters a `new_value` (new carrying/NBV) and an optional revised `new_remaining_life`. `action_revalue()` books a balanced adjustment move **split per IAS 16** and tracks two running balances on the asset (`revaluation_surplus_balance`, `revaluation_loss_recognized`):
- **Upward** (increment > 0): DR asset `increment`; the credit reverses any prior expensed decrease first — CR revaluation income `min(increment, loss_recognized)` — then CR revaluation surplus for the remainder.
- **Downward** (increment < 0): CR asset `decrease`; the debit offsets any existing surplus first — DR revaluation surplus `min(decrease, surplus_balance)` — then DR revaluation loss for the remainder. It adds the increment to `revaluation_value`, optionally sets `useful_life_months = posted_count + new_remaining_life`, then calls `_build_schedule()` to re-spread the new remaining base over the remaining life. **Prospective: previously posted lines/moves are never touched.** A `custom.fixed.asset.revaluation` history record captures each event (amounts, account split, running balances after). Default surplus/loss/income/retained-earnings accounts come from the asset group (`custom.fixed.asset.group.default_revaluation_*`).
- `action_cancel()` allowed only if no depreciation has posted; `action_reset_draft()` unlinks all schedule lines and reverts to draft.
- Manual single-line posting via `custom.fixed.asset.depreciation.line.action_post_now()` (delegates to `_post_due_depreciation(as_of=line.date)`).

**Key models**

- `custom.fixed.asset` — asset master (acquisition + accounts + state machine + schedule O2m). Inherits `mail.thread` + `mail.activity.mixin` + `pdp.audited.mixin`.
- `custom.fixed.asset.group` — category w/ default useful life + default accounts + default journal.
- `custom.fixed.asset.location` — hierarchical (`_parent_store`) physical location; computed `complete_name`.
- `custom.fixed.asset.depreciation.line` — one row per scheduled period; `posted` + `move_id` set when GL booked.
- `custom.fixed.asset.revaluation` — persistent history record of each revaluation (date, NBV before, new value, adjustment, life before/after, accounts, `move_id`); O2m `revaluation_ids` on the asset.
- `custom.fixed.asset.disposal.wizard` (TransientModel) — captures disposal_date + disposal_value + gain/loss accounts.
- `custom.fixed.asset.revaluation.wizard` (TransientModel) — captures new_value + optional new_remaining_life + surplus/loss/journal; books the adjustment move and rebuilds the schedule tail.
- `custom.fixed.asset.post.wizard` (TransientModel) — bulk-posts due depreciation up to `cutoff_date` with optional group/location/company filters.

**Important fields**

- `custom.fixed.asset.state` (Selection draft/running/disposed/cancelled) — only `running` is depreciated; `disposed` is terminal.
- `custom.fixed.asset.code` (Char, unique per company via `code_company_unique`) — auto from sequence.
- `custom.fixed.asset.acquisition_value` / `salvage_value` (Monetary) — `_check_salvage` bans `salvage > acquisition` and negatives.
- `custom.fixed.asset.useful_life_months` (Integer, default 60) — must be ≥1 when method ≠ none. Revaluation may rewrite this to `posted_count + new_remaining_life`.
- `custom.fixed.asset.posting_date` (Date) — depreciation schedule anchor; falls back to `acquisition_date` when empty.
- `custom.fixed.asset.depreciation_date_mode` (Selection specific/next_month/end_following_month, default next_month) — how each line date is derived from `posting_date`.
- `custom.fixed.asset.revaluation_value` (Monetary, readonly, default 0) — net cumulative revaluation booked to the asset account; folded into `_depreciable_base` and `net_book_value`.
- `custom.fixed.asset.revaluation_surplus_balance` (Monetary, readonly, default 0) — equity surplus held for this asset; offset by downward revaluations and transferred to retained earnings on disposal.
- `custom.fixed.asset.revaluation_loss_recognized` (Monetary, readonly, default 0) — cumulative expensed decrease reversed (as income) by a later upward revaluation before crediting surplus.
- `custom.fixed.asset.group.default_revaluation_surplus_account_id` / `default_revaluation_loss_account_id` / `default_revaluation_income_account_id` / `default_retained_earnings_account_id` — revaluation account defaults pulled into the revaluation/disposal wizards.
- `custom.fixed.asset.depreciation_method` (Selection straight_line/declining/none) — `none` skips schedule entirely.
- `custom.fixed.asset.declining_factor` (Float, default 2.0) — factor for double-declining (2.0 = DDB).
- `custom.fixed.asset.asset_account_id` / `depreciation_account_id` / `expense_account_id` (M2o `account.account`) — overrides group defaults.
- `custom.fixed.asset.journal_id` (M2o `account.journal`, type=general) — depreciation journal.
- `custom.fixed.asset.accumulated_depreciation` / `net_book_value` (Monetary, computed, non-stored) — `sum(posted lines)` and `acquisition + revaluation_value - accum`.
- `custom.fixed.asset.disposal_date` / `disposal_value` / `disposal_gain_loss` / `disposal_move_id` (readonly, set by wizard).
- `custom.fixed.asset.depreciation.line.posted` (Boolean) — gates the cron; once True the line is immutable to the cron.
- `custom.fixed.asset.depreciation.line.sequence` (Integer, required) — drives schedule order; new lines built from `max(sequence)+1`.

### custom_accounting_full — Custom Accounting Full

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_accounting_full` |
| Version | 19.0.0.5.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `account`, `analytic`, `sale_management`, `purchase`, `mail`, `l10n_id_psak_custom` |
| Models / routes / tests | 21 / 0 / 11 |
| Tags | accounting, intercompany, consolidation, audit-trail, approval-workflow |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.3.0, module is now 19.0.0.5.0.

Canonical multi-company accounting EE-gap module: closes the delta between Odoo CE `account` and the EE `account_consolidation` + `account_inter_company_rules` + `account_followup` + `account_3way_match` + `account_reconcile_oca` bundles. Owns the Indonesian PSAK-aligned chart template (`id_psak`), the intercompany mirror engine, two distinct consolidation models (perimeter-based + group-COA based), the fiscal-year lock workflow, bank-statement auto-reconcile rules, customer credit-limit enforcement, customer follow-up ladders, and 3-way matching (PO ↔ GRN ↔ vendor bill).

This is the umbrella accounting module — anything described in a BRD as "intercompany", "consolidation", "eliminations", "credit limit", "follow-up", "3-way match", "fiscal year close", "auto-reconcile" or "branch/cost-centre" lives here. Other ee_gap modules (`custom_accounting_asset`, `custom_accounting_recurring`, `custom_accounting_reports`) depend on this one.

**How it works**

- **Indonesian COA** install: `account.chart.template` `@template("id_psak")` ships a 5-digit PSAK chart — 53 accounts (1xxxx Aset … 8xxxx Pajak Penghasilan), 12 account groups for hierarchical reports, PPN 11% keluaran/masukan taxes + 1 tax group (PMK 58/2022 rate), 6 journals (INV/BILL/CASH/BANK/MISC/EXCH) with Bahasa Indonesia labels, and 2 fiscal positions (Ekspor, Pelanggan Bebas Pajak). PPh withholding (23, 4(2), 26) intentionally deferred. Company onboarding selects this template from Settings → Accounting.
- **Intercompany mirror**: `account.move._post` calls `_custom_run_intercompany_mirror()`; if `partner_id.commercial_partner_id` matches another `res.company.partner_id` and an active `account.intercompany.rule` exists with matching `direction`, `_custom_create_intercompany_mirror(rule)` creates a draft `account.move` in the receiving company with mapped accounts (via `account.intercompany.account.mapping`) and links `x_custom_ic_mirror_id` ↔ `x_custom_ic_source_id`. Optional `auto_validate` posts the mirror.
- **Consolidation (perimeter style)**: an `account.consolidation.config` declares parent + subsidiaries + elimination accounts. `build_trial_balance(date_from, date_to)` runs `_compute_balances` (read_group on `account.move.line`) → `_compute_eliminations` → returns a pivoted dict per account with `by_company` columns + `elimination` + `consolidated`. Audit row written via `_audit_report_run`.
- **Consolidation (group-COA style)**: a `custom.consolidation.chart` declares a group-COA with `custom.consolidation.chart.account` children + per-company `custom.consolidation.mapping` (local `account.account` → group account, with `fx_method` and `weight`). State `draft`→`locked` via `action_lock`.
- **Elimination workflow**: `custom.elimination.rule` defines an account pair (`account_a_id` in `company_a_id` ↔ `account_b_id` in `company_b_id`); `custom.elimination.proposal.action_compute()` aggregates posted lines, fills `custom.elimination.proposal.line` rows, sets `state=proposed`. `action_post()` calls `_make_elimination_move()` → creates a balanced `account.move` debiting A / crediting B for `total_amount = min(|a_amount|, |b_amount|)`. `action_reject` / `action_cancel` provided.
- **Lock dates**: Accounting → Configuration → Lock Dates opens `custom.account.lock.date.wizard`, which writes the four *soft* lock dates onto `res.company` (`fiscalyear_lock_date`, `tax_lock_date`, `sale_lock_date`, `purchase_lock_date`). CE enforces those fields everywhere but ships no UI — EE keeps it in `account_accountant`. `hard_lock_date` is deliberately not offered: core refuses to remove or decrease it, so a mis-click would be unrecoverable. The wizard warns when draft entries still sit on or before the Global Lock Date.
- **Fiscal year**: `custom.fiscal.year` records (one per `company_id` × non-overlapping date range) progress `draft`→`open`→`closed`; close is run from `custom.fiscal.year.close.wizard`.
- **Bank auto-reconcile cron**: `custom.reconcile.rule._cron_auto_reconcile` walks unmatched `account.bank.statement.line` per company; each line calls `_custom_apply_reconcile_rules` → for each applicable `custom.reconcile.rule`, `_candidate_move_lines` searches receivable/payable AMLs within `match_date_window_days`, filtered by `_line_matches` (amount within `amount_tolerance`, regex match on `payment_ref/ref/narration`). Best candidate auto-reconciles when `rule.auto_validate=True`.
- **Customer credit limit**: `sale.order.action_confirm` is overridden to call `_custom_credit_check`; reads `partner.custom_credit_limit` + `custom_outstanding_amount`; if `projected > limit` and `method=='block'` raises `UserError`, if `'warn'` posts a chatter warning. Every check writes a `custom.credit.check.log` row.
- **Follow-up ladder**: `custom.followup.level._cron_apply_followup` queries partners with posted unreconciled receivable lines past `date_maturity`; per partner `_custom_advance_followup_level` bumps `custom_followup_level_id` to the highest matching `delay_days`, and `_custom_send_followup_email_if_due` dispatches `email_template_id` respecting `custom_followup_next_date` throttle (`max(7, delay_days/2)` days).
- **Unique vendor bill reference**: `account.move._post` for `in_invoice`/`in_refund` runs `_custom_find_duplicate_bill_ref` per move; if another non-cancelled move for the same `commercial_partner_id` + `company_id` + `move_type` already carries the same (stripped) `ref`, it raises `UserError`. This hard-blocks what Odoo CE only surfaces as the soft `duplicated_ref_ids` banner. Empty refs are never duplicates. Search runs in `sudo()` so a duplicate hidden by record rules still triggers the block.
- **3-way match**: `account.move._post` for `in_invoice` runs `_custom_run_three_way_match`. Per bill line with a `purchase_line_id`, computes qty variance vs `qty_received` and price variance vs PO `price_unit`; line `status` is `pass`/`qty_variance`/`price_variance`/`both`. Overall result stored on `custom.match.result` + `custom.match.line.result`. `policy.on_qty_mismatch` / `on_price_mismatch` ∈ {`warn`,`block`} — `block` raises `UserError` and prevents posting.
- **Analytic branch dim**: `account.analytic.account.x_custom_branch_code` + `x_custom_is_branch_root` + `x_custom_parent_id` + computed `x_custom_branch_root_id` (recursive) for kantor-cabang reporting (Odoo 19 no longer ships `account.analytic.account.parent_id`).

**Key models**

- `account.intercompany.rule` — Declarative mirror policy (`company_from_id` → `company_to_id`, `direction` ∈ `sale_to_purchase`/`purchase_to_sale`/`both`, `target_journal_id`, `auto_validate`).
- `account.intercompany.account.mapping` — Per-rule source→target `account.account` pairs; `_check_company_alignment` ensures accounts belong to the right company's chart.
- `account.consolidation.config` — Perimeter (parent + subsidiaries + elimination accounts + presentation currency); exposes `build_trial_balance`, `_compute_balances`, `_compute_eliminations`.
- `custom.consolidation.chart` — Group-COA root (`_check_company_auto=True`, state `draft`/`locked`, `mail.thread`).
- `custom.consolidation.chart.account` — Account in the group COA (`account_category` ∈ asset/liability/equity/income/expense/off_bs).
- `custom.consolidation.mapping` — Per-(`chart_id`,`company_id`,`source_account_id`) → group `target_account_id` with `fx_method` (`avg`/`closing`/`historical`) + `weight`.
- `custom.elimination.rule` — Eliminate `account_a_id` in `company_a_id` against `account_b_id` in `company_b_id`; optional `match_partner_id`, `threshold_amount`, legacy `match_type`.
- `custom.elimination.proposal` — Workflow `draft`/`proposed`/`posted`/`rejected`/`cancelled`; produces an `account.move` via `_make_elimination_move`.
- `custom.elimination.proposal.line` — Computed source-balance row (per company × account).
- `custom.fiscal.year` — Non-overlapping period per `company_id`; `draft`/`open`/`closed`.
- `custom.reconcile.rule` — Bank reconcile rule (journals, `match_partner`, `match_amount` + `amount_tolerance`, `match_reference_regex`, `match_date_window_days`, `payment_match_partner_field`, `auto_validate`).
- `account.bank.statement.line` (inherited) — Adds `custom_reconcile_rule_id` + `custom_auto_matched`.
- `res.partner` (inherited) — Adds `custom_credit_limit`, `custom_credit_limit_check_method`, computed `custom_outstanding_amount`/`custom_credit_available`; also `custom_followup_level_id`, `custom_followup_last_sent`, `custom_followup_next_date`, computed `custom_max_overdue_days`.
- `custom.credit.check.log` — Append-only audit row per `sale.order` credit check; `decision` ∈ pass/allowed/warn/warned/blocked.
- `sale.order` (inherited) — `action_confirm` calls `_check_credit_limit` → `_custom_credit_check`.
- `custom.followup.level` — Ladder rung (`delay_days`, `action`, `email_template_id`).
- `custom.followup.stat.by.partner` — `_auto=False` SQL view aggregating overdue per partner.
- `custom.match.policy` — `qty_tolerance_percent`, `price_tolerance_percent`, `on_qty_mismatch`/`on_price_mismatch`.
- `custom.match.result` / `custom.match.line.result` — Per-bill / per-line outcome.
- `account.move` (inherited) — Adds `x_custom_ic_mirror_id`, `x_custom_ic_source_id`, `x_custom_ic_rule_id`, `custom_match_result_id`, `custom_match_status`; inherits `pdp.audited.mixin`.
- `account.analytic.account` (inherited) — `x_custom_branch_code`, `x_custom_is_branch_root`, `x_custom_parent_id`, computed `x_custom_branch_root_id`.
- `res.company` (inherited) — `x_custom_ic_enabled` kill-switch; `_sister_companies()` helper.

**Important fields**

- `account.intercompany.rule.direction` (Selection) — drives `account.move._custom_find_intercompany_rule` matching against `move_type`.
- `account.intercompany.rule.auto_validate` (Boolean) — when True the mirror is posted automatically.
- `account.move.x_custom_ic_mirror_id` / `x_custom_ic_source_id` (M2o `account.move`) — idempotency guard; never re-mirror if `x_custom_ic_mirror_id` already set.
- `account.consolidation.config.elimination_account_ids` (M2m `account.account`) — accounts whose perimeter balances are netted; residual is the "elimination" column.
- `account.consolidation.config.presentation_currency_id` (M2o, required) — FX consolidation currency; FX rate methods are declared per-mapping not per-config.
- `custom.consolidation.mapping.fx_method` (Selection avg/closing/historical) — per-account FX conversion rule.
- `custom.consolidation.mapping.weight` (Float, default 1.0) — multiplier for partial ownership / JV consolidation.
- `custom.elimination.proposal.total_amount` (Monetary) — `min(|a_amount|, |b_amount|)`; the netting amount used for the elimination move.
- `custom.fiscal.year.state` (Selection draft/open/closed) — `_check_dates_and_overlap` blocks overlap on the same `company_id`.
- `custom.reconcile.rule.match_reference_regex` (Char) — Python regex tested against `payment_ref or ref or narration`; `_check_regex` compiles at constraint time.
- `custom.reconcile.rule.amount_tolerance` (Float) — absolute tolerance for `|stmt.amount| - |aml.amount_residual|` (defaults to 0.005 fudge inside `_line_matches`).
- `res.partner.custom_credit_limit_check_method` (Selection none/warning/block) — drives `_custom_credit_check` action.
- `custom.followup.level.delay_days` (Integer) — minimum overdue threshold; `_custom_advance_followup_level` picks highest matching tier.
- `custom.match.result.overall_status` (Selection: pass/match/qty_variance/qty_mismatch/price_variance/price_mismatch/both/both_mismatch/no_po/error) — exposed via related `account.move.custom_match_status`.
- `account.analytic.account.x_custom_branch_root_id` (M2o, recursive compute) — entire branch subtree resolution.

### custom_accounting_recurring — Custom Accounting Recurring

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_accounting_recurring` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `account` |
| Models / routes / tests | 3 / 0 / 1 |
| Tags | accounting, recurring, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Two scheduled-recurrence engines that close the CE-side gap against EE `account_accountant`'s recurring entries: (1) `custom.recurring.journal.template` produces balanced `account.move` entries on a monthly/quarterly/yearly cadence (lease accruals, prepaid amortisation, manual recurring postings); (2) `custom.recurring.payment.template` produces inbound/outbound `account.payment` records on the same cadence (standing-order vendor payments, recurring customer collections).

Both engines share the same period machinery (`relativedelta` map), the same `end_date` semantics, and the same `pdp.audited.mixin` audit trail.

**How it works**

- Operator creates a `custom.recurring.journal.template` with `journal_id` (general), `period` ∈ monthly/quarterly/yearly, `next_date`, optional `end_date`, `auto_post`, and a balanced set of `custom.recurring.journal.template.line` rows (debit OR credit per line; `_check_balanced` enforces total_debit==total_credit; `_check_amounts` enforces a line cannot have both).
- `action_run_now()` (manual) or `_cron_generate_due()` (`@api.model`, daily) calls `_generate_one()` on every active template whose `next_date <= today`.
- `_generate_one()` creates an `account.move` (`move_type='entry'`, `custom_recurring_template_id=self.id`); if `auto_post`, posts immediately; advances `next_date` by `PERIOD_OFFSETS[period]` and stamps `last_generated_at`.
- Cron is resilient — exceptions are logged + `cr.rollback()` per template so one bad template doesn't break the batch.
- Payment template is parallel: `partner_id`, `payment_type` ∈ `inbound`/`outbound`, `journal_id` (bank/cash), `amount` (positive), and same period+next_date+end_date+auto_post+cron loop. `_generate_one()` creates `account.payment` with `partner_type` derived from `payment_type` (`customer` for inbound, `supplier` for outbound), optionally posts.
- Generated moves are surfaced on the template via `generated_move_ids` (`account.move.custom_recurring_template_id`).

**Key models**

- `custom.recurring.journal.template` — Header. Inherits `pdp.audited.mixin` + `mail.thread`. Code from sequence `custom.recurring.journal.template`.
- `custom.recurring.journal.template.line` — `account_id` + `partner_id` + `debit`/`credit` + `analytic_distribution` (Json, same shape as `account.move.line.analytic_distribution`).
- `custom.recurring.payment.template` — Header for payments. Inherits `pdp.audited.mixin` + `mail.thread`.
- `account.move` (inherited) — Adds back-ref `custom_recurring_template_id`.

**Important fields**

- `custom.recurring.journal.template.period` (Selection monthly/quarterly/yearly) — looked up in module-level `PERIOD_OFFSETS = {monthly: relativedelta(months=1), quarterly: relativedelta(months=3), yearly: relativedelta(years=1)}`.
- `custom.recurring.journal.template.next_date` (Date, required) — the *next* posting date; advances by period after each run.
- `custom.recurring.journal.template.end_date` (Date) — soft termination; cron skips when `next_date > end_date`.
- `custom.recurring.journal.template.auto_post` (Boolean, default True) — when False the move is left in draft.
- `custom.recurring.journal.template.code` (Char, readonly) — from `ir.sequence("custom.recurring.journal.template")`.
- `custom.recurring.journal.template.last_generated_at` (Datetime, readonly) — stamped by `_generate_one`.
- `custom.recurring.journal.template.line.debit` / `credit` (Monetary) — `_check_amounts` requires exactly one of the two to be set per line; `_check_balanced` requires total_debit == total_credit at the header level.
- `custom.recurring.journal.template.line.analytic_distribution` (Json) — `{analytic_account_id: percentage, ...}`, copied verbatim onto the generated `account.move.line`.
- `custom.recurring.payment.template.payment_type` (Selection inbound/outbound) — maps to `partner_type` automatically.
- `custom.recurring.payment.template.amount` (Monetary) — `_check_amount` requires > 0.
- `account.move.custom_recurring_template_id` (M2o, readonly, indexed) — back-pointer; `One2many` exposed as `generated_move_ids`.

### custom_accounting_reports — Custom Accounting Reports

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_accounting_reports` |
| Version | 19.0.0.19.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM, Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `account` |
| Models / routes / tests | 85 / 0 / 1 |
| Tags | accounting, financial-reports, audit-trail |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.18.0, module is now 19.0.0.19.0.

This module closes the Enterprise gap on Odoo CE `account_reports`. It provides a comprehensive suite of financial reports for the Custom Platform — P&L, Balance Sheet, Cash Flow (indirect method), General Ledger, Trial Balance, Partner Ledger, Partner Cards, Aged Receivable/Payable, Tax (PPN/PPh), Day/Cash/Bank Book, Journal Audit, Down-Payment (Uang Muka) ledger, Sales, and a tree-driven custom Financial Report. All reports are built on a single shared `custom.report.engine` AbstractModel and render to QWeb PDF/HTML or XLSX.

**How it works**

- **User Selection**: The user opens a report from the menu (e.g., Trial Balance, General Ledger).
- **Wizard Input**: A transient wizard (`custom.report.*.wizard`, under `wizard/`) collects filters such as date range, companies, journals, accounts, partners, and posted-only.
- **Report Generation**: The wizard normalises its fields into a `filters`/`options` dict and hands off to the matching report model, which runs parameterised SQL against `account_move_line` via the engine helpers and builds report lines.
- **Export/View**: Output is rendered as a QWeb PDF/HTML report (via the shared dispatch model) or exported to XLSX. Each run is written to the `pdp.audit_log` audit trail.

**Key models**

- `custom.report.engine` — **AbstractModel base.** Filter normalisation, raw-SQL aggregation (`_get_account_balances`, `_get_move_lines_query`, `_sum_by_account`), XLSX export, render context, and PDP audit logging.
- `report.custom_accounting_reports.report_dispatch` — **AbstractModel.** QWeb report dispatcher; maps a `report_code` to the target report model and returns its computed context.
- `custom.report.general.ledger` — General Ledger.
- `custom.report.trial.balance` — Trial Balance (default dispatch target).
- `custom.report.profit.loss` — Profit & Loss, bucketed by `account.group` (GROUP 1 code prefix), falling back to `account_type`.
- `custom.report.profit.loss.branch` — Profit & Loss with one amount column per branch; inherits `custom.report.profit.loss`. Reached from the P&L wizard's *View / Export by Branch* buttons (it owns no wizard, so no tenant needs a schema upgrade).
- `custom.report.balance.sheet` — Balance Sheet (Asset / Liability / Equity by account type, nested by `account.group`), including a computed **Current Year Earnings** equity line.
- `custom.report.cash.flow` — Cash Flow Statement (indirect method).
- `custom.report.partner.ledger` — Partner Ledger.
- `custom.report.partner.card.base` — Partner card base, subclassed by `custom.report.payable.card` and `custom.report.receivable.card`.
- `custom.report.aged.receivable` — Aged Receivable; `custom.report.aged.payable` inherits it.
- `custom.report.ar.aging.export` — AR Aging Export. Inherits `custom.report.aged.receivable` for its open-line query, but replaces the layout: one **flat** row per open receivable line carrying the commercial trail (customer PO / SO / DO), the tax split (DPP / PPN / Full), the settlement figures (Original / Paid / Outstanding) and fifteen *overdue-day* buckets (`<= 0`, then 1…7 day by day, `8-14`, `15-30`, `31-60`, `61-90`, `91-120`, `121-360`, `> 360`). Reached from the **AR Aging Export** menu, which opens the Aged Receivable wizard with `ar_aging_export` in the context.
- `custom.report.advance` — Uang Muka / Down-Payment ledger (auto-detects advance accounts).
- `custom.report.sales` — Sales report.
- `custom.report.tax` — Tax report (PPN / PPh subtotals; cross-references Coretax).
- `custom.report.book.mixin` — Day/Cash/Bank book mixin, subclassed by `custom.report.day.book`, `custom.report.cash.book`, `custom.report.bank.book` (three distinct models).
- `custom.report.journal.audit` — Journal Audit.
- `custom.report.financial` — **Concrete `models.Model`.** The only ORM model with stored fields; a self-referential tree defining custom financial-report line structure. Rendered by the `custom.report.financial.renderer` AbstractModel.

**Important fields**

- **custom.report.financial** (the only model with fields)
- `parent_id` / `child_ids`: self-referential tree (`custom.report.financial`).
- `account_ids`: `Many2many` to `account.account`.
- `company_id`: `Many2one` to `res.company`.
- `code`, `name`: used to compute the display name `[code] name`.
- **custom.report.advance.wizard**
- `account_ids`: `Many2many` to `account.account`.
- `company_ids`: `Many2many` to `res.company`.
- `date_from`, `date_to`: report date range.
- `posted_only`: `Boolean` (default `True`).
- **custom.report.aged.receivable.wizard / aged.payable.wizard**
- `partner_ids`: `Many2many` to `res.partner`.
- `detail_mode`: `Selection` switching summary vs. detail layout, **defaulting to `detail`**. (Note: `aging_detail` is only a **context key** derived from `detail_mode == "detail"`, not a field.)
- **Cash Flow bucketing** — `custom.report.cash.flow` has no `account_type` field. Buckets are defined by module-level tuples `OPERATING_TYPES`, `INVESTING_TYPES`, `FINANCING_TYPES`, `CASH_TYPES` matched against each row's Odoo `account_type`.

### custom_arka_aim_asset_register — ARKA-AIM Drone Fixed-Asset Register

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_arka_aim_asset_register` |
| Version | 19.0.2.0.0 |
| Scope | Khusus brand (ARKA-AIM) |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_accounting_asset` |
| Models / routes / tests | 0 / 0 / 0 |

> Knowledge file is generator output, not human-reviewed.

### custom_arka_aim_opening_balance — ARKA-AIM Opening Balances (31 May 2026)

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_arka_aim_opening_balance` |
| Version | 19.0.2.0.0 |
| Scope | Khusus brand (ARKA-AIM) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `account` |
| Models / routes / tests | 0 / 0 / 0 |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.1.0.0, module is now 19.0.2.0.0.

This module loads the beginning balances for PT Aero Inovasi Media (AIM) and
PT Aero Reksa Kreasi Angkasa (ARKA) as of 31 May 2026. It creates a handful of
missing bank/deposit accounts, then posts one balanced opening journal entry per
company. It defines no models, wizards, views, or controllers — all behavior runs
at install time via a `post_init_hook`.

**How it works**

- `_ensure_missing_accounts` reads `data/missing_accounts.csv` and creates any of the 5 `asset_cash` accounts that do not yet exist for their company (AIM: 1103019270, 1103019280; ARKA: 1103019290, 1103019300, 1105020007). Existing accounts are skipped (hooks.py:58).
- For each company (resolved by name), `_post_company_opening` reads the per-company opening CSV, resolves each row's account by (company, code), builds the journal lines, and creates + posts one `account.move`.
- The move is posted (`action_post`) on 31 May 2026 with ref "Saldo Awal 31 Mei 2026", on the company's `general` (Miscellaneous) journal.

**Key models**

- **None** — this module defines no classes and no models. It only *creates* records of existing models (`account.account`, `account.move`) via `.create`.

**Important fields**

- None. No fields are defined or extended.

### custom_arka_aim_seed — ARKA-AIM Chart of Accounts Seed

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_arka_aim_seed` |
| Version | 19.0.1.0.0 |
| Scope | Khusus brand (ARKA-AIM) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `account`, `base`, `product` |
| Models / routes / tests | 0 / 0 / 0 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Tenant-specific CoA, taxes, and fiscal positions for erp_dev_aimarka. ARKA-AIM Chart of Accounts seed.

### custom_arka_fx_header — ARKA-AIM Foreign-Currency Invoice Header

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_arka_fx_header` |
| Version | 19.0.1.1.0 |
| Scope | Khusus brand (ARKA-AIM) |
| Maturity / confidence | Beta / Sedang |
| Depends | `account` |
| Models / routes / tests | 0 / 0 / 0 |

> Knowledge file is generator output, not human-reviewed.

Puts the **foreign-currency total** and the **applied exchange rate** into the
header of a customer invoice / vendor bill whose currency differs from the
company currency, so an approver sees both without scrolling and without
mentally inverting a rate. Since 19.0.1.1.0 the same context is added to the
**Register Payment** popup. Display only — no posting, amount, or rate used by
the accounting engine is changed, and there is no schema change.

**How it works**

- A user opens an invoice/bill written in a non-company currency.
- `x_fx_is_foreign` computes True, revealing an `alert alert-info` block injected directly after the `oe_title` div (i.e. under the document number).
- The block renders `amount_total` with the `monetary` widget (already in the document currency) and the rate as `1 <currency_id> = <x_fx_rate_company_per_unit> <company_currency_id>`.
- On a same-currency document, or on a `move_type == 'entry'`, the block is invisible and the form is byte-for-byte the stock layout.

**Key models**

- `account.move` (inherited) — adds two non-stored computed display helpers. No overrides of any core method.
- `account.payment.register` (inherited `TransientModel`) — adds four non-stored computed display helpers. No overrides of any core method.

**Important fields**

- `account.move.x_fx_is_foreign` (Boolean, computed, **non-stored**) — True when `move_type` is in `out_invoice/out_refund/out_receipt/in_invoice/in_refund/ in_receipt` **and** `currency_id != company_currency_id`. Journal entries (`entry`) are deliberately excluded: a raw entry has no single document currency, so the block would be misleading.
- `account.move.x_fx_rate_company_per_unit` (Float, `digits=(16, 4)`, computed, **non-stored**) — `1 / invoice_currency_rate`, i.e. how many units of company currency one unit of the document currency is worth. Guarded against a zero rate (returns 0.0 rather than raising `ZeroDivisionError`); real data with `invoice_currency_rate == 0.0` exists on `trn_arkaaim`.
- `account.payment.register.x_fx_is_foreign` (Boolean) — `source_currency_id` differs from `currency_id`.
- `account.payment.register.x_fx_rate_payment_per_unit` (Float, `digits=(16, 4)`) — `source_currency._convert(1.0, currency_id, company, payment_date, round=False)`, i.e. payment-currency units per one document-currency unit.
- `account.payment.register.x_fx_amount_source` (Monetary on `source_currency_id`) — `amount` converted back into the document currency.
- `account.payment.register.x_fx_rate_missing` (Boolean) — no `res.currency.rate` row for the document (or payment) currency in that company. The company currency itself never needs one.

### custom_asset_from_receipt — Custom Asset From Receipt

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_asset_from_receipt` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM) |
| Maturity / confidence | Beta / Rendah |
| Depends | `stock`, `purchase`, `account`, `custom_accounting_asset`, `custom_rental` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | fixed-assets, rental, inventory |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Bulk-convert received serial-numbered products into Fixed Assets + Rental Assets via a per-item picker wizard Bridges ``custom_accounting_asset`` and ``custom_rental`` so a single goods receipt (e.g. 200 drones with 200 serial numbers) can spawn one ``custom.fixed.asset`` per SN — and optionally one ``rental.asset`` per SN — through a wizard with per-row select checkboxes and a Select All shortcut. Idempotent: previously-converted serial numbers are detected and disabled in the wizard.

**Key models**

- custom.asset.conversion.line
- custom.asset.conversion.wizard

### custom_bank_import — Custom Bank Import

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_bank_import` |
| Version | 19.0.0.3.0 |
| Scope | Umum, dikonfigurasi (Levi's, ARKA-AIM) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_adapter_framework`, `account` |
| Models / routes / tests | 4 / 0 / 1 |
| Tags | bank-import, accounting, audit-trail, h2h-api |

> Knowledge file is generator output, not human-reviewed.

Two complementary statement-ingestion pipelines for Indonesian banks (BCA, Mandiri, BNI, BRI, CIMB, Permata, Danamon + generic): (1) CSV/XLSX template-based wizard import where per-bank parsing rules are declared on `custom.bank.import.template`, and (2) host-to-host (H2H) API sync where each bank ships an adapter (`bank_bca_h2h`, `bank_mandiri_h2h`, etc.) built on `custom_adapter_framework` (HMAC, retry, circuit breaker), polled by a configurable interval cron.

Both pipelines write to `account.bank.statement` / `account.bank.statement.line` and create a `custom.bank.import.log` row with SHA256 file-hash deduplication. Pairs naturally with `custom_accounting_full.custom.reconcile.rule` for downstream auto-matching.

**How it works**

- **CSV pipeline**: Operator configures a `custom.bank.import.template` (`code`, `encoding`, `delimiter`, `date_format`, 1-based column indexes `date_column_index`/`ref_column_index`/`partner_column_index`/`amount_credit_column_index`/`amount_debit_column_index`/`balance_column_index`/`signed_amount_column_index`, decimal/thousand separators). Then opens `custom.bank.import.csv.wizard` and uploads file + selects journal + template.
- `action_import()`: computes `file_hash = sha256(bytes)`; if a prior log with same hash and state ∈ (imported, partial) exists → `UserError`. Calls `template.parse_csv(b64)` which returns `{lines, errors, total_rows}`. Each line is `{date, ref, partner_hint, amount (Decimal), balance}`; amount = `signed_amount` if `signed_amount_column_index>0`, else `credit - debit`. Zero-amount lines are skipped. Creates `account.bank.statement` + bulk `account.bank.statement.line` records; writes a `custom.bank.import.log` with state imported/partial/failed.
- **H2H pipeline**: Operator creates `custom.bank.h2h.connection` (`bank_code`, `adapter_config_id` referring to `custom.adapter.config`, `account_number`, `journal_id`, `sync_interval_minutes`). `action_sync_now()` or cron `_cron_sync_due()` calls `_do_sync()` which fetches adapter via `adapter_config_id.get_adapter()`, calls `adapter.inquiry_statement(account_number, date_from=last_sync_at, date_to=now)`. Lines from `AdapterResponse.data['lines']` are persisted via `_persist_lines` → one `account.bank.statement` + many `account.bank.statement.line` + a log row referencing a per-bank pseudo-template (`h2h_<bank_lower>` auto-created via `_h2h_pseudo_template`).
- Adapter implementations: `BcaH2HAdapter` knows BCA's `/banking/v3/corporates/accounts/{acct}/statements` path and normalises `Data: [{TransactionDate, Amount, TransactionType: D|C, ...}]` → internal `{date, description, ref, amount}` (sign-flipped on D). `GenericBankH2HAdapter` reads paths from `ir.config_parameter` keys `custom_bank_import.<adapter>.path_{balance,statement}`. Mandiri/BNI/BRI/CIMB/Permata/Danamon currently alias the generic adapter (placeholder until per-bank canonical signing is wired).
- Errors / circuit-breaker state are recorded on `custom.bank.h2h.connection.status` ∈ active/paused/error + `last_error`.

**Key models**

- `custom.bank.import.template` — Declarative parser config; one per (bank, layout, company).
- `custom.bank.import.log` — Audit row per import attempt. `state` ∈ imported/failed/partial. Tracks `file_hash` for dedup. Inherits `mail.thread`.
- `custom.bank.h2h.connection` — Per-account H2H credentials + journal + sync schedule. Inherits `mail.thread`.
- `BcaH2HAdapter` / `GenericBankH2HAdapter` (+ Mandiri/BNI/BRI/CIMB/Permata/Danamon aliases) — Python adapter classes (NOT Odoo models); registered via `@register_adapter("bank_<code>_h2h")` from `custom_adapter_framework`.
- `custom.bank.import.csv.wizard` (TransientModel) — Upload wizard.

**Important fields**

- `custom.bank.import.template.code` (Char, indexed, unique-per-company) — stable parser identifier (e.g. `bca_csv`).
- `custom.bank.import.template.encoding` (Selection utf-8/latin-1) / `delimiter` (Char size=1) / `has_header` (Boolean).
- `custom.bank.import.template.date_format` (Char, Python `strptime` format) — e.g. `%d/%m/%Y` (BCA), `%d-%m-%Y` (Mandiri).
- `custom.bank.import.template.*_column_index` (Integer, 1-based; `-1` = unused).
- `custom.bank.import.template.signed_amount_column_index` (Integer) — when > 0 overrides credit/debit split.
- `custom.bank.import.template.decimal_separator` / `thousand_separator` (Char, size=1).
- `custom.bank.import.log.file_hash` (Char, indexed) — SHA256 of raw bytes; dedup key.
- `custom.bank.import.log.state` (Selection imported/failed/partial, required, indexed).
- `custom.bank.import.log.line_count` / `error_count` (Integer).
- `custom.bank.import.log.raw_payload` (Text) — H2H raw response or CSV row-error summary (capped 8000 chars).
- `custom.bank.h2h.connection.bank_code` (Selection BCA/Mandiri/BNI/BRI/CIMB/Permata/Danamon/Other).
- `custom.bank.h2h.connection.adapter_config_id` (M2o `custom.adapter.config`, required) — provides base_url, auth, secret, breaker config.
- `custom.bank.h2h.connection.sync_interval_minutes` (Integer, default 60) — cron throttle.
- `custom.bank.h2h.connection.last_sync_at` (Datetime, readonly) — used as `date_from` for next call.
- `custom.bank.h2h.connection.status` (Selection active/paused/error, tracking).
- Unique constraint: `unique(bank_code, account_number, company_id)` on H2H connections.

### custom_esg — Custom ESG Reporting

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_esg` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `account`, `hr` |
| Models / routes / tests | 6 / 0 / 0 |
| Tags | accounting, audit-trail, approval-workflow, anomaly-detection |

> Knowledge file is generator output, not human-reviewed.

Standalone ESG (Environmental / Social / Governance) metric capture and sustainability-report generator for Indonesian SMB / listed companies subject to **OJK POJK 51/2017** sustainability reporting obligations. Supports POJK 51, GRI, SASB, and TCFD framework labels. Ships a GHG Scope 1/2/3 emission factor catalog, a GL-account → emission-factor mapping with an auto-collect cron that scans posted `account.move.line` rows and emits draft `custom.esg.measurement` records, a stakeholder-impact materiality assessment with quadrant compute, and a simple HTML sustainability report generator that aggregates measurements by metric category.

**How it works**

- An admin seeds the metric catalog (`custom.esg.metric` with `code` per GRI/POJK 51, `category`, `subcategory`, `unit`). A POJK 51 seed file is shipped in `data/esg_metrics_pojk51.xml`.
- An admin populates `custom.esg.emission.factor` rows (Scope 1 / 2 / 3, `unit_of_measure`, `kg_co2_per_unit`, optional `source_reference` citation, `metric_id` linking to the target ESG metric).
- An admin maps GL accounts to factors via `custom.esg.account.mapping(account_id, factor_id, unit_cost)`. Cron `_cron_collect_emission_from_accounting` scans posted `account.move.line` rows for each active mapping. For each AML not previously processed (idempotency via `source_document = "aml:<id>"`), it computes `activity_qty = abs(aml.balance / unit_cost)` (or `aml.quantity` when `unit_cost=0`), then `value = activity_qty × kg_co2_per_unit`, and creates a draft `custom.esg.measurement` linked to the factor's metric.
- Manual capture: a user creates `custom.esg.measurement(metric_id, period_start, period_end, value, source_document, notes)` in `draft`. State machine: `draft -> validated` (`action_validate` stamps `validated_by_user_id`) -> `audited` (`action_audit`). `action_reset_draft` reverts.
- Auditor evidence: `custom_esg_measurement_ext.py` adds `x_audit_evidence` (binary attachment), `x_audit_evidence_filename`, `x_auditor_signature` (tracked Char, typically SHA-256 hex digest of the evidence file + auditor identity).
- Materiality: an admin scores each topic on `stakeholder_importance` (1-10) and `business_impact` (1-10) per `assessment_year`; stored compute `quadrant` maps to `critical` (high SH / low biz) / `important` (high / high) / `minor` (low / high) / `monitoring` (low / low). Unique per (topic, year, company).
- Report: `custom.esg.report.action_generate()` aggregates linked `measurement_ids` by metric category, renders an HTML table grouped by Environmental / Social / Governance / Other, stamps `state='published'` and `published_date`.

**Key models**

- `custom.esg.metric` — Catalog row; unique `code`, category, optional subcategory + unit.
- `custom.esg.measurement` — Period-bound value with draft/validated/audited workflow; tracking on metric/period/value/state.
- `custom.esg.measurement` (extended in `custom_esg_measurement_ext.py`) — Adds auditor evidence file + signature/hash.
- `custom.esg.emission.factor` — GHG Scope 1/2/3 kg-CO2e-per-unit catalog; unique (name, category, company).
- `custom.esg.account.mapping` — GL account → emission factor mapping; hosts the auto-collect cron.
- `custom.esg.materiality` — Stakeholder × business-impact scoring; stored compute `quadrant`; unique per (topic, assessment_year, company).
- `custom.esg.report` — Sustainability report with M2M measurements + HTML output.

**Important fields**

- `custom.esg.metric.code` (Char, required, unique) — GRI / POJK 51 identifier.
- `custom.esg.metric.category` (Selection: environmental/social/governance, required, tracking) — drives report aggregation.
- `custom.esg.measurement.state` (Selection: draft/validated/audited, tracking) — workflow.
- `custom.esg.measurement.source_document` (Char) — free-form ref; for auto-collected rows uses `aml:<id>` for idempotency.
- `custom.esg.measurement.x_audit_evidence` (Binary, attachment) + `x_auditor_signature` (Char, tracking) — auditor attestation.
- `custom.esg.emission.factor.category` (Selection: scope_1/scope_2/scope_3, required) — GHG protocol scopes.
- `custom.esg.emission.factor.kg_co2_per_unit` (Float, digits=(16,6)) — conversion coefficient.
- `custom.esg.emission.factor.metric_id` (M2o `custom.esg.metric`, ondelete='set null') — target metric for auto-collect.
- `custom.esg.account.mapping.unit_cost` (Float, digits=(16,4)) — divide `aml.balance` by this to derive activity quantity; if 0, use `aml.quantity` directly.
- `custom.esg.materiality.quadrant` (Selection: critical/important/minor/monitoring, stored compute) — threshold at score ≥ 6.
- `custom.esg.report.framework` (Selection: pojk51/gri/sasb/tcfd, default `pojk51`).
- `custom.esg.report.generated_html` (Html, readonly) — rendered output stamped by `action_generate`.

### custom_finance_budget — Custom Finance Budget

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_finance_budget` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (Finance Portal) |
| Maturity / confidence | Beta / Tinggi |
| Depends | `custom_core`, `custom_finance_portal` |
| Models / routes / tests | 1 / 0 / 0 |
| Tags | finance-portal, budget-control |

A read-only **cost budget reference per division, cost centre and period**,
synced from SAP by `custom_finance_portal_sap`. Its whole job is to answer one
question at submission time: would this Finance Portal document overspend its
division's remaining budget?

**How it works**

- `custom_finance_portal_sap`'s daily master-data pull writes `finance.budget` rows. Nothing in Odoo edits them by hand — SAP owns the number.
- `finance.document.mixin` calls `_check_document_budget` when a document is submitted. The check resolves the document's division and period, sums what is already committed, and compares against the budget row.
- **Enforcement is soft by design.** When no matching budget row exists — the usual state before the SAP feed goes live for a division — the check passes. The portal stays usable rather than blocking every submission on missing reference data.
- Hard blocking is a switch: `ir.config_parameter` `custom_finance_budget.enforce`, default `1`.
- `custom_approval_engine_budget` builds on the same check to block a **non-PO vendor bill** that would overspend its division budget — the one place the budget reaches outside the Finance Portal.

**Key models**

- `finance.budget` — one row per division / cost centre / period, holding the budgeted amount and the SAP identifier it came from.

**Important fields**

- `finance.budget.vertical_id` — the division the budget belongs to; the join key for every check.
- Config parameter `custom_finance_budget.enforce` — `1` blocks, `0` warns. The single most consequential setting in the module.

### custom_finance_portal — Custom Finance Portal

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_finance_portal` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (Finance Portal) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_approval_engine`, `mail`, `portal`, `hr`, `account`, `product` |
| Models / routes / tests | 17 / 0 / 1 |
| Tags | finance-portal, approval-workflow, sap-engagement, audit-trail |

Makes Odoo a **system of engagement in front of SAP S/4HANA**, which stays the
system of record. Odoo runs the submission forms, the two-stage Tax Review →
Finance Review approval, and budget/PR validation. The approved document is
pushed to SAP by `custom_finance_portal_sap`; SAP posts the GL or MIRO and pays.

The design decision that matters to Finance: **Odoo never posts its own journal
entries here.** It mirrors SAP status back. Nothing in this module can create a
second version of the truth in the ledger.

**How it works**

- A requester opens one of four document types, all built on `approval.mixin` and `pdp.audited.mixin`: Cash Advance (with its own realization document), Reimbursement, Vendor Invoice (PO Non-Trade and Non-PO Non-Trade, with a vendor portal), and Travel Settlement — the last being a read-only mirror of HRIS travel data, settled against the cash advance.
- On submission the document checks its division budget through `custom_finance_budget._check_document_budget` and the PR-required threshold held in `finance.limitation`.
- Approval runs Tax Review, then Finance Review, through the shared approval engine — the same delegation, out-of-office and SLA escalation rules the rest of the platform uses.
- On final approval the mixin calls `_finance_push_to_sap`. Out of the box that hook runs a **local stub**, so the portal is fully usable before the SAP and Kafka connectors exist. `custom_finance_portal_sap` overrides the hook to enqueue a real async push.
- SAP status flows back through `_finance_apply_sap_status`, again stubbed until the bridge is live.

**Key models**

- `finance.document.mixin` — the shared spine: state, approval wiring, the `_finance_push_to_sap` / `_finance_apply_sap_status` hooks, PDP audit.
- `finance.cash.advance` + `finance.cash.advance.line`, and `finance.cash.advance.realization` + its line — request and settlement.
- `finance.reimbursement` + `finance.reimbursement.line` — reimbursement and expense claims.
- `finance.vendor.invoice` + `finance.vendor.invoice.line` — vendor-submitted invoices for MIRO.
- `finance.travel.settlement` — HRIS travel mirror settled against a cash advance.
- `finance.synced.mixin` — records that carry an SAP external identifier.
- Master data: `finance.submission.type`, `finance.invoice.type`, `finance.invoice.routine.type`, `finance.item.submission`, `finance.vertical` (division), `finance.limitation` (per-type thresholds incl. PR-required).

**Important fields**

- `finance.limitation` thresholds — decide when a purchase requisition becomes mandatory; the single most commonly reconfigured record in the module.
- `finance.vertical` — the division axis every budget check and approval matrix resolves against.
- `x_sap_external_id` (via `finance.synced.mixin`) — the idempotency key for every push and pull against SAP.

### custom_finance_portal_sap — Custom Finance Portal — SAP/HRIS Integration

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_finance_portal_sap` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (Finance Portal) |
| Maturity / confidence | Beta / Tinggi |
| Depends | `custom_core`, `custom_adapter_framework`, `custom_finance_portal`, `custom_finance_budget`, `queue_job` |
| Models / routes / tests | 1 / 2 / 0 |
| Tags | finance-portal, sap-integration, kafka-bridge, master-sync |

The Odoo side of the SAP/HRIS edge. **Odoo never speaks Kafka directly.** It
speaks HMAC-signed REST to a bridge microservice
(`services/finance-sap-bridge/`) that consumes and produces Kafka on its behalf.
That indirection is what lets the Finance Portal ship and be used before SAP
integration exists.

**How it works**

- The module registers two adapters — `finance_sap_bridge` and `finance_hris_bridge` — on `custom_adapter_framework`, inheriting its circuit breaker, HMAC signing, retry with backoff, and append-only call log.
- It overrides `finance.document.mixin._finance_push_to_sap` to enqueue a `queue_job` that pushes an approved document: cash-advance GL posting, journal posting, reimbursement GL posting, or invoice-for-MIRO depending on the type.
- A daily scheduler pulls master data — chart of accounts, cost budget, supplier, item category, division/vertical — and upserts idempotently keyed on `x_sap_external_id`.
- An inbound `@secure_endpoint('finance_sap')` webhook lets the bridge mirror the planned payment date and payment status back in near-real time.
- Every push and pull is written to `finance.sync.log`, which drives a Sync menu operators can read without database access.
- **Degradation is deliberate:** with no enabled `custom.adapter.config` the push falls back to the local stub and the crons no-op. Both adapters ship `status=disabled`.

**Key models**

- `finance.sync.log` — append-only record of every push and pull, with payload reference, direction, state and error text.
- `finance.document.mixin` (inherited) — the push hook is replaced here.

**Important fields**

- `custom.adapter.config.status` — the master switch. While `disabled`, the portal runs standalone and nothing leaves the database.
- `finance.sync.log.state` — the field operators watch when a document appears approved in Odoo but unpaid in SAP.
- `x_sap_external_id` — the upsert key on every synced master-data record.

**Endpoints**: `/finance/sap/master`, `/finance/sap/status`

### custom_finance_portal_sso — Custom Finance Portal — SSO (Keycloak)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_finance_portal_sso` |
| Version | 19.0.0.2.0 |
| Scope | Umum, dikonfigurasi (Finance Portal) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_finance_portal`, `auth_oauth` |
| Models / routes / tests | 0 / 0 / 1 |
| Tags | finance-portal, sso, keycloak, oidc |

> Knowledge file is generator output, not human-reviewed.

### custom_levis_asset_accounts — Levi's Fixed Asset Revaluation Accounts

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_levis_asset_accounts` |
| Version | 19.0.2.0.0 |
| Scope | Khusus brand (Levi's) |
| Maturity / confidence | Beta / Rendah |
| Depends | `custom_accounting_asset` |
| Models / routes / tests | 0 / 0 / 0 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Seed the 6 EBR fixed-asset categories and wire IAS 16 revaluation account defaults onto fixed-asset groups by resolving Erajaya chart codes per company. Levi's Fixed Asset Revaluation Accounts ======================================= Seeds the 6 EBR fixed-asset categories (Land, Building & improvements, Vehicles, Office & outlet equipment, Machinery, Furniture & fixtures) as ``custom.fixed.asset.group`` records — each wired to its Erajaya cost / accumulated-depreciation / depreciation-expense account by code per company — and fills the IAS 16 revaluation account defaults on every ``custom.fixed.asset.group`` (``default_revaluation_surplus_account_id`` / ``_loss_`` / ``_income_`` / ``default_retained_earnings_account_id``) for companies running

### custom_levis_bank_reconcile — Levi's Bank Reconciliation (POS Tender)

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_levis_bank_reconcile` |
| Version | 19.0.1.1.0 |
| Scope | Khusus brand (Levi's) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_levis_localization`, `custom_account_reconcile` |
| Models / routes / tests | 0 / 0 / 1 |

The monthly `levis.pos.clearing` run settles a whole period in one go. This
module teaches the **line-by-line bank matching wizard** the same four facts, for
the days Finance wants to look a single settlement in the eye.

It changes **what is offered**, not how a reconciliation is written: the write
path is still `custom_account_reconcile`'s `_reconcile_with_amls` on top of core
`reconcile()`.

**How it works**

- **The Operating Unit is on the tender line.** Every candidate row shows which store its POS receivable belongs to, so a settlement is never matched against another outlet's sales by accident.
- **A card settlement is matched at its gross.** The bank pays gross minus MDR while the tender receivable is carried at gross, so matching on the amount that actually landed would never find anything. The wizard reads the gross and the fee out of the statement narrative, targets the gross, and offers the fee ready-booked to the MDR expense account with the store's Operating Unit on it.
- **Cash deposits get a suggestion, capped at the deposit.** One transfer often covers several days of cash sales, so the wizard fills the selection largest-first up to — never over — the statement amount, and leaves the remainder open.
- **The statement line records which store it came from.** MID/TID and keyword resolution is stored on the line itself, so the reconciliation list can be filtered and grouped per Operating Unit.

**Key models**

- `account.bank.statement.line` (inherited) — stores the resolved store / Operating Unit from MID, TID or narrative keyword.
- `custom.bank.reconcile.wizard` and `custom.bank.reconcile.wizard.line` (inherited) — gross-based card matching, the MDR fee line, and the capped cash suggestion.

**Important fields**

- The resolved Operating Unit on `account.bank.statement.line` — what makes the reconciliation list filterable per store, and what stops a cross-store match.
- The gross-versus-net distinction on the wizard line: the target is the tender receivable's gross, and the MDR difference is offered as a booked fee rather than left as an unexplained residual.

### custom_levis_categ_approval — Levi's Product Category Change Approval

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_levis_categ_approval` |
| Version | 19.0.1.0.0 |
| Scope | Khusus brand (Levi's) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_levis_localization`, `custom_approval_engine` |
| Models / routes / tests | 1 / 0 / 1 |
| Tags | approval, product-category, governance, levis |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Block silent product-category changes and route them through Finance approval Levi's Product Category Change Approval =======================================

**Key models**

- levis.categ.reclass

### custom_levis_operating_unit — Custom Operating Unit — Levi's Migration

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_levis_operating_unit` |
| Version | 19.0.0.1.0 |
| Scope | Khusus brand (Levi's) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_operating_unit_docs`, `custom_levis_localization` |
| Models / routes / tests | 0 / 0 / 1 |
| Tags | operating-unit, levis, migration |

Lifts the Operating-Unit dimension Levi's already runs — one
`account.analytic.account` per store, wired to a warehouse and a per-store
purchase journal by `custom_levis_localization` — into the platform's
`operating.unit` master. Auto-installs where that localization and
`custom_operating_unit_docs` are both present.

### custom_operating_unit_reports — Custom Operating Unit — Reports

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_operating_unit_reports` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_operating_unit_docs`, `custom_accounting_reports` |
| Models / routes / tests | 0 / 0 / 1 |
| Tags | operating-unit, data-isolation, accounting-reports |

Makes the custom accounting reports respect the reader's Operating Units.
Auto-installs where `custom_accounting_reports` and
`custom_operating_unit_docs` are both present.

### custom_payment_admin_fee — Payment Admin Fees

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_payment_admin_fee` |
| Version | 19.0.1.1.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `account` |
| Models / routes / tests | 1 / 0 / 1 |

> Knowledge file is generator output, not human-reviewed.

Lets a payment carry bank/admin charges on top of the document it settles, each charge booked to its own COA. Tenant-neutral extraction of feature #8 of `custom_levis_localization`, built so tenants other than Levi's (first consumer: ARKA-AIM) get the fee lines without inheriting the Levi's card-BIN/MDR and Operating-Unit machinery.

**How it works**

- On a posted bill/invoice, `Register Payment` opens `account.payment.register`. The form gains an **Admin Fees** group (above the footer) where the user adds one or more fee lines: label, fee account, amount.
- `_onchange_admin_fee_line_ids` recomputes `amount = <batch residual> + Σ fees` from the batch on every change, so amounts never accumulate and clearing the lines restores the plain residual.
- **Several bills at once** — the common case, since batching bills into one transfer is exactly what saves the fee. Adding a fee line ticks *Group Payments*, so one payment settles every selected bill and the fee is charged once for the whole transfer. The form explains this inline; unticking *Group Payments* while fees exist raises rather than splitting the fee across bills.
- On confirm, `_create_payment_vals_from_wizard` replaces the native single-line write-off with one write-off val per fee, so a 1,000,000 bill with a 1,500 fee posts `Dr Payable 1,000,000 / Dr Fee COA 1,500 / Cr Bank 1,001,500` and the bill still reconciles in full.
- A **negative** amount nets the fee off an inbound receipt: `Dr Bank (net) / Dr fee / Cr Receivable` — the usual booking for transfer/acquirer charges deducted before settlement.

**Key models**

- `payment.register.admin.fee` (TransientModel) — one admin-fee line on the wizard; `ondelete="cascade"` to the wizard.
- `account.payment.register` (`_inherit`) — hosts the O2m, the total, the amount recomputation and the write-off generation.

**Important fields**

- `payment.register.admin.fee`: `wizard_id` (M2o account.payment.register, required), `company_id`/`currency_id` (related from the wizard), `name` (Char, default "Admin Fee"), `account_id` (M2o account.account, required; domain excludes `asset_receivable`/`liability_payable`/`off_balance` and filters on `company_ids`), `amount` (Monetary, required, may be negative).
- `account.payment.register`: `admin_fee_line_ids` (O2m), `admin_fee_total` (Monetary, computed from the line amounts).

### custom_payment_id — Custom Indonesia Payment Gateway

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_payment_id` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `payment`, `custom_subscription` |
| Models / routes / tests | 7 / 4 / 0 |
| Tags | payment-acquirer, indonesia-gateway, webhook, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Indonesia payment gateway integration on top of Odoo 19's `payment` framework. Registers Midtrans, Xendit, DOKU, and **Eraspace** as additional `payment.provider.code` values (`_ID_CODES = ("midtrans", "xendit", "doku", "eraspace")`), ships an HTTP adapter base with retry / exponential backoff / per-(db,provider) circuit breaker / outbound call log, and wires four webhook endpoints that verify signatures and transition `payment.transaction` state via documented helpers (`_set_done`/`_set_pending`/`_set_canceled`/`_set_error`).

This is the canonical Indonesia payment-acquirer module. Any BRD requirement involving "Midtrans Snap", "Xendit invoice", "DOKU checkout", "Indonesia payment gateway", or "QRIS / Virtual Account collection" maps here. Cleanly extensible to additional providers by adding `custom.payment.id.adapter.<name>` AbstractModel + provider selection_add.

**How it works**

- Admin creates a `payment.provider` record with `code` ∈ midtrans/xendit/doku; fills `x_id_server_key` (gated by group_manager), `x_id_client_key`, `x_id_merchant_id` (DOKU), `x_id_sandbox`, `x_id_webhook_secret` (Xendit X-Callback-Token / DOKU HMAC secret).
- `action_test_id_connection()` button → `_get_id_adapter()` returns the concrete adapter model → `adapter.test_connection(provider)` round-trips a minimal POST through `send()`. UI displays HTTP status, latency, log id via `display_notification`.
- **Outbound (create checkout)**: `payment.transaction._send_payment_request` is overridden — for ID-provider transactions, calls `provider._get_id_adapter().create_checkout(provider, tx)` which returns `{redirect_url, reference, raw}`. Stores `x_id_redirect_url`, `provider_reference`, `x_id_raw_response`; calls `tx._set_pending()`.
- `_get_specific_rendering_values(processing_values)` returns `{api_url, redirect_url}` so the storefront redirects the customer to the gateway-hosted page.
- **Inbound (webhook)**: three public endpoints, `csrf=False`, `auth=public`:
- `/custom_payment_id/webhook/midtrans` — verifies `signature_key == SHA512(order_id+status_code+gross_amount+server_key)` via `MidtransAdapter.verify_notification_signature`. Maps `transaction_status` through `_MIDTRANS_STATE_MAP`. `capture + fraud=challenge` → pending.
- `/custom_payment_id/webhook/xendit` — verifies `x-callback-token` header against `provider.x_id_webhook_secret` via `XenditAdapter.verify_callback_token`. Maps `status` through `_XENDIT_STATE_MAP`.
- `/custom_payment_id/webhook/doku` — verifies HMAC `Signature` header (client_id, request_id, timestamp, path, body, secret) via `DokuAdapter.verify_notification_signature`. Maps `transaction.status` through `_DOKU_STATE_MAP`.
- Each webhook calls `_reconcile_transaction(tx, new_state, raw_payload)` which guards already-final states, calls `_set_done/_set_pending/_set_canceled/_set_error`, posts chatter, returns 200/400/404 as appropriate.
- **Refund**: `payment.transaction.action_create_refund(amount=None)` routes ID providers to `adapter.refund(provider, tx, amount=amount)` (subclass-dependent).
- **Outbound call log**: every `IdPaymentAdapter.send()` materialises a `custom.payment.id.log` row (`state` ∈ queued/sent/ok/failed/timeout, `attempt`, `http_status`, `latency_ms`, `request_payload`, `response_payload`, `error_message`).
- **Circuit breaker**: module-level `_CB_STATE` dict keyed by `(db, provider_id)`; `_CB_THRESHOLD=10` consecutive failures opens breaker for `_CB_OPEN_SECONDS=3600`. `_circuit_open` short-circuits `send()` with `UserError`.

**Key models**

- `payment.provider` (inherited) — `selection_add` for midtrans/xendit/doku + 5 config fields (server_key, client_key, merchant_id, sandbox, webhook_secret). Sensitive fields gated by `group_manager`.
- `payment.transaction` (inherited) — `x_id_redirect_url`, `x_id_raw_response`; override `_send_payment_request`, `_get_specific_rendering_values`, `action_create_refund`.
- `payment.token` (inherited) — stub `x_id_saved_token_id` for Midtrans Snap saved-card; no live flow yet.
- `custom.payment.id.adapter.base` (AbstractModel) — HTTP machinery (`send`, retry, breaker, log). Subclass override hooks `_base_url`, `_endpoint`, `_auth_headers`, `create_checkout`, `test_connection`.
- `custom.payment.id.adapter.midtrans` / `custom.payment.id.adapter.xendit` / `custom.payment.id.adapter.doku` / `custom.payment.id.adapter.eraspace` — concrete AbstractModels (stubs in current revision; log payloads only — live API plumbing deferred per manifest). Eraspace overrides `_base_url` (`sandbox.payment.eraspace.com` / `payment.eraspace.com`), `_endpoint` (`/v1/checkout`), `_auth_headers` (`X-Eraspace-Key`/`X-Eraspace-Client`); `create_checkout` returns a placeholder redirect while `x_id_sandbox` is set; webhook signature placeholder is `HMAC-SHA256(webhook_secret, raw_body)` hex in `X-Eraspace-Signature`.
- `custom.payment.id.log` — outbound call audit row. Inherits `mail.thread`, tracking on `state`.
- `IdPaymentWebhookController` — three `http.Controller` routes for inbound notifications.

**Important fields**

- `payment.provider.code` (Selection, extended) — `midtrans`/`xendit`/`doku` added via `selection_add`; `ondelete={"...": "set default"}`.
- `payment.provider.x_id_server_key` (Char, `groups="custom_payment_id.group_manager"`) — Midtrans Server Key / Xendit Secret / DOKU Secret. Required for outbound.
- `payment.provider.x_id_client_key` (Char) — Midtrans Client Key / Xendit Public Key / DOKU Client Id.
- `payment.provider.x_id_merchant_id` (Char) — DOKU merchant id; optional for Midtrans/Xendit.
- `payment.provider.x_id_sandbox` (Boolean, default True) — drives sandbox vs production `_base_url`.
- `payment.provider.x_id_webhook_secret` (Char, `groups="custom_payment_id.group_manager"`) — Xendit callback token / DOKU HMAC secret. Midtrans ignores (uses server_key for signature).
- `payment.transaction.x_id_redirect_url` (Char, readonly) — gateway-hosted checkout URL.
- `payment.transaction.x_id_raw_response` (Text, readonly) — last raw response (capped 65000 chars).
- `payment.transaction.provider_reference` (existing field, populated from adapter response) — gateway-side reference.
- `payment.token.x_id_saved_token_id` (Char) — Midtrans saved-card token.
- `custom.payment.id.log.state` (Selection queued/sent/ok/failed/timeout, tracking, required, indexed).
- `custom.payment.id.log.attempt` (Integer, default 1) — retry counter.
- `custom.payment.id.log.http_status` (Integer) / `latency_ms` (Integer).
- `custom.payment.id.log.request_payload` / `response_payload` (Text) — capped 65000 chars.
- Module-level breaker constants: `_CB_THRESHOLD=10`, `_CB_OPEN_SECONDS=3600`, `_MAX_RETRIES=3`, `_BACKOFF_BASE=1.0`, `_DEFAULT_TIMEOUT=30`.

**Endpoints**: `/custom_payment_id/webhook/doku`, `/custom_payment_id/webhook/eraspace`, `/custom_payment_id/webhook/midtrans`, `/custom_payment_id/webhook/xendit`

### custom_payment_methods_id — Indonesian Payment Methods (Giro / Bank Transfer)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_payment_methods_id` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Kerangka / Sedang |
| Depends | `account` |
| Models / routes / tests | 0 / 0 / 1 |

> Knowledge file is generator output, not human-reviewed.

### custom_payment_voucher — Payment Voucher / Payment Receipt

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_payment_voucher` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `account` |
| Models / routes / tests | 0 / 0 / 1 |

> Knowledge file is generator output, not human-reviewed.

### custom_petty_cash — Custom Cash Advance & Petty Cash

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_petty_cash` |
| Version | 19.0.0.5.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM, Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `account`, `hr`, `mail`, `custom_approval_engine`, `custom_tax_id`, `custom_accounting_reports` |
| Models / routes / tests | 11 / 0 / 5 |
| Tags | cash-advance, petty-cash, employee-advance, multi-currency, approval-workflow, audit-trail, accounting |

> Knowledge file is generator output, not human-reviewed.

The cash-advance cycle Odoo does not have. Neither Community **nor Enterprise**
ships an employee-advance concept — the Expenses app only knows "the employee
already paid, reimburse them", so money always moves *after* the spend. This
module supplies the other direction: request → approval → Bank-Out disbursement
→ realization (third-party vendor bill *or* plain expense) → return/reimburse →
settlement, with Kartu Uang Muka / Outstanding / Aging monitoring and advance
ceilings.

(The OCA reference implementation, `hr_expense_advance_clearing`, is not ported
to 19.0 and cannot be ported as-is: Odoo 19 removed `hr.expense.sheet`.)

**Declared models**: `petty.cash.aging.wizard`, `petty.cash.outstanding.wizard`, `petty.cash.realization`, `petty.cash.realization.line`, `petty.cash.report.aging`, `petty.cash.report.outstanding`, `petty.cash.report.statement`, `petty.cash.request`, `petty.cash.request.line`, `petty.cash.statement.wizard`, `petty.cash.type`

### l10n_erajaya — Indonesia - Erajaya Chart of Accounts

|  |  |
| --- | --- |
| Path | `addons/ee_gap/l10n_erajaya` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM, Levi's) |
| Maturity / confidence | Kerangka / Tinggi |
| Depends | `account` |
| Models / routes / tests | 0 / 0 / 0 |

Registers **Erajaya's own 10-digit Indonesian chart of accounts** as a selectable
Odoo 19 chart template (template code `erajaya`), so a new company in the group
starts on the group standard instead of the upstream 4-digit `l10n_id` chart or
the 5-digit `l10n_id_psak_custom` one. Despite the brand in its name this is a
**shared** module: both live Erajaya tenants run it — ARKA-AIM (`prd_arkaaim`)
and Levi's / Era Busana Retailindo (`prd_levis_begbal`).

Bulk content ships as CSV rather than XML records: **534 accounts, 29 account
groups, 78 taxes and 7 tax groups**. The CSVs were produced once by
`tools/gen_l10n_erajaya.py` from the 548-row client master CoA in
`imports/arka_aim_coa.csv` plus a live tax dump, with bank/cash and
brand-specific accounts filtered out so the template stays company-neutral.

**How it works**

- An operator creates the company, then picks **Erajaya** in Settings → Accounting → Chart Template. Odoo discovers the template through the `@template("erajaya")` methods on `account.chart.template`, which is why the module must stay in the `Accounting/Localizations/Account Charts` category.
- Loading the template applies the root metadata: 10 code digits, country `id`, receivable `erajaya_1106000001`, payable `erajaya_2103100001`.
- Company defaults follow: anglo-saxon accounting on, bank prefix `1103`, cash prefix `1102`, transfer prefix `1101`, FX gain/loss accounts, and the default 12% non-luxury sale and purchase taxes.
- The stock `sale` and `purchase` journals are renamed to **Penjualan** and **Pembelian** so the journal list reads in Bahasa Indonesia from day one.
- Fiscal positions (`erajaya_fpos_domestic` and siblings) are created last.
- Per-tenant deviations are *not* handled here. Levi's strips the accounts EBR does not use through `scripts/tenants/levis/30_fix_coa.py`; ARKA-AIM's development database seeds its own variant via `custom_arka_aim_seed`.

**Key models**

- `account.chart.template` (inherited) — carries the `@template("erajaya")` methods that expose the chart, its company defaults, journals and fiscal positions. The module declares no model of its own.

**Important fields**

- `code_digits` = `"10"` — the group standard. A tenant on a different digit count cannot share this template.
- `property_account_receivable_id` = `erajaya_1106000001` — Trade Receivables.
- `property_account_payable_id` = `erajaya_2103100001` — Trade Payables.
- `bank_account_code_prefix` / `cash_account_code_prefix` = `1103` / `1102` — every new bank or cash journal numbers itself from these.

### l10n_id_psak_custom — Indonesia — PSAK Chart of Accounts (Custom Platform)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/l10n_id_psak_custom` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Kerangka / Tinggi |
| Depends | `account` |
| Models / routes / tests | 0 / 0 / 0 |

An alternative **5-digit Indonesian chart of accounts aligned to the PSAK
numbering convention**, for tenants that are not on the Erajaya group chart. It
sits between the upstream 4-digit `l10n_id` template and the 10-digit
`l10n_erajaya` one, and is what `trn_arkaaim` runs.

The module is `auto_install: True` and is a hard dependency of
`custom_accounting_full`, so in practice it is present on every database that
has the accounting layer — even the ones that then load a different chart.
Having it installed does not select it; a company still has to pick `id_psak`.

**How it works**

- Odoo's `ir.module.module._compute_account_templates` discovers the `@template("id_psak")` methods and lists **PSAK** among the available charts.
- Selecting it creates 53 accounts under 12 hierarchical account groups on the 1xxxx–8xxxx spine: 1xxxx Aset, 2xxxx Kewajiban, 3xxxx Ekuitas, 4xxxx Pendapatan, 5xxxx Harga Pokok Penjualan, 6xxxx Beban Operasional, 7xxxx Pendapatan/Beban Lain, 8xxxx Pajak Penghasilan.
- Two PPN 11% taxes (PMK 58/2022) are created — Keluaran and Masukan — with explicit repartition lines pointing at `21400` (PPN liability) and `11500` (PPN asset), rather than relying on defaults.
- Six journals are created with Bahasa labels: Faktur Penjualan, Tagihan Pembelian, Kas, Bank, Jurnal Umum, Selisih Kurs.
- Two fiscal positions close it out: **Ekspor** (drops PPN) and **Pelanggan Bebas Pajak**.
- PPh withholding taxes (21/23/26) are deliberately absent. They belong to `custom_pph_witholding` and `custom_tax_id`, which feed Bupot lines into Coretax; duplicating them here would double-book the withholding.

**Key models**

- `account.chart.template` (inherited) — hosts the `@template("id_psak")` definitions. No own model.

**Important fields**

- Chart template code `id_psak` — the selector value; `custom_accounting_full` and several tenant scripts branch on it (see the `WHT_COA_ALIAS` handling in the withholding loader).
- PPN repartition targets `21400` / `11500` — hard-coded in the template, so a tenant that renumbers these accounts must re-point the taxes by hand.

## Indonesian Taxation (Perpajakan Indonesia)

### custom_coretax — Custom Coretax (Indonesia DJP)

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_coretax` |
| Version | 19.0.0.4.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `account`, `mail` |
| Models / routes / tests | 7 / 0 / 1 |
| Tags | indonesian-tax, coretax, withholding, accounting, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Implements the **Indonesian Coretax DJP compliance surface** (PER-11/PJ/2025) for the Custom Odoo platform: NSFP (Nomor Seri Faktur Pajak) lifecycle on `account.move`, XML export/import wizards for the 7 main document types (e-Faktur Keluaran/Masukan, Bupot PPh 21 Tetap/Bukan Tetap, Bupot 23/26/Unifikasi), Bukti Potong receipt records, encrypted Sertifikat Elektronik (.p12) storage, and a pluggable adapter abstraction so that future host-to-host (ASPP) backends can replace the default manual portal-upload flow.

Every export, import, and sertel access emits an audit row to `pdp.audit_log` (`xml_export` / `xml_import` / `sertel_access`).

**How it works**

- Tenant admin creates a `custom.coretax.config` (NPWP digits-only, KPP code, taxpayer name/address) and runs the `custom.coretax.sertel.upload.wizard` to upload the `.p12`. The wizard validates the file via `cryptography.hazmat.primitives.serialization.pkcs12` (if installed), encrypts via `custom.ir.config.set_encrypted` (env-keyed Fernet), and persists the ciphertext at `ir.config_parameter` key `coretax.sertel.<config_id>`. The password is **never** persisted; `sertel_access` audit row is written.
- Operator opens `custom.coretax.export.wizard`, picks a `document_type` and a year/month range, runs `action_generate_xml`:
- `_gather_records` selects posted `account.move`s (for VAT docs) or `custom.coretax.bukti.potong` rows (for bupot).
- `_build_xml` constructs the tree with `lxml.etree`, `NS_CORETAX = "urn:djp:coretax:v1"` (placeholder; operator must align with official targetNamespace once XSDs are present).
- `_validate_xml` checks `addons/.../data/xsd/<doc_type>.xsd`; if missing, emits a warning string; if present, calls `xmlschema.XMLSchema(...).validate()`.
- Persists `ir.attachment`, sets `xml_file` for download, writes `xml_export` audit row.
- Operator uploads the XML to the official Coretax portal (manual adapter), then runs `custom.coretax.import.wizard` to ingest the DJP response XML:
- For bupot docs: creates `custom.coretax.bukti.potong` rows, partner-matched on `vat` digits-only (with `vat ilike npwp[:9]` fallback), tolerant of namespaced and unnamespaced XML, dedupes on `(no_bupot, source)`.
- For VAT docs: locates the `account.move` by `name`, writes `x_custom_nsfp` (if 17 digits) and bumps `x_custom_coretax_status` to `approved` or `submitted`.
- `custom.coretax.adapter.base._get_for_config(config)` dispatches by `config.adapter_type`: `manual` → `custom.coretax.adapter.manual` (returns `manual_required`, no NSFP, raises on `download_response`); `h2h_aspp` → must be installed separately.
- `account.move.x_custom_coretax_status` workflow: `draft → submitted → approved | rejected_djp`. Constraint `_check_nsfp_required_on_approval` blocks `approved` without a 17-digit NSFP. NSFP format `_NSFP_RE = ^\d{17}$` (2 transaction-code + 2 status-code + 13 serial).

**Key models**

- `custom.coretax.config` — Per-tenant taxpayer identity + sertel pointer + adapter selection. Stored model (not `res.config.settings`) so sertel/credential survive settings rewrites.
- `custom.coretax.bukti.potong` — Bukti Potong record (received/issued). Unique on `(no_bupot, source)`. Inherits `mail.thread`/`mail.activity.mixin`.
- `custom.coretax.adapter.base` (AbstractModel) — Adapter contract: `submit_xml(bytes) -> {submission_uuid, status, message}`, `query_nsfp(uuid)`, `download_response(uuid)`.
- `custom.coretax.adapter.manual` (AbstractModel) — Default no-op adapter returning `manual_required`.
- `custom.coretax.export.wizard` / `custom.coretax.import.wizard` / `custom.coretax.sertel.upload.wizard` (TransientModels).
- `account.move` (inherited) — adds NSFP + Coretax status fields.

**Important fields**

- `custom.coretax.config.npwp` (Char size=16) — 15 or 16 digits only; constraint `_NPWP_DIGITS_RE = ^\d{15,16}$`; unique.
- `custom.coretax.config.kpp_code` (Char size=3) — must be 3 digits.
- `custom.coretax.config.adapter_type` (Selection: manual/h2h_aspp) — dispatch key.
- `custom.coretax.config.sertel_uploaded` (Boolean, computed) — derived from `custom.ir.config.get_encrypted` truthiness.
- `custom.coretax.config.aspp_credential_key` (Char) — ir.config_parameter key pointer; plaintext never stored on the record.
- `account.move.x_custom_nsfp` (Char size=17, tracked) — 17 digits assigned by DJP after Coretax approval. Format `TT + SS + YYNNNNNNNNNNN`.
- `account.move.x_custom_coretax_status` (Selection: draft/submitted/approved/rejected_djp, tracked) — independent of accounting state.
- `account.move.x_custom_coretax_status_code` (Selection: `00`..`09`) — faktur status / pengganti code.
- `account.move.x_custom_coretax_submission_uuid` (Char) — reference from portal/ASPP.
- `account.move.x_custom_coretax_response_attach_id` (M2o `ir.attachment`) — approval PDF/XML.
- `custom.coretax.bukti.potong.jenis_pph` (Selection: 21/23/26/4_2/15/22, indexed) — PPh kind.
- `custom.coretax.bukti.potong.source` (Selection: received/issued, indexed) — perspective; uniqueness scoped per source.
- `custom.coretax.bukti.potong.state` (Selection: draft/confirmed/exported/submitted/approved/cancelled, tracked).
- `custom.coretax.bukti.potong.period_year` / `period_month` (Integer, indexed) — constrained `1≤month≤12`, `2000≤year≤2100`.

### custom_coretax_bupot — Custom Coretax e-Bupot Unifikasi

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_coretax_bupot` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_coretax`, `account`, `mail` |
| Models / routes / tests | 4 / 0 / 1 |
| Tags | indonesian-tax, coretax, withholding, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Implements **e-Bupot Unifikasi v2** (PPh 22 / 23 / 4(2) / 15 / 26 in a single SPT) on top of `custom_coretax`. Per-period header (`custom.bupot.unifikasi`) + per-cut line (`custom.bupot.unifikasi.line`), an XML export wizard producing the DJP Coretax v2 schema, a CSV upload wizard for ingesting DJP-assigned bupot numbers after acceptance, and a QWeb PDF report "Bukti Potong PPh Unifikasi". Both header and line inherit `pdp.audited.mixin`.

This is the unified-bupot companion to `custom_coretax` (which itself models the more generic `custom.coretax.bukti.potong` plus PPh 21 documents).

**How it works**

- Operator creates `custom.bupot.unifikasi(company_id, month, year)` — `name` auto-computed as `BPU/<year>/<month>`. Uniqueness `period_unique` on `(company_id, month, year)`.
- Operator adds `custom.bupot.unifikasi.line` rows (pph_type, cuttee NPWP/NITKU/name, gross/dpp/withheld, rate, optional `doc_ref` Reference to `account.move` / `account.payment`). `internal_ref` is auto-assigned from `ir.sequence` `custom.bupot.unifikasi.line`. NPWP must match `^\d{15,16}$`; amounts non-negative; rate 0..100.
- Operator runs `action_generate_xml` → opens `custom.bupot.xml.export.wizard`. The wizard's `action_generate` builds the XML in-memory (manual `BytesIO` + `xml.sax.saxutils.escape`, NOT lxml), creates an `ir.attachment` on the period, and bumps `state: draft → generated`.
- Operator uploads the XML to the DJP Coretax portal, then runs `action_mark_submitted` (state `submitted`).
- DJP returns a CSV mapping internal-ref → DJP-assigned bupot number. Operator runs `action_open_number_upload` → `custom.bupot.number.upload.wizard` parses the CSV (headers `internal_ref,bupot_number` required, UTF-8 BOM tolerant), writes `bupot_number` on matched lines, surfaces missing/ambiguous refs in the `report` field. If all lines are filled and the header was `submitted`, auto-promotes to `accepted`.
- On rejection: `action_mark_rejected` (free state); `action_reset_draft` returns to `draft`; `action_mark_accepted` is a manual override (only allowed from `submitted`).

**Key models**

- `custom.bupot.unifikasi` — Period header (1 per company per month). Inherits `pdp.audited.mixin`, `mail.thread`, `mail.activity.mixin`.
- `custom.bupot.unifikasi.line` — One withholding cut. Inherits `pdp.audited.mixin`.
- `custom.bupot.xml.export.wizard` (TransientModel) — XML generation + attachment + state promote.
- `custom.bupot.number.upload.wizard` (TransientModel) — CSV-driven number assignment + auto-promote.

**Important fields**

- `custom.bupot.unifikasi.month` (Selection `"1"`..`"12"`, required) — stored as string with two-digit display.
- `custom.bupot.unifikasi.year` (Char size=4, required) — 4-char string year.
- `custom.bupot.unifikasi.state` (Selection: draft/generated/submitted/accepted/rejected, tracked) — workflow gate.
- `custom.bupot.unifikasi.line_ids` (O2m → `custom.bupot.unifikasi.line`) — period lines.
- `custom.bupot.unifikasi.line_count` (Integer, computed) / `total_withheld` (Float, computed sum of line withheld_amount).
- `custom.bupot.unifikasi.line.internal_ref` (Char, sequence `custom.bupot.unifikasi.line`, fallback `"/"`) — pre-DJP-acceptance reference; the CSV upload joins on this.
- `custom.bupot.unifikasi.line.bupot_number` (Char) — DJP-assigned number filled by the upload wizard.
- `custom.bupot.unifikasi.line.pph_type` (Selection: 23/22/4_2/15/26, required) — note: no `21` (PPh21 lives in `custom_coretax` and HR).
- `custom.bupot.unifikasi.line.cuttee_npwp` (Char) — validated by `_NPWP_RE = ^\d{15,16}$`.
- `custom.bupot.unifikasi.line.cuttee_nitku` (Char) — NITKU (Nomor Identitas Tempat Kegiatan Usaha) for sub-locations.
- `custom.bupot.unifikasi.line.doc_ref` (Reference: `account.move` | `account.payment`) — back-link to source transaction.
- `custom.bupot.unifikasi.line.gross_amount` / `dpp_amount` / `withheld_amount` (Float 16,2, required, non-negative).
- `custom.bupot.unifikasi.line.rate` (Float 6,4, required, 0..100).

### custom_coretax_export — Coretax Import File Export (DJP Templates)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_coretax_export` |
| Version | 19.0.1.3.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM, Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_tax_id`, `custom_coretax`, `account` |
| Models / routes / tests | 3 / 0 / 4 |
| Tags | indonesian-tax, coretax, efaktur, bupot, export |

> Knowledge file is generator output, not human-reviewed.

Emits the XLSX workbooks DJP's Coretax accepts as **import** files: e-Faktur Keluaran
(FK/OF), Retur Masukan, Bupot Unifikasi, Bupot PPh 21, and Bupot Non-Resident. Unlike
`custom_coretax`'s XML wizard — whose envelope is a placeholder schema never aligned to a
published XSD — every layout here is transcribed column-for-column from the official DJP
template workbooks, including their typos (`Nomor Setifikat Insentif`) and their
per-template casing (`PPH23` in Unifikasi vs `PPh26` in Non-Resident).

**How it works**

- **Invoice form** — `Export e-Faktur (FK)` button on a posted customer invoice.
- **Invoice list** — select any number of invoices, then *Actions ▸ Export e-Faktur Keluaran (FK/OF)*; one workbook holds the whole selection in date order.
- **Reporting ▸ Export e-Faktur Keluaran (FK)** — date range plus optional customer and sales-journal filters, with a live count before committing.
- **Reporting ▸ Export File Import Coretax** — the whole-masa-pajak wizard.

**Key models**

- `custom.coretax.fk.builder` — **AbstractModel.** Owns the FK/OF column layout and every helper the templates share (`_fmt_date`, `_digits`, `_partner_address`, `_line_vat`, `_item_jenis`, `_render`). Both wizards pull it in via `_inherit`, so the helpers stay on `self` where the other `_rows_*` builders expect them; `account.move` reaches it through `self.env[...]`. No table, so it needs no `ir.model.access` row.
- `custom.coretax.template.export.wizard` — **TransientModel.** The original masa-pajak wizard; owns `_rows_bppu` / `_rows_bp21` / `_rows_bpnr` / `_rows_retur` / `_rows_taxlist` and the `_pemotong()` signer logic. Its `_rows_fk` now just delegates to the builder.
- `custom.coretax.fk.export.wizard` — **TransientModel.** Date-range FK/OF export with optional partner/journal filters and a computed `preview_count`.
- `account.move` — extended with `action_coretax_fk_export()`, written multi-record so the form button and the list-view server action share one implementation.

**Important fields**

- **custom.coretax.template.export.wizard**
- `template`: `Selection` — bppu / bp21 / bpnr / fk / retur / taxlist.
- `masa_pajak`, `tahun_pajak`: the tax period; `_period_bounds()` turns them into dates.
- `company_id`: the pemotong.
- `file_data` / `file_name` / `line_count`: the rendered result, shown for download.
- **custom.coretax.fk.export.wizard**
- `date_from` / `date_to`: required, default first/last day of the current month.
- `partner_ids`, `journal_ids`: optional filters; empty means all.
- `preview_count`: computed count of matching posted invoices.

### custom_coretax_pajakku — Custom Coretax — Pajakku ASPP Adapter

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_coretax_pajakku` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_coretax` |
| Models / routes / tests | 4 / 0 / 4 |
| Tags | indonesian-tax, coretax, audit-trail, multi-tenant, withholding |

> Knowledge file is generator output, not human-reviewed.

**Canonical concrete Pajakku ASPP (Authorized Service Provider Pajak) adapter** for the platform's Coretax stack. This module IS the host-to-host bridge between `custom_coretax`'s XML generators and the live Pajakku (mitrapajakku) REST API: OAuth2 client-credentials token cache, exponential-backoff retry, HTTP 429 Retry-After handling, circuit breaker, transaction ledger, per-tenant per-month usage meter, and a 30-minute sync cron that polls submission status and stamps approved NSFP back onto the source `account.move` / `custom.coretax.bukti.potong`.

This is the locked Phase-2 ASPP choice — verticals already subscribe to Pajakku. Other ASPPs (OnlinePajak, Klikpajak, Pajak.io) are intentionally separate sibling adapters that share the same `custom.coretax.adapter.base` contract.

**How it works**

- **Per-tenant setup**: admin opens **Coretax Config**, switches `adapter_type` to `pajakku`, ticks `pajakku_enabled`, leaves `pajakku_sandbox_mode=True`, fills `pajakku_client_id`, then uses **Set / Rotate Secret…** wizard (`custom.coretax.pajakku.secret.wizard`) to store the client secret encrypted at rest via `custom.ir.config.set_encrypted` (Fernet wrap with master KMS key). **Test Connection** runs a real OAuth2 exchange and stamps `pajakku_last_test` + `pajakku_last_test_ok` + `pajakku_last_test_message`.
- **Dispatcher hook**: the `custom.coretax.adapter.base._get_for_config` is overridden so that whenever `config.adapter_type == "pajakku"`, the resolver returns `custom.coretax.adapter.pajakku`.
- **Submit**: `custom_coretax` calls `adapter.submit_xml(xml_bytes, config=…, transaction_type=…, source_record=…)`. The adapter creates a `custom.coretax.transaction` row in `submitting` state, performs `POST /api/v1/{efaktur|bupot|coretax}/submit` with Bearer token + multipart XML, parses `submission_uuid`, marks `submitted`, bumps usage `faktur_submits` or `bupot_submits`, returns `{submission_uuid, status, message, transaction_id}`.
- **Resiliency**: `_http_request` retries up to `_MAX_RETRIES=3` attempts with backoff `1s → 2s → 4s`. HTTP 401 → force token refresh + retry once. HTTP 429 → sleep `min(Retry-After, 30s)` + retry. HTTP 5xx + transport errors → backoff retry. Each call bumps `api_calls`.
- **Circuit breaker** (module-globals `_CB_STATE`): `_CB_THRESHOLD=10` consecutive failures opens the breaker for `_CB_OPEN_SECONDS=3600` (1 hour). When tripped, posts a `mail.mt_note` on the config's chatter and `submit_xml` raises `UserError` immediately. Auto-reset after window.
- **Token cache** (module-global `_TOKEN_CACHE` keyed by `cr.dbname`): in-process dict with `{token, expires_at}`; `_get_token` returns cached unless within 30s of expiry or `force_refresh=True`. OAuth2 endpoint `/oauth/token` with `grant_type=client_credentials` + scope `efaktur:write bupot:write`.
- **Poll cron** `_cron_poll_pending` (every 30 min): for each `submitted` transaction, calls `query_nsfp(uuid)`; on `approved` → `mark_approved(nsfp)` writes NSFP back to `account.move.x_custom_nsfp` + `x_custom_coretax_status='approved'` (or `bukti_potong.no_bupot`); on `rejected` → `mark_rejected(code, message)` with chatter post + status flip. Also retries `queued` transactions with `retry_count < _MAX_RETRIES`.
- **Audit**: every state transition on `custom.coretax.transaction` writes `pdp.audit_log` via `pdp.audited.mixin` with classification `financial` (actions `coretax_pajakku_submitted` / `_approved` / `_rejected` / `_error`).
- **Usage metering**: `custom.coretax.pajakku.usage.increment(kind, company=…)` atomic SQL `UPDATE` per company per month (`unique(company_id, period)` constraint).

**Key models**

- `custom.coretax.adapter.pajakku` (AbstractModel) — Concrete adapter implementing `submit_xml` / `query_nsfp` / `download_response` / `test_connection`.
- `custom.coretax.adapter.base` (extended) — Dispatcher override registering `pajakku` adapter.
- `custom.coretax.transaction` — Per-submission ledger row (queued/submitting/submitted/approved/rejected/error).
- `custom.coretax.pajakku.usage` — Per-company-per-month counters (api_calls / faktur_submits / bupot_submits / errors).
- `custom.coretax.config` (extended) — Adds Pajakku fields, secret-set flag, test-connection action.
- `custom.coretax.pajakku.secret.wizard` (TransientModel) — Capture + encrypt client secret.

**Important fields**

- `custom.coretax.config.adapter_type` (extended Selection adding `pajakku`) — dispatcher key.
- `custom.coretax.config.pajakku_enabled` (Boolean) — master kill-switch; even with credentials set, adapter refuses to send while False.
- `custom.coretax.config.pajakku_api_url` (Char) — override; defaults to `https://sandbox-api.pajakku.com` or `https://api.pajakku.com`.
- `custom.coretax.config.pajakku_sandbox_mode` (Boolean, default True).
- `custom.coretax.config.pajakku_client_id` (Char).
- `custom.coretax.config.pajakku_client_secret_set` (Boolean, computed) — presence indicator; actual ciphertext lives in `custom.ir.config` keyed `custom_coretax_pajakku.client_secret.{config.id}`.
- `custom.coretax.config.pajakku_last_test` / `pajakku_last_test_ok` / `pajakku_last_test_message` — Test Connection result.
- `custom.coretax.config.pajakku_pending_tx` / `pajakku_error_tx` (Integer, computed) — dashboard counters.
- `custom.coretax.transaction.transaction_type` (Selection: efaktur_keluaran/masukan, bupot_pph21/23/26/4(2)/unifikasi).
- `custom.coretax.transaction.state` (queued/submitting/submitted/approved/rejected/error).
- `custom.coretax.transaction.external_uuid` (Char, indexed) — Pajakku submission UUID.
- `custom.coretax.transaction.nsfp` (Char, tracking) — DJP-issued number; written back to source doc on approval.
- `custom.coretax.transaction.payload` / `response_xml` / `response_pdf` (Binary, attachment) — audit artifacts.
- `custom.coretax.transaction.retry_count` (Integer, readonly).
- `custom.coretax.pajakku.usage.period` (Date, required) — first day of month; `unique(company_id, period)` constraint.

### custom_pph_witholding — Custom PPh Witholding Engine

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_pph_witholding` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_coretax`, `custom_hr_payroll_id`, `account`, `mail` |
| Models / routes / tests | 4 / 0 / 1 |
| Tags | indonesian-tax, withholding, coretax, accounting, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Generic, reusable **Indonesian PPh withholding engine** (PPh 21 / 22 / 23 / 26 / 4(2) / 15) extracted from `era_ppob_commission` and generalised. Provides three pieces:

1. A **rate registry** (`custom.witholding.rate`) keyed by `(pph_type, service_category, effective_date)` with separate **with-NPWP** and **without-NPWP** rates (latter is typically punitive 2× per UU PPh).
2. A stateless **engine** (`custom.witholding.engine`, AbstractModel) with `compute(partner, amount, pph_type, date, service_category)` and `compute_and_log(...)` producing a `custom.witholding.application` log entry.
3. An **append-only application log** (`custom.witholding.application`) auditing every computation, optionally linked to a `custom.bupot.unifikasi.line` for downstream Coretax reporting.

Triggers: manual `custom.apply.witholding.wizard` on any `account.move`; lazy `action_post` hook on `account.payment` (vendor payments with negative-amount tax lines); lazy override on `hr.payslip._custom_pph_apply_pph21` (no-op if `hr.payslip` not installed).

**How it works**

- Tax officer maintains `custom.witholding.rate` rows: per `(pph_type, service_category, effective_date_from..to)` set `with_npwp_rate` and `without_npwp_rate`, optional `legal_basis` citation.
- `custom.witholding.rate._find_active(pph_type, service_category, date)` picks the most-specific active row (matching `service_category` first), falls back to `service_category = "general"` if none.
- `custom.witholding.engine.compute(partner, amount, pph_type, date, service_category)` — `_has_valid_npwp(partner)` checks `res.partner.vat` after stripping `.`/`-`/space against `^\d{15,16}$`. Returns `{rate, withheld, gross_remain, applicable_rule_id, has_npwp}`. `withheld` is integer rupiah (Decimal `ROUND_HALF_UP`); zero if no rule matched.
- `engine.compute_and_log(...)` does the same plus creates a `custom.witholding.application` row (`state="computed"` by default, callable with `state="applied"`).
- Manual flow: user opens an `account.move` and clicks "Apply Witholding" → `account.move.action_open_witholding_wizard` opens `custom.apply.witholding.wizard` prefilled with partner + `amount_untaxed or amount_total`. User runs `action_preview` (no log) then `action_apply` (log with `state="applied"`); raises `UserError` if no rate matched. Returns an `act_window` opening the resulting application record.
- Payment hook: `account.payment.action_post()` → `_custom_pph_log_witholding()` iterates outbound payments, fetches `reconciled_bill_ids`, detects "withholding tax was applied" via any `line.tax_line_id.amount < 0` on the bill, and logs a PPh23 application (`amount=bill.amount_untaxed`, `date=payment.date`, `source_doc=payment`, `state="applied"`). Failures are swallowed (`_logger.warning`).
- Payslip hook: `hr.payslip._custom_pph_apply_pph21()` logs a PPh21 application per slip (`amount=slip.basic_wage`, `date=slip.date_to`); only attached when `hr.payslip` is in the registry. Failures logged, never raised.
- Application records expose `action_mark_applied` (computed → applied) and `action_reverse` (free → reversed).

**Key models**

- `custom.witholding.rate` — Rate matrix; inherits `pdp.audited.mixin`.
- `custom.witholding.engine` (AbstractModel) — Stateless service.
- `custom.witholding.application` — Per-event log; inherits `pdp.audited.mixin`, `mail.thread`, `mail.activity.mixin`.
- `custom.apply.witholding.wizard` (TransientModel) — Manual application UI.
- `account.move` (inherited) — adds `action_open_witholding_wizard` button.
- `account.payment` (inherited) — overrides `action_post` to log withholdings.
- `hr.payslip` (lazily inherited) — adds `_custom_pph_apply_pph21`.

**Important fields**

- `custom.witholding.rate.pph_type` (Selection: 23/22/4_2/15/21/26, required) — note the full PPh21 inclusion (unlike `custom_coretax_bupot`).
- `custom.witholding.rate.service_category` (Char, required, default `"general"`) — discriminator e.g. `sewa`, `jasa_teknik`, `manajemen`.
- `custom.witholding.rate.with_npwp_rate` / `without_npwp_rate` (Float 6,4, required, 0..100) — both required; "without NPWP" is typically 2× the with-NPWP rate per UU PPh Pasal 23 ayat (1a).
- `custom.witholding.rate.effective_date_from` (Date, required) / `effective_date_to` (Date, optional open-ended) — temporal validity.
- `custom.witholding.rate.legal_basis` (Text) — citation for auditors.
- `custom.witholding.application.partner_id` (M2o `res.partner`, indexed) — cuttee; sourced from caller (may be empty for bulk computes).
- `custom.witholding.application.source_doc` (Reference: account.move / account.payment / hr.payslip) — back-link.
- `custom.witholding.application.pph_type` (Selection incl. PPh21) — copied from the engine call.
- `custom.witholding.application.gross` / `rate` / `withheld` (Float) — engine results.
- `custom.witholding.application.has_npwp` (Boolean) — captured at compute time so retro-changes to partner.vat don't rewrite history.
- `custom.witholding.application.rule_id` (M2o `custom.witholding.rate`, `ondelete="restrict"`) — rate row that fired; restricts deletion of rules with applications.
- `custom.witholding.application.bupot_line_id` (M2o `custom.bupot.unifikasi.line`, `ondelete="set null"`) — link to the bupot line produced from this application.
- `custom.witholding.application.state` (Selection: computed/applied/reversed, tracked).

### custom_tax_id — Custom Tax Indonesia (PPh + DPP Nilai Lain)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_tax_id` |
| Version | 19.0.0.5.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM, Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_coretax`, `custom_accounting_full`, `account`, `base_vat`, `purchase`, `product` |
| Models / routes / tests | 5 / 0 / 6 |
| Tags | indonesian-tax, withholding, coretax, audit-trail |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.1.0, module is now 19.0.0.5.0.

Indonesian-specific tax engine: PPh withholding (Pasal 23, 4(2), 26, 22, 21) on vendor bills, PPN DPP Nilai Lain (PMK 131/2024) on the tax base, NPWP / NIK validation on partners, and the Faktur Pengganti relink workflow. Sits between Odoo `account` and `custom_coretax` — generates draft `custom.coretax.bukti.potong` records that Coretax then serialises to the DJP e-Bupot XML.

This is the canonical Indonesian withholding + DPP module. Any BRD with "potong PPh", "bukti potong", "PPh 23/4(2)/26", "DPP nilai lain", "PMK 131", "NPWP validation", or "Faktur Pengganti" maps here. Coretax depends on this module's bupot draft for export.

**How it works**

- **NPWP/NIK setup**: `res.partner.x_custom_npwp` (15 legacy or 16-digit NIK-based since 2024), `x_custom_nik` (16-digit, individuals); computed `x_custom_npwp_status` ∈ valid/invalid/none and `x_custom_has_valid_npwp`. `x_custom_pkp` flag for PPN registration. `x_custom_foreign_counterparty` auto-set when partner country ≠ company country.
- **Withholding catalogue** (`tax.withholding.category`): jenis penghasilan with `pph_kind` ∈ pph_23/pph_4_2/pph_26/pph_22/pph_21, `bupot_object_code` (matches Coretax e-Bupot XML).
- **Withholding rule** (`tax.withholding.rule`): `category_id` + `tarif` + optional `tarif_no_npwp` (PPh 23: 2% → 4% bump) + `account_id` (account hutang pajak) + optional filters `product_category_ids` / `partner_category_ids` / `foreign_only`. Resolution priority `priority desc, sequence asc`.
- **Apply on vendor bill post**: `account.move._post` (for `in_invoice`/`in_refund`) calls `_custom_apply_withholding` BEFORE super. Idempotent (skips if `x_custom_withholding_line_ids` already populated). For each non-display invoice line, resolves rule via `tax.withholding.rule._resolve_for_line(ml)` (filters by `active`, `company_id`, then `foreign_only`/`product_category_ids`/`partner_category_ids`); picks `_effective_tarif(partner)` (`tarif_no_npwp` if vendor lacks valid NPWP). Creates `account.move.withholding.line` with `base = ml.price_subtotal`, `tax = round(base * tarif/100, 2)`. PDP audit row written.
- **Bupot draft materialisation**: `account.move.withholding.line.create()` runs `_materialise_bupot()` which creates a `custom.coretax.bukti.potong` with `no_bupot = "DRAFT-{move.name}-{line.id}"`, `jenis_pph`, `tarif`, `dpp`, `pph_terpotong`, `tanggal_bupot`, `period_year`/`period_month` from invoice_date, `source='outgoing'` (we cut, vendor receives), state=draft. NSFP is empty — Coretax fills after DJP approval.
- **PPN DPP Nilai Lain**: `account.tax.x_custom_dpp_method` ∈ regular/nilai_lain + `x_custom_dpp_factor` (e.g. 11/12 ≈ 0.916667) + `x_custom_dpp_category` enumerating PMK 131/2024 categories. `_dpp_adjust(raw_base)` multiplies by factor when method is nilai_lain. Overridden into Odoo 19's tax pipeline: `_eval_tax_amount_price_excluded`, `_eval_tax_amount_price_included`, `_eval_tax_amount_fixed_amount`.
- **Faktur Pengganti wizard**: applies kode status `01`/`02`/... sequentially on `account.move.coretax_status` with NSFP relinking.
- **Bulk validation wizard**: pre-flight check before Coretax export — NPWP (15/16 digit), NIK (16 digit), DPP > 0, sertel attached + not expired, across a batch of moves.

**Key models**

- `res.partner` (inherited) — NPWP/NIK + PKP + foreign-counterparty flags.
- `tax.withholding.category` — jenis penghasilan + pph_kind + Coretax `bupot_object_code`.
- `tax.withholding.rule` — tarif + account hutang pajak + filters; resolution helper `_resolve_for_line`.
- `account.move.withholding.line` — one row per (vendor bill line × rule); back-refs `bupot_id` to the auto-materialised `custom.coretax.bukti.potong`.
- `account.move` (inherited) — Adds `x_custom_withholding_line_ids` + computed `x_custom_total_withheld`; overrides `_post` to apply withholding.
- `account.tax` (inherited) — DPP Nilai Lain fields + tax-pipeline overrides.
- `product.template` (inherited) — `x_custom_withholding_category_id` hint.
- `tax.faktur.pengganti.wizard` (TransientModel) — kode status sequencing + NSFP relinking.
- `tax.bulk.validation.wizard` (TransientModel) — pre-export validator.

**Important fields**

- `res.partner.x_custom_npwp` (Char) — accepts dots/hyphens; computed status strips them before regex match.
- `res.partner.x_custom_npwp_status` (Selection valid/invalid/none, computed, stored).
- `res.partner.x_custom_has_valid_npwp` (Boolean, computed, stored) — drives `_effective_tarif`.
- `res.partner.x_custom_pkp` (Boolean) — fiscal-position trigger.
- `res.partner.x_custom_foreign_counterparty` (Boolean, computed, stored) — auto from country comparison.
- `res.partner.x_custom_nik` (Char) — 16-digit constraint `_check_nik`.
- `tax.withholding.category.pph_kind` (Selection pph_23/pph_4_2/pph_26/pph_22/pph_21).
- `tax.withholding.category.bupot_object_code` (Char) — kode objek pajak per PER-04/PJ/2023; surfaces in Coretax XML.
- `tax.withholding.rule.tarif` (Float, digits=(6,4), 0–100) — base rate.
- `tax.withholding.rule.tarif_no_npwp` (Float) — bumped rate; 0 = no bump (fall back to `tarif`).
- `tax.withholding.rule.account_id` (M2o `account.account`, liability_current) — required before `active=True` via `_check_account_when_active`.
- `tax.withholding.rule.foreign_only` (Boolean) — switches PPh 23 → PPh 26 routing.
- `tax.withholding.rule.priority` (Integer, default 10) — `priority desc, sequence asc` resolution.
- `account.move.withholding.line.base_amount` / `tax_amount` (Monetary) / `tarif` (Float, 6,4).
- `account.move.withholding.line.bupot_id` (M2o `custom.coretax.bukti.potong`, readonly) — auto-materialised draft.
- `account.move.x_custom_total_withheld` (Monetary, computed, stored) — `sum(withholding_line_ids.tax_amount)`.
- `account.tax.x_custom_dpp_method` (Selection regular/nilai_lain).
- `account.tax.x_custom_dpp_factor` (Float, digits=(12,6), default 1.0) — `_check_dpp_factor` requires > 0 when method = nilai_lain.
- `account.tax.x_custom_dpp_category` (Selection) — 13 enumerated PMK 131/2024 categories (impor/film/emas_perhiasan/kendaraan_bekas/paket_wisata/agen_perjalanan/jasa_pengiriman/hasil_tembakau/pemasaran_perdagangan/freight_forwarding/jasa_lain/ppn_efektif_11_12/ppn_efektif_12).
- `product.template.x_custom_withholding_category_id` (M2o `tax.withholding.category`) — default for jasa konsultan / sewa / royalti.

## HR & Payroll (SDM & Payroll)

### custom_attendance — Custom Attendance

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_attendance` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_ai_bridge`, `hr_attendance`, `hr_work_entry`, `custom_hr_payroll_id`, `portal`, `mail` |
| Models / routes / tests | 3 / 2 / 2 |
| Tags | attendance, geofence, kiosk, approval-workflow, payroll, ai |

> Knowledge file is generator output, not human-reviewed.

Extends CE `hr_attendance` with geofenced GPS check-in/out (haversine validation), a PIN-based public kiosk portal, an anomaly-driven manual approval workflow (long shifts > 12h or late-night check-ins), automatic overtime hours computation (configurable threshold + weekday/weekend rules), one-click conversion of OT hours into `hr.work.entry` records that feed `custom_hr_payroll_id`, and a face-recognition verification stub bridged to `custom.ai`.

**How it works**

- HR seeds `attendance.geofence` records (name, latitude/longitude, `radius_meters`, company_id).
- HR seeds `custom.attendance.overtime.rule` rows (one per `differential` ∈ weekday/weekend/holiday) via `data/attendance_overtime_rule_seed.xml`; each has `threshold_hours` (default 8.0), `multiplier` (default 1.5), `is_active`.
- Employee opens `/custom_attendance/kiosk` on a tablet (auth=public). A cookie `custom_attendance_kiosk` carrying an opaque token is set on first GET.
- Employee enters their `hr.employee.pin` (4+ digits) and submits to `/custom_attendance/kiosk/submit` with optional lat/lng. `_kiosk_resolve_employee_by_pin` looks up the employee; `_kiosk_toggle` either:
- If an open attendance (no `check_out`) exists → write `check_out=now`, `x_check_out_lat/lng` if provided.
- Else → create a new `hr.attendance` with `check_in=now`, `x_check_in_lat/lng`, and `x_kiosk_session=<cookie token>`.
- `_compute_geofence_validated` runs haversine between `(x_check_in_lat, x_check_in_lng)` and `(x_geofence_id.latitude, x_geofence_id.longitude)`; valid if distance ≤ `radius_meters`.
- `_compute_overtime_hours` reads `worked_hours` and the best-matching active rule (weekday/weekend via `check_in.weekday() >= 5`) and stores `x_overtime_hours = max(0, worked_hours - threshold_hours)` (fallback threshold 8.0 if no rule).
- `_compute_approval_required` flags `x_approval_required=True` when `worked_hours > 12.0` OR `check_in.hour >= 22 or < 5`.
- Anomalous attendances: `action_request_approval()` (draft/rejected → pending) schedules a `mail.activity` for the employee's manager (via `parent_id.user_id`, fallback to current user). Manager calls `action_approve()` or `action_reject()` (pending → approved/rejected, stamps `x_approval_by`).
- Approved attendance with OT: `action_create_overtime_work_entry()` ensures an `hr.work.entry.type` with `code='OT'` exists (creates one if missing), cancels the previous work entry if re-run (idempotent), creates a new `hr.work.entry` (`state='draft'`, duration = `x_overtime_hours`, `date_start=check_in`, `date_stop=check_in + OT hours`), and writes `x_payroll_work_entry_id` + `x_payroll_synced=True`. On `unlink`, linked work entries are cancelled.
- Optional face verification: `action_verify_face()` calls `custom.ai._recommend(model='hr.attendance', res_id=self.id, payload={...})`; parses confidence (0-1) from response, sets `x_face_recognition_confidence`. If `confidence < 0.6`, forces `x_approval_required=True` and posts chatter.

**Key models**

- `hr.attendance` (inherited) — Adds GPS, kiosk session, approval workflow, OT, payroll bridge, face-recognition fields; mixes in `mail.thread`, `mail.activity.mixin`.
- `attendance.geofence` — Geofence definition (lat/lng + radius_meters, default 100).
- `custom.attendance.overtime.rule` — Rule rows; `(threshold_hours >= 0)` and `(multiplier > 0)` CHECK constraints.

**Important fields**

- `hr.attendance.x_geofence_id` (M2o `attendance.geofence`) — assigned fence; without it, validation is False.
- `hr.attendance.x_geofence_validated` (Boolean, computed, stored) — depends on geofence + check_in coords; **only checks check-in**, not check-out.
- `hr.attendance.x_check_in_lat/lng` / `x_check_out_lat/lng` (Float, digits=(10,7)).
- `hr.attendance.x_overtime_hours` (Float, computed, stored) — depends on `worked_hours` and `check_in` (for weekday/weekend rule lookup).
- `hr.attendance.x_approval_state` (Selection: draft/pending/approved/rejected, default draft, tracked).
- `hr.attendance.x_approval_required` (Boolean, computed, stored, tracked) — `True` if worked_hours > 12 OR hour ∈ [22..24) ∪ [0..5).
- `hr.attendance.x_approval_by` (M2o `res.users`, readonly) — actor.
- `hr.attendance.x_kiosk_session` (Char) — opaque session id from kiosk cookie; trace-only.
- `hr.attendance.x_face_recognition_data` (Binary, attachment=True) — selfie snapshot.
- `hr.attendance.x_face_recognition_confidence` (Float, readonly) — 0-1, threshold 0.6.
- `hr.attendance.x_payroll_work_entry_id` (M2o `hr.work.entry`, readonly) — payroll link.
- `hr.attendance.x_payroll_synced` (Boolean, readonly, tracked) — flag set when work entry created.
- `custom.attendance.overtime.rule.differential` (Selection: weekday/weekend/holiday) — match key; `holiday` exists as a value but **no public-holiday lookup is done** in `_get_active_overtime_rule` (only weekday vs weekend by `weekday() >= 5`).
- `custom.attendance.overtime.rule.threshold_hours` (Float, default 8.0) — daily threshold above which hours are OT.
- `custom.attendance.overtime.rule.multiplier` (Float, default 1.5) — pay multiplier; **stored but not used in compute** (consumed by payroll downstream).

**Endpoints**: `/custom_attendance/kiosk`, `/custom_attendance/kiosk/submit`

### custom_elearning — Custom eLearning

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_elearning` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `website_slides`, `custom_hr_appraisal`, `hr`, `mail` |
| Models / routes / tests | 1 / 0 / 0 |
| Tags | knowledge, indonesian-payroll, crm |

> Knowledge file is generator output, not human-reviewed.

Extends the CE `website_slides` module with Indonesian-localized e-learning capabilities: learner cohort/batch management, Bahasa Indonesia QWeb-PDF certificate generation, course catalog filter fields (level / duration / category / certificate validity), quiz pass-threshold logic, HR department auto-enrolment, mid-point completion reminder cron, and an `hr.skill` bridge that awards skills on course completion.

Intended for SMB tenants running internal training / onboarding / compliance courses where certificate issuance and cohort-based reporting matter more than the CE website storefront.

**How it works**

- An admin creates a `slide.channel` (course) and fills the localization fields: `x_level`, `x_duration_hours`, `x_certificate_validity_months`, `x_id_category`, `x_id_language`, optional `x_certificate_template_id` and `x_completion_appraisal_skill_code`.
- An admin creates `custom.elearning.cohort(name, channel_id, start_date, end_date, capacity, department_id)` and either manually fills `member_ids` or calls `action_auto_enrol_by_department(department_id)` — which sweeps `hr.employee` in that department and adds `work_contact_id` (preferred) or `user_id.partner_id` to `member_ids`, creating any missing `slide.channel.partner` enrolment rows.
- Learners progress through slides; `slide.channel.partner.completion` (CE field) advances. A custom `write` override on `slide.channel.partner` fires `_on_course_completed` when `completion` hits 100, which calls `_assign_hr_skill(code)` to add the configured `hr.skill` to the matching `hr.employee` (graceful no-op if `hr_skills` not installed).
- Mid-point reminder cron `slide.channel._cron_send_completion_reminders` iterates `custom.elearning.cohort` in state `open`/`running`. For each cohort past its 50% elapsed window (`_past_midpoint`), it emails every member whose `slide.channel.partner.completion < 50` via `mail_template_cohort_completion_reminder`; falls back to chatter note when the template is missing.
- Certificate issuance: `slide.channel.action_generate_certificate(partner_ids=None)` selects either explicit partners or all `completion >= 100` members, calls `slide.channel.partner._stamp_certificate_issued()` to set `x_certificate_issued / x_certificate_issue_date / x_certificate_expiry_date` (issue_date + `validity_months × 30` days), increments `x_certificate_generated_count`, and returns the `action_report_elearning_certificate` QWeb-PDF action.
- `slide.slide.check_quiz_pass(score)` accepts 0..1 or 0..100, normalises, compares to `x_passing_score` (default 70%), and posts a chatter line.

**Key models**

- `custom.elearning.cohort` — Batch/cohort with M2M members, instructor, start/end window, capacity, state machine, last_reminder_date, optional auto-enrol department.
- `slide.channel` (inherited) — Adds certificate template + counter + language, catalog filter fields (level/duration/category/validity), `x_completion_appraisal_skill_code`. Hosts `action_generate_certificate` and the cron entry point.
- `slide.channel.partner` (inherited) — Adds certificate issuance markers, computed `report_certificate_id`, `_stamp_certificate_issued`, `_on_course_completed` hook, and the `_assign_hr_skill` bridge.
- `slide.slide` (inherited) — Adds `x_passing_score` + `check_quiz_pass(score)` helper.

**Important fields**

- `custom.elearning.cohort.state` (Selection: draft/open/running/completed/cancelled, tracking) — gates cron eligibility (`open`/`running`).
- `custom.elearning.cohort.member_ids` (M2M `res.partner`) — cohort roster; also drives `enrolled_count` stored compute.
- `custom.elearning.cohort.department_id` (M2o `hr.department`) — default department for `action_auto_enrol_by_department`.
- `custom.elearning.cohort.last_reminder_date` (Date, copy=False) — bookkeeping for the mid-point reminder.
- `slide.channel.x_certificate_validity_months` (Integer, default 12) — multiplied by 30 days when stamping expiry.
- `slide.channel.x_id_language` (Selection: id/en, default `id`) — certificate render language.
- `slide.channel.x_id_category` (Selection: technical/softskill/compliance/onboarding/other).
- `slide.channel.x_completion_appraisal_skill_code` (Char) — `hr.skill.name` to assign on 100% completion.
- `slide.channel.partner.x_certificate_issued` / `x_certificate_issue_date` / `x_certificate_expiry_date` — certificate lifecycle stamps.
- `slide.slide.x_passing_score` (Float, default 70.0) — quiz pass threshold percentage.

### custom_expenses — Custom Expenses

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_expenses` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_ai_bridge`, `custom_approval_engine`, `hr_expense`, `account`, `product`, `mail` |
| Models / routes / tests | 3 / 0 / 3 |
| Tags | expense-management, ai, approval-workflow, audit-trail, ocr |

> Knowledge file is generator output, not human-reviewed.

Extends Odoo's `hr_expense` application with the EE-gap features the platform needs: AI-assisted receipt OCR (vendor / amount / date / tax / currency / confidence) via `custom_ai_bridge`, multi-tier approval workflow via `custom_approval_engine.approval.mixin`, expense-report batching (`custom.expense.report`), corporate card registry (`custom.expense.corporate.card`) with PAN masking validation, mileage tracking with configurable per-km rate, and reimbursement payment generation. PDP audit on submit/approve.

This is the canonical "claim / klaim biaya / reimbursement" module. Any BRD with "expense claim", "OCR struk", "corporate card", "mileage", "expense approval", or "bulk reimbursement" maps here.

**How it works**

- **Card setup**: HR creates `custom.expense.corporate.card` with `employee_id` + `bank_journal_id` + `masked_number` (e.g. `**** **** **** 1234`). Validation `_check_masked_number` rejects strings that look like a full PAN (13–19 digits with no `*`).
- **Mileage product**: a `product.product` with `default_code = "MILEAGE"` triggers `x_is_mileage=True` (computed). Default per-km rate from `ir.config_parameter "custom_expenses.id_mileage_rate"` (default 5000 IDR/km).
- **Expense capture**: User attaches receipt (image/PDF) and clicks `action_ai_extract_receipt`. Method builds payload via `_custom_ai_payload()` — encodes primary attachment as base64 (priority: `message_main_attachment_id` → latest of `attachment_ids` → most recent `ir.attachment` on record) — calls `env['custom.ai']._recommend(model='hr.expense', res_id=self.id, payload={task:'extract_receipt', image_base64, ...})`. Response parsed by `_parse_ai_receipt_response(result)` and written to `x_ai_extracted_amount` / `_tax_amount` / `_date` / `_vendor` / `_currency_code` / `x_ai_confidence` / `x_receipt_ocr_text`. Failure surfaces as warning notification, never blocks.
- **Mileage**: `_onchange_mileage` and `write()` keep `total_amount = x_mileage_km * x_mileage_rate` in sync. `quantity = km`, `unit_amount = rate`.
- **Corporate card linkage**: `_onchange_corporate_card` + `_apply_corporate_card_payment_mode(vals)` force `payment_mode = "company_account"` when `x_corporate_card_id` is set — excludes from employee reimbursement queue.
- **Approval**: `hr.expense._inherit = ["hr.expense", "approval.mixin"]`. `action_submit_expenses()` overridden to partition via `_approval_request_or_proceed()` — auto-creates + submits the approval when a matrix matches (expense waits, Waiting Approval), and for the proceeding subset audits `_pdp_audit_expense_event("submit")` then super-submits. After full approval the engine re-runs `action_submit_expenses` via `_approval_on_granted`. The standalone "Request Approval" button (`action_request_approval_expense`) has been removed from the view (the method is retained).
- **Expense report**: `custom.expense.report` batches expenses for one employee. State machine `draft` → `submitted` → `approved` → `paid` (+ `cancelled`). `action_submit_for_approval()` flips state + calls `_approval_request_or_proceed()` (no-op when no matrix). `_approval_on_granted()` → `action_approve()` auto-advances the report to `approved` once all tiers approve; `action_approve()` itself remains gated by `_approval_check_required()` for the no-matrix manual path. `action_register_payment()` (approved only) creates ONE `account.payment` per report on `partner = employee_id.work_contact_id`, summing only expenses without corporate card and not `company_account` mode. All-corporate-card reports go directly to paid without payment.
- **Single-expense reimbursement**: `hr.expense.action_register_reimbursement_payment()` creates `account.payment(outbound, supplier, amount=total_amount)` on `employee.work_contact_id` (or `user_id.partner_id` fallback) — only when approval state=='approved', no corporate card, and payment_mode ≠ company_account.
- **PDP audit**: `_pdp_audit_expense_event(event)` direct INSERT to `pdp.audit_log` (classification='internal'), best-effort.

**Key models**

- `hr.expense` (inherited) — mixes `approval.mixin`; adds AI OCR fields, corporate card link, mileage, reimbursement helper.
- `custom.expense.report` — Batch container. Inherits `mail.thread`, `approval.mixin`. Sequence `custom.expense.report`.
- `custom.expense.corporate.card` — Card registry. Inherits `mail.thread`.

**Important fields**

- `hr.expense.x_receipt_ocr_text` (Text) — raw OCR text, capped 65000.
- `hr.expense.x_ai_extracted_amount` / `_tax_amount` (Monetary, currency=`currency_id`) — AI numbers, separate from user-entered `total_amount`.
- `hr.expense.x_ai_extracted_date` (Date) / `_vendor` (Char) / `_currency_code` (Char size=8).
- `hr.expense.x_ai_confidence` (Float, digits=(3,2)) — 0.0–1.0 confidence score.
- `hr.expense.x_corporate_card_id` (M2o `custom.expense.corporate.card`) — when set, `payment_mode` is forced to `company_account` on create/write.
- `hr.expense.x_is_mileage` (Boolean, computed from `product_id.default_code == "MILEAGE"`, stored).
- `hr.expense.x_mileage_km` (Float, digits=(12,2)) / `x_mileage_rate` (Monetary).
- `hr.expense.x_custom_approval_request_id` (from `approval.mixin`, M2o, computed, stored).
- `hr.expense.x_custom_approval_state` (from `approval.mixin`, related, stored).
- `custom.expense.report.state` (Selection draft/submitted/approved/paid/cancelled, required, tracking).
- `custom.expense.report.employee_id` (M2o `hr.employee`, required) — `expense_ids` constrained to same employee via `_check_expenses_same_employee`.
- `custom.expense.report.expense_ids` (M2m `hr.expense` via `custom_expense_report_expense_rel`).
- `custom.expense.report.total_amount` (Monetary, computed=`sum(expense_ids.total_amount)`, stored).
- `custom.expense.report.payment_ids` (M2m `account.payment`) — generated reimbursements.
- `custom.expense.corporate.card.masked_number` (Char, required, tracking) — `_check_masked_number` blocks PAN-shaped strings.
- `custom.expense.corporate.card.bank_journal_id` (M2o `account.journal`, type∈bank/cash, required).
- Unique constraint on card: `unique(employee_id, masked_number, company_id)`.
- Config param: `custom_expenses.id_mileage_rate` (default 5000.0 IDR/km).

### custom_fleet_id — Custom Fleet ID

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_fleet_id` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `fleet`, `mail` |
| Models / routes / tests | 2 / 0 / 2 |
| Tags | fleet, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Indonesia localization for the standard Odoo Fleet app. Adds STNK (Surat Tanda Nomor Kendaraan) and KIR (Kartu Uji Berkala) number/expiry tracking with computed status (`valid`/`expiring`/`expired`/`na`) and configurable alert windows, BBM (Pertamina fuel) type selection covering Pertalite/Pertamax/Pertamax Turbo/Dex/Dexlite/Solar/Listrik (EV), a fuel log with km/L consumption compute, full driver assignment history with single-active-per-vehicle constraint and PDP audit on driver change, next-service-due tracking by km or date, and an Indonesia plate-format validator (warning-only, non-blocking).

A daily cron posts STNK/KIR reminders to vehicle chatter and (when `maintenance` is installed) auto-creates a `maintenance.request` idempotently for renewals due within 30 days.

Note: **BPKB is mentioned in the task brief but is not implemented here** — only STNK + KIR are tracked.

**How it works**

- An admin records `fleet.vehicle.x_stnk_number`, `x_stnk_expiry_date`, `x_stnk_alert_days_before` (default 30), and the equivalent KIR fields. Computed status is `expired` if delta<0, `expiring` if 0≤delta≤alert_days, else `valid`. KIR additionally has `na` for vehicles not subject to uji berkala.
- License plate input is validated against `^[A-Z]{1,2}\s\d{1,4}\s[A-Z]{1,3}$` (e.g. `B 1234 ABC`). Mismatches post a chatter note via `mail.mt_note`; only the context flag `custom_fleet_id_strict_plate` upgrades it to a hard `UserError` (used in tests).
- Driver assignment: writing `x_driver_partner_id` triggers `_pdp_audit_driver_change` (direct INSERT into `pdp.audit_log` with classification `internal`) and `_sync_driver_assignment_history` — closes any prior active assignment (`status='ended'` or `'transferred'`) and creates a new `custom.fleet.driver.assignment(status='active', start_date=today)`. A SQL-level constraint (`_check_single_active_per_vehicle`) prevents two active assignments per vehicle.
- BBM logging: an operator creates `custom.fleet.bbm.log(vehicle_id, date, odometer_km, liter, price_per_liter, gas_station, receipt_attachment)`. `_compute_consumption` derives km/L from delta-odometer vs liters since the previous log for that vehicle. `_sync_vehicle_odometer` pushes the highest reading back to `fleet.vehicle.x_current_odometer`.
- Service-due: stored compute `x_service_due` = `(current_odo ≥ next_service_km) OR (today ≥ next_service_date)`. Cron `cron_check_service_due` posts a chatter reminder for vehicles within 14 days or already due.
- STNK/KIR cron: `cron_check_expiry` runs daily; for vehicles in `expiring`/`expired` status posts a structured chatter note. If the standard `maintenance` module is installed and expiry falls within 30 days, `_create_stnk_kir_maintenance_request` creates a `maintenance.request(maintenance_type='preventive')` — idempotent per vehicle by matching on title `"STNK/KIR Renewal Needed: <plate>"` against requests whose `stage_id.done = False`.

**Key models**

- `fleet.vehicle` (inherited) — Adds 4 STNK/KIR fields each (+ status compute), BBM type, driver partner, service-due tracking, BBM log + driver-assignment O2M reverse links + counts, plate validator, write/create hooks, two daily crons.
- `custom.fleet.bbm.log` — Fuel log row with stored consumption compute; pushes odometer back to vehicle on save.
- `custom.fleet.driver.assignment` — Assignment history row; single-active per vehicle constraint; computed `duration_days`.

**Important fields**

- `fleet.vehicle.x_stnk_status` / `x_kir_status` (Selection, stored compute) — drives reminders + maintenance auto-creation.
- `fleet.vehicle.x_stnk_alert_days_before` / `x_kir_alert_days_before` (Integer, default 30) — slack window before expiry.
- `fleet.vehicle.x_bbm_type` (Selection: pertalite/pertamax/pertamax_turbo/dex/dexlite/solar/listrik) — Pertamina + EV catalog.
- `fleet.vehicle.x_driver_partner_id` (M2o `res.partner`, tracking) — current driver; write triggers PDP audit + history sync.
- `fleet.vehicle.x_current_odometer` (Float, km) — synced from BBM log highest reading.
- `fleet.vehicle.x_next_service_km` (Integer) / `x_next_service_date` (Date) / `x_service_due` (Boolean stored compute).
- `custom.fleet.bbm.log.odometer_km` (Integer, required, tracking) — feeds the vehicle's `x_current_odometer`.
- `custom.fleet.bbm.log.consumption_km_per_l` (Float, stored compute, digits=(8,2)) — km / liters since previous log.
- `custom.fleet.driver.assignment.status` (Selection: active/ended/transferred, tracking) — `active` is unique per vehicle.
- `custom.fleet.driver.assignment.duration_days` (Integer, stored compute) — `(end_date or today) - start_date`, floored at 0.

### custom_frontdesk — Custom Frontdesk

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_frontdesk` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_whatsapp`, `hr`, `mail`, `web` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | visitor-management, whatsapp, qr-checkin, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Standalone visitor-management module (no CE/EE equivalent in Odoo 19): captures `custom.frontdesk.visitor` records at named `custom.frontdesk.station` stations, generates a one-time `kiosk_token` + PNG QR for pre-registration self-check-in, notifies the host via WhatsApp (using `custom_whatsapp.whatsapp.message`), tracks a workflow `expected → checked_in → checked_out / cancelled`, group-restricts KTP/Passport access, and exposes `export_anonymized()` to mask `id_number` for compliance dumps. Visitors are PDP-audited via `pdp.audited.mixin`.

**How it works**

- A receptionist or host pre-creates a visitor with `state=expected`, host (`hr.employee`), station, ETA, KTP/Passport, photo, phone.
- Host clicks `action_preregister_visitor()` → generates `kiosk_token = secrets.token_urlsafe(24)`, sends `mail_template_preregister_visitor` email (best-effort), and creates a draft `whatsapp.message` (template `whatsapp_template_host_notify` referenced) with the QR self-check-in URL `<web.base.url>/custom_frontdesk/kiosk_checkin/<token>`. `qr_code_image` is a non-stored compute that renders a PNG via the `qrcode` library (no-op if the lib is missing).
- At the kiosk the visitor scans the QR → controller hits `_check_in_by_token(token)` which validates (`missing/unknown/used/cancelled` raise `UserError`), and if `state=expected` flips to `checked_in`, stamps `check_in_time`, marks `kiosk_token_used=True`, and triggers host WhatsApp via `_notify_host_whatsapp()`.
- Alternative path: receptionist clicks `action_check_in()` directly (no QR) — same notification path.
- Host receives WhatsApp via `whatsapp.message` (template body with `{{name}}/{{company}}/{{station}}/{{purpose}}` literal-substitution, NOT Meta `{{1}}` positional form; the `whatsapp.template` Meta sync handles positional translation elsewhere).
- `action_check_out` writes `check_out_time`; `action_cancel` flips to cancelled.
- `action_print_badge` returns the QWeb report action `action_report_visitor_badge` (badge contains the QR if it was rendered).
- `action_view_visits_for_partner` opens the list of all visits for the same `res.partner`.
- `export_anonymized()` returns a list of dicts where `id_number` is masked to `****<last4>` regardless of caller permissions (uses `sudo()` then masks). Field-level `id_number` is `groups="custom_frontdesk.group_manager"` so non-managers don't see the raw value in the UI either.

**Key models**

- `custom.frontdesk.visitor` — Visitor record (`mail.thread + pdp.audited.mixin`).
- `custom.frontdesk.station` — Named station (kiosk) per company.

**Important fields**

- `custom.frontdesk.visitor.state` (Selection: expected/checked_in/checked_out/cancelled) — workflow.
- `custom.frontdesk.visitor.host_employee_id` (M2o `hr.employee`, required, tracked) — notification target.
- `custom.frontdesk.visitor.station_id` (M2o `custom.frontdesk.station`, required).
- `custom.frontdesk.visitor.partner_id` (M2o `res.partner`, indexed) — historical aggregation key.
- `custom.frontdesk.visitor.id_number` (Char, `groups="custom_frontdesk.group_manager"`) — KTP/Passport, manager-only.
- `custom.frontdesk.visitor.kiosk_token` (Char, indexed, single-use) / `kiosk_token_used` (Boolean) — QR self check-in credentials.
- `custom.frontdesk.visitor.qr_code_image` (Binary, computed, non-stored) — PNG of `<web.base.url>/custom_frontdesk/kiosk_checkin/<token>`.
- `custom.frontdesk.visitor.badge_number` (Char, default `ir.sequence.next_by_code('custom.frontdesk.visitor.badge')`).
- `custom.frontdesk.visitor.whatsapp_notified` (Boolean).
- `custom.frontdesk.visitor.check_in_time` / `check_out_time` (Datetime).

### custom_hr_appraisal — Custom HR Appraisal

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_hr_appraisal` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `hr`, `mail` |
| Models / routes / tests | 5 / 0 / 0 |
| Tags | knowledge, audit-trail, pdp, approval-workflow |

> Knowledge file is generator output, not human-reviewed.

Lightweight EE-equivalent performance appraisal: define weighted competency templates, launch periodic cycles, auto-create an `appraisal.appraisal` per in-scope employee, run self → manager → calibration → closed workflow with weighted overall score, and audit every state change as `sensitive_pii`.

**How it works**

- HR designs an `appraisal.template` with `appraisal.template.item` children (name, competency, weight).
- HR creates an `appraisal.cycle` (name, period_start, period_end, template_id, optional `department_ids`) in `draft`.
- `action_launch()` searches active `hr.employee` (filtered by departments if any), creates one `appraisal.appraisal` per employee with the cycle's template, copying each template item into an `appraisal.line` (name, competency, weight). Cycle moves `draft`→`running`. Unique constraint `(cycle_id, employee_id)` prevents duplicates.
- Employee/manager workflow on `appraisal.appraisal`:
- `action_start_self_review()` — `draft`→`self_review`.
- Employee fills `line_ids.score_employee` (1-5) and `comment_employee`, `action_submit_self()` → `self_review`→`manager_review`, stamps `submitted_at_employee`.
- Manager fills `line_ids.score_manager` (1-5) and comments, `action_submit_manager()` → `manager_review`→`calibration`, stamps `submitted_at_manager`. `overall_score` is recomputed (weighted average of `score_manager * weight / sum(weight)`).
- HR `action_close()` → `calibration`→`closed`, stamps `closed_at`.
- Every transition writes a `pdp.audit_log` row via `pdp.audited.mixin._pdp_audit_write` with classification `sensitive_pii`.
- `appraisal.cycle.action_close()` is a free transition (no state guard) to mark the cycle done.

**Key models**

- `appraisal.template` — Reusable item set + weights, multi-company via `company_id`.
- `appraisal.template.item` — Per-template line: name, competency, weight, description.
- `appraisal.cycle` — Time-windowed campaign (`period_start`/`period_end`) with optional `department_ids` scoping; tracks count + completed_count.
- `appraisal.appraisal` — Per-employee record; inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`.
- `appraisal.line` — Per-item review row with both `score_employee` and `score_manager`.

**Important fields**

- `appraisal.appraisal.state` (Selection: draft/self_review/manager_review/calibration/closed) — drives flow; guards in `action_submit_self`/`action_submit_manager`.
- `appraisal.appraisal.overall_score` (Float, computed, stored) — `Σ(score_manager × weight) / Σ(weight)` rounded 2dp; weight=0 falls back to divisor=1.0.
- `appraisal.appraisal._uniq_cycle_employee` — `unique(cycle_id, employee_id)` constraint.
- `appraisal.line.score_employee` / `score_manager` (Integer 1-5) — no DB constraint enforcing 1-5; only the help text says so.
- `appraisal.cycle.department_ids` (M2M `hr.department`) — Empty = all departments.
- `appraisal.cycle.appraisal_count` / `completed_count` (Integer, computed, not stored) — KPI badges on cycle.
- `appraisal.appraisal.submitted_at_employee` / `submitted_at_manager` / `closed_at` (Datetime, readonly) — audit timestamps.

### custom_hr_leave_id — Custom HR Leave Indonesia

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_hr_leave_id` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `hr`, `hr_holidays`, `custom_approval_engine`, `mail` |
| Models / routes / tests | 4 / 0 / 2 |
| Tags | indonesian-hr, approval-workflow, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

Indonesian localization for `hr.leave` / CE `hr_holidays`. Adds the regulatory leave categories (cuti tahunan, cuti melahirkan 6 months per UU Cipta Kerja No. 6/2023, cuti haid, cuti besar, cuti alasan penting, cuti di luar tanggungan), an Indonesian public-holiday master seeded 2024-2026, holiday-overlap warnings on leave requests, a carry-over policy with annual cron stub, auto pro-rated cuti tahunan allocation on employee hire, and a SQL view aggregating leave balances per employee × type × year. Approval flows through `custom_approval_engine` via the `approval.mixin`.

**How it works**

- HR ensures `hr.leave.type` records carry an `x_id_leave_category` (e.g. `cuti_tahunan`, `cuti_melahirkan`, `cuti_haid`). Seeded by `data/id_leave_types.xml`.
- Public holidays are seeded from `data/id_public_holiday_2024.xml` / `_2025.xml` / `_2026.xml` (noupdate=1) into `id.public.holiday` (date, type_code ∈ national/regional/religious).
- Cron `cron_import_public_holidays` (in `id.public.holiday`) runs to verify current + next year are seeded; only logs warnings when missing (no upstream API fetch implemented).
- New `hr.employee` with `x_auto_leave_allocation=True` (default) triggers `_x_create_initial_annual_allocations` in `create`: for each `hr.leave.type` of category `cuti_tahunan`, pro-rate 12 days from max(hire_date, year-start) to year-end and create an `hr.leave.allocation` (regular type). Already-existing allocation in the year is skipped. Failures are logged but do not block employee creation.
- Employee files an `hr.leave` (Time Off request). The `_compute_x_overlapping_holidays` field finds `id.public.holiday` rows within `[date_from, date_to]` and produces `x_overlapping_holidays_count` + `x_overlapping_holidays_warning` (e.g. "2 public holiday(s) overlap..."). These are computed, non-stored — purely advisory; the module does **not** subtract them from `number_of_days`.
- Approval workflow is delegated to `custom_approval_engine` (via `approval.mixin` injected on `hr.leave`). `action_confirm` (employee submit) is gated by `_approval_request_or_proceed()`: when a leave matrix matches, clicking Confirm auto-submits the approval (Waiting Approval) and does NOT advance to the native To-Approve state until the final tier approves (`_approval_on_granted` re-runs `action_confirm`). With no matrix configured the engine is a no-op and Odoo's native manager approval stands alone. The standalone "Request Approval" button was removed from the leave form.
- Annual carry-over cron `custom.leave.carryover.policy.cron_apply_carryover` runs on Jan 1 (per `data/id_public_holiday_cron.xml`): for each active policy, find previous-year validated allocations, compute `remaining = number_of_days - leaves_taken`, intended carry = `min(remaining, max_carryover_days)`. **Currently a stub — logs intent only, no rewrites performed.**
- `custom.leave.balance.report` is a read-only Postgres view (`_auto = False`) joining `hr_leave_allocation` (state=validate) with `hr_leave` (state=validate) on (employee, leave_type, year-of-date_from) to produce per-row `allocated`, `used`, `remaining`.

**Key models**

- `hr.leave.type` (inherited) — Adds `x_id_leave_category` (Selection of 6 Indonesian regulatory categories).
- `hr.leave` (inherited) — Mixes in `approval.mixin`; adds holiday-overlap compute fields (`x_overlapping_holidays*`); overrides `action_confirm` to auto-submit approval + defines `_approval_on_granted` (re-runs `action_confirm` after grant).
- `hr.employee` (inherited) — Adds `x_auto_leave_allocation` flag and the pro-rated allocation hook.
- `id.public.holiday` — Indonesian public holiday master; `date` indexed, `(date, name)` unique.
- `custom.leave.carryover.policy` — Per leave-type policy (max days, expiry months); unique on `leave_type_id`.
- `custom.leave.balance.report` — `_auto=False` SQL view; per (employee, leave_type, year) → (allocated, used, remaining).

**Important fields**

- `hr.leave.type.x_id_leave_category` (Selection: cuti_tahunan/cuti_melahirkan/cuti_haid/cuti_besar/cuti_alasan_penting/cuti_di_luar_tanggungan) — drives policy lookups; **regulator-aligned values**.
- `hr.leave.x_id_leave_category` (Selection, related, stored) — denormalised for filtering.
- `hr.leave.x_overlapping_holidays` (M2M `id.public.holiday`, computed, **not stored**) — advisory.
- `hr.leave.x_overlapping_holidays_count` / `_warning` (Integer/Char, computed, not stored) — advisory.
- `hr.employee.x_auto_leave_allocation` (Boolean, default True) — toggle for the hire-time hook.
- `id.public.holiday.type_code` (Selection: national/regional/religious, default national).
- `id.public.holiday.year` (Integer, computed from `date`, stored, indexed).
- `custom.leave.carryover.policy.max_carryover_days` (Integer, default 5).
- `custom.leave.carryover.policy.expiry_months_after_year_end` (Integer, default 3 = end of March).
- `custom.leave.balance.report.allocated/used/remaining` (Float, readonly) — SQL-view columns; `remaining = allocated - used` per (employee, leave_type, year) bucket where year = `EXTRACT(YEAR FROM COALESCE(date_from, create_date))`.

### custom_hr_payroll_id — Custom HR Payroll (Indonesia)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_hr_payroll_id` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_pdp_core`, `custom_coretax`, `hr`, `mail` |
| Models / routes / tests | 6 / 0 / 4 |
| Tags | indonesian-payroll, payroll, indonesian-tax, withholding, coretax, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Self-contained Indonesian payroll engine — does **not** depend on Odoo EE `hr_payroll`. Implements PPh 21 monthly withholding under the PP 58/2023 TER regime (effective Jan 2024), legacy annualised calculation, annual reconciliation under UU HPP, BPJS Kesehatan + Ketenagakerjaan (JHT/JKK/JKM/JP) contributions, PTKP per PMK 101/2016, THR runs, and SPT 1721 A1 annual reporting (PDF + Coretax XML).

It is the canonical payroll module: any other HR module needing payroll integration (attendance overtime, timesheet OT, lunch deductions) feeds `hr.work.entry` records or extends `hr.payslip` here. On approve, the payslip materialises a draft `custom.coretax.bukti.potong` (Bupot PPh 21) for Coretax submission.

**How it works**

- Operator pre-fills `hr.employee` Indonesian fields: `x_custom_nik` (16 digits), `x_custom_npwp` (15 or 16 digits), `x_custom_ptkp_status` (TK/0…K/I/3), `x_custom_employment_type` (`pegawai_tetap` / `pegawai_tidak_tetap` / `bukan_pegawai`), `x_custom_bpjs_kesehatan_no`, `x_custom_bpjs_tk_no`. `x_custom_ter_category` is auto-derived from PTKP via `PTKP_TO_TER_CATEGORY`.
- HR officer opens `hr.payslip.batch.wizard`, picks `period_year` + `period_month` (and optional `is_thr`), runs `action_run()` — for each in-scope employee (active in current company, or explicit list) the wizard creates a `hr.payslip` (state `draft`) and calls `slip.action_compute()`.
- `_do_compute(config)` computes BPJS + PPh21 and writes lines into `hr.payslip.line`, transitioning state `draft`→`computed`. PPh 21 branches:
- **THR run** (`is_thr=True`): treats THR as monthly gross, taxable_year = max(0, gross − PTKP), then full progressive UU HPP. Method tag = `annual_recon`.
- **TER** (when `calc_method='ter'` AND `employment_type='pegawai_tetap'` AND month ≠ 12): looks up `hr.payroll.ter.bracket.get_rate(ter_cat, gross_total_month)` (returns fraction), `pph_month = gross_total_month * rate`. Method = `ter`.
- **Annualised fallback** (December always, or non-TER configs): annual_gross = monthly × 12; biaya jabatan = min(5% × annual_gross, 6,000,000); net_year = annual_gross − biaya_jabatan − jht_emp×12 − jp_emp×12 − PTKP; PPh year via `_compute_pph21`; pph_month = pph_year / 12. Method = `annualised` or `annual_recon` for December.
- `action_approve()` moves `computed`→`approved`, calls `_materialise_bupot_pph21()` which creates one `custom.coretax.bukti.potong` per slip (idempotent on `bupot_id`) with `jenis_pph='pph_21'`, `dpp=gross+tj+tl`, `pph_terpotong=pph21`, `tarif=ter_rate_used`, state `draft`. Failure is logged but does not block approval.
- `action_pay()` moves `approved`→`paid`. `action_draft()` reverts to `draft`. `write()` blocks edits to `gross_salary`/`tunjangan_*` once `approved` or `paid`.
- Every state-change writes a row into `pdp.audit_log` via raw SQL (classification `financial`) including actor, tenant_db, slip name, state, THP, PPh 21.
- Year-end: HR officer opens `hr.payroll.spt.a1.wizard`, picks `fiscal_year` (default = current year - 1), optionally selects employees, picks `output_format` (`pdf`/`xml`/`both`). `action_run()` aggregates all `approved`/`paid` slips of the year, recomputes annual progressive PPh 21, compares to sum of monthly deductions to surface `delta` (kurang/lebih bayar), and emits the PT.A1 PDF and/or the `SPT_1721_A1_<year>.xml` Coretax batch as an `ir.attachment`.
- A `pre_init_hook` runs before install (purpose: seed/migration; not detailed here).

**Key models**

- `hr.payslip` — One row per employee × period × THR flag. Holds gross, BPJS amounts, PPh 21, THP, method used, Bupot link, state. `_inherit = ['mail.thread', 'mail.activity.mixin']`. NOT inheriting CE `hr.payroll`'s payslip — this is a fresh `_name = "hr.payslip"`.
- `hr.payslip.line` — Per-payslip breakdown row (sequence, code, label, type ∈ {income, deduction, info}, amount).
- `hr.payroll.ter.bracket` — TER table row (category A/B/C × lower_bound × upper_bound × rate%). `upper_bound=0` means open-ended. Seeded via `data/hr_payroll_ter_data.xml`.
- `hr.payroll.config` — Singleton-style configuration (default record auto-created by `get_default()`). Holds calc_method, PTKP values, biaya jabatan, all BPJS percentages + ceilings.
- `hr.employee` (inherited) — Adds 8 Indonesian payroll fields prefixed `x_custom_*`.
- `hr.payslip.batch.wizard` (TransientModel) — Bulk payslip generator with `skip_if_exists` + `auto_approve`.
- `hr.payroll.spt.a1.wizard` (TransientModel) — Annual SPT 1721 A1 generator (PDF + XML batch).

**Important fields**

- `hr.payslip.state` (Selection: draft/computed/approved/paid) — drives lifecycle; financial fields locked once approved.
- `hr.payslip.is_thr` (Boolean) — distinguishes THR runs (unique constraint on `(employee_id, period_year, period_month, is_thr)`); routes to a different PPh 21 branch.
- `hr.payslip.calc_method_used` (Selection: ter/annualised/annual_recon, readonly) — cached method tag for audit.
- `hr.payslip.ter_category_used` / `ter_rate_used` (Selection A/B/C, Float %) — TER applied at compute time, stored on the slip.
- `hr.payslip.pph21` (Monetary, readonly, tracked) — monthly PPh 21 to be withheld.
- `hr.payslip.bpjs_kesehatan_emp` / `bpjs_kesehatan_company` (Monetary, readonly) — Kesehatan contributions, computed off `min(gross, bpjs_kesehatan_ceiling=12,000,000)` × 1% (emp) / 4% (co).
- `hr.payslip.bpjs_jht_emp` / `bpjs_jht_company` (Monetary, readonly) — JHT 2% (emp) / 3.7% (co) of gross_total_month, **no ceiling**.
- `hr.payslip.bpjs_jp_emp` / `bpjs_jp_company` (Monetary, readonly) — JP 1% (emp) / 2% (co) of `min(gross, bpjs_jp_ceiling=10,042,300)`.
- `hr.payslip.bpjs_jkk` / `bpjs_jkm` (Monetary, readonly) — Company-only JKK (default 0.54%, range 0.24–1.74% per industry) and JKM (0.30%) on gross_total_month.
- `hr.payslip.take_home_pay` (Monetary, readonly, tracked) — `gross_total_month − (bpjs_kes_emp + bpjs_jht_emp + bpjs_jp_emp + pph_month)`. **JKK/JKM/Kesehatan-company/JHT-company/JP-company are NOT deducted from THP** (employer-borne).
- `hr.payslip.bupot_id` (M2o `custom.coretax.bukti.potong`, readonly, no copy) — materialised on approve; idempotent.
- `hr.employee.x_custom_ptkp_status` (Selection 12 values) — drives PTKP amount via `config.get_ptkp()` and TER category via `_compute_ter_category`.
- `hr.employee.x_custom_ter_category` (Selection A/B/C, stored compute) — read by payslip compute; A=TK/0/1+K/0, B=TK/2/3+K/1/2, C=K/3+K/I/*.
- `hr.payroll.config.calc_method` (Selection: ter/annualised) — TER is default since Jan 2024; December always reconciles via annual progressive regardless.
- `hr.payroll.config.ptkp_*` (12 Float fields) — PTKP per PMK 101/2016 (TK/0=54M up to K/I/3=126M).
- `hr.payroll.ter.bracket.upper_bound` (Float) — `0` is a sentinel for "open-ended highest bracket"; the comparison is `monthly_gross <= upper_bound`.

### custom_hr_referral — Custom HR Referral

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_hr_referral` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `hr`, `mail` |
| Models / routes / tests | 3 / 0 / 0 |
| Tags | recruitment, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

Employee-referral program: employees submit candidates against `referral.position` records; HR moves the candidate through `submitted → screening → interviewed → offered → hired` (or `rejected`/`withdrawn`); on `hired`, a `referral.reward` is automatically materialised at the position's `reward_amount` and goes through its own `pending → approved → paid` ledger.

**How it works**

- HR opens a `referral.position` (name, department_id, job_id, description, `reward_amount`, currency_id), state `open`.
- Employee creates `referral.candidate` (name, email, phone, CV attachment, `position_id`, `referrer_id=self`) — defaults state `submitted`.
- HR advances state with `action_advance(target_state)` or explicit `action_mark_hired()` / `action_reject()` / `action_withdraw()`.
- `action_mark_hired()` writes `state=hired`, stamps `hired_at`, calls `_materialise_reward()` which creates a `referral.reward` (idempotent on `reward_id`) at `position_id.reward_amount` with state `pending`. Audit row classification `sensitive_pii`.
- HR/Finance on `referral.reward`: `action_approve()` (→approved, stamps approved_at) → `action_pay()` (→paid, stamps paid_at). Audit classification `financial`.
- All transitions chatter-tracked and audited via `pdp.audited.mixin._pdp_audit_write`.

**Key models**

- `referral.position` — Open requisition with bonus amount; inherits `mail.thread`, `mail.activity.mixin`.
- `referral.candidate` — Submitted candidate; inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`.
- `referral.reward` — Bonus ledger tied to candidate + referrer; inherits `pdp.audited.mixin`.

**Important fields**

- `referral.candidate.state` (Selection: submitted/screening/interviewed/offered/hired/rejected/withdrawn).
- `referral.candidate.referrer_id` (M2o `hr.employee`, required, indexed) — who claims the reward.
- `referral.candidate.cv_attachment_id` (M2o `ir.attachment`, `ondelete=set null`) — uploaded CV.
- `referral.candidate.reward_id` (M2o `referral.reward`, readonly) — materialised on hire; idempotency anchor.
- `referral.candidate.hired_at` (Datetime, readonly) — stamped by `action_mark_hired`.
- `referral.position.reward_amount` (Monetary) — per-position bonus; `0` skips reward creation.
- `referral.position.state` (Selection: open/on_hold/closed) — informational only; no enforcement on candidate creation.
- `referral.reward.state` (Selection: pending/approved/paid).
- `referral.reward.amount` (Monetary, required) — frozen from position at hire time.

### custom_hr_sso_keycloak — Custom HR — SSO (Keycloak) + Employee Sync

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_hr_sso_keycloak` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `auth_oauth`, `hr` |
| Models / routes / tests | 1 / 0 / 2 |
| Tags | hr, sso, keycloak, oidc, multi-tenant |

> Knowledge file is generator output, not human-reviewed.

**Declared models**: `hr.sso.sync`

### custom_lunch — Custom Lunch (Indonesia) EE

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_lunch` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `lunch`, `custom_hr_payroll_id` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | lunch, payroll, halal, indonesian-hr |

> Knowledge file is generator output, not human-reviewed.

EE-equivalent Indonesia extensions on top of CE `lunch`: deep-link supplier integration with **GoFood / GrabFood / ShopeeFood** (computed `x_partner_app_url` from merchant ids), halal certification + spice level + calorie + day-of-week scheduling on products, daily auto-publish cron flipping `lunch.product.active` based on a `mon,tue,wed,...` CSV, monthly cron aggregating confirmed lunch orders into payroll deductions on the matching `hr.payslip`.

**How it works**

- HR sets up `lunch.supplier` with `x_id_vendor_type` (walking/delivery/gofood/grabfood/shopeefood/direct), per-vendor merchant id (`x_id_gofood_id` etc.), `x_id_halal_certified`, `x_id_min_order`. `_compute_partner_app_url` builds the public deep link from the matching template (e.g. `https://gofood.co.id/restaurant/{merchant_id}`).
- "Open" button on supplier form calls `action_open_vendor_app()` returning an `ir.actions.act_url` (`target='new'`). Raises if no merchant id configured.
- HR creates `lunch.product` rows with `x_id_halal`, `x_id_vegetarian`, `x_id_spice_level` (none/mild/medium/hot/very_hot), `x_id_calories`, and optional `x_available_days` CSV like `"mon,wed,fri"`. `@api.constrains` validates day tokens (first 3 chars must be in `mon/tue/wed/thu/fri/sat/sun`).
- Daily cron `lunch.product.cron_publish_daily_menu` (per `data/lunch_cron.xml`): for products with a non-empty `x_available_days`, set `active = today's weekday token IN allowed`. Uses `with_context(active_test=False)` so archived rows can be re-activated. Empty schedule = always-on (left untouched).
- Employees place `lunch.order` records (CE flow) with `x_payroll_deduction=True` (default).
- Monthly cron `lunch.order.cron_aggregate_lunch_to_payroll`: aggregates the previous calendar month's `confirmed`/`ordered` orders where `x_payroll_deduction=True` and `x_payslip_id=False`, sums `price` per `order.user_id.employee_id`. **Currently a stub** — only logs `[custom_lunch] Payroll aggregation ...` per employee; the manifest description claims it posts a "Lunch Deduction" line on the draft payslip and links back via `x_payslip_id`, but the implementation has a TODO and performs no writes.

**Key models**

- `lunch.supplier` (inherited) — Vendor type, merchant ids per board, halal flag, computed deep-link URL.
- `lunch.product` (inherited) — Halal/vegetarian flags, spice level, calories, day-of-week CSV.
- `lunch.order` (inherited) — Payroll deduction toggle + payslip link.

**Important fields**

- `lunch.supplier.x_id_vendor_type` (Selection: walking/delivery/gofood/grabfood/shopeefood/direct, default direct).
- `lunch.supplier.x_id_halal_certified` (Boolean).
- `lunch.supplier.x_id_min_order` (Monetary, currency=`x_id_currency_id`).
- `lunch.supplier.x_id_gofood_id` / `x_id_grabfood_id` / `x_id_shopeefood_id` (Char) — merchant ids.
- `lunch.supplier.x_partner_app_url` (Char, computed, **stored**) — deep link; URL-quoted merchant id; empty if vendor type not in templates or no merchant id.
- `lunch.product.x_id_halal` / `x_id_vegetarian` (Boolean).
- `lunch.product.x_id_spice_level` (Selection: none/mild/medium/hot/very_hot, default none).
- `lunch.product.x_id_calories` (Integer kcal).
- `lunch.product.x_available_days` (Char) — CSV `"mon,tue,..."`; empty means always-on.
- `lunch.order.x_payroll_deduction` (Boolean, default True).
- `lunch.order.x_payslip_id` (M2o `hr.payslip`, readonly) — currently never written by the stub cron.

### custom_planning — Custom Planning

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_planning` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `hr`, `mail` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | planning, shift-scheduling, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Lightweight resource-planning / shift-scheduling module. Define `planning.role` records, assign `hr.employee` to roles, and create `planning.slot` shifts (start/end, optional employee) with overlap protection per employee. Slots progress through `open → assigned → published → cancelled`. State changes are audited via `pdp.audited.mixin`.

**How it works**

- HR creates `planning.role` rows (name, color, `employee_ids` M2M of eligible employees).
- Manager creates `planning.slot` (role_id, employee_id optional, start_dt, end_dt, state `open`).
- `_compute_name` derives `"<role>: <employee or 'Open'> @ <start_dt>"`.
- `_compute_duration` derives `duration_hours = (end_dt - start_dt) / 3600`.
- `@api.constrains` `_check_overlap` enforces:
- `start_dt < end_dt` else `ValidationError("End must be after start.")`.
- If `employee_id` set, search any other slot for the same employee in state `assigned` or `published` overlapping `[start_dt, end_dt)`; raise if any.
- Transitions:
- `action_assign(employee_id)` — writes `employee_id` + state `assigned`; audit `planning_assign` (payload: `{employee_id}`).
- `action_publish()` — requires `employee_id`; → `published`; audit `planning_publish`.
- `action_cancel()` — → `cancelled`; audit `planning_cancel`.

**Key models**

- `planning.role` — Role definition with eligible employee pool.
- `planning.slot` — Shift assignment; inherits `mail.thread`, `pdp.audited.mixin`.

**Important fields**

- `planning.slot.state` (Selection: open/assigned/published/cancelled, default open, tracked).
- `planning.slot.role_id` (M2o `planning.role`, required, indexed).
- `planning.slot.employee_id` (M2o `hr.employee`, indexed, tracked) — empty = open shift; anyone in the role can claim.
- `planning.slot.start_dt` / `end_dt` (Datetime, required, tracked).
- `planning.slot.duration_hours` (Float, computed, stored).
- `planning.slot.name` (Char, computed, stored) — `"<role>: <who> @ <start_dt>"`.
- `planning.role.employee_ids` (M2M `hr.employee` via `planning_role_employee_rel`).

### custom_recruitment_id — Custom Recruitment ID

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_recruitment_id` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_pdp_retention`, `hr_recruitment`, `calendar`, `mail` |
| Models / routes / tests | 1 / 1 / 2 |
| Tags | recruitment, webhook-intake, pdp, audit-trail, indonesian-hr |

> Knowledge file is generator output, not human-reviewed.

Indonesia-localized + EE-equivalent extensions to CE `hr_recruitment`: job-board source tracking (Jobstreet/Glints/LinkedIn/Kalibrr/Direct), HMAC-SHA256-verified webhook intake for inbound applications, SHA1-based candidate dedup with duplicate pointer, one-click pre-filled `calendar.event` for interviews, Indonesia offer letter PDF with PPh 21 estimate, PDP-aware applicant retention cron that anonymises expired records (`REDACTED-<id>`) while preserving stage history, and stub auto-publish actions for Jobstreet/Glints.

**How it works**

- HR creates `hr.job` records; toggles `x_publish_jobstreet`/`x_publish_glints`; `action_post_to_jobstreet()` / `action_post_to_glints()` generate a mock external post id (`JS-MOCK-<hex>` / `GL-MOCK-<hex>`) and store it (stub — no real API call).
- Inbound application paths:
- **Webhook**: external partner POSTs JSON to `/custom_recruitment_id/webhook/<source>` with `X-Signature` header. Controller verifies HMAC-SHA256 against secret `custom_recruitment_id.webhook_secret_<source>` (ir.config_parameter; fail-closed on missing). Body is parsed and forwarded to `custom.recruitment.webhook.log.ingest_payload(source, data)`.
- `_normalize_payload` maps vendor-specific JSON shapes (Jobstreet `candidate.full_name/email/phone/ref_id/job_ref`; Glints `applicant.name/email/mobile/id/job_id`; LinkedIn `applicant.firstName/lastName/emailAddress/phoneNumber/applicationId/jobPostingId`; generic) into a flat dict.
- A `custom.recruitment.webhook.log` row is persisted with the raw payload; on success an `hr.applicant` is created with `x_job_board_source` + `x_external_id`. Best-effort `job_id` match by `hr.job.name = job_ref` or `int(job_ref)`. Failures leave `processed=False` and `error_message` set.
- **Manual**: HR creates `hr.applicant` directly; `x_job_board_source='manual'` by default.
- On `create`/`write` of an `hr.applicant` with email or phone, `_compute_x_dedup_hash` recomputes `x_dedup_hash = SHA1(lower(email) + '|' + normalize_phone(phone))`. `_flag_if_duplicate` searches earlier applicants with the same hash and sets `x_duplicate_of` + `x_is_duplicate=True`. Phone normalisation: strips non-digit, drops leading `+`, replaces leading `0` with `62`.
- Offer letter: HR fills `x_offer_salary`, `x_offer_probation_months` (default 3), `x_offer_start_date`; `_compute_x_offer_pph21_estimated` derives a rough PPh 21 estimate via a hardcoded TER-style table (see Gotchas). `action_print_offer_letter()` renders `custom_recruitment_id.action_report_offer_letter`.
- Interview scheduling: `action_schedule_interview()` opens a `calendar.event` create form pre-filled with applicant partner + interviewer partners from `hr.job.interviewer_ids` and (if available) `hr.recruitment.source.user_id`.
- PDP retention cron `cron_purge_expired_applicants` runs (per `data/recruitment_id_cron.xml`): for `hr.applicant` with `x_pdp_retention_until < today` and `partner_name NOT LIKE 'REDACTED-%'`, anonymises `partner_name`/`email_from`/`partner_phone`/`x_external_id`/`x_dedup_hash`, posts chatter note, and inserts a `pdp.audit_log` row (classification=`pii`, reason=`PDP retention horizon reached — auto-anonymize`). Returns count.

**Key models**

- `hr.applicant` (inherited) — Adds 11 fields: source, external_id, retention, consent, dedup hash, duplicate pointer/flag, offer fields.
- `hr.job` (inherited) — Adds publish toggles + external post ids per board.
- `custom.recruitment.webhook.log` — Inbound payload log; per-source state, applicant link, error message.

**Important fields**

- `hr.applicant.x_job_board_source` (Selection: manual/jobstreet/glints/linkedin/kalibrr/direct, default manual, tracked).
- `hr.applicant.x_external_id` (Char, tracked) — vendor-side applicant id.
- `hr.applicant.x_pdp_retention_until` (Date, tracked) — drives anonymise cron.
- `hr.applicant.x_pdp_consent_given` (Boolean, default False, tracked) — explicit PDP consent; cleared on anonymise.
- `hr.applicant.x_dedup_hash` (Char, computed, **stored**, indexed) — SHA1(email + '|' + e164-ish phone).
- `hr.applicant.x_duplicate_of` (M2o `hr.applicant`, indexed, `ondelete=set null`).
- `hr.applicant.x_is_duplicate` (Boolean, tracked).
- `hr.applicant.x_offer_salary` (Monetary, currency=`x_offer_currency_id`).
- `hr.applicant.x_offer_pph21_estimated` (Monetary, computed, **not stored**) — hardcoded TER-style approximation; NOT the canonical payroll calc.
- `hr.applicant.x_offer_probation_months` (Integer, default 3).
- `hr.applicant.x_offer_start_date` (Date).
- `hr.job.x_publish_jobstreet` / `x_publish_glints` (Boolean, tracked).
- `hr.job.x_external_post_id_jobstreet` / `x_external_post_id_glints` (Char, readonly).
- `custom.recruitment.webhook.log.source` (Selection of 6 sources, required, tracked).
- `custom.recruitment.webhook.log.processed` (Boolean, tracked).
- `custom.recruitment.webhook.log.applicant_id` (M2o `hr.applicant`, `ondelete=set null`).

**Endpoints**: `/custom_recruitment_id/webhook/<string:source>`

## Warehouse & Inventory (Gudang & Inventori)

### custom_barcode — Custom Barcode

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_barcode` |
| Version | 19.0.2.0.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_product_barcode`, `barcodes`, `barcodes_gs1_nomenclature`, `stock` |
| Models / routes / tests | 10 / 0 / 3 |
| Tags | barcode-scan, wms, hht, audit-trail |

> Knowledge file is generator output, not human-reviewed.

CE-compatible replacement for the EE-only `stock_barcode` app. Builds on the CE `barcodes` + `barcodes_gs1_nomenclature` modules to provide a mobile/kiosk-friendly scan workflow that **actually mutates `stock.move.line`** on a picking — including real GS1 AI parsing (GTIN, lot, expiry, weight), batch picking (one scan distributed across many pickings), cluster picking (one walk for many orders grouped by source location), barcode-format auto-generation, label templates (ZPL/ESC-POS/PDF), printer configuration, and a print spool.

**How it works**

- **Single picking flow**: operator opens a `custom.barcode.scan.session` linked to a `stock.picking`, calls `action_start_scanning`, scans products via `on_barcode_scanned(barcode)`. Each scan parses GS1, looks up product (by GTIN then raw barcode) + lot, creates a `custom.barcode.scan.line` with status `ok`/`not_found`/`duplicate`. `action_apply_to_picking` reconciles OK lines against `stock.move.line.qty_done` (creating lots and move.lines as needed), then posts a chatter summary on both session and picking.
- **Batch flow**: `custom.barcode.batch.session` aggregates scans across many pickings without pre-allocation (status `unallocated`). `auto_distribute_lines()` walks pickings in order, greedy-fills each picking's outstanding demand per product, splits scan lines when they span pickings, then `action_apply()` reuses the standard session apply per picking.
- **Cluster flow**: `custom.barcode.cluster.run` calls `build_plan()` which groups outstanding moves by `(location, product, picking)`, sorts by `location.complete_name → product → picking name` for a walk-order pick. Each scan increments the matching `custom.barcode.cluster.assignment.scanned_qty`; `action_apply()` materialises sessions per picking.
- **Auto-barcoding**: `custom.barcode.format` defines `code` (Code128/EAN-13/EAN-8/QR) + `prefix` + `suffix` + `sequence_id` + `applied_models`. `product.product.create` and `stock.lot.create` look up `_format_for_model` and auto-populate `barcode` / `name` (EAN check-digit computed in-place).
- **Labels + Printing**: `custom.label.template` renders `{{field}}` / `{{rel.field}}` substitutions to ZPL/ESC-POS/PDF bytes. `custom.printer.config` supports `zebra_network` / `zebra_usb` / `escpos_network` / `cups` transports — network printers go via raw socket 9100, CUPS is stubbed (no python-cups dependency). `custom.print.queue` spools jobs with state queued/printing/done/failed; cron `_cron_process_queue` drains 50/tick.
- **Reporting**: `stock.picking._barcode_summary_rows()` and `custom.barcode.scan.session.get_picking_summary_data()` feed a QWeb-PDF `picking_barcode_summary` report with expected vs scanned + deviation %.

**Key models**

- `custom.barcode.scan.session` — Single-picking scan session; inherits `barcodes.barcode_events_mixin` for HW event capture.
- `custom.barcode.scan.line` — One scan event; belongs to a session, batch, or cluster (constrained to exactly one owner).
- `custom.barcode.batch.session` — Scan-many-pickings session with greedy distributor.
- `custom.barcode.cluster.run` + `custom.barcode.cluster.assignment` — One operator, many orders, grouped by location.
- `custom.barcode.format` + `custom.barcode.auto.mixin` — Auto-barcoding on product/lot create.
- `custom.label.template` — Renderable ZPL/ESC-POS/PDF label.
- `custom.printer.config` — Physical/virtual printer with raw-socket or CUPS transport.
- `custom.print.queue` — Async print-job spool.
- `stock.picking` (inherited) — `_barcode_summary_sessions` + `_barcode_summary_rows` for the QWeb report.

**Important fields**

- `custom.barcode.scan.session.state` (draft/scanning/completed/cancelled).
- `custom.barcode.scan.line.status` (ok/not_found/duplicate/wrong_location/unallocated) — `_check_owner` constraint enforces exactly one of session/batch/cluster.
- `custom.barcode.scan.line.x_gs1_parsed` (Text, JSON) — parsed GS1 AI dict (gtin/lot/exp_date/prod_date/serial/weight/weight_unit/count).
- `custom.barcode.scan.line.quantity` (Float, default 1.0) — overridden by GS1 weight when present.
- `custom.barcode.batch.session.picking_ids` (M2m `stock.picking`) — pickings the batch can drain into; domain `state in ('confirmed','assigned')`.
- `custom.barcode.cluster.assignment.expected_qty` / `scanned_qty` / `remaining_qty` (computed) — per-stop progress.
- `custom.barcode.format.code` (Selection: Code128/EAN13/EAN8/QR) — auto-applies EAN check-digit via `_ensure_ean13` / `_ensure_ean8`.
- `custom.barcode.format.applied_models` (M2m `ir.model`, restricted to product.product/product.template/stock.lot/stock.location).
- `custom.label.template.output_mode` (zpl/escpos/pdf), `paper_format`, `template_source` (placeholder body).
- `custom.printer.config.printer_type` (zebra_network/zebra_usb/escpos_network/cups), `host`, `port` (default 9100), `cups_queue`, `last_error`.
- `custom.print.queue.state` (queued/printing/done/failed), `res_model` + `res_ids` (CSV) + `copies`.

### custom_hht_bridge — Custom HHT Bridge

|  |  |
| --- | --- |
| Path | `addons/core/custom_hht_bridge` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_bast`, `custom_barcode`, `custom_super_admin`, `stock`, `mail`, `web` |
| Models / routes / tests | 4 / 11 / 1 |
| Tags | hht, barcode-scan, wms, audit-trail, multi-tenant |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.1.0, module is now 19.0.0.2.0.

Brings physical handheld terminals (Zebra TC21/TC52/TC72, Honeywell CT40, generic Android with DataWedge, plus generic browser PWA) into the Odoo platform as first-class scan-aware clients. Provides a device enrollment registry with HMAC `api_key`/`api_secret` and CIDR allow-listing, an append-only scan audit log with GPS + payload, an offline sync queue with idempotent `client_id` de-duplication, an OWL PWA shell served at `/hht/`, a `@secure_endpoint('hht')`-protected REST API at `/api/hht/*`, and a DataWedge ingest endpoint for thin keyboard-wedge scanners.

**How it works**

- Admin enrolls a device: creates `hht.device` (name, `device_id` serial, model, `tenant_id`, `user_id` default operator, optional `allowed_cidrs`). `create()` auto-generates `api_key = secrets.token_hex(16)` and `api_secret = secrets.token_hex(32)`. `api_secret` is write-protected — `write()` raises `UserError` unless context `hht_allow_secret_write=True`; rotation goes through `action_regenerate_secret()` (gated on group `custom_hht_bridge.group_hht_admin`).
- Operator opens the PWA at `/hht/` on the device. PWA reads `api_key`/`api_secret` from local storage, signs every request to `/api/hht/*` with HMAC-SHA256 over `<timestamp>.<body_bytes>`, adds headers `X-Device-Key: <api_key>` + `X-Signature` + `X-Timestamp`.
- `@secure_endpoint('hht')` (from `custom_core`) validates timestamp drift (±300s), HMAC against the scope secret, nonce replay (Redis-backed when configured), and CIDR allowlist before dispatching.
- Each scan POSTs to `/api/hht/scan` (or DataWedge endpoint) with `barcode`, `action` (receipt/issue/transfer/count/handover/lookup), optional `location_id`/`qty`/`lot_id`/`picking_id`. Server writes `hht.scan.log` row (sha256-indexed device+time index `hht_scan_log_device_time_idx`), updates `hht.device.last_seen_at`/`last_action_at` via `_touch_seen()`.
- Offline scans accumulate in IndexedDB on the device; when connectivity returns, the PWA flushes them to `/api/hht/sync` as `hht.sync.queue` rows. The unique constraint `(device_id, client_id)` enforces idempotent dedup; the apply cron processes queued items into business records (transfers, counts, BAST documents).
- `hht.device.action_view_scan_logs()` / `action_view_sync_queue()` open per-device drilldowns. `_compute_scan_count_today` shows daily volume; computed `status` becomes `quarantined` when `scan_count_today > 10000` (heuristic anomaly).
- Daily cron `_cron_purge_old_queue(days=30)` deletes applied/deduped queue rows older than 30 days.

**Key models**

- `hht.device` — Enrolled physical/browser device. Inherits `mail.thread`, `mail.activity.mixin`. Holds HMAC credentials, tenant link, optional CIDR allowlist, telemetry.
- `hht.scan.log` — Append-only audit log; one row per scan/lookup. Indexed by `(device_id, scanned_at DESC)` via `init()` raw SQL.
- `hht.sync.queue` — FIFO journal of operations queued offline. `(device_id, client_id)` unique → idempotent. Lifecycle: queued → processing → applied/failed/deduped.

**Important fields**

- `hht.device.device_id` (Char, indexed, unique per tenant) — physical serial (e.g. `TC52-SN12345`) or browser fingerprint.
- `hht.device.model` (Selection zebra_tc21/tc52/tc72/honeywell_ct40/generic_browser/other) — hardware class.
- `hht.device.tenant_id` (M2o tenant.registry, set_null) — tenant ownership.
- `hht.device.api_key` (Char, readonly, copy=False, indexed) — `secrets.token_hex(16)`, looked up by `_find_by_api_key`.
- `hht.device.api_secret` (Char, readonly, copy=False) — `secrets.token_hex(32)`; HMAC shared secret. WRITE-PROTECTED.
- `hht.device.allowed_cidrs` (Char) — CSV of CIDRs/IPs; validated by `_check_allowed_cidrs` via `ipaddress`.
- `hht.device.enabled` (Boolean, tracking) — kill switch.
- `hht.device.last_seen_at` / `last_action_at` / `last_action_summary` (readonly) — telemetry.
- `hht.device.scan_count_today` (Integer, computed) — drives the `quarantined` heuristic.
- `hht.device.status` (Selection active/disabled/quarantined, computed) — derived from `enabled` and `scan_count_today > 10000`.
- `hht.scan.log.barcode` / `action` / `location_id` / `qty` / `lot_id` / `picking_id` — scan facts.
- `hht.scan.log.result` (Selection ok/error/pending_sync, indexed) — outcome.
- `hht.scan.log.payload` (Json) — raw request payload for forensics.
- `hht.scan.log.client_ip` (Char) — extracted from `X-Forwarded-For` / `remote_addr`.
- `hht.sync.queue.client_id` (Char, indexed) — client-generated stable id; uniqueness `(device_id, client_id)` enforces idempotency.
- `hht.sync.queue.state` (Selection queued/processing/applied/failed/deduped, indexed) — processing lifecycle.
- `hht.sync.queue.batch_id` (Char, indexed) — groups related items.

**Endpoints**: `/api/hht/bast/sign`, `/api/hht/datawedge`, `/api/hht/manifest`, `/api/hht/me`, `/api/hht/scan`, `/api/hht/sync`, `/hht`, `/hht/`, `/hht/boot-report`, `/hht/manifest.webmanifest`, `/hht/sw.js`

### custom_intercompany_procurement — Custom Intercompany Procurement

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_intercompany_procurement` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `custom_rental`, `purchase`, `sale_management`, `stock` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | intercompany, procurement, audit-trail |

> Knowledge file is generator output, not human-reviewed.

This module automates the mirroring of purchase orders and stock pickings between sister companies within the Erajaya group. When a purchase order is confirmed in one company, a corresponding draft sales order is auto-created in the receiving sister company; when an outgoing picking is validated, a matching incoming picking is created in the receiving company. It also spawns internal asset-loan rental orders for drone-style loan flows. The base `account.intercompany.rule` (from `custom_accounting_full`) previously mirrored only the GL invoice; this module adds the procurement/logistics side.

**How it works**

- **Purchase Order Confirmation:**
- A purchase order (PO) is confirmed in the issuing company (`purchase.order.button_confirm`).
- The module resolves the receiving company from the PO partner's `commercial_partner_id` and searches for an active intercompany rule with `mirror_purchase_order = True`.
- If found, it creates a draft sales order (SO) in the receiving company (`with_company`, `sudo`).
- **Stock Picking Validation:**
- An outgoing stock picking is validated in the issuing company (hook on `stock.picking._action_done`).
- Only outgoing pickings with a partner are considered; the receiving company is resolved from the partner, and an active rule with `mirror_picking = True` is searched.
- If found, it creates a matching incoming picking in the receiving company.
- **Asset Loan Integration:**
- When the mirrored SO in the receiving company is confirmed and carries the loan service line, the module auto-creates a draft internal asset-loan rental order (`rental.order`).
- The physical asset moves via an Internal->Internal loan transfer (it never leaves the selling company's location tree and posts no COGS/valuation journal); only the service line is invoiced.

**Key models**

- **account.intercompany.rule** (`_inherit`) — Extends the base rule from `custom_accounting_full` with procurement-side toggles and asset-loan spawn configuration.
- **purchase.order** (`_inherit = ["purchase.order", "pdp.audited.mixin"]`) — On `button_confirm`, runs `_custom_run_ic_po_mirror` → `_custom_create_ic_mirror_so` to spawn the mirror SO in the receiving company. Audit classification `"financial"`.
- **stock.picking** (`_inherit = ["stock.picking", "pdp.audited.mixin"]`) — On `_action_done`, runs `_custom_run_ic_picking_mirror` → `_custom_create_ic_mirror_picking` to spawn the incoming mirror picking. Audit classification `"internal"`.
- **sale.order** (`_inherit`) — Holds mirror back-references and asset-loan logic; on `action_confirm` spawns the event-cycle asset loan.
- **rental.order** (`_inherit`) — Links back to the source intercompany SO (`sale_order_id`) and tags the loan cycle (`loan_type`).

**Important fields**

- **mirror_purchase_order** (Boolean, default `False`): enable PO → SO mirroring.
- **mirror_picking** (Boolean, default `False`): enable outgoing → incoming picking mirroring.
- **target_warehouse_id** (Many2one `stock.warehouse`): receiving warehouse for mirrored pickings/SO; if empty, the first warehouse of the receiving company is used.
- **target_sale_journal_id** (Many2one `account.journal`): **(Reserved) Future** — declared but never read by any code.
- **spawn_rental_loan** (Boolean, default `False`): when the mirrored SO is confirmed with the loan service line, auto-create an internal asset-loan.
- **loan_service_product_id** (Many2one `product.product`, service): its presence on the SO marks it as an asset loan; its qty becomes the primary loan qty.
- **loan_asset_product_id** (Many2one `product.product`): the physical asset moved on loan (e.g. the drone).
- **loan_on_loan_location_id** (Many2one `stock.location`, internal): the location the asset sits in while on loan.
- **x_custom_ic_mirror_so_id** (Many2one `sale.order`): the SO auto-generated in the sister company.
- **x_custom_ic_source_so_id** (Many2one `sale.order`): set when this PO was itself created by a mirror flow (back-reference).
- **x_custom_ic_rule_id** (Many2one `account.intercompany.rule`).
- **x_custom_ic_source_po_id** (Many2one `purchase.order`): the source PO that mirrored into this SO.
- **x_custom_ic_rule_id** (Many2one `account.intercompany.rule`).
- **loan_order_ids** (One2many `rental.order`, inverse `sale_order_id`).
- **loan_order_count** (Integer, computed).
- **is_asset_loan** (Boolean, computed): True when the SO carries the rule's loan service product.
- **x_custom_ic_mirror_picking_id** (Many2one `stock.picking`): the incoming picking auto-generated in the sister company (idempotency guard).
- **x_custom_ic_source_picking_id** (Many2one `stock.picking`): back-reference when this picking is itself a mirror.
- **x_custom_ic_rule_id** (Many2one `account.intercompany.rule`).
- **sale_order_id** (Many2one `sale.order`): the intercompany SO this loan was spawned from.
- **loan_type** (Selection `preflight`/`event`): pre-flight and event handovers share one SO but are separate physical pickup/return cycles.

### custom_po_return — Custom PO Return

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_po_return` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `purchase_stock`, `stock_account`, `account`, `mail` |
| Models / routes / tests | 3 / 0 / 1 |
| Tags | purchase, inventory, vendor-return |

> Knowledge file is generator output, not human-reviewed.

Quantity-driven vendor return (RTV): the user states a total qty per product
to return to a supplier; the system allocates it FIFO across previous
POs/GRs at original PO prices, creates return pickings and draft vendor
credit notes, and shows which GR and vendor bill back every slice.

**Declared models**: `custom.po.return`, `custom.po.return.allocation`, `custom.po.return.line`

### custom_product_barcode — Custom Product Barcode (Multi-barcode)

|  |  |
| --- | --- |
| Path | `addons/core/custom_product_barcode` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Rendah |
| Depends | `product` |
| Models / routes / tests | 1 / 0 / 0 |
| Tags | retail, barcode |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Alternate barcodes per product variant — one variant, one inventory, all scannable Lets a product variant carry MORE THAN ONE barcode. The native ``product.product.barcode`` stays the primary (e.g. the latest GTIN); additional GTINs are stored as ``product.barcode`` rows and matched by ``product.product._resolve_barcode`` (primary first, then alternates).

**Key models**

- product.barcode

### custom_receipt_async — Custom Receipt Async Validate

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_receipt_async` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Rendah |
| Depends | `stock`, `queue_job`, `mail` |
| Models / routes / tests | 0 / 0 / 0 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Background validate untuk stock.picking besar via queue_job Menambah tombol 'Validate (Background)' di stock.picking yang memindahkan eksekusi button_validate ke queue_job. Cocok untuk receipt dengan ribuan move_line yang biasanya gagal di browser dengan ERR_EMPTY_RESPONSE karena proxy/port-forward timeout (vpnkit Docker Desktop, dll).

### custom_stock_delivery_report_fix — Custom Stock Delivery Report Fix

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_stock_delivery_report_fix` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Nonaktif / Sedang |
| Depends | `stock` |
| Models / routes / tests | 0 / 0 / 0 |

> Knowledge file is generator output, not human-reviewed.

Single-purpose compatibility patch for Odoo 19's stock delivery-slip report. Upstream's `stock.stock_report_delivery_has_serial_move_line` QWeb template reads `move_line.packaging_uom_id`, but `packaging_uom_id` is defined on `stock.move` (see `stock/models/stock_move.py`), **not** on `stock.move.line`. Rendering a delivery slip for a picking with serial/lot move lines therefore raises `AttributeError: 'stock.move.line' object has no attribute 'packaging_uom_id'`. This module replaces the broken template block to read the field from `move_line.move_id` and guards against an unset packaging.

**How it works**

- A warehouse user prints / previews a delivery slip (`stock.report_deliveryslip`) for a picking that contains serial- or lot-tracked move lines.
- Without this module the report crashes on the packaging line. With it installed, the inherited template renders the packaging quantity + UoM from `move_line.move_id.packaging_uom_id`, only when that field is set and differs from `product_uom_id`, and only for users in `uom.group_uom`.

### custom_wms_cycle_count — Custom WMS Cycle Count

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_cycle_count` |
| Version | 19.0.0.2.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_barcode`, `stock`, `product`, `mail` |
| Models / routes / tests | 5 / 0 / 1 |
| Tags | wms, barcode-scan, approval-workflow, audit-trail, hht |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.1.0, module is now 19.0.0.2.0.

Plan-driven perpetual-inventory / **cycle counting** with a session→line→adjustment workflow and a supervisor approval gate for variance posting. Replaces ad-hoc CE inventory adjustments with cadence-aware sampling (ABC velocity, random, by zone, by value, last-counted) plus a daily cron that materialises new counting sessions from due plans.

**How it works**

- A warehouse manager creates a `custom.cycle.count.plan` per `stock.warehouse` with a `frequency` (daily/weekly/monthly/quarterly/adhoc), `method` (sampling strategy), optional `scope_zone_ids`, and a `target_count_per_period`.
- The daily cron `CycleCountPlan._cron_generate_sessions()` selects active plans where `next_run_date <= today` (excluding adhoc), invokes the `custom.cycle.count.start.wizard` to materialise a `custom.cycle.count.session`, and advances `next_run_date` per frequency delta (30/90 day flat approximations).
- The session starts in `draft` with auto-assigned `name` from `ir.sequence(custom.cycle.count.session)`; `action_start()` flips to `in_progress` and stamps `started_at`.
- For each `custom.cycle.count.line`, a counter calls `action_count(qty)` recording `counted_qty`, `counter_user_id`, `counted_at`; `variance_qty` / `variance_pct` are computed.
- Supervisor (group `custom_wms_cycle_count.group_cycle_count_supervisor`) calls `action_approve()` or `action_reject()` on each line. Approval with non-zero variance auto-creates a `custom.cycle.count.adjustment`.
- `action_post()` on the adjustment materialises a `stock.move` to/from `stock.location_inventory` (or any `usage=inventory` location fallback) to reconcile the variance.
- `action_review()` moves the session to `reviewing`; `action_close()` validates all lines are `approved` or `skipped` then closes (stamping `completed_at`).
- `is_new_item=True` lines + `new_item_product_temp_name` capture barcoded items that don't match any product (operator-recognition workflow).

**Key models**

- `custom.cycle.count.plan` — Cadence + scope definition; one per recurring count programme.
- `custom.cycle.count.session` — Materialised run instance; one per (plan, period); tracks `line_count`, `variance_count`, `variance_value`.
- `custom.cycle.count.line` — One (location, product[, lot]) tuple to count; status pending/counted/skipped/recount_required/approved/rejected.
- `custom.cycle.count.adjustment` — Variance-posting record; creates a `stock.move` against the inventory loss location.

**Important fields**

- `custom.cycle.count.plan.frequency` (Selection daily/weekly/monthly/quarterly/adhoc) — drives cron `_advance_next_run` (timedelta-based, month=30, quarter=90 days).
- `custom.cycle.count.plan.method` (Selection abc_velocity/random/by_zone/by_value/last_counted) — semantic tag for the start wizard's sampling logic.
- `custom.cycle.count.plan.target_count_per_period` (Integer, default 50) — used by `coverage_pct` compute.
- `custom.cycle.count.plan.next_run_date` (Date) — cron pivot.
- `custom.cycle.count.session.state` (draft/in_progress/reviewing/closed/canceled) — workflow gate; close requires all lines approved/skipped.
- `custom.cycle.count.session.variance_value` (Float, computed/stored) — `Σ |variance_qty| × product.standard_price`.
- `custom.cycle.count.line.variance_qty` / `variance_pct` (Float, computed/stored) — guarded against expected_qty=0.
- `custom.cycle.count.line.status` (Selection 6-state) — approval gate keyed on `approved`/`skipped`.
- `custom.cycle.count.line.is_new_item` + `new_item_product_temp_name` — captures unknown barcodes.
- `custom.cycle.count.adjustment.posted` (Boolean) — idempotency guard for `action_post`.

### custom_wms_docs — Custom WMS Documents & Labels

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_docs` |
| Version | 19.0.0.2.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_barcode`, `stock`, `product` |
| Models / routes / tests | 4 / 0 / 1 |
| Tags | wms, barcode-scan, labels, reporting, hht |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.1.0, module is now 19.0.0.2.0.

Warehouse **documents & labels**: the paper (and sticker) layer of the WMS stack. Ships four QWeb-PDF reports — Picking List, Packing List, Barcode List and Price Tag / Product Label — plus the Python helpers that compute their content, so the templates stay thin and the logic stays testable. All data shaping (walk-path ordering, package grouping, gross-weight arithmetic, label expansion) lives in Python; QWeb only iterates.

**How it works**

- **Picking List** — printed from a transfer (`stock.picking`, bound to outgoing/internal via the report's `domain`). `_wms_pick_rows()` calls `_wms_pick_lines()` which sorts `move_line_ids` along an optimised walk path (source `location_id.complete_name`, then product `default_code`). Each row carries a walk sequence number, the source location plus its QR image, product code/name, lot/serial, expiry (when `product_expiry` is installed), demanded qty + UoM and an empty tick box. Footer prints line count, total qty and a picker signature line.
- **Packing List** — `_wms_packing_blocks()` groups `move_line_ids` by `result_package_id` (Odoo 19 model `stock.package`) and appends a final "Loose / unpacked" block for lines with no destination package. Every block prints the package name as **both** Code128 and QR, the `stock.package.type` name, its PxLxT dimensions and the computed gross weight (Σ product weight × qty + `package_type.base_weight`), then the contents table. The header prints the ship-to address, the picking partner and the carrier when `delivery` is installed.
- **Barcode List** — `_wms_barcode_rows()` collects every distinct package barcode and every distinct product barcode of the shipment (falling back to `default_code` when a product has no barcode), de-duplicates them, and renders each as QR *and* Code128 side by side with the human-readable value underneath. `_wms_barcode_row_pairs()` chunks the rows into a two-column grid.
- **Price Tag / Product Label** — the operator opens `custom.wms.label.wizard` (menu Inventory → Warehouse Documents → Print Labels, or the contextual *Print Labels* action on `product.product` / `product.template` / `stock.picking`). `qty_source = manual` repeats each selected product `qty_per_product` times; `qty_source = picking_qty` explodes one label per unit of the picking's move-line quantity (or move demand when the transfer is not reserved yet). The total is checked against `ir.config_parameter custom_wms_docs.max_labels` (default 500) — over the cap `action_print()` raises a `UserError` naming the cap instead of truncating. `action_print()` returns the report action with the expanded label list in `data`; `report.custom_wms_docs.report_wms_product_label` turns it into one sticker dict each.

**Key models**

- `stock.picking` (inherited) — hosts every document helper; no new stored fields are added.
- `custom.wms.label.wizard` (TransientModel) — label print job definition and expansion.
- `report.custom_wms_docs.report_wms_product_label` (AbstractModel) — rendering context for the label grid.
- Read-only consumers: `stock.move.line`, `stock.package`, `stock.package.type`, `product.product`.

**Important fields**

- `custom.wms.label.wizard.picking_id` (M2o `stock.picking`) — optional; required by the form when `qty_source == 'picking_qty'`.
- `custom.wms.label.wizard.product_ids` (M2m `product.product`) — the label subject; also acts as a filter when expanding from a picking.
- `custom.wms.label.wizard.qty_source` (Selection `manual` / `picking_qty`) — `picking_qty` = "one label per unit shipped".
- `custom.wms.label.wizard.qty_per_product` (Integer, default 1) — used in `manual` mode only; ≤ 0 is coerced to 1.
- `custom.wms.label.wizard.label_kind` (Selection `price_tag` / `product_label`) — price tag shows `list_price`; product label shows the UoM instead.
- `custom.wms.label.wizard.barcode_kind` (Selection `Code128` / `QR` / `datamatrix`, default `QR`) — symbology passed to `/report/barcode/<Type>/<value>`.
- System parameter `custom_wms_docs.max_labels` (default `500`, constant `MAX_LABELS_DEFAULT`) — hard cap per print job.

### custom_wms_hht — Custom WMS Handheld

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_hht` |
| Version | 19.0.0.4.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_hht_bridge`, `custom_barcode`, `custom_product_barcode`, `custom_wms_putaway`, `custom_wms_inbound_qc`, `custom_wms_cycle_count`, `custom_wms_to_engine`, `custom_wms_receiving_ext`, `stock` |
| Models / routes / tests | 0 / 22 / 1 |
| Tags | hht, wms, barcode-scan, goods-receipt, picking |

The **handheld warehouse application** that actually moves stock. It replaces
the demo shell in `custom_hht_bridge` — five flat tabs, empty stubs, and a scan
endpoint that only *logged* the scan — with a task-driven app wired into the
`custom_wms_*` modules.

It is deliberately a **separate module from `custom_hht_bridge`**: the bridge is
installed on ARKA production databases that have none of the WMS models, and it
must not be forced to upgrade for a WMS-only feature.

The module declares no Python model. Everything it does is controllers plus an
OWL front end over models owned by the WMS stack — which is why an automated
scan reports it as empty and why this entry exists.

**How it works**

- **Sidebar shell** with a work-queue badge per module, instead of flat tabs, so a picker sees where the work is.
- **Receive** — open receipts, GS1/EAN scan, IMEI serial capture, expiry and supplier batch entry, QC pass/fail against the quarantine gate from `custom_wms_inbound_qc`.
- **Putaway** — the engine's ranked bin suggestion per line; accept it, or override by scanning a different bin.
- **Pick & Pack** — pick list grouped by source bin, scan-to-confirm, put in package, validate.
- **Package** — scan any package to see contents, location and history, and move it bin to bin.
- **Count** — cycle-count and spot-check sessions, line by line.
- **Bin-to-bin** — transfer-order proposals raised by the low-water engine in `custom_wms_to_engine`.
- **Stock check** — read-only: scan a product to see its details, the suggested bin, and on-hand versus reserved stock per bin.

**Endpoints**: `/hht/`, `/hht/wms/bin2bin/execute`, `/hht/wms/bin2bin/list`, `/hht/wms/count/lines`, `/hht/wms/count/sessions`, `/hht/wms/count/submit`, `/hht/wms/package`, `/hht/wms/package/move`, `/hht/wms/pick/confirm`, `/hht/wms/pick/pack`, `/hht/wms/pick/validate`, `/hht/wms/picking`, `/hht/wms/pickings`, `/hht/wms/putaway/apply`, `/hht/wms/putaway/suggest`, `/hht/wms/qc`, `/hht/wms/queue`, `/hht/wms/receive/scan`, `/hht/wms/receive/validate`, `/hht/wms/scan/resolve`, `/hht/wms/stock/lookup`, `/hht/wms/warehouses`

### custom_wms_inbound_qc — Custom WMS Inbound QC

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_inbound_qc` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_wms_putaway`, `stock`, `product`, `mail` |
| Models / routes / tests | 1 / 0 / 1 |
| Tags | wms, quality, audit-trail, approval-workflow |

> Knowledge file is generator output, not human-reviewed.

Makes inbound quarantine real. Plain Odoo 19 CE will happily reserve stock that
has only just landed on the dock, so a two-step reception is a *routing* device,
not a *hold*. This module turns the inbound area into an actual gate: quants in
a flagged location are invisible to outbound reservation, a receipt cannot be
released until an inspector passes it, and a barcode nobody recognises becomes a
reviewable registration record instead of a blocked receiving operator.

**How it works**

- Admin flags the inbound / QC location (`wms_is_qc_area`, which implies `wms_block_reservation`). The block is inherited by every child bin, so flagging `WH/Input` quarantines the whole area.
- Admin sets `wms_qc_required` (and optionally `wms_qc_location_id`) on the incoming `stock.picking.type`.
- A receipt of that type is created with `wms_qc_state = 'pending'` and its destination forced to the QC area.
- Goods are received. They are physically on hand but `_get_available_quantity` returns 0 for them, so no delivery, MO or transfer can reserve them.
- An inspector (`group_wms_qc_inspector`) calls `action_wms_qc_pass`. The module adopts the route's existing `Input -> Stock` transfer when a multi-step reception already created one, otherwise it builds one; either way the transfer is stamped `wms_qc_release_ok` and reserved with the bypass context. `custom_wms_putaway` then slots each released line into a real bin.
- `action_wms_qc_fail` leaves the goods quarantined, records who failed it, and opens a `quality.alert` when the quality module happens to be installed.
- A scan that matches no product goes to `custom.wms.product.registration.capture`, which accumulates re-scans on one open row; approval creates the product.

**Key models**

- `stock.location` (inherited) — `wms_is_qc_area`, `wms_block_reservation`, plus the cached `_wms_blocked_location_ids()` resolver.
- `stock.quant` (inherited) — `_get_gather_domain` override; the single choke point for the whole reservation stack.
- `stock.picking.type` (inherited) — `wms_qc_required`, `wms_qc_location_id`.
- `stock.picking` (inherited) — QC state machine, release-transfer builder, and an outbound guard on `button_validate`.
- `stock.move` (inherited) — `_action_assign` split so only an authorised release transfer may reserve out of quarantine.
- `stock.move.line` (inherited) — redefines `_is_incoming()` for the putaway engine.
- `custom.wms.product.registration` — unknown-item capture and approval.

**Important fields**

- `stock.location.wms_block_reservation` (Boolean, indexed) — the actual switch.
- `stock.location.wms_is_qc_area` (Boolean) — intent flag; its onchange sets the switch above.
- `stock.picking.wms_qc_state` (Selection not_required/pending/passed/failed).
- `stock.picking.wms_qc_release_ok` (Boolean) — marks the ONE internal transfer allowed to draw from quarantine.
- `stock.picking.wms_qc_release_picking_id` (M2o) — the adopted or created leg.
- `custom.wms.product.registration.state` (draft/submitted/approved/rejected).
- `custom.wms.product.registration.barcode` (Char, indexed, required).

### custom_wms_integration — Custom WMS Integration

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_integration` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_adapter_framework`, `stock`, `purchase`, `sale_management` |
| Models / routes / tests | 2 / 4 / 1 |
| Tags | wms, integration, sap, audit-trail, multi-tenant |

> Knowledge file is generator output, not human-reviewed.

Two-way integration between Odoo Inventory and an external WMS or host system — SAP (WM/EWM behind a PI/CPI or REST facade) and generic REST hosts. Inbound, the host pushes ASNs, delivery orders and acknowledgements into Odoo over an HMAC-signed REST API and reads on-hand stock. Outbound, every warehouse event Odoo produces (goods receipt, putaway, pick, pack, goods issue, cycle-count adjustment) is persisted in a durable outbox and drained through a `custom_adapter_framework` adapter by a cron. The module owns no warehouse logic of its own — it is a translation and delivery layer.

**How it works**

- **Host → Odoo (ASN).** `POST /api/wms/asn` with `{external_ref, partner_ref, warehouse_code, expected_date, lines[]}`. `stock.picking._wms_upsert_from_host(payload, "incoming")` resolves the operation type from `warehouse_code` (`stock.warehouse.in_type_id`), resolves partner and SKUs through `wms.integration.mapping`, and creates a **draft** incoming picking stamped with `wms_external_ref`. A repeat POST with the same `external_ref` finds the existing picking, wipes its draft moves and rebuilds them — one picking, never two. Once the picking has left `draft`/`confirmed` the payload is ignored and reported back as a warning; the host cannot rewrite work in progress.
- **Host → Odoo (DO).** `POST /api/wms/do` — identical path, `outgoing`, `stock.warehouse.out_type_id`.
- **Host → Odoo (stock query).** `GET /api/wms/stock?sku=&location_code=&warehouse_code=&limit=&offset=` reads `stock.quant` restricted to internal locations, paginated (default 200, hard max 1000) and translated back to host codes.
- **Odoo → Host.** `stock.picking.button_validate()` runs `super()` first; for every picking that actually reached `done` it enqueues `wms.integration.event` rows: `goods_receipt` (incoming), `goods_issue` + `pick_confirmed` (outgoing), `putaway_done` (internal), plus one `pack_created` per result package. `custom.cycle.count.adjustment.action_post` — when that module happens to be installed — enqueues `stock_adjustment`.
- **Drain.** The cron `wms.integration.event._cron_drain_outbox()` (every 5 minutes) walks pending rows oldest-first, resolves the adapter config, and calls `WmsHostAdapter.push_event()`. The framework does the retry/backoff, the circuit breaker and the `custom.adapter.call.log` write. The drain stops early when the breaker is open.
- **Ack.** `POST /api/wms/ack` with `{external_ref | external_refs[], host_ref}` moves the outbox rows to `acked` and stamps `acked_at`. Unknown references are reported in `data.unknown` rather than erroring.

**Key models**

- `wms.integration.event` — the outbound outbox. Append-only-ish: payload and source reference freeze at creation, only delivery bookkeeping mutates. Carries the cron, the ack handler, and (via `_register_hook`) the cycle-count patch.
- `wms.integration.mapping` — host-code ↔ Odoo-record translation for `product.product`, `stock.location`, `res.partner`, with a natural-key fallback so most tenants need very few rows.
- `stock.picking` (extension) — `wms_external_ref` idempotency key, the `button_validate` hook, the ASN/DO upsert, and the payload builders.
- `WmsHostAdapter` / `WmsSapHostAdapter` — plain Python `BaseAdapter` subclasses (not Odoo models), registered as `wms_host` and `wms_sap_host`.

**Important fields**

- `wms.integration.event.name` — `WMSEVT/<year>/######` from `ir.sequence` code `wms.integration.event`; doubles as the default `external_ref`.
- `wms.integration.event.event_type` — `goods_receipt` / `putaway_done` / `pick_confirmed` / `pack_created` / `goods_issue` / `stock_adjustment`. Kept in one place (`EVENT_TYPES` in `models/wms_host_adapter.py`) so the Selection and the adapter endpoint map cannot drift apart.
- `wms.integration.event.state` — `pending` → `sending` → `sent` → `acked`, or `failed` after `MAX_ATTEMPTS` (8). Indexed; the cron's only selector.
- `wms.integration.event.payload` — `fields.Json`. The `data` sub-object of the wire envelope, not the whole envelope (see `_envelope()`).
- `wms.integration.event.external_ref` — correlation key the host echoes on `/api/wms/ack`. Defaults to `name`; `pack_created` events use `<picking>/<package>`.
- `wms.integration.mapping.direction` — `inbound` / `outbound` / `both`. A row only applies to lookups in its own direction, which lets a tenant translate asymmetrically.
- `wms.integration.mapping.company_id` — empty means "all companies"; a company-specific row wins over a global one (`order="company_id desc"`).
- `stock.picking.wms_external_ref` — the ASN/DO idempotency key, indexed, `copy=False`.

**Endpoints**: `/api/wms/ack`, `/api/wms/asn`, `/api/wms/do`, `/api/wms/stock`

### custom_wms_putaway — Custom WMS Putaway

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_putaway` |
| Version | 19.0.0.3.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_barcode`, `stock`, `product` |
| Models / routes / tests | 6 / 0 / 1 |
| Tags | wms, barcode-scan, hht, audit-trail |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.2.0, module is now 19.0.0.3.0.

Generic, configurable, tier-prioritised **putaway engine** that closes the CE-vs-EE gap for SAP-style ZWME001 multi-tier slotting. On every incoming `stock.move.line` create, the engine evaluates all active rules of all active strategies for the destination warehouse, scores them per kind, and either auto-rewrites `location_dest_id` (score >= the configured threshold) or surfaces a `custom.wms.putaway.suggestion` for operator review (typically through the HHT bridge).

Since 19.0.0.2.0 the engine **defers to the native Odoo 19 capacity model** rather than competing with it: `stock.package.type` supplies PxLxT and tare weight, `stock.storage.category` supplies the weight ceiling and per-package-type capacity, and this module only adds what the native model has no field for — bin geometry, walk order, and product-category reservation.

Rule kinds are pluggable: `fixed_location`, `nearest_empty`, `zone_round_robin`, `by_volume`, `by_dimension`, `by_weight`, `by_temperature`, `by_abc_velocity`, and a `safe_eval`-sandboxed `custom_python`.

**How it works**

- Warehouse admin creates a `custom.wms.putaway.strategy` per `stock.warehouse`, picking a `rule_set` (default `zwme001_6tier`). A PostgreSQL `EXCLUDE` constraint allows only one active strategy per warehouse.
- Admin adds `custom.wms.putaway.rule` rows: each has `tier` (1..6, lower = higher priority), `sequence`, `kind`, optional `target_location_id` / `target_location_domain` / `product_categ_ids` / `product_domain`, optional `abc_class`, `temperature_zone`, `dock_location_id`, or a `custom_python` expression.
- An inbound `stock.picking` is processed; for every new `stock.move.line` on an `incoming` picking, `custom.putaway.engine.apply_top_proposal(move_line)` is invoked.
- `propose()` enumerates active rules in `(tier, sequence)` order. For each rule the candidate bins pass a **hard feasibility gate** (`_feasible_locations`) covering category reservation, weight ceiling and PxLxT fit, and only then are scored.
- A `custom.wms.putaway.suggestion` row is created. If the top score clears `custom_wms_putaway.auto_apply_threshold` (default 90), `action_apply()` runs immediately.
- Operator can `action_accept` / `action_reject`, or set `overridden_location_id` and `action_apply`.

**Key models**

- `custom.wms.putaway.strategy` — Per-warehouse rule container; exactly one active per warehouse.
- `custom.wms.putaway.rule` — Single tiered scoring entry; kind selects the handler.
- `custom.wms.putaway.suggestion` — Engine output awaiting operator decision.
- `custom.putaway.engine` (AbstractModel) — Feasibility + scoring + auto-apply service.
- `custom.wms.hd.pallet` — Handling unit / pallet tracker.
- `stock.location` (inherited) — capacity, geometry, walk order, category reservation.
- `stock.move.line` (inherited) — `create()` hook + category-reservation constraint.
- `product.template` / `product.product` (inherited) — `abc_class`, default handling unit.

**Important fields**

- `custom.wms.putaway.rule.kind` (Selection) — dispatches to `_score_<kind>`.
- `custom.wms.putaway.rule.product_categ_ids` (M2m) — declarative category filter; prefer it over the `product_domain` safe_eval string.
- `custom.wms.putaway.rule.dock_location_id` (M2o) — distance origin for `nearest_empty`.
- `custom.wms.putaway.rule.round_robin_cursor` (Integer, readonly) — rotation state for `zone_round_robin`.
- `stock.location.wms_length_mm` / `wms_width_mm` / `wms_height_mm` (Float) — bin opening.
- `stock.location.wms_max_weight_kg` (Float) — fallback ceiling; the storage category always wins.
- `stock.location.wms_walk_sequence` (Integer, indexed) — position along the physical route.
- `stock.location.wms_allowed_categ_ids` (M2m) + `wms_enforce_categ` (Boolean) — category reservation, advisory or hard.
- `product.template.wms_package_type_id` (M2o `stock.package.type`) — default handling unit; **optional**, the engine degrades to `product.volume` / `product.weight` without it.
- `product.template.wms_units_per_package` (Float) — units-to-handling-unit conversion.
- `ir.config_parameter` `custom_wms_putaway.auto_apply_threshold` (default 90).

### custom_wms_receiving_ext — Custom WMS Receiving Extensions

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_receiving_ext` |
| Version | 19.0.0.2.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `stock`, `product_expiry`, `custom_barcode`, `custom_product_barcode` |
| Models / routes / tests | 1 / 0 / 1 |
| Tags | wms, barcode-scan, goods-receipt |

Closes the goods-receipt gaps in the WMS stack **without touching the shared
`custom_barcode` addon** — which matters because `custom_barcode` is installed
on tenant databases that have no interest in these behaviours, and every shared
addon version bump forces an upgrade run across all of them.

**How it works**

- **GS1 expiry write-through.** AI 17 (expiration date) was already parsed into the scan line's `x_gs1_parsed` JSON but never applied anywhere. It now lands on `stock.lot.expiration_date` when the scan is applied to the picking.
- **Supplier batch reference.** A new field on both `stock.lot` and the scan line, filled manually or from the GS1 lot (AI 10) when the scan is applied — so a recall can be traced to the supplier's own batch number, not just ours.
- **Serial / IMEI capture.** GS1 AI 21 becomes the `stock.lot` name for serial-tracked products. A bare 14–16 digit IMEI scan, which previously fell through as "not found", is attributed to the picking's sole serial-tracked product.
- **Receipt template import.** A wizard on incoming pickings uploads a CSV or XLSX template (barcode or SKU, serial or lot, quantity, expiry date, supplier batch) and creates move lines and lots in bulk. A blank template is downloadable from the same wizard, so the format is never guessed.

**Key models**

- `custom.wms.receipt.import.wizard` — the CSV/XLSX bulk receipt loader.
- `stock.lot` (inherited) — gains the supplier batch reference and receives the GS1 expiry.
- `stock.move.line` (inherited) — carries the scanned lot/serial through to the picking.
- `custom.barcode.scan.line` / `custom.barcode.scan.session` (inherited) — where the GS1 write-through and IMEI attribution hook in.

**Important fields**

- `stock.lot.supplier_batch_ref` — the supplier's own batch number, the field that makes a supplier-side recall traceable. Declared here.
- The scan line's `x_gs1_parsed` JSON — the raw parse result, kept so a mapping bug can be diagnosed after the fact.
- The expiry target is `expiration_date`, which belongs to upstream `product_expiry`. This module does not declare it; it finally *writes* it, from GS1 AI 17, at the moment the scan is applied to the picking.

### custom_wms_reports — Custom WMS Reports

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_reports` |
| Version | 19.0.0.2.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse, Levi's) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `stock_account`, `purchase_stock`, `custom_wms_cycle_count`, `custom_wms_docs` |
| Models / routes / tests | 8 / 0 / 1 |
| Tags | wms, reporting |

The **warehouse reporting pack** — six analyses plus printable documents,
covering the reporting requirements the WMS stack did not answer. Every analysis
model is a **read-only SQL view**, not a stored table, so nothing here can drift
from the operational data it summarises.

**How it works**

- **Purchase Return Report** — done moves to supplier locations, grouped per supplier and per SKU (list and pivot).
- **Stock Summary Report** — on-hand per SKU, warehouse and location with unit cost and stock value.
- **Stock Take Report** — cycle-count lines with expected, counted and variance quantity plus variance value, and a printable PDF sheet per session.
- **Spot Check** — a `spot_check` sampling method added to cycle-count plans (small random sample) with a report view filtered to it.
- **Transfer Report** — stock moves by operation type with demand and done quantity.
- **Scrap Report** — write-offs per bin, SKU and lot with scrap value and the replenish flag, plus a printable Scrap Note PDF.
- Every analysis exports to **XLSX with embedded Code128 barcodes** at two levels: one column for the transaction (picking, scrap order, count session or bin) and one for the line item (the lot when tracked, otherwise the product EAN). The sheet stays scannable outside Odoo. The PDFs carry the same two barcode levels.

**Key models**

- `custom.wms.purchase.return.report`, `custom.wms.stock.summary.report`, `custom.wms.stock.take.report`, `custom.wms.transfer.report`, `custom.wms.scrap.report` — the five SQL-view analysis models.
- `custom.wms.xlsx.report` — the shared XLSX writer with the Code128 embedding.
- `custom.cycle.count.plan` / `custom.cycle.count.session` (inherited) — where the `spot_check` sampling method is added.
- `stock.scrap` (inherited) — extended for the Scrap Note.

**Important fields**

- `custom.cycle.count.plan.method` — extended by `selection_add` with `spot_check` alongside the existing sampling methods, and `ondelete={"spot_check": "set default"}` so uninstalling does not orphan plans.
- Stock value columns on the summary and take reports read from the move value, not from a valuation layer: Odoo 19 has no `stock.valuation.layer` in this configuration, and reading one would silently return nothing.

### custom_wms_sap_slotting — Custom WMS SAP Slotting

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_sap_slotting` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_wms_putaway`, `stock`, `product` |
| Models / routes / tests | 4 / 0 / 1 |
| Tags | wms, slotting, putaway, sap |

Adds the two **SAP WM slotting dimensions** that `custom_wms_putaway` does not
model: Storage Type (SAP *Lagertyp*) and Storage Section (SAP *Lagerbereich*).
Warehouses migrating off SAP WM expect putaway to search in that order; without
these dimensions the generic engine cannot reproduce their slotting rules.

Everything is added by **inheritance**. `custom_wms_putaway` is untouched, so
tenant databases that do not use SAP slotting never need to upgrade the shared
putaway addon.

**How it works**

- Storage Types and Storage Sections become first-class records, each carrying an ordered **search sequence**. The reference configuration ships AC1/AC2/AP1/AP2/FO1/FO2/FL1 as types and BB1/GF1/GO1/LS1/OD1/RU1/SL1/SS1/TR1/GA2 as sections.
- A new putaway rule kind, `sap_storage_search`, walks the two sequences — storage type on the outer loop, storage section on the inner — and slots into the first bin with free volume.
- The resulting suggestion is **scored by how far down each sequence** the search had to go, so the ranked list the handheld shows reflects how good a fit the bin actually is, not just that it fits.
- Products and locations carry their type and section, which is what the search matches against.

**Key models**

- `custom.wms.storage.type` + `custom.wms.storage.type.search.line` — the Lagertyp dimension and its ordered search sequence.
- `custom.wms.storage.section` + `custom.wms.storage.section.search.line` — the Lagerbereich dimension and its sequence.
- `custom.putaway.engine`, `custom.wms.putaway.rule` (inherited) — the `sap_storage_search` rule kind.
- `stock.location`, `product.template`, `product.product` (inherited) — carry the type/section assignment.

**Important fields**

- The `sequence` on each search line — the ordering is the rule. Reordering these changes slotting behaviour with no code change, which is the point.
- `custom.wms.putaway.rule.kind` = `sap_storage_search` — selects the 2-D search instead of the generic multi-tier strategy.

### custom_wms_to_engine — Custom WMS Transfer Order Engine

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_wms_to_engine` |
| Version | 19.0.0.3.0 |
| Scope | Umum, dikonfigurasi (JDS Warehouse) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_core`, `custom_pdp_audit`, `stock`, `product`, `barcodes`, `mail` |
| Models / routes / tests | 4 / 0 / 1 |
| Tags | wms, barcode-scan, audit-trail |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.1.0, module is now 19.0.0.3.0.

The `custom_wms_to_engine` module implements a rule-driven internal transfer orchestration system for warehouse management (WMS). It evaluates predefined rules based on triggers such as low water mark, expiry approaching, zone consolidation, and picking replenishment (plus a no-op `manual` trigger). The engine produces proposal dicts and materializes them into concrete transfer orders (`custom.transfer.order`) with backing `stock.move` internal transfers.

**How it works**

- **Rule Definition**: Admins define rules (`custom.to.rule`) with source/target location domain expressions (stored as text, evaluated via `safe_eval`) and trigger-specific parameters.
- **Evaluation**: `custom.to.engine.evaluate_all` searches all active rules ordered by `priority asc, sequence asc` and dispatches each to a per-trigger `_eval_*` handler via `evaluate_rule`.
- **Proposal Generation**: Each `_eval_*` handler returns proposal dicts (source/target location, product, lot, planned qty, reason).
- **Materialization**: Proposals are turned into records. `materialize` creates the backing `stock.move`, will create the `custom.transfer.order` itself when none is passed, and performs the `draft`→`proposed` transition. The `cron_evaluate_and_materialize` entrypoint ties `evaluate_all` to TO creation.
- **Execution**: Transfer orders are advanced manually via `action_start` (draft/proposed → in_progress) and `action_done`. There is no state-driven auto-execution; the cron only creates proposed TOs, it does not advance or execute them.

**Declared models**: `custom.to.engine`, `custom.to.rule`, `custom.transfer.order`, `custom.transfer.order.manual.wizard`

**Important fields**

- **custom.to.rule**
- `name` (Char) — Rule name.
- `trigger` (Selection: low_water_mark, expiry_approaching, zone_consolidation, picking_replenishment, manual) — Trigger type; default `manual`.
- `source_location_domain`, `target_location_domain` (Char) — Odoo domain expressions (text) evaluated via `safe_eval`.
- **custom.transfer.order**
- `name` (Char) — Order name (sequence-assigned from `custom.transfer.order`).
- `state` (Selection: draft, proposed, in_progress, done, canceled) — State of the transfer order.
- `source_location_id`, `target_location_id` (Many2one to stock.location) — Source and target locations.
- `product_id` (Many2one to product.product) — Product being transferred.

## Sales, Retail & POS (Penjualan, Retail & POS)

### custom_crm — Custom CRM

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_crm` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_ai_bridge`, `crm`, `mail`, `base_automation` |
| Models / routes / tests | 2 / 0 / 3 |
| Tags | crm, ai, pdp, audit-trail, whatsapp |

> Knowledge file is generator output, not human-reviewed.

Extends standard CE `crm.lead` with EE-equivalent lead-management features: a rules-based predictive score (0-100), an AI scoring action that delegates to `custom.ai._recommend` (custom_ai_bridge), a mock lead-enrichment action, a stub lead-mining model that fabricates `crm.lead` rows from an internal seed list (no real IAP), a token-secured webhook intake (`custom.crm.web.form.token.ingest_payload`), a WhatsApp contact field, and PDP-audit logging of salesperson reassignments.

The module is intentionally a CE-on-platform replacement for EE features (Predictive Lead Scoring, Lead Mining/IAP, Lead Enrichment) — all "AI" features tunnel through `custom_ai_bridge` so the same code path works in offline/mock mode.

**How it works**

- A salesperson or external system creates a `crm.lead`. If created via webhook, `custom.crm.web.form.token.ingest_payload(token, data)` validates the token, increments `use_count`, sets `team_id` from the token, and returns the new lead id.
- `_compute_predictive_score` runs on each write to `email_from / phone / partner_id / source_id / medium_id / country_id` and stores `x_predictive_score` as a heuristic 30..100 number, with a +20 boost when the lead's source has historical win-rate > 50%.
- A user clicks "AI Score Lead" → `action_ai_score_lead()` packs a payload via `_custom_ai_payload`, calls `custom.ai._recommend`, writes `x_ai_score`, `x_ai_reasoning`, `x_ai_scored_date`, posts a chatter note. On bridge failure it returns a non-blocking notification.
- "Enrich Lead" → `action_enrich_lead()` calls the same bridge; on failure falls back to a deterministic mock (industry, employees, website, linkedin) and may write `website` onto the linked `res.partner`.
- "Lead Mining" → user creates `custom.crm.lead.mining.request` (draft), clicks `action_get_leads()` which creates up to `lead_number` draft `crm.lead` rows from `_MOCK_COMPANIES`, flips to `done`, bumps `credits_used`.
- On `write({"user_id": …})` the `_pdp_audit_owner_change` hook raw-inserts an `internal` classification row into `pdp.audit_log` (best-effort, swallowed on error).
- `base.automation` rules in `data/crm_automation_rules.xml` provide round-robin assignment and follow-up activity samples.

**Key models**

- `crm.lead` (inherited) — Adds AI/predictive/enrichment fields + WhatsApp number + owner-change audit + mining link.
- `custom.crm.lead.mining.request` — Draft/done state machine, mocked IAP-style credits, generates draft leads from `_MOCK_COMPANIES`.
- `custom.crm.web.form.token` — Webhook intake credential; `ingest_payload(token, data)` is the public ORM entrypoint (no controller in this module).

**Important fields**

- `crm.lead.x_predictive_score` (Float, computed, stored) — heuristic 0-100, EE-equivalent.
- `crm.lead.x_ai_score` / `x_ai_reasoning` / `x_ai_scored_date` — output of AI bridge call.
- `crm.lead.x_whatsapp_number` — Indonesian SMB outreach channel (E.164).
- `crm.lead.x_enrichment_data` (Text JSON) / `x_enriched_at` — enrichment payload trail.
- `crm.lead.x_lead_mining_request_id` (M2o) — back-link to mining request that generated this lead.
- `custom.crm.lead.mining.request.state` (draft/done) — one-shot generator; `action_get_leads` blocked when done.
- `custom.crm.lead.mining.request.lead_number` (Integer, default 3) — capped by `len(_MOCK_COMPANIES)` = 5.
- `custom.crm.web.form.token.token` (Char, unique, default `secrets.token_urlsafe(24)`) — rotated via `action_rotate_token`.
- `custom.crm.web.form.token.team_id` — default `crm.team` for ingested leads.

### custom_ecommerce — Custom eCommerce Indonesia

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_ecommerce` |
| Version | 19.0.0.2.0 |
| Scope | Umum, dikonfigurasi (GentleWoman) |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `website_sale`, `delivery`, `custom_payment_id`, `mail` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | ecommerce, marketing, crm, pdp |

> Knowledge file is generator output, not human-reviewed.

Indonesia localization for `website_sale` + `delivery`. Provides a registry of Indonesian couriers (JNE, J&T, SiCepat, AnterAja, Pos Indonesia, Grab, Gojek, Custom), per-carrier service-type/COD metadata, a mock shipping-rate calculator that is RajaOngkir/Komerce-ready (returns a real-adapter-shaped dict so call sites never branch on mock-vs-live), AWB/Resi tracking on `sale.order`, and a cart-abandonment reminder cron that prefers WhatsApp (with PDP consent) and falls back to email.

It does **not** ship its own payment gateway; Midtrans/Xendit checkout entry is delegated to `custom_payment_id`.

**How it works**

- An admin populates `custom.ecommerce.courier` rows for each provider (`code` from the fixed selection, `api_endpoint`, `api_key` group-gated, `tracking_url_template` with `{awb}` placeholder).
- A standard `delivery.carrier` is linked to a courier via `x_id_courier_id` and tagged with `x_id_service_type` (`REG/YES/OKE/...`). `x_id_cod_supported` + `cod_max_amount` enable COD ceiling validation.
- During checkout, `delivery.carrier.id_rate_shipment(order)` returns the standard delivery-framework dict by wrapping `_get_id_shipping_rate(order)`. The mock rate is `base_rate_per_kg[code] × weight × service_multiplier × distance_factor`, where distance is approximated by comparing first 2 digits of origin/destination ZIP (intra-province = 1.0x, inter = 1.4x). Weight is derived from `order_line.product_id.weight × qty`, minimum 1kg.
- Once shipped, an operator sets `sale.order.x_awb_number`; the stored compute `x_awb_tracking_url` renders the courier's `tracking_url_template` with the AWB number.
- Cart abandonment: cron `cron_send_abandoned_reminders` sweeps draft `sale.order` with `write_date <= now - 24h`, partner not public, at least one line. For each new order it creates a `custom.ecommerce.cart.abandonment` row. If the partner has phone + active `pdp.consent.purpose_marketing` and `custom_whatsapp` is installed, dispatch via WhatsApp; otherwise email via `mail_template_cart_abandonment`. The WhatsApp branch currently posts a chatter marker rather than a real `whatsapp.message` (manifest pattern — actual send delegated to `custom_whatsapp` when integration is wired).
- Indonesian DJP-style invoice receipt qweb report is shipped (referenced in manifest description).

**Key models**

- `custom.ecommerce.courier` — Registry of Indonesian couriers; `code` (jne/jnt/sicepat/anteraja/posindo/grab/gojek/custom), API endpoint, tracking URL template, service types.
- `delivery.carrier` (inherited) — Adds `x_id_courier_id`, `x_id_service_type`, `x_id_cod_supported`, `cod_max_amount`, `currency_id`; `_get_id_shipping_rate`, `id_rate_shipment`.
- `sale.order` (inherited) — Adds `x_awb_number`, stored `x_awb_tracking_url` (computed), and a related read-only `x_id_courier_id` mirror.
- `custom.ecommerce.cart.abandonment` — Abandoned cart record + reminder dispatch state; unique `sale_order_id` constraint.

**Important fields**

- `custom.ecommerce.courier.code` (Selection, required, tracked) — drives the base-rate lookup in `_BASE_RATE_PER_KG`.
- `custom.ecommerce.courier.tracking_url_template` (Char) — `{awb}` placeholder; rendered into `sale.order.x_awb_tracking_url`.
- `delivery.carrier.x_id_courier_id` (M2o `custom.ecommerce.courier`) — link to the localized courier.
- `delivery.carrier.x_id_service_type` (Char) — `REG`/`YES`/`OKE`/`ECO`/`EXP`/`SAMEDAY`/`INSTANT`; multiplier in `_SERVICE_MULTIPLIER`.
- `delivery.carrier.x_id_cod_supported` (Boolean) + `cod_max_amount` (Monetary) — COD ceiling; `_check_cod_max` rejects negative ceilings.
- `sale.order.x_awb_number` (Char) — set by operator post-shipment.
- `sale.order.x_awb_tracking_url` (Char, stored compute) — depends on `x_awb_number`, `carrier_id`, courier's template.
- `custom.ecommerce.cart.abandonment.reminder_channel` (Selection: email/whatsapp/none) — channel actually used by the dispatcher.
- `custom.ecommerce.cart.abandonment.reminder_sent` / `reminder_sent_at` — idempotency markers.

### custom_levis_localization — Levi's Localization

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_levis_localization` |
| Version | 19.0.1.29.0 |
| Scope | Khusus brand (Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `product`, `stock`, `stock_account`, `stock_delivery`, `purchase`, `purchase_stock`, `account`, `point_of_sale`, `custom_retail_import_pos` |
| Models / routes / tests | 21 / 0 / 7 |

> Knowledge file is generator output, not human-reviewed.

This module implements five specific requirements for the Levi's tenant: HS Code management on the product master, ensuring receipt quantities do not exceed demand quantities, skipping the inventory journal entry at goods receipt confirmation, generating branded payment vouchers and receipts, and providing a periodic inventory reconciliation tool that realigns GL inventory-asset accounts with actual on-hand stock value.

**How it works**

- **HS Code Management**:
- Delivered as a `product.template` view that inherits `product.product_template_form_view` to surface the native `stock_delivery` `hs_code` field on the General Information tab (`views/product_template_views.xml:9-18`). There is no Python `product` override; the field itself comes from `stock_delivery`.
- **Receipt Quantity Validation**:
- On confirming an incoming stock picking, if any line's done quantity exceeds its demand quantity (compared with `float_compare`), a `UserError` is raised listing the offending products.
- **Inventory Journal at Goods Receipt & Vendor Return (opt-in switch)**:
- Governed by `ir.config_parameter` `custom_levis_localization.suppress_gr_journal` (default **OFF**). This build has no standard stock input/output interim accounts, so core real-time valuation posts nothing; the module books inventory GL directly via the category pair `property_stock_valuation_account_id` + `account_stock_variation_id` (same pair the Inventory Reconciliation tool uses).
- Switch OFF (default): on a vendor **goods receipt** (source = supplier) it posts `Dr Stock Valuation / Cr Stock Variation` for `move.value` (ref `GR-VAL:<move id>`); on a vendor **return / RTV** (destination = supplier) it posts the exact reverse `Dr Stock Variation / Cr Stock Valuation` (ref `GR-RET-VAL:<move id>`). Both are idempotent by `ref` and only fire for `real_time` categories with the accounts + a stock journal set.
- Switch ON (periodic): both receipt and return journals are suppressed; GL is trued up periodically by `levis.inventory.reconciliation`.
- **Payment Vouchers & Payment Receipts**:
- Two branded PDF documents are generated for payments on `account.payment`: a *Payment Voucher* for vendor/outbound payments and a *Payment Receipt* for customer/inbound payments. Each renders only for its matching payment direction.
- **Periodic Inventory Reconciliation**:
- Because receipts/deliveries do not post inventory journals in this setup, GL inventory-asset accounts drift from real on-hand value. `levis.inventory.reconciliation` computes, per valuation account, the actual stock value (`stock.quant.value`) vs the current GL balance and generates a DRAFT adjustment journal against an inventory-variation account for the accountant to review and post.

**Key models**

- `levis.inventory.reconciliation` — Manages periodic inventory reconciliations, computing differences between GL balances and actual stock values and producing a DRAFT `account.move`.
- `levis.inventory.reconciliation.line` — One line per stock-valuation account, holding the GL balance, stock value, and computed difference.
- `stock.move` — Overrides to skip GL journal entries on vendor goods-receipt moves.
- `stock.picking` — Overrides to validate receipt quantities against demand quantities.

**Important fields**

- **levis.inventory.reconciliation**:
- `name`: Sequence-generated identifier. Defaults to `"/"` and is replaced in `create()` via the `levis.inventory.reconciliation` `ir.sequence` (prefix `INVREC/%(year)s/`).
- `company_id`: Company for the reconciliation (defaults to the active company).
- `date`: Date up to which posted GL balances are considered (default is today).
- `journal_id`: General account journal used for generating the reconciliation entry.
- `counterpart_account_id`: Inventory variation account where differences are booked when a category-level Stock Variation account is not set.
- `line_ids`, `move_id`, `state` (draft/computed/generated), `total_difference` (computed sum of line differences), `currency_id`.
- **levis.inventory.reconciliation.line**:
- `reconciliation_id`: Parent reconciliation (cascade delete).
- `company_id`, `currency_id`: Related from the parent.
- `account_id`: Valuation Account.
- `counterpart_account_id`: Variation Account.
- `book_value`: GL Balance.
- `stock_value`: Actual on-hand stock value.
- `difference`: Computed and stored, `stock_value − book_value`.
- **stock.move**:
- `_is_levis_goods_receipt()`: True when the move enters from a supplier location (`location_id.usage == 'supplier'`).
- `_is_levis_vendor_return()`: True when the move leaves to a supplier location (`location_dest_id.usage == 'supplier'`) — a vendor return / RTV.
- `_levis_suppress_gr_journal()`: Reads the `suppress_gr_journal` config switch (default OFF).
- `_should_create_account_move()`: Returns `False` for vendor receipts only when the suppress switch is ON; otherwise defers to core.
- `_action_done()`: After super, calls `_levis_post_gr_journal()` (receipts) and `_levis_post_return_journal()` (vendor returns).
- `_levis_book_valuation_entry(ref, label, incoming)`: Shared idempotent poster — `incoming=True` → Dr Valuation/Cr Variation; `incoming=False` → the reverse. No-op if already posted for `ref`, non-real-time category, missing accounts/journal, or zero `move.value`.
- **stock.picking**:
- `button_validate()`: Validates the done quantity against demand quantities on incoming stock pickings (via `float_compare`). Raises an error if any line exceeds its demand.

### custom_operating_unit_pos — Custom Operating Unit — Point of Sale

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_operating_unit_pos` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_operating_unit_docs`, `point_of_sale` |
| Models / routes / tests | 3 / 0 / 1 |
| Tags | operating-unit, data-isolation, point-of-sale |

Operating-Unit isolation for the point of sale, and the unit on the session
closing entry. Auto-installs where `point_of_sale` and
`custom_operating_unit_docs` are both present.

**Declared models**: `pos.config`, `pos.order`, `pos.session`

### custom_pos_id — Custom POS Indonesia

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_pos_id` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `point_of_sale`, `custom_whatsapp`, `custom_sms_id` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | ecommerce, whatsapp, indonesian-tax, pdp |

> Knowledge file is generator output, not human-reviewed.

Indonesia localization for the standard Odoo POS. Adds QRIS (Quick Response Code Indonesian Standard) payment-method metadata with a deterministic EMVCo-TLV payload builder, rupiah rounding for cash kembalian (none / 50 / 100 / 500 / 1000 IDR with up/down/nearest strategies), and electronic-receipt delivery through WhatsApp (`custom_whatsapp`) and SMS (`custom_sms_id`). Includes a simple loyalty-point accrual (1 point per IDR 10,000) wired to `res.partner.x_loyalty_balance`.

This is the canonical POS localization for Indonesian SMB retail; receipt dispatch is integrated with the platform's canonical messaging channels.

**How it works**

- An admin configures `pos.config` with `x_rupiah_rounding` step + `x_rupiah_rounding_strategy`, optional `x_whatsapp_account_id` and `x_sms_account_id` for e-receipt routing, and toggles `x_eperformance_receipt_whatsapp` / `x_ereceipt_sms`.
- Per `pos.payment.method` an admin sets `x_qris_provider` (`bca`/`bri`/`mandiri`/`dana`/`gopay`/`ovo`/`linkaja`/`shopeepay`/`custom`/`manual`), `x_qris_merchant_id`, `x_qris_merchant_name`, `x_qris_merchant_city`, optional `x_qris_static_qr` binary, and `x_qris_dynamic_supported`.
- Frontend POS or backend calls `pos.payment.method.action_generate_qris_payload(transaction_amount)` -> builds the EMVCo TLV payload (00, 01, 26, 52, 53, 54 amount if >0, 58, 59, 60) + CRC-16/CCITT-FALSE checksum -> renders a PNG QR (via stdlib `qrcode` if available) -> returns `{payload, qr_png_b64, provider}`. Manual provider raises UserError.
- On order finalisation, `pos.order.action_apply_idr_rounding()` computes the rounded change for cash payments via `_idr_round_change_amount`: raw change = amount_paid - amount_total, then `math.ceil/floor/round(raw/step)*step` per the configured strategy. `x_idr_rounding_applied = rounded - raw` is persisted (idempotent).
- Loyalty: `x_loyalty_points_earned` is a stored compute = `floor(amount_total / 10000)`. `action_credit_loyalty()` adds those points to `partner.x_loyalty_balance` (sudo write) and sets `x_loyalty_credited=True` to prevent double-credit.
- E-receipt: `pos.order.action_send_ereceipt()` routes by `x_eperformance_receipt_channel` (`whatsapp` / `sms` / `email` / `print` / `none`). WhatsApp path creates a `whatsapp.message` row using the configured account and `_build_ereceipt_body()` plaintext rendering, then calls `action_send`. SMS path creates a `custom.sms.message` with `purpose='transactional'`. Email/print/none are stub-logged.

**Key models**

- `pos.config` (inherited) — Adds rupiah-rounding config + e-receipt channel toggles + account bindings to `whatsapp.account` and `custom.sms.account`.
- `pos.payment.method` (inherited) — QRIS metadata + payload generator. Builds EMVCo TLV strings via internal `_tlv` and `_crc16_ccitt` helpers.
- `pos.order` (inherited) — IDR rounding fields, loyalty accrual, e-receipt dispatch + tracking.

**Important fields**

- `pos.config.x_rupiah_rounding` (Selection: none/50/100/500/1000, default `100`) — IDR step for cash change.
- `pos.config.x_rupiah_rounding_strategy` (Selection: up/down/nearest, default `nearest`) — favouring merchant/customer/neutral.
- `pos.config.x_whatsapp_account_id` (M2o `whatsapp.account`) — required if dispatching WA receipts.
- `pos.config.x_sms_account_id` (M2o `custom.sms.account`) — required if dispatching SMS receipts.
- `pos.payment.method.x_qris_provider` (Selection: manual/bca/bri/mandiri/dana/gopay/ovo/linkaja/shopeepay/custom, default `manual`) — drives MID stub lookup.
- `pos.payment.method.x_qris_merchant_id` / `x_qris_merchant_name` / `x_qris_merchant_city` — EMVCo fields 26.02, 59, 60.
- `pos.payment.method.x_qris_static_qr` (Binary, attachment) — pre-uploaded static QR image.
- `pos.payment.method.x_qris_dynamic_supported` (Boolean) — drives tag 01 (`12` dynamic vs `11` static).
- `pos.order.x_idr_rounding_applied` (Monetary, readonly) — signed adjustment from raw to rounded change.
- `pos.order.x_idr_rounded_change` (Monetary, unstored compute) — rounded change for display.
- `pos.order.x_loyalty_points_earned` (Integer, stored compute on `amount_total`) — `floor(amount_total / 10000)`.
- `pos.order.x_loyalty_credited` (Boolean, copy=False, readonly) — idempotency marker.
- `pos.order.x_eperformance_receipt_channel` (Selection: whatsapp/sms/email/print/none, tracking) — dispatch router.
- `pos.order.x_eperformance_receipt_sent` (Boolean, tracking) — set after dispatch.

### custom_retail_import — Custom Retail Import

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_retail_import` |
| Version | 19.0.0.23.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_product_barcode`, `queue_job`, `product`, `stock`, `account` |
| Models / routes / tests | 9 / 0 / 6 |
| Tags | data-import, retail, excel, sftp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Productized adapter that converts customer-provided Excel/CSV files into Odoo records, plus an optional direct-from-SFTP recurring feed. Built for the Levi's (PT Sinar Eka Selaras / `levis` tenant) onboarding and reusable for any retail tenant. Generalizes the `custom_bank_import` template/wizard/log trio into per-file-type **import profiles**, and ports the proven `scripts/tenants/era_busana_retailindo` X101 pipeline into the X101 executor.

Answers the three customer questions: (1) Excel→Odoo adapter = the wizard + profiles; (2) read directly from FTP = `retail.import.feed` (paramiko/SFTP + cron); (3) X* master/transaction files = per-`file_type` executors.

**How it works**

- **Manual import**: Operator opens **Retail Import ▸ Import Data** (`retail.import.wizard`), picks a `retail.import.profile`, uploads a file. `action_preview()` parses the first 20 rows and shows them with NO commit (dry-run). `action_import()` computes `sha256`, blocks duplicates (unless `force`), persists the file to `ir.attachment`, creates a `retail.import.log` (state `queued`), then runs `retail.import.executor.run(log)` — **async via queue_job** (`channel="root.retail_import"`) for large files (`ASYNC_TYPES = {x101,x20,x24,x70d,x32p}`), synchronous otherwise. Falls back to sync if queue_job is unavailable.
- **SFTP feed**: `retail.import.feed` binds an SFTP location + glob to a profile. `ir.cron cron_poll_retail_feeds` (hourly, **off by default**) → `_cron_poll_feeds()` → per active feed, **in `sequence` order**, `_poll_one()` lists files matching `file_glob`, dedups by `retail.import.log` file-hash, stores to `ir.attachment`, and enqueues the same executor.
- **Mailbox feed (19.0.0.9.0)**: `retail.import.mailbox` pulls the nightly X-center reports out of IMAP. `ir.cron cron_fetch_retail_mailboxes` (hourly) → `_cron_fetch_mailboxes()` → per active mailbox `_fetch()` then `_purge()`. `_fetch` writes every attachment to `backup_dir` (`YYYY/MM/`) and copies the `ingest_glob` subset into `drop_dir`, where the ordinary `local` feeds pick it up. The import pipeline is untouched — this is a transport bridge, not a second importer.
- **`cron_poll_retail_feeds` stays DISABLED** through the 19.0.0.9.0 migration. It is the switch that turns a staged file into `pos.order` + journal entries (where `retail_import.x24_post_enabled` is set). Enabling it is an operator decision that must follow the X70D-vs-`pos.payment` Rp 0 reconciliation — never a side effect of a schema upgrade.
- **Executor dispatch**: `run(log)` reads the stored attachment, calls `_load_<file_type>`. Idempotency via `ir.model.data` external IDs under `profile.namespace` (e.g. `levis`).

**Key models**

- `retail.import.profile` — Declarative parser config per file type. `read_records(file_b64, limit)` → `{records:[{logical_field: value, _row}], total_rows, blank_rows}`.
- `retail.import.log` — Audit row; `file_hash` (SHA256 dedup), `attachment_id` (kept source), `job_uuid`, `records_created/matched/skipped`, `state` ∈ queued/running/imported/partial/failed. Inherits `mail.thread`.
- `retail.import.executor` — **AbstractModel**; the per-file-type loaders. Delayable via queue_job.
- `retail.import.feed` — SFTP/local source + cron poller. `sequence` fixes poll order.
- `retail.import.mailbox` — IMAP source (stdlib `imaplib`) + retention policy. `retail.import.mail.message` is its per-attachment ledger (uid, uidvalidity, sha256, backup_path, staged_path, state).
- `retail.import.wizard` (TransientModel) — Upload + preview + import.

**Important fields**

- `retail.import.profile.code` (Char, unique-per-company), `file_type` (Selection, see list), `namespace` (Char — per-tenant external-ID module, e.g. `levis`).
- `retail.import.profile.file_format` (xlsx/csv), `sheet_name`, `data_start_row` (Integer, 1-based — **the key generalization** over bank import: X70T/X31/X32P have a title row before the header; X101=3, Store Master=3, X24/X70D=2, X20=2, CoA=3).
- `retail.import.profile.column_map_json` (Text) — JSON `{logical_field: 1-based_col_index}`. Seeded per Levi's file in `data/retail_import_profiles.xml`.
- `retail.import.profile.fix_encoding` (Boolean) — restore U+FFFD → '®' (X101 quirk).
- `retail.import.log.file_hash` (Char, indexed) — dedup key.
- `retail.import.feed.password_param` (Char) — `ir.config_parameter` key holding the SFTP secret.
- `retail.import.feed.sequence` (Integer) — poll order. X24=10, X70D=20, X31=30. Matters once posting is enabled: X24 books the POS entries that X70D's tender reconciliation settles against.
- `retail.import.mailbox.password_env` (Char) — environment variable read first (`LEVIS_MAIL_PASSWORD`, injected via docker-compose). `password_param` is a clear-text DB fallback.
- `retail.import.mailbox.ingest_glob` (Char) — comma-separated globs; backed-up attachments matching one are also copied to `drop_dir`. Everything else is backup-only.
- `retail.import.mailbox.purge_enabled` / `dry_run` / `retention_days` — three switches, thrown in that order.

### custom_retail_import_api — Retail Import — MDM Product API

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_retail_import_api` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_core`, `custom_retail_import`, `queue_job`, `product`, `stock` |
| Models / routes / tests | 4 / 6 / 5 |
| Tags | integration, rest-api, retail, product-master, mdm |

Receives **product master data pushed by an upstream MDM hub** instead of pulling
the same data from a scheduled report. Built for Levi's, whose XStore MDM HUB
feeds Odoo through SAP PO → IBM MQ → Mulesoft: running the SSRS X101 report often
enough to stay current was loading their XCenter database.

**Why it is a separate module from `custom_retail_import`.** Odoo builds
`ir.http.routing_map` per database from the modules installed in it.
`custom_retail_import` is installed in several Levi's databases; putting the
controller there would expose `/api/mdm/*` in all of them. Installing this module
only where the integration is wanted makes the route *not exist* elsewhere — a
stronger guarantee than any runtime flag.

**How it works**

- The hub POSTs product JSON to `/api/mdm/products` behind `@secure_endpoint('mdm')`. The raw payload is staged on `retail.mdm.request` with its items on `retail.mdm.item`.
- Keeping the raw payload is deliberate: a mapping bug is fixed by editing code and **replaying** the stored request, never by asking the sender to retransmit. A unique `dedupe_key` makes a re-POST a no-op.
- `retail.mdm.category.map` crosswalks the feed's two-level taxonomy onto existing product categories. This is not optional — `categ_id` drives the revenue and COGS accounts and must not be guessed.
- The actual product writes go through `retail.import.executor._x101_upsert_items`, the same seam the X101 file import uses, so both routes produce identical records.
- **Everything is off until switched on.** The controller answers 503 unless `retail_import.mdm_api_enabled` is `1`, and a shadow mode (`retail_import.mdm_dry_run`) validates real traffic without touching master data.
- Request auditing lives on `retail.mdm.request` — payload, source IP, timings, state, per-item outcome — rather than in `custom.adapter.call.log`. That table is keyed to a `custom.adapter.config` whose `adapter_type` must name a registered *outbound* adapter, and it stores only `sha256(body)`, which is precisely what an inbound feed needs to keep. Rejected requests (bad key, wrong IP, oversize body) are logged by `secure_endpoint` itself.

**Key models**

- `retail.mdm.request` — one inbound call: raw payload, source IP, timings, state, dedupe key. The replay unit.
- `retail.mdm.item` — per-product outcome within a request.
- `retail.mdm.category.map` — feed taxonomy → `product.category` crosswalk.
- `retail.mdm.processor` — turns a staged request into executor calls.

**Important fields**

- `retail.mdm.request.dedupe_key` — unique; the idempotency guarantee.
- `retail.mdm.request.state` — where an operator looks when the hub reports a successful push but the product did not change.
- Config parameters `retail_import.mdm_api_enabled` and `retail_import.mdm_dry_run` — the two switches that decide whether the feed is live, shadow, or closed.

**Endpoints**: `/api/mdm/pending`, `/api/mdm/ping`, `/api/mdm/products`, `/api/mdm/products/lookup`, `/api/mdm/requests/<string:request_id>`, `/api/mdm/requests/<string:request_id>/replay`

### custom_retail_import_pos — Custom Retail Import — POS bridge

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_retail_import_pos` |
| Version | 19.0.0.5.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Kerangka / Sedang |
| Depends | `custom_retail_import`, `point_of_sale` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | data-import, retail, pos, accounting |

> Knowledge file is generator output, not human-reviewed.

The POS half of the retail importer. `custom_retail_import` deliberately does **not** depend on `point_of_sale` — the ARKA-AIM tenant runs the importer without POS, and a hard dependency would force-install the POS application there — so everything that only makes sense once `pos.order` exists lives in this bridge instead. `auto_install: True`, so it appears by itself on any tenant that has both.

Its job is to make POS session close book **exactly** the amounts the source workbook already states, rather than whatever Odoo's own tax engine would recompute from prices.

**How it works**

- **Source amounts survive the import.** `pos.order.line` gains `ri_src_net` / `ri_src_tax` / `ri_src_discount` / `ri_is_return`, filled by the X24DN and X48 executors from the workbook's own columns. `_prepare_base_line_for_taxes_computation` feeds `ri_src_net` / `ri_src_tax` into the tax engine's `manual_tax_amounts` hook.
- **Why that hook is needed:** the source file truncates net per line (`net = trunc(total / 1.11)`, `tax = total - net`) while Odoo rounds tax globally per order. Without the override the two disagree by ±1 rupiah per line — small individually, material over 16k orders.
- **Returns move to their own COA.** A line with `ri_is_return` is re-pointed from `Gross Sales-<category>` to `Sales Return-<category>` via `_ri_return_account`, so returns report separately instead of netting silently against revenue.
- **Discounts ride the store's own closing entry.** `pos.session._create_account_move` appends the source `NET DISCOUNT AMOUNT` reclass (Dr `Sales Discount-<cat>` / Cr `Gross Sales-<cat>`) to the session's closing move **while it is still draft**, rather than posting a separate summary journal. A store can tie its own closing entry to its own day; it cannot tie a detached summary journal to anything.
- **Descriptive columns are kept on the posted records** so the ledger stays auditable against the workbook: cashier (`ri_staff_id` / `ri_staff_name`), the four discount slots folded into `ri_discount_type` / `ri_discount_code` / `ri_discount_description`, and the transaction's member / notes / Omni order id on `pos.order`.

**Key models**

- `pos.order.line` (inherit) — the `ri_src_*` amount trio, `ri_is_return`, the cashier and discount-slot columns, `_ri_return_account`, `_prepare_base_line_for_taxes_computation`.
- `pos.order` (inherit) — cashier, member, customer phone, transaction note, Omni order id.
- `pos.session` (inherit) — `_ri_discount_reclass_line_vals` + the `_create_account_move` override.

### custom_retail_import_recon — Retail Import — X-Store Reconciliation

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_retail_import_recon` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Levi's) |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_retail_import`, `custom_accounting_reports`, `point_of_sale`, `account` |
| Models / routes / tests | 1 / 0 / 0 |

> Knowledge file is generator output, not human-reviewed.

Answers the question finance asks after every nightly retail import: *did everything the stores rang up land in Odoo, and if not, why not?* One read-only row per source transaction from the X24DN sales file, showing the transaction header, what the file said, what Odoo booked, the difference, and — for anything rejected — the importer's own reason.

Replaces the manual routine of exporting the POS list, exporting the X-Store file, and diffing them in a spreadsheet.

**How it works**

- The nightly orchestrator imports X24DN and stages every row on `retail.import.line`.
- The accountant (or the operator who just ran an import) opens **Retail Import → X-Store Reconciliation**, or **Invoicing → Reporting → Reports → X-Store vs Odoo Reconciliation**.
- Default filters answer the two questions actually asked: *Not in Odoo* (`status in parked, missing`) and *Has a Difference* (`difference != 0`).
- A parked row carries the message the importer wrote, e.g. `produk belum teregister di master X101 (…)` or `no X70D tender (sync X70D first)`, so the fix is obvious without reading logs.

**Key models**

- `retail.import.recon` — **`_auto = False` SQL view.** No stored data of its own; every column is derived from `retail_import_line` + `retail_import_log` + `pos_order` at query time.

**Important fields**

- Header: `txn_ref` (`store-register-transaction`, the same reference `pos_order.pos_reference` carries), `store_code`, `store_name`, `trans_date`, `register`, `transnum`, `staff_name`, `member_id`, `transaction_note`.
- Source side: `line_count`, `source_qty`, `source_amount`, `source_tax`.
- Odoo side: `pos_order_id`, `odoo_amount`.
- Outcome: `difference` (source less Odoo), `status`, `reason`, `log_id`.

### custom_storefront_api — Custom Storefront API

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_storefront_api` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (GentleWoman) |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_ecommerce`, `custom_payment_id`, `payment_custom`, `website_sale`, `sale`, `auth_jwt` |
| Models / routes / tests | 5 / 40 / 0 |
| Tags | ecommerce, headless-api, jwt, cors |

> Knowledge file is generator output, not human-reviewed.

**Declared models**: `custom.storefront.content`, `custom.storefront.payment.proof`, `custom.storefront.subscriber`, `custom.storefront.token`, `custom.wishlist`

**Endpoints**: `/storefront/api/<path:rest>`, `/storefront/api/admin/health`, `/storefront/api/admin/orders/<int:order_id>/status`, `/storefront/api/admin/sync/products`, `/storefront/api/affiliate/apply`, `/storefront/api/affiliate/links`, `/storefront/api/affiliate/me`, `/storefront/api/auth/guest`, `/storefront/api/auth/login`, `/storefront/api/auth/logout`, `/storefront/api/auth/refresh`, `/storefront/api/auth/register`, `/storefront/api/cart`, `/storefront/api/cart/address`, `/storefront/api/cart/items`, `/storefront/api/cart/items/<int:line_id>`, `/storefront/api/cart/pickup`, `/storefront/api/cart/shipping`, `/storefront/api/categories`, `/storefront/api/checkout`, `/storefront/api/checkout/<int:order_id>/pay`, `/storefront/api/checkout/<int:order_id>/payment-proof`, `/storefront/api/content`, `/storefront/api/customer/addresses`, `/storefront/api/customer/addresses/<int:address_id>`, `/storefront/api/customer/me`, `/storefront/api/newsletter`, `/storefront/api/orders`, `/storefront/api/orders/<int:order_id>`, `/storefront/api/payment/methods`, `/storefront/api/products`, `/storefront/api/products/<int:product_id>`, `/storefront/api/products/<int:product_id>/availability`, `/storefront/api/shipping/quote`, `/storefront/api/stores`, `/storefront/api/tags`, `/storefront/api/wishlist`, `/storefront/api/wishlist/<int:product_tmpl_id>`, `/storefront/api/wishlist/<int:product_tmpl_id>/move-to-cart`, `/storefront/api/wishlist/move-all-to-cart`

### custom_subscription — Custom Subscriptions

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_subscription` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_ai_bridge`, `sale_management`, `account` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | subscription, recurring, ai, accounting |

> Knowledge file is generator output, not human-reviewed.

Subscription contract lifecycle + recurring billing + MRR/LTV analytics + AI-assisted churn prediction. Closes the CE-side gap against EE `sale_subscription` for SaaS, retainer, and membership use cases.

A `subscription.plan` declares the SKU + billing cadence + price + optional trial; a `subscription.contract` ties a partner to a plan and runs a state machine (`draft` → `active` ↔ `paused` → `churned`/`closed`). A daily cron generates an `account.move` (`out_invoice`) per active contract whose `next_billing_date <= today`. MRR and LTV are stored computed metrics. A churn-prediction button calls `custom.ai._recommend` and stamps the resulting summary + priority on the contract.

**How it works**

- Set up `subscription.plan` records: `recurring_interval` ∈ daily/weekly/monthly/yearly, `recurring_count` (every N intervals), `price`, `currency_id`, `product_id` (billing SKU, `sale_ok=True`), `trial_days`. `code` uniqueness enforced.
- Create a `subscription.contract` (`draft`) linking `partner_id` + `plan_id` + `start_date`; name from sequence `subscription.contract` (fallback `SUB/0001`).
- `action_activate()`: state `draft|paused` → `active`. If `plan.trial_days` and state was `draft`, sets `next_billing_date = start + trial_days`; otherwise advances by `_advance(start, interval, count)` (`timedelta(days)` / `timedelta(weeks)` / `relativedelta(months/years)`).
- `cron_generate_invoices` (`@api.model`): daily search `state='active' AND next_billing_date<=today` → per contract `action_invoice_now()`. Each run creates an `account.move` (`out_invoice`) with one `invoice_line_id` (the plan's `product_id`, qty=1, price_unit=`plan.price`), back-linked via `x_custom_subscription_id`; auto-posts (logs warning on failure); advances `next_billing_date` by `_advance(base, interval, count)`. Posts chatter message.
- Workflow buttons: `action_pause()` → paused; `action_churn()` → churned (lost); `action_close()` → closed (graceful termination).
- AI churn: `action_churn_predict()` builds `_custom_ai_payload()` (contract ref, partner, plan, MRR, LTV, state, last 6 invoices), calls `env['custom.ai']._recommend(model='subscription.contract', res_id=self.id, payload=...)`, parses `summary`/`response`/raw JSON and `priority` ∈ info/warn/critical; writes `ai_churn_summary`, `ai_churn_priority`, posts mt_note. Errors surface as `display_notification` (warning), never block.
- Metrics: `_compute_metrics` derives `mrr` from `plan.price` / `recurring_count` × normalisation factor (daily×30, weekly×30/7, monthly×1, yearly÷12), `lifetime_value = sum(paid/in_payment invoices.amount_total)`, `invoice_count = len(invoice_ids)`. `_compute_last_invoice` picks most recent by `invoice_date`.

**Key models**

- `subscription.plan` — plan SKU + cadence + price. Sequence-style `code` (unique).
- `subscription.contract` — partner × plan instance. Inherits `mail.thread` + `mail.activity.mixin`.
- `account.move` (inherited) — adds back-ref `x_custom_subscription_id` (indexed M2o).

**Important fields**

- `subscription.plan.recurring_interval` (Selection daily/weekly/monthly/yearly) — drives `_advance()` and MRR normalisation.
- `subscription.plan.recurring_count` (Integer, default 1, ≥1) — "every N intervals"; divisor in MRR formula.
- `subscription.plan.price` (Monetary, required) — flat price per billing event.
- `subscription.plan.product_id` (M2o `product.product`, required, `sale_ok=True`) — invoice line product.
- `subscription.plan.trial_days` (Integer, default 0) — only applied once at first activation.
- `subscription.contract.state` (Selection draft/active/paused/churned/closed) — `active` is the only state that bills; `churned` and `closed` are terminal.
- `subscription.contract.next_billing_date` (Date, tracking) — cron query key; advanced after each invoice.
- `subscription.contract.mrr` (Monetary, computed, stored) — only non-zero when `state=='active'`.
- `subscription.contract.lifetime_value` (Monetary, computed, stored) — sum of `amount_total` for invoices in `payment_state in ('paid','in_payment')`.
- `subscription.contract.invoice_count` (Integer, computed, stored).
- `subscription.contract.ai_churn_summary` (Text) / `ai_churn_priority` (Selection info/warn/critical) — populated by `action_churn_predict()`.
- `subscription.contract.payment_term_id` (M2o `account.payment.term`) — copied onto generated invoices.
- `account.move.x_custom_subscription_id` (M2o, indexed) — back-ref for `invoice_ids` O2m.

## Services, Projects & Rental (Layanan, Proyek & Sewa)

### custom_arka_show_date — ARKA Show Date

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_arka_show_date` |
| Version | 19.0.1.5.0 |
| Scope | Khusus brand (ARKA-AIM) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `sale_management`, `account`, `custom_core`, `custom_accounting_reports` |
| Models / routes / tests | 1 / 0 / 1 |

> Knowledge file is generator output, not human-reviewed.

Adds a **Show Date** to the sale → invoice flow for opt-in companies (PT ARKA)
and anchors customer-invoice payment-term due dates to the show date instead of
the invoice date. Gated by a `res.company` boolean flag so it is safe on a
multi-company tenant DB (e.g. AIM + ARKA): only the flagged company is affected.

**How it works**

- An operator ticks `res.company.x_custom_show_date_enabled` on the PT ARKA company (Settings → Companies → PT ARKA → "Show Date" page).
- On a quotation, `x_custom_show_date` becomes required — but only when the order's company has the flag on (enforced server-side at confirm).
- On confirmation the date stays on the Sales Order (`copy=True`).
- `sale.order._prepare_invoice()` copies `x_custom_show_date` onto the customer invoice (`account.move`, `out_invoice`).
- `account.move._compute_needed_terms` is overridden: for an `out_invoice` of a flagged company with a show date set, it re-runs the core compute on the move with context `arka_show_date_ref=<show_date>`.
- `account.payment.term._compute_terms` reads that context key and substitutes it for `date_ref`, so every `date_maturity` and the early-payment `discount_date` are anchored to the show date. Non-flagged companies are untouched (pure pass-through).

**Key models**

- `res.company` (inherited) — `x_custom_show_date_enabled` (Boolean gate flag).
- `sale.order` (inherited) — `x_custom_show_date` (Date), `x_custom_show_date_required` (computed view-driver). Overrides `_confirmation_error_message`, `_prepare_invoice`.
- `account.move` (inherited) — `x_custom_show_date` (Date). Overrides `_compute_needed_terms`.
- `account.payment.term` (inherited) — overrides `_compute_terms`.

**Important fields**

- `res.company.x_custom_show_date_enabled` (Boolean, default False) — gate.
- `sale.order.x_custom_show_date` (Date, copy=True, tracking=True).
- `sale.order.x_custom_show_date_required` (Boolean, computed, non-stored) — related to `company_id.x_custom_show_date_enabled`; drives view required/invisible attrs.
- `account.move.x_custom_show_date` (Date, copy=False).

### custom_bast — Custom BAST

|  |  |
| --- | --- |
| Path | `addons/core/custom_bast` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `mail`, `stock`, `sale` |
| Models / routes / tests | 3 / 0 / 1 |
| Tags | audit-trail, field-service, wms |

> Knowledge file is generator output, not human-reviewed.

Reusable abstraction for **Berita Acara Serah Terima** (Indonesian-style handover documents). Provides a generic two-party handover record with optional reference to any source document (sale order, transfer, rental order, work order, etc.), dual signatures with timestamps + signer names, optional GPS coordinates, optional witness, itemized lines with per-line condition + photo + optional product/lot, an audit-logged state machine, and a QWeb PDF report. Designed to be the canonical BAST building block for rental, field service, delivery, manufacturing, and any vertical that needs signed handover artifacts.

**How it works**

- A user creates a `custom.bast.document` (state `draft`), picks `kind` (pickup/return/delivery/installation/handover), parties (`party_from_id`, `party_to_id`), optional `reference` (Reference field to `stock.picking`/`sale.order`/`purchase.order`/`fsm.work.order`/`rental.order` — filtered by `_get_referenceable_models()` to models present in env). Sequence `custom.bast.document` assigns `name`.
- User adds `custom.bast.line` rows: item_description, qty, uom, optional product/lot, `condition` (good/damaged/partial), optional photo + note.
- `action_open_sign_wizard()` opens `custom.bast.sign.wizard` — user picks `party` (from/to), draws/uploads `signature` (Binary), optionally fills `signed_by` + `gps_latitude`/`gps_longitude`. Wizard calls `action_sign_from()` or `action_sign_to()` on the document.
- `action_sign_from`/`action_sign_to` raise `UserError` if state ∈ {completed, voided}, else write signature + `_signed_at = now()` + `_signed_by = signed_by or env.user.name`, optionally GPS, then call `_recompute_state()` which transitions: both signed → `completed`; one signed → `signed_one_side`; none → `draft`.
- `action_void(reason)` writes state=`voided`; from `completed` requires group `custom_bast.group_bast_manager`. Posts `Voided: <reason>` to chatter if reason given.
- `_check_parties_distinct` constraint blocks `party_from_id == party_to_id`.
- QWeb PDF report renders the BAST as the printable artifact.

**Key models**

- `custom.bast.document` — The handover record. Inherits `pdp.audited.mixin`, `mail.thread`, `mail.activity.mixin`. Holds parties, kind, location (M2o stock.location OR free-text), dual signatures, state, optional GPS, optional witness, optional source reference.
- `custom.bast.line` — Itemized line per BAST; condition + photo + optional product/lot.
- `custom.bast.sign.wizard` — TransientModel; signature capture UI dispatching to `action_sign_from`/`action_sign_to`.

**Important fields**

- `custom.bast.document.name` (Char, unique, sequence-driven default `"New"`) — BAST number from `custom.bast.document` ir.sequence.
- `custom.bast.document.kind` (Selection pickup/return/delivery/installation/handover, default handover, tracking) — drives report headers and downstream filtering.
- `custom.bast.document.reference` (Reference, dynamic via `_selection_reference_models`) — link to source business document. Selection list auto-filtered to models present in env (so installing without `rental` doesn't break it).
- `custom.bast.document.state` (Selection draft/signed_one_side/completed/voided, indexed, tracking) — computed by `_recompute_state` from signature presence; only manual transition is `action_void`.
- `custom.bast.document.party_from_id` / `party_to_id` (M2o res.partner, required, tracking) — `_check_parties_distinct` enforces ≠.
- `custom.bast.document.party_from_signature` / `party_to_signature` (Binary, attachment=True) — actual signature image.
- `custom.bast.document.party_from_signed_at` / `party_to_signed_at` (Datetime, readonly) — stamped automatically by sign actions.
- `custom.bast.document.party_from_signed_by` / `party_to_signed_by` (Char) — captured name string; defaults to `env.user.name` if not supplied.
- `custom.bast.document.witness_id` (M2o res.users) — optional internal witness.
- `custom.bast.document.gps_latitude` / `gps_longitude` (Float, 10,7) — captured by mobile signer.
- `custom.bast.document.date_handover` (Datetime, required, default now, tracking) — official handover moment.
- `custom.bast.document.location_id` (M2o stock.location) + `location_text` (Char) — structured OR free-text location.
- `custom.bast.line.condition` (Selection good/damaged/partial, default good) — per-line condition assessment.
- `custom.bast.line.photo` (Binary, attachment=True) — per-line evidence photo.
- `custom.bast.line.lot_id` (M2o stock.lot) — optional serial/lot binding.

### custom_field_service — Custom Field Service

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_field_service` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `mail`, `stock`, `product` |
| Models / routes / tests | 5 / 0 / 0 |
| Tags | field-service, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

Lightweight **field service management (FSM)** module. Work orders are pinned to a customer site, dispatched to a technician with required-skill validation, walked through scheduled → in_progress → on_hold → done, materials consumed are line-itemed, and a customer signature is captured at completion. Sites are PDP-classified as `pii` (address tied to partner); all state transitions write `pdp.audit_log`.

**How it works**

- Admin sets up `fsm.skill` records (code-unique) and `fsm.technician` records linking `user_id` / `employee_id` with `skill_ids`.
- Customer service creates `fsm.site` records under a `res.partner` capturing address, lat/long, and `access_notes` (gate codes, parking).
- Dispatcher creates `fsm.work.order`: `site_id` + `technician_id` (required) + `scheduled_start` + `scheduled_end` + `required_skill_ids`. `name` from `ir.sequence(fsm.work.order)`. Constraint `_check_schedule` ensures `end > start`. `_check_skills` validates `required_skill_ids ⊆ technician.skill_ids` — raises `UserError` on missing skills.
- Workflow: `action_schedule` (draft→scheduled) → `action_start` (scheduled/on_hold → in_progress, stamp `started_at`) → optional `action_hold` (in_progress→on_hold) → `action_complete` (in_progress/on_hold → done, stamp `completed_at`, compute `duration_hours`).
- During execution, technician adds `fsm.work.order.material` lines: product + quantity + unit_cost; `uom_id` defaults from product, `subtotal = quantity * unit_cost` (Monetary, currency from work-order company).
- At completion, `action_capture_signature(signature_b64, signed_by)` writes the binary signature, `signed_by_name`, `signed_at`, plus a PDP audit log entry.
- `action_cancel` from any state except `done`.
- `fsm.site.work_order_count` and `fsm.technician.open_wo_count` are computed (search-counts; `sudo()`).

**Key models**

- `fsm.site` — Customer site / location (PDP classification `pii`).
- `fsm.technician` — Worker with skill set; optional `user_id` + `employee_id` link.
- `fsm.skill` — Reusable skill tag (code-unique).
- `fsm.work.order` — Dispatched job; full workflow with audit + signature.
- `fsm.work.order.material` — Per-WO material consumption line.

**Important fields**

- `fsm.site.partner_id` (M2o `res.partner`, required, ondelete cascade) — PDP-classified PII anchor.
- `fsm.site.latitude` / `longitude` (Float, digits 10/7) — geocoded coordinates.
- `fsm.site.access_notes` (Text) — gate codes, parking, on-site contact.
- `fsm.technician.skill_ids` (M2m `fsm.skill`) — drives skill validation on WO.
- `fsm.skill.code` (Char, required, unique constraint) — stable external key.
- `fsm.work.order.state` (draft/scheduled/in_progress/on_hold/done/cancelled).
- `fsm.work.order.scheduled_start` / `scheduled_end` (Datetime, required, tracking) — `_check_schedule` constraint.
- `fsm.work.order.started_at` / `completed_at` (Datetime, readonly) — stamped on transitions.
- `fsm.work.order.duration_hours` (Float, computed/stored) — `(completed_at - started_at) / 3600`.
- `fsm.work.order.required_skill_ids` (M2m `fsm.skill`) — `_check_skills` constraint vs technician.
- `fsm.work.order.customer_signature` (Binary) + `signed_at` + `signed_by_name`.
- `fsm.work.order.material_ids` (O2m) → `fsm.work.order.material.subtotal` (Monetary, computed/stored).

### custom_helpdesk — Custom Helpdesk

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_helpdesk` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_ai_bridge`, `custom_pdp_audit`, `mail`, `project` |
| Models / routes / tests | 4 / 0 / 0 |
| Tags | helpdesk, ai, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

CE-targeted re-implementation of Odoo EE Helpdesk: a `helpdesk.ticket` model with state/priority/SLA/tags, `helpdesk.team` with mail-alias intake (email-to-ticket), `helpdesk.sla` policies that drive a computed deadline + warn/breach status, an AI suggested-response action via `custom_ai_bridge`, and PDP audit logging on every state transition.

This module owns the platform's canonical helpdesk ticketing model — other modules (e.g. `custom_livechat`, future field-service) escalate to `helpdesk.ticket` here.

**How it works**

- A `helpdesk.team` is created and inherits `mail.alias.mixin`; `_alias_get_creation_values()` routes any inbound email at the team alias into a new `helpdesk.ticket` with `team_id` + default priority pre-filled.
- A ticket is created either via mail alias, manually, or by `discuss.channel.action_escalate_to_helpdesk` (custom_livechat). The sequence `helpdesk.ticket` assigns `name`; if `team_id.default_priority` is set and `priority` is not passed, that becomes the default.
- `_compute_sla` picks the SLA in this order: (1) team's `sla_id` if priority matches, (2) any active `helpdesk.sla` matching priority. `_compute_sla_deadline = create_date + time_resolve_hours`.
- `_compute_sla_status` (depends on `sla_deadline / state / resolved_date`) flags `done` when state ∈ {resolved, closed}, else `breach` if past deadline, `warn` if < 1h to deadline, else `ok`.
- The hourly cron `cron_check_sla` recomputes SLA status for all non-resolved tickets.
- State transitions: `action_set_open / action_set_pending / action_set_resolved / action_set_closed`. On entering `resolved`/`closed`, `resolved_date` is auto-stamped. Every `state` change writes a raw `pdp.audit_log` row.
- `action_ai_suggest_response()` calls `custom.ai._recommend` with subject+description+priority+tags, writes `ai_suggested_text` and posts to chatter. Errors degrade to a non-blocking notification.

**Key models**

- `helpdesk.ticket` — Core record; `mail.thread + mail.activity.mixin`, state/priority/SLA/AI fields.
- `helpdesk.team` — Inherits `mail.alias.mixin`; alias dispatches to `helpdesk.ticket`.
- `helpdesk.sla` — Policy: priority + response/resolution hour budgets.
- `helpdesk.tag` — Simple tag taxonomy (unique name).

**Important fields**

- `helpdesk.ticket.state` (Selection: new/open/pending/resolved/closed) — drives SLA done logic + audit.
- `helpdesk.ticket.priority` (Selection 0..3) — drives SLA matching.
- `helpdesk.ticket.team_id` / `assignee_id` / `partner_id` — routing fields.
- `helpdesk.ticket.sla_id` / `sla_deadline` / `sla_status` (computed, stored) — SLA enforcement state machine.
- `helpdesk.ticket.ai_suggested_text` (Text) — last AI suggestion.
- `helpdesk.ticket.resolved_date` (Datetime, auto-stamped on entering resolved/closed).
- `helpdesk.team.default_priority` / `sla_id` — team defaults applied to new tickets.
- `helpdesk.sla.time_response_hours` (default 4.0) / `time_resolve_hours` (default 24.0) — hour budgets from `create_date`.

### custom_ops_reports — Custom Operational Reports

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_ops_reports` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM) |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_accounting_reports`, `custom_accounting_asset`, `custom_rental`, `custom_maintenance`, `custom_repairs`, `custom_bast`, `stock` |
| Models / routes / tests | 10 / 0 / 0 |

> Knowledge file is generator output, not human-reviewed.

Five operational reports for the AIM Inventory / warehouse team covering the
drone fleet: asset opname, per-event movement, spare parts, maintenance health
and repair history. They answer the AIM half of the ARKA report-requirements
sheet (items 15–19); the finance half is served by `custom_accounting_reports`.

This module contributes **reports only** — it defines no business data. Every
model is an AbstractModel over data owned by other modules.

**How it works**

- A user opens *Operational Reports → <report>* and fills the wizard (period and/or company; the opname report also filters by asset group / location / state).
- **View** opens the shared OWL table client action; **Export Excel** streams an XLSX. There is deliberately no PDF (see Gotchas).
- Both paths run the same `_xlsx_columns()` + `_build_lines(filters)` contract on the report model, exactly like every report in `custom_accounting_reports`.

**Key models**

- `custom.report.asset.opname` (`asset_opname`) — #15. One row per `custom.fixed.asset` (the AIM drone register), enriched with an operational state from `rental.asset` and a condition from the latest `custom.bast.line`. Snapshot: it ignores the period.
- `custom.report.event.movement` (`event_movement`) — #16. One row per `stock.move` on a rental order's pickup (OUT) / return (IN) picking, grouped by event with a per-event quantity subtotal. `stock.move.is_loan` separates loan/cadangan tools from rented units.
- `custom.report.spareparts` (`spareparts`) — #17. One row per spare-part product, pairing a `stock.quant` availability snapshot with in-period usage.
- `custom.report.maintenance.health` (`maintenance_health`) — #18. Aggregates `maintenance.request` per equipment and **reads** the reliability metrics already computed on `maintenance.equipment` (MTBF / MTTR / failures).
- `custom.report.repair.history` (`repair_history`) — #19. One row per `repair.order` created in the period, with SLA, rework flag and costs.

**Important fields**

- `custom.fixed.asset.serial_number` — added by the **tenant** module `custom_arka_aim_asset_register`, not by the generic asset app; it is the only join key back to rental/BAST records. This module does **not** depend on that tenant module, so the field may be absent — `_has_serial()` guards every read and the enrichment degrades to blank.
- `stock.move.is_loan` — added by `custom_rental`; drives the Rental vs Tool/Loan column.
- `maintenance.request.x_spare_part_ids` — many2many with **no per-part quantity**, hence "Used" is a count of requests, not a consumed qty.
- `maintenance.equipment.x_mtbf_hours` / `x_mttr_hours` / `x_total_failures` / `x_last_failure_at` — read, never recomputed here.
- `repair.order.x_sla_status` / `x_returned` / `x_labor_cost` / `x_material_cost` / `x_total_repair_cost` — all from `custom_repairs`.

### custom_project_api — Custom Project - VAS PMO REST API

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_project_api` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (VAS PMO) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_project_portfolio`, `custom_project_cr`, `custom_project_notify`, `auth_jwt` |
| Models / routes / tests | 1 / 31 / 1 |

The JWT + HMAC REST surface the headless Next.js app (`vas-pmo/`, port 18110) runs on.
Shaped like `custom_storefront_api` so the two front-ends are operated the same way.

**Declared models**: `custom.vaspmo.token`

**Endpoints**: `/vaspmo/api/<path:subpath>`, `/vaspmo/api/admin/notify-rules`, `/vaspmo/api/admin/notify-rules/<int:rule_id>`, `/vaspmo/api/admin/stages`, `/vaspmo/api/admin/stages/<int:stage_id>`, `/vaspmo/api/admin/users`, `/vaspmo/api/admin/verticals`, `/vaspmo/api/admin/verticals/<int:vertical_id>`, `/vaspmo/api/auth/login`, `/vaspmo/api/auth/logout`, `/vaspmo/api/auth/me`, `/vaspmo/api/auth/refresh`, `/vaspmo/api/change-requests`, `/vaspmo/api/change-requests/<int:cr_id>/action`, `/vaspmo/api/dashboard/ba-summary`, `/vaspmo/api/dashboard/summary`, `/vaspmo/api/health`, `/vaspmo/api/hmac/notify-result`, `/vaspmo/api/hmac/ping`, `/vaspmo/api/hmac/tasks/<int:task_id>/verify`, `/vaspmo/api/logs`, `/vaspmo/api/meta/stages`, `/vaspmo/api/meta/verticals`, `/vaspmo/api/projects`, `/vaspmo/api/search`, `/vaspmo/api/tasks`, `/vaspmo/api/tasks/<int:task_id>`, `/vaspmo/api/tasks/<int:task_id>/comment`, `/vaspmo/api/tasks/<int:task_id>/stage`, `/vaspmo/api/weekly`, `/vaspmo/api/weekly/<int:weekly_id>`

### custom_project_cr — Custom Project - Change Requests (VAS)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_project_cr` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (VAS PMO) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_project_portfolio` |
| Models / routes / tests | 2 / 0 / 1 |

Change Request as its own record type, not `task_type = change_request`. Three things a
task does not have and which would otherwise sit empty on every task in the system: a
tiered approval gate, an impact analysis, and a response SLA counted from when the brand
asked.

**Key models**

- `custom.change.request` — `code` auto `CR-YYYY-NNNN` from `ir.sequence`, mandatory `vertical_id`, optional `project_id`, impact analysis fields, `approval_state`, shares `stage_id` (`project.task.type`) with tasks.
- `custom.change.request.approval` — one row per tier, kept as records so the decision trail survives. Tier N cannot approve before tier N-1.
- `project.task` (extended) — `change_request_id`, `custom_cr_code` (stored related).

**Important fields**

- `impact` — `high` / `critical` pulls in a third approver (the vertical owner); `_required_tiers()` is where that rule lives.
- `sla_response_due` — computed from `request_date` + working days per priority (`RESPONSE_SLA_DAYS`), using the portfolio module's working-day helper.
- `sla_response_met` — stamped once, at first response. Not recomputed later.

### custom_project_notify — Custom Project - VAS Notifications (WA + Email + Odoo)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_project_notify` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (VAS PMO) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_project_portfolio`, `custom_project_cr` |
| Models / routes / tests | 8 / 0 / 1 |

Rule-driven notifications for project / CR / task / weekly events. The event is born in
Odoo and dispatched to the Next.js BFF over HMAC, which renders and sends WhatsApp +
e-mail.

**Key models**

- `custom.project.notify.rule` — event × recipient kind × channels. 40 rows seeded `noupdate="1"` so an upgrade never overwrites what the PO Lead tuned.
- `custom.project.notify.outbox` — the queue; `payload_json` is what the BFF receives.
- `custom.project.notify.log` — one row per channel per recipient. Phone numbers are masked (`mask_phone`) because this log is read by many people.
- `vaspmo.notify.source` (AbstractModel) — the shared behaviour; concrete models only answer "who is the assignee / PO / brand PIC for me".

**Important fields**

- `rule.recipient_kind` — assignee / reporter / ba / po / portfolio_owner / vertical_owner / **brand_pic** / group. `brand_pic` resolves to `custom.project.vertical.pic_partner_ids` — people outside the team.
- `log.skipped_reason` — set when a channel was never attempted (no number, no address). "Nobody was reachable" is recorded as a finding rather than swallowed.

### custom_project_portfolio — Custom Project - VAS Portfolio, Verticals & SLA Clock

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_project_portfolio` |
| Version | 19.0.1.1.0 |
| Scope | Umum, dikonfigurasi (VAS PMO) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_core`, `custom_pdp_audit`, `project`, `hr_timesheet`, `mail` |
| Models / routes / tests | 7 / 0 / 2 |

Delta over CE `project` for the Erajaya Product Owner — Value-Added Services team: brand
verticals, portfolios, weekly sprints, weekly progress reports, and the per-stage **SLA
clock** that makes Hold and Waiting-User-Verification behave differently from a label.

**How it works**

- Master data: `custom.project.vertical` (brand) and `custom.project.portfolio`. Verticals seed LEVIS / GTW / ERASPACE / ARKAAIM / JDS / CORP active, ERAFONE / URBAN archived. `legal_entity` is filled only where confirmed (Levi's = Era Busana Retailindo, Erajaya Swasembada); blanks are deliberate, not missing data.
- A project belongs to one vertical and one portfolio. Tasks inherit the vertical from their parent (change request first, then project) and may only override it with a reason.
- Stage transitions book the time just spent into one of three buckets. `project.task.type` carries `custom_sla_clock`: `running` (team), `paused` (Hold — deducted from cycle time), `user_side` (waiting on the brand — booked to the user), `stopped` (closed).
- Hold demands a reason, remembers where it came from (`custom_prev_stage_id`), and is flagged once when it outlives `custom_hold_until`.
- Waiting User Verification sets `custom_verification_due` (working days), nudges the brand PIC at H+2 and H+5, then auto-closes with `custom_auto_closed=True`.
- `custom.project.sprint` is one ISO week; a cron closes Friday, opens the next week, and carries unfinished work forward. `custom.weekly.progress` drafts itself Friday 15:00 with the factual half already filled; the BA writes the blocker and next week.

**Key models**

- `custom.project.vertical` — brand axis. `pic_partner_ids` is who gets asked to verify.
- `custom.project.portfolio` — health is the worst of its projects, computed and stored.
- `project.task.type` (extended) — the stage config the plan called `custom.project.stage.config`. Implemented as an extension so Odoo keeps owning one stage engine and one kanban.
- `custom.project.sprint` — weekly, `week_code` like `2026-W31`.
- `custom.weekly.progress` — one row per (sprint × project), unique-constrained.
- `project.project` / `project.task` (extended) — vertical, health, hold, verification, cycle-time fields.

**Important fields**

- `project.task.custom_cycle_time_team` — elapsed minus hold minus user-wait.
- `project.task.custom_lead_time_total` — plain elapsed. Reported next to the above; the gap between them *is* the time the team did not own.
- `project.task.custom_hold_duration_hours` / `custom_user_wait_hours` — accumulated on each transition by `_vaspmo_book_elapsed`.
- `project.task.custom_stage_entered_at` — basis for that accumulation.
- `project.task.custom_is_blocked` — derived from Odoo's native `depend_on_ids`; this module deliberately adds no second blocker field.

### custom_rental — Custom Rental

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_rental` |
| Version | 19.0.0.3.1 |
| Scope | Umum, dikonfigurasi (ARKA-AIM) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_bast`, `mail`, `portal`, `product`, `stock`, `account` |
| Models / routes / tests | 5 / 4 / 3 |
| Tags | rental, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.3.0, module is now 19.0.0.3.1.

This module manages the lifecycle of asset rentals: rentable products with per-period pricing tiers, a calendar-friendly schedule, BAST handover documents, late-fee accrual, an internal asset-loan flow, and customer portal access with signature capture. Fees (rental fee, late penalty, cumulative late-fee total, total due) are only **computed and displayed** — the module creates **no** `account.move` / invoice. The `account` dependency is declared in the manifest but no accounting/invoicing logic exists here.

**How it works**

- **Order creation:**
- A `rental.order` is created selecting either an `asset_id` (single-serial mode, requires `qty=1`) or a `product_id` (bulk-by-qty mode) — exactly one, enforced by `_check_rental_mode`.
- Details include `pickup_dt`, `return_dt_expected`, `qty`, optional `loan_qty` (spare/loan units, not billed), `daily_rate`, and `late_fee_rate`.
- **Order confirmation (`action_confirm`):**
- State moves `draft` → `confirmed`.
- An outgoing `stock.picking` is created via `_create_stock_picking("outgoing")` when stock integration is enabled (config param `custom_rental.config_stock_integration`, default True). In internal-loan mode this is an internal Stock → On-Loan transfer instead.
- **Pickup (`action_pickup`):**
- State `confirmed` → `picked_up`; the linked `rental.asset` is set to `on_rent`.
- A pickup BAST may be generated (`action_generate_bast_pickup`).
- **Return (`action_return`):**
- State `picked_up` → `returned`; `return_dt_actual` stamped; asset set back to `available`.
- An incoming picking is created; a return BAST may be generated.
- `action_validate_loan_return` verifies loan quantity came back in full and (for serial products) that the exact dispatched serials returned.
- **Late-fee accrual:**
- `_cron_accrue_late_fees()` exists to accrue one `custom.rental.late.fee.line` per day per overdue `picked_up` order and grow `late_fee_total`.
- **IMPORTANT:** No `ir.cron` record is shipped. `data/cron_data.xml` is an empty placeholder ("original data file missing... generated by demo-bootstrap to allow module install"). As shipped, nothing runs this method daily — only the test suite invokes it.
- **Customer portal:**
- Customers view rentals via the portal and can capture a signature (`action_capture_signature`).

**Key models**

- `rental.order` — Top-level rental agreement. `_inherit`s `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`. Holds partner, asset/product, quantities, dates, computed fees, BAST links, picking links, signature, and internal-loan config.
- `rental.asset` (`_name="rental.asset"`, inherits `mail.thread`, `mail.activity.mixin`) — Serial-tracked rentable unit. State machine `available` / `on_rent` / `maintenance` / `retired`. Fields: `name`, `code` (unique), `product_id`, `serial_number`, `daily_rate`, `deposit_amount`. Central to serial-mode rentals; `create()` on the order copies `daily_rate`/`deposit_amount` from the asset.
- `custom.rental.pricing` — Per-period pricing tier attached to `product.template` (`product_template_id`). Fields: `duration` (Integer), `unit` (Selection hour/day/week/month), `price` (Monetary), `currency_id`, `active`, computed `name`. Multiple tiers co-exist; quoting picks the cheapest combination.
- `custom.rental.schedule` — Read-only SQL view (`_auto=False`), one row per rental.order, for calendar/kanban/list. Fields: `name`, `order_id`, `line_id`, `product_id`, `asset_id`, `partner_id`, `date_start` (=`pickup_dt`), `date_stop` (=`return_dt_expected`), `state`.
- `custom.rental.late.fee.line` — Audit row, one per day per overdue order (unique `(order_id, accrued_on)`). Fields: `accrued_on`, `days_overdue`, `rate`, `base_amount`, `fee_amount`, `currency_id`, `note`.

**Important fields**

- `rental.order.state` (Selection: `draft` / `confirmed` / `picked_up` / `returned` / `cancelled`): lifecycle state.
- `rental.order.daily_rate` (Monetary), `late_fee_rate` (Float, % per day, default from config param `custom_rental.default_late_fee_rate` = 10.0).
- `rental.order.is_internal_loan` (Boolean) + `on_loan_location_id` (Many2one stock.location, internal): internal-loan mode moves the unit Stock ↔ On-Loan with no COGS/valuation impact. Enabling `is_internal_loan` requires `on_loan_location_id` (constraint `_check_rental_mode`).
- `rental.order.loan_qty` (Integer): spare/loan units shipped alongside; excluded from billing; must return in full.
- `custom.rental.pricing.duration` (Integer): a count expressed in the sibling `unit` field, NOT hours. `_hours()` converts it via `UNIT_TO_HOURS[unit]` (hour=1, day=24, week=168, month=720).
- `custom.rental.schedule.state`: computed in SQL — a `picked_up` order past its expected return is reported as `late`, a state that exists only on the schedule view and not on `rental.order.state`.

**Endpoints**: `/my/rentals`, `/my/rentals/<int:order_id>`, `/my/rentals/<int:order_id>/sign`, `/my/rentals/page/<int:page>`

### custom_rental_bom_explosion — Custom Rental — BOM Explosion

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_rental_bom_explosion` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM) |
| Maturity / confidence | Beta / Rendah |
| Depends | `custom_rental`, `custom_bast`, `mrp` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | rental, bom, audit-trail |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Bundling drone + perangkat via BOM kit, otomatis populate BAST lines saat pickup/return rental Extends ``custom_rental`` so that a rental.asset (or its product.product) with a ``mrp.bom`` of type ``phantom`` (kit) gets its components auto-exploded into the BAST document lines on pickup / return.

### custom_rental_invoicing — Custom Rental — Invoicing

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_rental_invoicing` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM) |
| Maturity / confidence | Beta / Rendah |
| Depends | `custom_rental`, `account` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | rental, invoicing, audit-trail |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Generate account.move (customer invoice) saat rental return — rental fee + late fee + damages Extends ``custom_rental`` with proper invoice posting.

### custom_rental_quality_hook — Custom Rental — Quality & Maintenance Hook

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_rental_quality_hook` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (ARKA-AIM) |
| Maturity / confidence | Beta / Rendah |
| Depends | `custom_rental`, `custom_quality_full`, `custom_maintenance` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | rental, quality, maintenance, audit-trail |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Auto-create quality.check pada rental return; link rental.asset ↔ maintenance.equipment Wires three previously-disconnected modules together:

### custom_sale_bast — Custom Sale — BAST Bridge

|  |  |
| --- | --- |
| Path | `addons/core/custom_sale_bast` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `sale`, `custom_bast` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | audit-trail, sales |

> Knowledge file is generator output, not human-reviewed.

Thin bridge between standard Sales and `custom_bast`. Lets users generate and open a BAST (Berita Acara Serah Terima — handover document) directly from a Sales Order: a **BAST** smart button shows the count of linked handover documents, and a **Generate BAST** header button creates a `delivery` BAST pre-filled from the order. Carries no models of its own beyond a `sale.order` inheritance; all BAST data lives in `custom_bast`.

**How it works**

- On a Sales Order form, `bast_count` (computed) renders a smart button counting `custom.bast.document` rows whose `reference` equals `"sale.order,<id>"` (`_bast_reference()`).
- **Generate BAST** (`action_generate_bast`): validates `custom_bast` is installed and a customer is set, then `sudo`-creates a `custom.bast.document` with `kind="delivery"`, `party_from_id = company partner` (hands the goods over), `party_to_id = customer`, `company_id`, `reference = "sale.order,<id>"`, and one BAST line per **real** order line (sections / notes — `display_type` set — are skipped). The document `name` is assigned by `custom_bast`'s ir.sequence, not set here. Returns a form action opening the new document.
- **View BAST** (`action_view_bast`): opens the `list,form` of `custom.bast.document` filtered by `_bast_domain()` (`reference = "sale.order,<id>"`), with `default_*` context so a doc created from that view is pre-linked back to the order.

**Key models**

- `sale.order` (inherited) — adds the `bast_count` computed field and the `action_generate_bast` / `action_view_bast` buttons plus helpers. No new model is defined.

**Important fields**

- `sale.order.bast_count` (Integer, compute=`_compute_bast_count`, non-stored) — count of linked `custom.bast.document` records; `0` for unsaved orders.

### custom_timesheet — Custom Timesheet

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_timesheet` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_approval_engine`, `custom_ai_bridge`, `hr_timesheet`, `project`, `account`, `sale_management`, `sale_timesheet`, `hr_work_entry`, `custom_hr_payroll_id`, `mail` |
| Models / routes / tests | 4 / 0 / 2 |
| Tags | timesheet, approval-workflow, payroll, ai, accounting |

> Knowledge file is generator output, not human-reviewed.

EE-equivalent extensions on top of CE `hr_timesheet` + `project` + `sale_timesheet`: per-line billable flag with per-line billing rate, draft→submitted→validated workflow gated by `custom_approval_engine`, overtime hours computation (anything above 8h/day), OT-to-payroll bridge via `hr.work.entry`, customer-invoice wizard that bulk-creates a draft `account.move` from selected validated billable lines, and an AI weekly summary per project (`custom.timesheet.weekly.summary`) bridged to `custom.ai`.

**How it works**

- Employee logs hours by creating `account.analytic.line` (CE timesheet entry) with `unit_amount` (hours), `project_id`, `task_id`. New fields default: `x_billable=False`, `x_validation_state='draft'`.
- `_compute_overtime_hours` derives `x_overtime_hours = max(0, unit_amount - 8.0)` (constant `STANDARD_DAILY_HOURS=8.0`).
- Validation workflow on the line:
- `action_submit_validation()` — draft → submitted; calls `_approval_request_or_proceed()` from `approval.mixin`. When a matrix matches it auto-creates + submits the approval (line stays `submitted`, Waiting Approval); when none matches the helper returns True → auto-validates → `validated`.
- `action_validate()` — gates via `_approval_check_required()` (engine-side); on pass → `validated`. The engine calls this automatically (`_approval_on_granted`) once all tiers approve.
- `action_reset_to_draft()` — back to draft; **blocks if `x_billed_invoice_line_id` is set** (already invoiced).
- OT → payroll: `action_create_overtime_work_entry()` on a validated line with `x_overtime_hours > 0`:
- Ensures `hr.work.entry.type` code='OT' exists (creates `display_code='OT'` too).
- Cancels previous work entry if re-run (idempotent).
- Creates `hr.work.entry` (`state='draft'`, `duration=x_overtime_hours`, `date_start = date 17:00`, `date_stop = date_start + OT hours`).
- Stores back-link on `x_overtime_work_entry_id`; optional `x_source_timesheet_id` on work entry if field exists.
- Billable invoicing: user opens `sale.order` form; `x_billable_timesheet_pending_count` is computed by counting analytic lines with `x_billable=True`, `x_validation_state='validated'`, no `x_billed_invoice_line_id`, on the SO's order_line.
- `action_open_invoice_timesheet_wizard()` launches `custom.timesheet.invoice.wizard` (Transient): user picks date range; `_onchange_filters` populates `line_ids` from domain (billable, validated, not billed, in range, matching `so_line` or partner). User toggles `selected` per line and clicks `action_create_invoice()`:
- Builds invoice line vals using `billing_rate || aal.x_billing_rate` as `price_unit`, `unit_amount` as `quantity`.
- Resolves `product_id` from `aal.so_line.product_id` if present.
- Creates an `account.move` (`move_type='out_invoice'`, draft) and links each analytic line's `x_billed_invoice_line_id` to its invoice line.
- AI weekly summary: HR/PM creates a `custom.timesheet.weekly.summary` per (project, week_start) — unique constraint. `_compute_aggregates` populates `total_hours`, `billable_hours`, `overtime_hours`, `line_count` from analytic lines in `[week_start, week_end]`. `action_ai_summarize()` collects payload (project metadata + up to 200 line `_custom_ai_payload()` dicts) and calls `custom.ai._recommend(model, res_id, payload)`; the response's `summary`/`response`/`text` is stored in `summary_html` and chatter-posted. State → `summarized`.
- `unlink` on analytic line cancels the linked OT work entry first.

**Key models**

- `account.analytic.line` (inherited) — Adds billable flag, billing rate/currency, OT hours, billed-invoice link, OT work entry link, validation state. Mixes in `mail.thread` + `approval.mixin`.
- `custom.timesheet.weekly.summary` — Per (project, week) AI summary row; unique `(project_id, week_start, company_id)`.
- `custom.timesheet.invoice.wizard` (Transient) + `custom.timesheet.invoice.wizard.line` (Transient).
- `sale.order` (inherited) — Adds `x_billable_timesheet_pending_count` and the invoice-wizard launcher action.

**Important fields**

- `account.analytic.line.x_billable` (Boolean, default False, tracked).
- `account.analytic.line.x_billing_rate` (Monetary, currency_field=`x_billing_currency_id`) — per-line override.
- `account.analytic.line.x_billing_currency_id` (M2o `res.currency`, default company currency).
- `account.analytic.line.x_overtime_hours` (Float, computed, stored) — `max(0, unit_amount - 8.0)`.
- `account.analytic.line.x_validation_state` (Selection: draft/submitted/validated, tracked) — only validated lines may be invoiced or fed to payroll.
- `account.analytic.line.x_billed_invoice_line_id` (M2o `account.move.line`, readonly) — set by the invoice wizard.
- `account.analytic.line.x_overtime_work_entry_id` (M2o `hr.work.entry`, readonly) — set by OT bridge.
- `custom.timesheet.weekly.summary.week_start` (Date, required) — ISO Monday; `week_end = week_start + 6 days`.
- `custom.timesheet.weekly.summary.summary_html` (Html, sanitised, tracked) — AI output wrapped in `<div class='o_ai_summary'>`.
- `custom.timesheet.weekly.summary.state` (Selection: draft/summarized).

## Manufacturing, Quality & Maintenance (Manufaktur, Kualitas & Pemeliharaan)

### custom_iot_bridge — Custom IoT Bridge

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_iot_bridge` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `mail` |
| Models / routes / tests | 3 / 1 / 0 |
| Tags | iot, audit-trail, anomaly-detection |

> Knowledge file is generator output, not human-reviewed.

A lightweight device-data gateway for Odoo. Represents physical devices (`iot.device`), ingests timestamped sensor readings (`iot.reading`) via a tokenised public webhook (`POST /iot/ingest`), and evaluates user-defined comparator thresholds (`iot.threshold`) that auto-raise `alert_active` and post chatter notifications on the device when breached.

This is the **canonical IoT capability module** for the platform. BRD analyzers should map any requirement about "sensor ingestion / device gateway / threshold alert / telemetry" to this module — vertical modules (cold-chain, manufacturing, fleet, smart-building) should depend on it and add domain models that reference `iot.device` / `iot.reading`, not re-implement the ingest endpoint.

**How it works**

- Operator registers a device on `iot.device` (kind=sensor/gateway/plc/camera/other). `create()` auto-mints an `api_token` via `secrets.token_urlsafe(32)`; status starts `offline`.
- Optional: configure one or more `iot.threshold` rules on the device — pick a `metric` (free-form key, e.g. `temperature_c`), a `condition` (`>` `<` `>=` `<=` `==`), `threshold_value`, `severity`, and `notify_user_ids`.
- Device firmware POSTs each reading to `/iot/ingest` with header `X-Device-Token: <api_token>` and JSON body `{metric, value, unit?, recorded_at?, extra?}`. The controller `IotIngestController.ingest()` validates the token, creates an `iot.reading` (using context flag `iot_internal_write=True` to bypass the immutable guard), bumps `device.last_seen_at` + `device.status=online`, then calls `iot.threshold.evaluate(reading)`.
- `iot.threshold.evaluate(reading)` searches all active thresholds on `(device_id, metric)`, applies the comparator, and: (a) if breached and not already alerting → set `alert_active=True`, `alert_since=now`, post chatter on the device, audit `iot_threshold_trip`; (b) if cleared and was alerting → clear `alert_active`, post "back within range", audit `iot_threshold_clear`; (c) otherwise just stamp `last_evaluated_at`.
- `action_rotate_token()` on the device regenerates `api_token` (breaks existing firmware until reconfigured).
- Readings and threshold-evaluation history are surfaced as list views; the device form shows `reading_count` + `alert_count` computed counters.

**Key models**

- `iot.device` — Physical device registration; carries the secret API token and online/offline status.
- `iot.reading` — Immutable timestamped (metric, value, unit) row; arbitrary JSON `extra` for raw payload. Write/unlink blocked unless `iot_internal_write` context flag is set.
- `iot.threshold` — Per-device, per-metric comparator rule with hysteresis-free alert flip-flop (`alert_active`).

**Important fields**

- `iot.device.code` (Char, unique, indexed) — stable external identifier.
- `iot.device.kind` (Selection sensor/gateway/plc/camera/other).
- `iot.device.api_token` (Char, readonly, indexed) — only authentication for the webhook; auto-generated, rotatable.
- `iot.device.status` (Selection online/offline/decommissioned, tracked) — bumped to online on every successful ingest.
- `iot.device.last_seen_at` (Datetime, readonly) — touched on each ingest.
- `iot.reading.metric` (Char, indexed) — free-form key (no enum); the threshold join key.
- `iot.reading.value` (Float, required).
- `iot.reading.recorded_at` (Datetime, indexed) — defaults to ingest time; the device may override via ISO-8601 payload.
- `iot.reading.extra` (Json) — raw device payload.
- `iot.threshold.condition` (Selection `>`/`<`/`>=`/`<=`/`==`) + `threshold_value` (Float) — the comparator.
- `iot.threshold.alert_active` (Boolean, readonly) + `alert_since` (Datetime, readonly) — current trip state.
- `iot.threshold.severity` (Selection info/warn/critical) — informational only; no routing logic in this module.
- `iot.threshold.notify_user_ids` (M2m res.users) — declared, but actual notification beyond the device chatter post is left to downstream modules.

**Endpoints**: `/iot/ingest`

### custom_maintenance — Custom Maintenance

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_maintenance` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `maintenance`, `custom_iot_bridge`, `product`, `mail` |
| Models / routes / tests | 3 / 0 / 2 |
| Tags | iot, anomaly-detection, audit-trail, approval-workflow |

> Knowledge file is generator output, not human-reviewed.

Extends CE `maintenance` with **IoT-driven alerting, MTBF/MTTR analytics, predictive scheduling, team-SLA policies, spare-parts catalogue with stock-move materialisation, and cost tracking**. The module is the bridge between `custom_iot_bridge` sensor readings and the CE maintenance workflow: thresholds on `maintenance.equipment` are evaluated by a cron, breaches optionally auto-create `maintenance.request` corrective tickets, and an SLA cron escalates approaching/breached resolution deadlines via mail.

**How it works**

- **Configuration**: maintenance admin sets `x_iot_threshold_metric` (e.g. `temperature_c`), `x_iot_threshold_value`, `x_iot_threshold_op` (gt/lt/eq), and `x_auto_request_on_breach` on a `maintenance.equipment`. Optionally defines `custom.maintenance.team.sla` per `(team_id, priority)` with `response_hours` + `resolve_hours`.
- **IoT breach cron** (`cron_check_iot_breaches`): scans equipment with thresholds, reads latest `iot.reading` newer than `x_last_iot_breach`, evaluates operator. On breach: stamps `x_last_iot_breach`, and if `x_auto_request_on_breach=True` creates a `maintenance.request` (`maintenance_type=corrective`, `priority=2`, populated description) with `x_iot_triggered=True` + `x_iot_metric_value`.
- **MTBF/MTTR compute** (`_compute_failure_stats`): on every change to maintenance_ids, walks done-stage corrective requests for the equipment. `x_total_failures` = count. `x_mttr_hours` = mean `(close_date - request_date)` in hours. `x_mtbf_hours` = `(last_failure - effective_date_or_first_failure) / failures`.
- **Predictive next maintenance** (`_compute_predicted_next_maintenance`): if `mtbf_hours > 0` and a base date exists, adds `int(mtbf_hours / 8.0)` days (treating 8h as an operating day). `x_predicted_via` = `mtbf` (preferred) or `iot` (fallback when only thresholds exist).
- **Schedule predicted maintenance**: `action_schedule_predicted_maintenance()` creates draft preventive `maintenance.request` per equipment with the prediction context in the description.
- **Spare parts on done**: when a request transitions to a done stage and has `x_spare_part_ids`, `_create_spare_part_stock_moves` creates `stock.move` rows from any internal location to production (or inventory) for each part — best-effort, silent if stock not installed.
- **Cost tracking**: `x_labor_cost` (manual) + `x_parts_cost` (sum of part `list_price`) → `x_total_cost`.
- **SLA**: `_compute_sla` resolves the best policy per `(team_id, priority)` with global fallback (team=False). `_compute_sla_deadlines` adds hours to `create_date`. `_compute_sla_status` returns ok/warn/breach/done. Cron `cron_check_sla_breach` posts a chatter note + emails team manager on first breach (idempotent via `x_sla_breach_notified`).
- **PDP audit** on equipment write: changes to `owner_user_id`, `employee_id`, or `department_id` write a raw SQL row into `pdp.audit_log` (classification `internal`).

**Key models**

- `maintenance.equipment` (inherited) — Adds IoT thresholds, MTBF/MTTR, predictive fields, PDP audit on owner changes.
- `maintenance.request` (inherited) — Adds IoT flags, spare parts (M2m product), SLA fields, cost fields, predictive stamps.
- `custom.maintenance.team.sla` — Per-team-per-priority SLA policy (response + resolve hours).

**Important fields**

- `maintenance.equipment.x_iot_threshold_metric` (Char) + `x_iot_threshold_value` (Float) + `x_iot_threshold_op` (gt/lt/eq) — breach definition.
- `maintenance.equipment.x_auto_request_on_breach` (Boolean) — gates auto-creation of corrective requests.
- `maintenance.equipment.x_last_iot_breach` (Datetime, readonly) — high-water mark for the cron to avoid duplicate triggers.
- `maintenance.equipment.x_total_failures` / `x_last_failure_at` / `x_mtbf_hours` / `x_mttr_hours` (computed/stored) — reliability metrics.
- `maintenance.equipment.x_predicted_next_maintenance` (Date, computed/stored) — `last_failure + mtbf_hours/8 days`.
- `maintenance.equipment.x_predicted_via` (mtbf/iot/manual).
- `maintenance.request.x_iot_triggered` (Boolean, readonly, tracking).
- `maintenance.request.x_priority_score` (Integer, computed/stored) — `priority*10 - 50 if done + 5 if iot_triggered`.
- `maintenance.request.x_spare_part_ids` (M2m product.product, domain `type='consu'`).
- `maintenance.request.x_sla_id` / `x_sla_response_deadline` / `x_sla_resolve_deadline` / `x_sla_status` (computed/stored).
- `maintenance.request.x_labor_cost` / `x_parts_cost` / `x_total_cost` (Monetary).
- `custom.maintenance.team.sla.team_id` (M2o, may be False for global default) + `priority` (0..3) + `response_hours` + `resolve_hours`.

### custom_mrp_plm — Custom MRP PLM

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_mrp_plm` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `mrp`, `mail` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | plm, manufacturing, approval-workflow, audit-trail |

> Knowledge file is generator output, not human-reviewed.

**Product Lifecycle Management (PLM)** layer on top of Odoo MRP. Provides Engineering Change Order (`mrp.eco`) workflow with multi-stage approval gates; on final approval, the new BoM revision is promoted to active and the old one is **archived** (`active=False`) — never deleted — preserving full audit traceability via `pdp.audited.mixin` with classification `confidential`.

**How it works**

- Engineer creates an `mrp.eco` in `draft` against a `product.template`, captures `kind` (bom_change/product_attr/manufacturing_step), `current_bom_id`, `proposed_bom_id`, `revision` label, `reason` (HTML, required), and `impact_assessment`. `name` from `ir.sequence(mrp.eco)`.
- `action_submit()` (draft only) moves to `state=in_review` and assigns the first active `mrp.eco.stage` by sequence; writes `pdp.audit_log` action `eco_submit`.
- Reviewers iterate `action_approve()`: each call advances `stage_id` to the next active stage by sequence (audit log `eco_stage_advance`). When the current stage is `is_final=True` (or there is no next active stage), `_promote_revision()` runs:
- `current_bom_id.active=False` (archive)
- `proposed_bom_id.active=True` (promote)
- ECO state → `approved`, stamping `approved_by_id` + `approved_at`
- Audit log `eco_approved` with revision + product_tmpl payload
- `action_reject()` moves to `rejected` (any state).
- `action_cancel()` allowed unless `approved` (raises UserError if approved); audit log `eco_cancel`.
- `_group_expand_stages` ensures the kanban shows all active stages even when empty.

**Key models**

- `mrp.eco` — Engineering Change Order; the workflow record. Inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin` (classification `confidential`).
- `mrp.eco.stage` — Workflow stage definition (name, sequence, is_approval, is_final, folded, active).

**Important fields**

- `mrp.eco.kind` (Selection: bom_change/product_attr/manufacturing_step) — semantic categorisation; does not change the workflow.
- `mrp.eco.product_tmpl_id` (M2o `product.template`, required, tracking) — target product.
- `mrp.eco.current_bom_id` (M2o `mrp.bom`, domain on product_tmpl_id) — soon-to-be-archived BoM.
- `mrp.eco.proposed_bom_id` (M2o `mrp.bom`) — soon-to-be-active BoM; promoted on final approval.
- `mrp.eco.revision` (Char, default `"A"`) — free-text revision label.
- `mrp.eco.reason` (HTML, required) — change rationale.
- `mrp.eco.impact_assessment` (HTML) — impact narrative.
- `mrp.eco.stage_id` (M2o `mrp.eco.stage`, group_expand) — current workflow stage.
- `mrp.eco.state` (draft/in_review/approved/rejected/cancelled).
- `mrp.eco.approved_by_id` + `approved_at` (readonly) — stamped by `_promote_revision`.
- `mrp.eco.stage.is_final` (Boolean) — triggers BoM promotion on advance.
- `mrp.eco.stage.is_approval` (Boolean) — informational; does not gate code paths.

### custom_quality_full — Custom Quality (Full)

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_quality_full` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `mrp`, `stock`, `mail` |
| Models / routes / tests | 8 / 0 / 1 |
| Tags | quality, manufacturing, audit-trail, approval-workflow |

> Knowledge file is generator output, not human-reviewed.

Full-featured **Quality / NCR / CAPA** module that replaces the CE quality skeleton with a per-check multi-line inspection checklist, reusable test templates, tamper-evident SHA-256 e-signatures, and structured Corrective/Preventive/Containment Actions (CAPAs) with an auto-resolve cascade. Quality points define what to measure; checks execute against them; failed checks auto-raise NCR alerts; CAPAs close the loop.

**How it works**

- Quality manager defines `quality.point` records: per-product, per-operation (incoming/manufacturing/outgoing/ad_hoc), with `check_kind` (instructions/pass_fail/measure/visual), `frequency`, optional `measure_min/max/uom`, and an optional `default_test_id` pointing to a reusable `custom.quality.test` template.
- A `custom.quality.test` template carries `custom.quality.test.line` rows (question + response_type: text/number/boolean/photo/select + is_required + expected_min/max/set).
- Operator runs a `quality.check` against a point. `name` from `ir.sequence(quality.check)`. `action_apply_test_template()` seeds `custom.quality.inspection.line` rows from `point.default_test_id` (or an explicit template).
- Per inspection line, operator fills `actual_value` / `actual_photo`; `pass_fail` is computed from response_type + expected_min/max/set + is_required.
- `overall_result` on the check rolls up required lines: `pass` if all required lines pass, `fail` if any required line fails, `na` if no required lines.
- `action_pass()` validates the measurement against `point.measure_min/max` (raises UserError if out-of-range), stamps `performed_at`, writes `pdp.audit_log`.
- `action_fail()` stamps state, then **auto-creates** a `quality.alert` (NCR) with `severity='major'` and links it via `alert_id`.
- The alert walks `open → investigating → corrective_action → resolved → closed`. CAPAs (`custom.quality.capa`) are attached: type corrective/preventive/containment, with `responsible_id`, `deadline`, `completion_date`.
- When **all** CAPAs on an alert are `done`/`canceled`, `custom.quality.capa.action_done()` cascades and auto-calls `alert.action_resolve()`.
- Signatures (`custom.quality.signature`) attach to either a check or a CAPA. On create, a SHA-256 `hash` is computed over `signer_id | check_id | capa_id | signed_at | sha256(image)`. Subsequent edits to any protected field raise `ValidationError`; `is_valid` recomputes the hash and surfaces tampering.

**Key models**

- `quality.point` — Control point definition (what / where / how).
- `quality.check` — Execution instance against a point.
- `quality.alert` — NCR (non-conformance report); auto-raised on check fail.
- `custom.quality.inspection.line` — Per-question result on a check.
- `custom.quality.test` + `custom.quality.test.line` — Reusable test/question templates.
- `custom.quality.capa` — Corrective / Preventive / Containment Action.
- `custom.quality.signature` — Tamper-evident SHA-256 e-signature for check or CAPA.

**Important fields**

- `quality.point.check_kind` (Selection: instructions/pass_fail/measure/visual) — semantic, gates measurement range validation.
- `quality.point.measure_min` / `measure_max` / `measure_uom_id` — range check in `action_pass`.
- `quality.point.default_test_id` (M2o `custom.quality.test`) — auto-seed inspection lines.
- `quality.check.state` (waiting/pass/fail).
- `quality.check.overall_result` (Selection: pass/fail/na, computed/stored) — required-line rollup.
- `quality.check.alert_id` (M2o `quality.alert`, readonly) — set by `action_fail`.
- `quality.alert.severity` (minor/major/critical) — defaults `major` from check fail.
- `quality.alert.state` (open/investigating/corrective_action/resolved/closed).
- `custom.quality.inspection.line.pass_fail` (pass/fail/na, computed) — per-response-type logic.
- `custom.quality.inspection.line.response_type` (text/number/boolean/photo/select).
- `custom.quality.capa.action_type` (corrective/preventive/containment).
- `custom.quality.signature.hash` (Char, readonly) — SHA-256; tamper detector.
- `custom.quality.signature.is_valid` (Boolean, computed) — `True` iff stored hash == recomputed hash.

### custom_repairs — Custom Repairs

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_repairs` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_quality_full`, `repair`, `maintenance`, `mail` |
| Models / routes / tests | 0 / 0 / 3 |
| Tags | maintenance, quality, manufacturing |

> Knowledge file is generator output, not human-reviewed.

Extends CE `repair.order` for **internal asset maintenance** (repairs on the
company's own equipment, not external-customer jobs). Links each repair to a
`maintenance.equipment` asset and bridges to the maintenance module by
auto-creating a corrective `maintenance.request`, feeding the asset's
maintenance history (MTBF/MTTR in `custom_maintenance`). Adds turnaround SLA,
labour + material cost analysis, optional MRP work-order link, optional
quality check on completion, and a re-open/rework flag. All extra fields are
namespaced `x_*` so the module composes cleanly with other repair extensions.

> Reoriented in 19.0.1.0.0 from the earlier customer-facing form (product
> warranty matrix, WhatsApp-to-customer status, customer complaint/returns).
> Those were removed; the WhatsApp action and `custom.repairs.warranty.matrix`
> model are gone. See `migrations/19.0.1.0.0/pre-migrate.py`.

**How it works**

- Operator links the repair to an internal asset via `x_equipment_id` (`maintenance.equipment`) and records the internal fault in `x_id_complaint` and the requester in `x_requesting_user_id` / `x_requesting_team_id`.
- On `write({'state':'confirmed'})`, two best-effort bridges fire:
- `_maybe_create_maintenance_request` opens a corrective `maintenance.request` on the linked asset (idempotent, `.sudo()`, no-op when no equipment or `maintenance` absent). Stored on `x_maintenance_request_id`; the asset's `maintenance_ids` back-link populates automatically.
- `_maybe_create_mrp_workorder` creates an `mrp.production` stub when material lines exist and `mrp` is installed. Stored on `x_mrp_production_id`.
- Operator sets `x_promised_completion_date`; `_compute_sla_status` returns on_track / at_risk (≤ 1 day) / breached / done.
- On `write({'state':'done'})`, `x_actual_completion_date` is auto-stamped, then `_maybe_launch_quality_check` best-effort creates a `quality.check` against the first matching `quality.point` (by `product_id` when present, else any).
- Cost compute (`_compute_total_repair_cost`): material cost iterates `move_ids` (Odoo 19) / `operations` / `parts_lines` (older), preferring `product.standard_price * qty`, falling back to `price_subtotal` / `price_total` / `price_unit`. Labour cost = `x_labor_hours * x_labor_rate` (default rate from ICP `custom_repairs.labor_rate`, default 100 000 IDR/hour).
- `action_set_rework()` flags `x_returned=True` + stamps `x_return_date`; chatter post ("Repair re-opened for rework.").

**Key models**

- `repair.order` (inherited) — Adds `x_*` fields covering asset link / SLA / cost / rework / MRP / quality.

**Important fields**

- `repair.order.x_equipment_id` (M2o `maintenance.equipment`, tracking) — the internal asset.
- `repair.order.x_maintenance_request_id` (M2o `maintenance.request`, readonly) — bridged corrective request.
- `repair.order.x_requesting_user_id` (M2o `res.users`, default=current user, tracking).
- `repair.order.x_requesting_team_id` (M2o `maintenance.team`).
- `repair.order.x_promised_completion_date` (Date, tracking).
- `repair.order.x_actual_completion_date` (Datetime, readonly) — auto-stamped on done.
- `repair.order.x_sla_status` (on_track/at_risk/breached/done, computed/stored).
- `repair.order.x_id_complaint` (Text) — internal fault description.
- `repair.order.x_labor_hours` / `x_labor_rate` / `x_material_cost` / `x_labor_cost` / `x_total_repair_cost`.
- `repair.order.x_returned` (Boolean, readonly, copy=False) "Re-opened / Rework" + `x_return_date` (Datetime, readonly) + `x_return_reason` (Text).
- `repair.order.x_mrp_production_id` (M2o `mrp.production`, readonly).
- `repair.order.x_quality_check_ids` (O2m `quality.check`, computed) + `x_quality_check_count`.

## Productivity & AI (Produktivitas & AI)

### custom_ai_bridge — Custom AI Bridge

|  |  |
| --- | --- |
| Path | `addons/core/custom_ai_bridge` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | ai, multi-tenant |

> Knowledge file is generator output, not human-reviewed.

Thin Odoo-side client for the platform's external AI gateway (`ai-gateway` HTTP service which fronts Anthropic Claude, OpenAI, and Ollama). Every Odoo-originated AI call — recommendations on records, chat completions for downstream modules, the BRD analyzer — funnels through this bridge so signing, tenant tagging, timeouts, and on/off toggling are uniform.

Provides one abstract service model (`custom.ai`) and one generic "Ask AI" record-agnostic wizard (`custom.ai.recommend.wizard`). All transport is HMAC-signed via `custom.security.sign_payload` and tagged with `X-Tenant-Id: <env.cr.dbname>`.

**How it works**

- Downstream code calls `self.env["custom.ai"]._chat(messages, system, model, quality, tools, max_tokens, temperature)` or `._recommend(model, res_id, payload, history, locale)`.
- `_call(path, body)` checks the `custom_ai.enabled` `ir.config_parameter` (raise `UserError` if off), serializes body with `json.dumps(default=str)`, asks `custom.security.sign_payload` for an `X-Custom-Signature: t=<ts>,v1=<hmac>` header, POSTs to `${AI_GATEWAY_URL}/v1/chat` or `/v1/workflow/recommend` via `httpx.Client` with `Timeout(connect=10, read=300, write=30, pool=10)`.
- Non-200 → `UserError(f"AI gateway error {status}: {text[:200]}")`. Network failure → `UserError("AI gateway unreachable: ...")`.
- The "Ask AI" wizard (`custom.ai.recommend.wizard.action_ask`) introspects any record's `_fields`, skips `binary`/`image`, serializes recordsets as `(_name, ids[:5])`, calls `_recommend`, and surfaces `summary` / `next_actions` / `priority` / `tags` / `raw_text` on the wizard form.
- Settings page exposes `custom_ai.enabled`, `custom_ai.quality` (fast/high), `custom_ai.provider_override` (""/anthropic/openai/ollama) — all stored as `ir.config_parameter`.

**Key models**

- `custom.ai` — AbstractModel; the gateway client service. No DB row; methods are `@api.model`.
- `custom.ai.recommend.wizard` — TransientModel; generic "Ask AI about this record" UI invokable from any form view's action menu.
- `res.config.settings` (inherited) — exposes the three `custom_ai.*` config parameters.

**Important fields**

- `custom.ai.recommend.wizard.model_name` (Char, required) — technical model name of the record to ask AI about.
- `custom.ai.recommend.wizard.res_id` (Integer, required) — record id within `model_name`.
- `custom.ai.recommend.wizard.locale` (Char, default `"id_ID"`) — passed to gateway for response language.
- `custom.ai.recommend.wizard.summary` / `next_actions_text` / `priority` / `tags` / `raw_text` (Text/Char, readonly) — populated from gateway response keys `summary`, `next_actions`, `priority`, `tags`, `raw_text`.
- `res.config.settings.custom_ai_enabled` (Boolean, `config_parameter="custom_ai.enabled"`, default True) — master kill switch.
- `res.config.settings.custom_ai_default_quality` (Selection fast/high, `config_parameter="custom_ai.quality"`) — default `quality` tier.
- `res.config.settings.custom_ai_provider_override` (Selection ""/anthropic/openai/ollama, `config_parameter="custom_ai.provider_override"`) — forces a specific provider regardless of gateway default.

### custom_ai_features — Custom AI Features

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_ai_features` |
| Version | 19.0.0.1.1 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_ai_bridge`, `custom_approval_engine`, `custom_coretax_pajakku`, `custom_documents`, `custom_field_service`, `custom_helpdesk`, `custom_hr_payroll_id`, `mail`, `portal`, `website` |
| Models / routes / tests | 4 / 2 / 0 |
| Tags | ai, anomaly-detection, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Surfaces the platform's ai-gateway capabilities (provided by `custom_ai_bridge`'s `custom.ai` service) throughout the Odoo UI as concrete end-user features. It is not infrastructure — it consumes infrastructure — but it defines the **canonical UX patterns** ("Ask AI…" cog action, anomaly inbox, NLQ chat portal, document auto-classify) that BRD analyzers should map any new "AI" capability requirement onto.

Four feature surfaces are bundled: (1) per-record "Ask AI…" server actions bound to 9 key business models that open `custom.ai.recommend.wizard`; (2) nightly anomaly scan cron writing `ai.anomaly.finding` rows for triage; (3) `/ai/chat` internal portal with `ai.nlq.session` / `ai.nlq.message` history and read-only NLQ execution; (4) `document.document` create-hook that auto-suggests `pdp.classification` + tags from filename/content excerpt.

**How it works**

- **Ask AI cog menu:** XML data (`ask_ai_actions_data.xml`) declares one `ir.actions.server` per binding model (`account.move`, `purchase.order`, `sale.order`, `res.partner`, `helpdesk.ticket`, `hr.payslip`, `custom.coretax.transaction`, `fsm.work.order`, `document.document`). Each action context-launches `custom.ai.recommend.wizard` with `default_model_name` + `default_res_id`.
- **Anomaly scan cron:** `ai.anomaly.scan._cron_run()` creates a scan row, then iterates the `SCANNERS` registry (one config dict per model). Each `_scan_model(cfg)` pulls recent records, computes a metric history list, calls `custom.ai._detect_anomaly(...)` on the gateway, and if `is_anomaly=True && score>=0.5` creates an `ai.anomaly.finding` row (state `new`, severity from gateway).
- **Finding triage:** Reviewer opens an `ai.anomaly.finding` (`new`→`triaged`→`resolved`, or `dismissed`). `action_open_source()` opens the underlying record via `res_model`/`res_id`. Each transition writes a `pdp.audited.mixin` audit row.
- **NLQ chat:** User hits `/ai/chat`, controller calls `ai.nlq.session.open_or_create_for_user()` (one rolling session per user). On POST the controller calls `session.with_user(env.user).ask(question)`; `ask()` posts the user message, calls `custom.ai._nlq(question, schema_hint, locale, user_can_view_pii)`, then `_execute_plan(plan)` runs `Model.search_read(domain, fields, limit=min(plan.limit,100))` strictly read-only, whitelisted against `ALLOWED_SCHEMA`, with PII fields stripped when user lacks `custom_pdp_masking.group_view_pii`.
- **Document auto-classify:** `document.document.create()` is overridden; after the super-create, `_ai_auto_classify()` skips records that already have `classification_id`, otherwise calls `custom.ai._classify_document(filename, mimetype, text_excerpt)` and assigns the returned `pdp.classification` code + creates/links `document.tag` rows. Plain-text/JSON/XML attachments are decoded for an 8 KB text excerpt; PDFs are skipped.

**Key models**

- `ai.anomaly.scan` — Scheduler run record (`running`/`done`/`error`) owning a One2many of findings.
- `ai.anomaly.finding` — Single flagged anomaly with severity, score, rationale, suggested action, triage state, and pointer to source record via `res_model`+`res_id`/`res_ref`.
- `ai.nlq.session` — Per-user rolling NLQ chat thread, inherits `pdp.audited.mixin`.
- `ai.nlq.message` — Persisted user/assistant message row with `plan_json` + `result_json`.
- `custom.ai` (AbstractModel inherit) — Extends `custom_ai_bridge`'s service with `_detect_anomaly`, `_classify_document`, `_nlq` POST helpers hitting `/v1/workflow/{anomaly,classify-document,nlq}`.
- `document.document` (inherit) — Adds `create()` override invoking `_ai_auto_classify`.

**Important fields**

- `ai.anomaly.finding.res_model` / `res_id` (Char/Int, indexed) — pointer to flagged record.
- `ai.anomaly.finding.res_ref` (Reference, dynamic selection) — clickable cross-model link.
- `ai.anomaly.finding.severity` (Selection info/warning/critical, tracked) — drives inbox prioritisation.
- `ai.anomaly.finding.score` (Float) — gateway confidence; findings <0.5 are dropped at creation.
- `ai.anomaly.finding.state` (Selection new/triaged/dismissed/resolved, tracked) — triage workflow.
- `ai.anomaly.finding.rationale` / `suggested_action` (Text) — gateway-produced human-readable guidance.
- `ai.nlq.session.user_id` (M2o res.users) — defines whose PII-mask group governs the schema hint.
- `ai.nlq.message.role` / `content` / `plan_json` / `result_json` / `is_error` — message + structured plan/result trace.

**Endpoints**: `/ai/chat`, `/ai/chat/ask`

### custom_dashboards — Custom Dashboards

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_dashboards` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_ai_bridge`, `board` |
| Models / routes / tests | 3 / 1 / 2 |
| Tags | ai, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

A CE-targeted reimplementation of EE's `board` dashboard builder. Dashboards (`custom.dashboard`) own a One2many of tiles (`custom.dashboard.tile`); each tile computes a single KPI — count / sum / avg / last_value / formula / chart_bar / chart_pie — over any model + domain, caches the result as JSON on the row, and a cron auto-refreshes tiles whose cache exceeds their per-tile interval.

Adds publishing (`is_published`), per-group ACLs (`allowed_group_ids`), public read-only share-by-token endpoint (`/custom_dashboard/share/<token>`), drill-down from tile to underlying records, and an **Ask AI** entry point that forwards dashboard context + question to `custom.ai._recommend`.

**How it works**

- User creates a `custom.dashboard` with a name + optional description; defaults to unpublished, private to owner.
- User adds `custom.dashboard.tile` rows: pick `tile_type`, set `model_name` (technical, e.g. `helpdesk.ticket`), domain (Odoo domain literal), and the relevant compute inputs (`measure_field` for sum/avg/last_value/chart; `groupby_field` for chart; `formula_expression` for formula).
- `action_refresh` on the tile evaluates the domain via `safe_eval`, dispatches to the per-type compute helper, stores result as JSON in `cached_value`, sets `cached_at`, clears or sets `last_error`. The `_compute_cached_display` renders a human string for scalar tiles or "N series" for charts.
- `_cron_refresh_stale_tiles` (cron) iterates all tiles and re-runs `action_refresh` on any whose `cached_at` is older than `refresh_interval_seconds` (floor 30s).
- `action_open_tile_records` returns an `ir.actions.act_window` on the tile's model+domain for drill-down.
- `action_generate_share_link` mints `share_token` (`secrets.token_urlsafe(32)`); `share_url` exposes `{web.base.url}/custom_dashboard/share/<token>`. `action_revoke_share_link` clears the token.
- `action_ask_ai(question)` packages dashboard + tile metadata + cached values via `_custom_ai_payload(question)` and calls `custom.ai._recommend(model="custom.dashboard", res_id=self.id, payload=…)`. Result text lands in `last_ai_answer` (HTML, sanitized), `last_ai_question`, `last_ai_at`, and is mirrored to chatter.
- Publish/unpublish gating is via `action_publish` / `action_unpublish`; ACL enforcement against `allowed_group_ids` is via record rules in `security/security.xml`.
- Public share controller `/custom_dashboard/share/<token>` renders `share_templates.xml` read-only.

**Key models**

- `custom.dashboard` — Container with metadata, owner, ACLs, share token, AI Q&A scratchpad, One2many tiles. Inherits `mail.thread` + `pdp.audited.mixin`.
- `custom.dashboard.tile` — Single KPI definition + cache; one row per tile.

**Important fields**

- `custom.dashboard.is_published` (Boolean, tracked) — gates list visibility for non-owners.
- `custom.dashboard.is_public` (Boolean, tracked) — enables `/custom_dashboard/share/<token>` rendering.
- `custom.dashboard.allowed_group_ids` (M2m res.groups) — read ACL beyond owner.
- `custom.dashboard.share_token` (Char, indexed, unique) — share URL secret.
- `custom.dashboard.last_ai_question` / `last_ai_answer` (Char / Html-sanitized) / `last_ai_at` (Datetime) — Ask AI scratchpad.
- `custom.dashboard.tile_ids` (One2many) — tile composition.
- `custom.dashboard.tile.tile_type` (Selection count/sum/avg/last_value/formula/chart_bar/chart_pie).
- `custom.dashboard.tile.model_name` (Char) — technical model; resolved via `self.env[...]`.
- `custom.dashboard.tile.domain` (Char) — string literal evaluated with `safe_eval`.
- `custom.dashboard.tile.measure_field` / `groupby_field` (Char) — compute inputs.
- `custom.dashboard.tile.formula_expression` (Text) — `safe_eval` expression with `env`/`domain`/`model`/`fields` in scope.
- `custom.dashboard.tile.refresh_interval_seconds` (Integer, default 300, floor 30) — cron staleness threshold.
- `custom.dashboard.tile.cached_value` (Text, JSON) — scalar `{"value": ...}` or chart `{"labels": [...], "data": [...]}`.
- `custom.dashboard.tile.cached_at` (Datetime, readonly) — last successful refresh.
- `custom.dashboard.tile.last_error` (Char, readonly) — last refresh failure message.

**Endpoints**: `/custom_dashboard/share/<string:token>`

### custom_data_cleaning — Custom Data Cleaning

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_data_cleaning` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `data_recycle` |
| Models / routes / tests | 4 / 0 / 2 |
| Tags | pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

CE substitute for Odoo Enterprise `data_cleaning`. Built atop CE `data_recycle`, it provides rule-driven deduplication for any model, with Indonesian-aware normalisation (phone canonicalisation to `+62…`, email lower-casing) applied **before** comparison so equivalent values bucket together.

Also exposes reusable module-level helpers `_normalize_phone_id(value)`, `_validate_nik(value)`, `_is_valid_phone_id_format(value)` used by other addons (HR, contacts, KYC).

**How it works**

- Admin creates a `custom.dedup.rule`: pick `model_name` (technical, e.g. `res.partner`), comma-separated `match_fields`, toggle `normalize_phone_id` / `normalize_email_case`, optionally turn on `cron_active` (daily ir.cron).
- On `action_run_scan` (manual or cron): the rule reads `search_read([], match_fields + ['id'])` over the target model, builds a key tuple per record using `_normalize_value` (lower+strip default; phone canonicalised via `_normalize_phone_id` for `phone`/`mobile`/`phone_id`/`x_phone`/`x_mobile`; email lower-cased for `email`/`email_normalized`/`x_email`), and groups records by key.
- For each bucket with >1 record, the rule unlinks existing `pending` candidates (idempotent re-scan) and creates a `custom.dedup.candidate` with `res_ids_json` (JSON array of IDs), a 255-char `preview` string built from display names, and the `match_key`.
- `last_run_at` and `last_match_count` are stamped on the rule; a chatter note is posted.
- Reviewer opens a candidate, clicks `action_open_merge_wizard` → `custom.dedup.merge.wizard` (form, target=new) which guides conflict-aware merging; `action_dismiss` flips state to `dismissed`.
- Bulk normalisation: `custom.dedup.normalize.wizard` applies phone/NIK normalisation across an arbitrary model in a single pass without merging.
- Cron lifecycle: when `cron_active=True`, `_create_cron_if_active` provisions/updates an `ir.cron` row (daily) running `rule.action_run_scan()`; clearing the flag unlinks the cron. Unlinking the rule also unlinks its cron.
- Recycle presets (`data/data_recycle_presets.xml`) seed `data_recycle.model` rows for stale archived contacts, dormant draft leads, and old cancelled sales.

**Key models**

- `custom.dedup.rule` — Per-model deduplication rule with normalisation flags and optional cron.
- `custom.dedup.candidate` — A bucket of >1 duplicate IDs awaiting reviewer action.
- `custom.dedup.merge.wizard` (TransientModel) — Guided merge UI; preserves master values where conflicting.
- `custom.dedup.normalize.wizard` (TransientModel) — Bulk normaliser for phone/NIK on any model.

**Important fields**

- `custom.dedup.rule.model_name` (Char, required) — technical target.
- `custom.dedup.rule.match_fields` (Char, required) — comma-separated field names.
- `custom.dedup.rule.normalize_phone_id` (Boolean, default True) — applies `_normalize_phone_id` to phone-like fields.
- `custom.dedup.rule.normalize_email_case` (Boolean, default True) — lower-cases email-like fields.
- `custom.dedup.rule.cron_active` (Boolean, tracked) — toggles the daily cron.
- `custom.dedup.rule.cron_id` (M2o ir.cron, readonly, ondelete=set null) — owned cron handle.
- `custom.dedup.rule.last_run_at` / `last_match_count` (Datetime/Integer, readonly) — telemetry.
- `custom.dedup.candidate.res_ids_json` (Text) — JSON array of duplicate record IDs (the source of truth, not a Many2many).
- `custom.dedup.candidate.preview` (Char, 255) — human-readable head of the bucket.
- `custom.dedup.candidate.match_key` (Char, 255) — normalised key joined by `" || "`.
- `custom.dedup.candidate.state` (Selection pending/merged/dismissed).

### custom_documents — Custom Documents

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_documents` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_pdp_core`, `mail`, `portal` |
| Models / routes / tests | 4 / 0 / 0 |
| Tags | pdp, audit-trail, knowledge |

> Knowledge file is generator output, not human-reviewed.

A lightweight workspace-organised Document Management System (DMS) for the platform. Each `document.document` lives in a `document.workspace` (hierarchical, member-gated), wraps an `ir.attachment` (the real file storage), and carries metadata: tags (`document.tag`), PDP classification (`pdp.classification`, default inherited from workspace), description, owner, lifecycle state (draft/published/archived), token-protected share link with expiry, and immutable version history (`document.version`).

Every CRUD-side action writes a PDP audit row, and `_pdp_audit_classification()` is overridden so each document carries its own classification code into the audit stream. This is the **canonical DMS module** — other modules that need file storage with versioning + classification should depend here.

**How it works**

- Admin defines a `document.workspace` (code unique, optional parent, members list, `default_classification_id`).
- User creates a `document.document` with a name, target workspace, and an `attachment_id` (the uploaded file). On `create()`:
- If `classification_id` is not set, it is auto-populated from `workspace_id.default_classification_id` via `_compute_classification` (stored, non-readonly).
- A `document.version` row with `version=1` and a "Initial version" comment is created.
- `action_upload_new_version(attachment_id, comment)`: looks up the latest version number, creates a new `document.version` with `version = latest+1`, swaps the document's `attachment_id` to point at the new file, audits `document_new_version`.
- `action_publish()` flips state draft→published + audit `document_publish`. `action_archive()` flips to archived + audit.
- `action_generate_share_link()` mints `share_token` (`secrets.token_urlsafe(32)`), sets `share_expires_at = now + 7 days`, audits.
- `action_revoke_share()` clears token + expiry, audits.
- All versions are immutable: `document.version.write` raises `UserError` unless `document_version_internal` context flag is set; `unlink` is unconditionally forbidden.

**Key models**

- `document.workspace` — Hierarchical container; carries default classification + member ACL.
- `document.document` — A logical document (one current file + N historical versions); inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`.
- `document.version` — Append-only history row pointing at a snapshot `ir.attachment`.
- `document.tag` — Free-form tag dictionary (Many2many on `document.document`).

**Important fields**

- `document.document.workspace_id` (M2o document.workspace, required, indexed) — primary scoping.
- `document.document.attachment_id` (M2o ir.attachment, required, ondelete=cascade, copy=False) — current file pointer.
- `document.document.classification_id` (M2o pdp.classification, computed-stored, non-readonly) — falls back to workspace default; writable for override.
- `document.document.filename` / `mimetype` / `file_size` (related from attachment).
- `document.document.state` (Selection draft/published/archived, tracked) — lifecycle.
- `document.document.share_token` (Char, readonly, copy=False) — share URL secret.
- `document.document.share_expires_at` (Datetime) — defaults to +7 days from generation.
- `document.document.owner_id` (M2o res.users, required, defaults to env.user).
- `document.document.tag_ids` (M2m document.tag).
- `document.version.document_id` (M2o, ondelete=cascade, indexed).
- `document.version.attachment_id` (M2o ir.attachment, ondelete=restrict) — restrict prevents deleting an attachment still referenced by history.
- `document.version.version` (Integer, required) — monotonic per document; `(document_id, version)` unique.
- `document.workspace.code` (Char, unique, indexed) — stable external identifier.
- `document.workspace.member_ids` (M2m res.users) — workspace ACL.
- `document.workspace.default_classification_id` (M2o pdp.classification) — inherited by new docs.

### custom_knowledge — Custom Knowledge

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_knowledge` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_documents`, `mail`, `portal` |
| Models / routes / tests | 4 / 2 / 2 |
| Tags | knowledge, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

A CE-targeted reimplementation of Odoo Knowledge — an internal wiki / knowledge base. Articles (`knowledge.article`) are hierarchical (parent/child), rich-text (sanitized HTML), tagged (`knowledge.tag`), owner-attributed, and optionally restricted to specific `res.groups`. PostgreSQL `to_tsvector` + GIN index (built in `post_init_hook`) powers full-text search. Articles can be shared externally via token-protected `/knowledge/share/<token>`, started from reusable templates (`knowledge.article.template`), favourited per user, and snapshot-versioned on every body change.

This is the **canonical knowledge / wiki / SOP / runbook surface** for the platform. BRD analyzers should map "knowledge base / wiki / internal docs / runbook / SOP repository" requirements here.

**How it works**

- User creates a `knowledge.article` with a name, optional parent, rich-text body, tags, optional `read_group_ids` restriction. On create, if `is_shared_externally=True` and no token, one is minted via `secrets.token_urlsafe(32)`.
- On any `write()` where `body` changes, the **previous** body is snapshotted into a new `knowledge.article.version` row with `version_no = current_count + 1` and `saved_by = uid` — append-only history.
- `action_apply_template(template_id)` overwrites `body` with `knowledge.article.template.body_template` (seeded categories: meeting_notes, project_brief, sop, runbook, onboarding).
- `action_toggle_favorite()` adds/removes the calling user from `favorite_user_ids`. The `is_favorite` computed boolean and `_search_is_favorite` enable a "My Favorites" filter.
- `action_generate_share_link()` rotates `share_token` + sets `is_shared_externally=True`, then shows a sticky notification with the full URL.
- `action_revoke_share_link()` clears the flag and token.
- Public route `GET /knowledge/share/<token>` (controller `KnowledgePortalController.share_article`) requires token length ≥ 16, `is_shared_externally=True`, and `share_token` match; renders `custom_knowledge.portal_share_article`.
- JSON endpoint `POST /knowledge/search` (auth=user) calls `search_articles(query, limit)` which uses `to_tsvector('english', name||' '||body) @@ plainto_tsquery(...)` with `ts_rank` ordering and `ts_headline` snippets, filtered to record-rule-accessible IDs. Fallback to `ilike` on `name` if pgsql refuses the tsquery.
- `_get_access_action` is overridden so mail-notification links to an externally-shared article route to the public share URL when `force_website=True`.
- Dynamic Properties: each article carries a `Properties` bag whose definition is inherited from `parent_id.property_definitions`, enabling per-subtree custom fields without `ir.model.fields` records.

**Key models**

- `knowledge.article` — Main wiki node; inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`.
- `knowledge.article.version` — Immutable append-only snapshot of a previous body.
- `knowledge.article.template` — Reusable starting body keyed by category (meeting_notes/project_brief/sop/runbook/onboarding/other).
- `knowledge.tag` — Free-form tag dictionary.

**Important fields**

- `knowledge.article.parent_id` (M2o self, ondelete=cascade, indexed) — hierarchy.
- `knowledge.article.body` (Html, sanitized, translate=True) — main content; change triggers versioning.
- `knowledge.article.search_vector` (Char, computed-stored) — denormalised tag-stripped concat of name+body, capped 8 000 chars; the real GIN index is on `to_tsvector` of name+body (built in `post_init_hook`).
- `knowledge.article.is_published` (Boolean, tracked) — visibility flag for internal users.
- `knowledge.article.read_group_ids` (M2m res.groups) — optional read restriction; empty = all Knowledge users.
- `knowledge.article.share_token` (Char, indexed, copy=False) — external share secret.
- `knowledge.article.is_shared_externally` (Boolean, tracked) — gates the public route.
- `knowledge.article.favorite_user_ids` (M2m res.users) — per-user pinning storage.
- `knowledge.article.is_favorite` (Boolean, computed, searchable, non-stored) — UI helper bound to env.uid.
- `knowledge.article.properties` / `property_definitions` (Properties / PropertiesDefinition) — Odoo 19 dynamic field bag; definition lives on the parent article.
- `knowledge.article.version_ids` (One2many) / `version_count` (Integer, computed).
- `knowledge.article.template.body_template` (Html, sanitized, translate=True).
- `knowledge.article.template.category` (Selection) — taxonomy for the template picker.

**Endpoints**: `/knowledge/search`, `/knowledge/share/<string:token>`

### custom_sign — Custom Sign

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_sign` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `mail`, `portal`, `website` |
| Models / routes / tests | 3 / 2 / 0 |
| Tags | approval-workflow, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

A lightweight e-signature workflow for the platform. A `sign.template` wraps a reusable PDF (`ir.attachment`); a `sign.request` bundles that template with an ordered list of `sign.request.signer` rows. On send, every signer gets a unique tokenised public portal URL (`/sign/<token>`) where they view the document and submit either a drawn signature (canvas data URL → base64 PNG) or a typed-name fallback. Aggregated state (`partially_signed` → `signed`) is recomputed on every signer submission, with PDP audit + `mail.thread` tracking throughout.

This is the **canonical e-signature module** for the platform. Anything in a BRD that mentions "electronic signature / DocuSign-like / multi-signer routing / signature collection" should map here.

**How it works**

- Admin uploads a PDF, creates a `sign.template` pointing at its `ir.attachment`.
- User creates a `sign.request` (default state `draft`, name from `ir.sequence` `sign.request`, fallback `SIGN-???`), picks the template, and adds `sign.request.signer` rows with `name`/`email`/optional `role`/`sequence`/optional `partner_id`.
- `action_send()` guards `state == 'draft'` and `signer_ids` non-empty, then mints a `secrets.token_urlsafe(32)` `access_token` for each signer missing one, flips request state to `sent`, stamps `sent_at`, audits `sign_request_sent`.
- Each signer receives a `/sign/<access_token>` URL (email/notification mechanism is out of scope here — only token generation lives in this module). When the URL is opened, `SignPortal.sign_open()` looks up the signer, calls `mark_opened(ip, ua)` which transitions `waiting`→`opened` with IP + user-agent capture, and renders `custom_sign.sign_page`.
- Signer POSTs to `/sign/<token>/submit` with `signature_data` (data:image base64 URL) and/or `signature_text`. The controller decodes the data URL, calls `submit_signature(signature_data, signature_text)`. That method enforces "not already signed/declined", "at least one of drawn or typed provided", writes signature + signed_at, audits `sign_signer_signed`, then calls `request._refresh_state()`.
- `_refresh_state()` recomputes: all-signed → `signed` + stamp `completed_at` + audit `sign_request_complete`; any-signed-but-not-all → `partially_signed`.
- `decline(reason)` flips the signer to `declined` and posts a chatter note on the request (does not change request state on its own).
- `action_cancel()` is allowed from any non-`signed` state and audits.

**Key models**

- `sign.template` — Reusable PDF + label; bound to one `ir.attachment`.
- `sign.request` — One signature collection round; owns ordered signer list and aggregated state. Inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`.
- `sign.request.signer` — One row per addressee; carries token, state, IP/UA, signature blob/text. Inherits `mail.thread`, `mail.activity.mixin`.

**Important fields**

- `sign.request.name` (Char) — `ir.sequence`-allocated identifier.
- `sign.request.state` (Selection draft/sent/partially_signed/signed/cancelled, tracked, indexed) — workflow.
- `sign.request.template_id` (M2o sign.template, required).
- `sign.request.attachment_id` (related from template, stored) — denormalised for direct attachment access.
- `sign.request.signer_ids` (One2many).
- `sign.request.signed_count` / `total_signers` (Integer, computed) — for UI progress.
- `sign.request.sent_at` / `completed_at` (Datetime, readonly).
- `sign.request.requested_by_id` (M2o res.users, required, defaults to env.user).
- `sign.request.signer.access_token` (Char, readonly, copy=False, indexed) — the only auth for the public portal.
- `sign.request.signer.state` (Selection waiting/opened/signed/declined, tracked).
- `sign.request.signer.signature_data` (Binary, attachment=True) — drawn signature as PNG bytes (base64-encoded after data-URL strip).
- `sign.request.signer.signature_text` (Char) — typed-name fallback.
- `sign.request.signer.ip_address` / `user_agent` (Char, readonly) — captured at `mark_opened`, immutable thereafter.
- `sign.request.signer.opened_at` / `signed_at` (Datetime, readonly).

**Endpoints**: `/sign/<string:token>`, `/sign/<string:token>/submit`

### custom_spreadsheet — Custom Spreadsheet

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_spreadsheet` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_documents`, `custom_ai_bridge` |
| Models / routes / tests | 5 / 1 / 2 |
| Tags | ai, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

A workbook layer (`custom.spreadsheet.workbook`) for the platform that complements Odoo 19 CE's `spreadsheet` engine. The grid renderer remains delegated to CE — this module owns the metadata: tags, sharing, versioning, CSV import/export, "load records from any model" bulk-fill, and three AI helpers (Ask AI, formula suggestion, data-cleaning report) that flow through `custom.ai._recommend`.

Grid data is stored as JSON text in `data_json` (default `{"sheets":[{"name":"Sheet1","cells":{}}]}`); cells are keyed `"row_col"`. Every `data_json` write auto-snapshots the *previous* value into `custom.spreadsheet.version` (unless `spreadsheet_skip_versioning` context flag is set).

**How it works**

- User creates a `custom.spreadsheet.workbook` with a name, optional description, tags, owner; starts with an empty Sheet1.
- User edits the grid (UI delegated to CE `spreadsheet`) — every save passes `data_json` through `write()` which: detects changes, snapshots the old value as the next `custom.spreadsheet.version` row (`version_no` = previous max + 1), then super-writes.
- `action_open_import_wizard()` launches `custom.spreadsheet.import.wizard` to parse a CSV file (≤10 000 rows) and replace the target sheet via `_apply_csv_rows`.
- `action_export_csv()` materialises sheet 0 of the workbook into a downloadable `ir.attachment` (CSV), attaches it to the workbook chatter, and returns an `act_url` to `/web/content/<id>?download=1`.
- `action_load_from_model(model_name, domain, fields_list, sheet_name, append)` (also via `custom.spreadsheet.load.wizard`) pulls up to 10 000 records from any model with a configurable domain + field list, writes them as a header row + data rows into the named sheet. `append=True` appends below existing data.
- `action_ask_ai(question)` → AI mode `ask`; result text posted to chatter.
- `action_ai_formula_suggest(cell_ref, context_text)` → AI mode `formula`; result stored on `suggested_formulas` + chatter.
- `action_ai_data_clean()` → AI mode `clean`; result stored on `ai_clean_report` + chatter.
- All three AI calls build a payload via `_custom_ai_payload(question, mode, extra)` that includes `data_summary` (per-sheet row/col/cell counts + 25 sample cells) and a truncated 4 000-char excerpt of `data_json`.
- `action_generate_share_token()` mints a token; `share_url` exposes `{base}/custom_spreadsheet/share/<token>` for read-only HTML render.
- `action_view_versions()` opens the version list; `custom.spreadsheet.version` rows expose a one-click restore.

**Key models**

- `custom.spreadsheet.workbook` — Main entity; inherits `mail.thread`, `pdp.audited.mixin`.
- `custom.spreadsheet.version` — Immutable snapshot row (`version_no`, `data_json_snapshot`, `saved_by`, `note`).
- `custom.spreadsheet.tag` — Free-form tag dictionary (M2m on workbook).
- `custom.spreadsheet.import.wizard` (TransientModel) — CSV importer.
- `custom.spreadsheet.load.wizard` (TransientModel) — Load-from-model bulk-fill.

**Important fields**

- `custom.spreadsheet.workbook.data_json` (Text, default `{"sheets":[…]}`) — full grid state.
- `custom.spreadsheet.workbook.owner_id` (M2o res.users, tracked).
- `custom.spreadsheet.workbook.shared_user_ids` (M2m res.users) — explicit shares (read access governed by record rules in security).
- `custom.spreadsheet.workbook.tag_ids` (M2m custom.spreadsheet.tag).
- `custom.spreadsheet.workbook.is_published` (Boolean).
- `custom.spreadsheet.workbook.share_token` (Char, indexed, copy=False) + `share_url` (Char, computed).
- `custom.spreadsheet.workbook.suggested_formulas` (Text, readonly) — last AI formula response.
- `custom.spreadsheet.workbook.ai_clean_report` (Text, readonly) — last AI cleaning response.
- `custom.spreadsheet.workbook.version_ids` (One2many) / `version_count` (Integer, computed).
- `custom.spreadsheet.version.version_no` (Integer, monotonic per workbook).
- `custom.spreadsheet.version.data_json_snapshot` (Text) — full previous grid.
- `custom.spreadsheet.version.saved_by` (M2o res.users) / `note` (Char).
- Constants: `_AI_PAYLOAD_MAX_CHARS=4000`, `_MAX_IMPORT_ROWS=10000`, `_MAX_LOAD_RECORDS=10000`.

**Endpoints**: `/custom_spreadsheet/share/<string:token>`

### custom_studio_lite — Custom Studio Lite

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_studio_lite` |
| Version | 19.0.0.6.3 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `base`, `base_automation`, `custom_whatsapp` |
| Models / routes / tests | 8 / 0 / 5 |
| Tags | audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed. Written against version 19.0.0.1.0, module is now 19.0.0.6.3.

A minimal CE-friendly substitute for Odoo Enterprise Studio's custom-field manager. Admins declare custom fields against any model through DB records (`studio.custom.field`) rather than editing source code; clicking **Apply** materialises an `ir.model.fields` row on the target model.

The scope is deliberately narrow: **fields only**, not view inserts (despite the manifest summary mentioning view extensions, the model does not implement any `ir.ui.view` creation). Use this module for quick vertical-specific column additions; for anything more invasive, fork a proper module.

**How it works**

- Admin creates a `studio.custom.field` row: pick `model_id`, choose `field_type` from the supported list, set `name` (label) and `technical_name` (must match `^x_studio_[a-z0-9_]{1,60}$`), optionally `required` / `readonly` / `help_text`.
- For `selection` type, fill `selection_values` with one `key|label` line per option.
- Click `action_apply()` — the wizard creates (or updates if `ir_model_fields_id` already linked) the underlying `ir.model.fields` row via `sudo()`. State flips `draft` → `applied`; failures land in `error` with `last_error` populated. A PDP audit row is written for both success and failure paths.
- Once applied, the field is a real ORM column on the target model — visible to views, ORM, exports.

**Key models**

- `studio.custom.field` — Declarative descriptor for a single custom field; owns the lifecycle from draft to applied/error.

**Important fields**

- `studio.custom.field.technical_name` (Char, regex-validated) — must begin with `x_studio_`; uniqueness enforced per `(model_id, technical_name)`.
- `studio.custom.field.model_id` (M2o ir.model, ondelete=cascade) — target model; deletion of the model deletes the declaration.
- `studio.custom.field.model_name` (Char, related, stored) — denormalised technical model name for searching.
- `studio.custom.field.field_type` (Selection: char/text/integer/float/boolean/date/datetime/selection) — limited subset of Odoo field types.
- `studio.custom.field.selection_values` (Text) — newline-separated `key|label` pairs; parsed at apply time and serialised as `str(list[tuple])` into `ir.model.fields.selection`.
- `studio.custom.field.required` / `readonly` (Boolean) — propagated to the materialised field.
- `studio.custom.field.ir_model_fields_id` (M2o ir.model.fields, readonly, copy=False) — back-pointer to the materialised field; used to detect "update vs create" on re-apply.
- `studio.custom.field.state` (Selection draft/applied/error) — lifecycle marker.
- `studio.custom.field.last_error` (Text, readonly) — exception text from last failed apply.

### custom_todo — Custom Todo

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_todo` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_ai_bridge`, `project_todo` |
| Models / routes / tests | 1 / 0 / 0 |
| Tags | ai, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Extends CE `project_todo` with three productivity overlays on `project.task`: a pomodoro timer (`focus` → `break` → `idle` cycle with cron auto-transition), AI-powered task breakdown via `custom.ai._recommend` that creates real child tasks from the suggestion, and recurring template tasks (`custom.todo.template`, daily/weekly/monthly) that instantiate on schedule. Also ships a daily standup digest cron emailing each user their "done yesterday + in-progress today" task list.

**How it works**

- **Pomodoro:** User clicks `action_pomodoro_start_focus` on a task → `x_pomodoro_state='focus'` + stamp `x_pomodoro_started_at`. `action_pomodoro_tick` (callable from JS heartbeat or `cron_pomodoro_tick`) checks elapsed time vs `x_pomodoro_minutes_focus` (default 25); when exceeded → `break`. `break` exceeding `x_pomodoro_minutes_break` (default 5) → `idle` (cycle complete). Each transition posts a chatter note. `action_pomodoro_done` is a manual short-circuit to `done`.
- **AI breakdown:** User clicks `action_ai_breakdown` on a task → builds `{name, description[:4000]}` payload, calls `custom.ai._recommend(model="project.task", res_id=…, payload=…)`. The response text is stored on `x_ai_breakdown`. `_parse_ai_subtasks(result)` extracts `result["subtasks"]` (list of strings OR list of dicts with `text`/`name`/`title`); each becomes a real `project.task` child via `Task.create({name, parent_id, project_id, user_ids})` inheriting the first assignee of the parent. Chatter post summarises count of subtasks created.
- **Recurring templates:** Admin creates `custom.todo.template` rows with name, description, default assignee/project, recurrence (`none`/`daily`/`weekly`/`monthly`). `action_create_task` manually instantiates a task. `cron_create_recurring_todos` (scheduler) iterates active templates and instantiates whenever `last_created_at` is empty or older than the recurrence window (1d/7d/30d). `last_created_at` is stamped after creation.
- **Standup digest:** `cron_send_daily_standup` (scheduler) iterates all active internal users (`share=False`), computes `_standup_user_summary(user, yesterday, today)` returning `(done_yesterday, in_progress_today)` recordsets via Odoo 19 state codes (`1_done`/`1_canceled` for done; `01_in_progress`/`02_changes_requested`/`03_approved` for active), and sends `custom_todo.mail_template_daily_standup` with `done_tasks`/`in_progress_tasks`/`digest_date` context. Users with no activity are skipped.

**Key models**

- `project.task` (inherited) — adds pomodoro fields + AI breakdown text + the actions.
- `custom.todo.template` — Recurring task template.

**Important fields**

- `project.task.x_pomodoro_state` (Selection idle/focus/break/done, default `idle`).
- `project.task.x_pomodoro_minutes_focus` (Integer, default 25).
- `project.task.x_pomodoro_minutes_break` (Integer, default 5).
- `project.task.x_pomodoro_started_at` (Datetime) — phase start; used by `action_pomodoro_tick`.
- `project.task.x_ai_breakdown` (Text) — last AI breakdown result text.
- `custom.todo.template.recurrence_rule` (Selection none/daily/weekly/monthly, tracked).
- `custom.todo.template.default_user_id` (M2o res.users) / `default_project_id` (M2o project.project).
- `custom.todo.template.last_created_at` (Datetime, readonly) — last instantiation stamp; gates the cron.
- `custom.todo.template.is_active` (Boolean, tracked) — cron filter.

## Marketing & Communications (Pemasaran & Komunikasi)

### custom_affiliate — Custom Affiliate

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_affiliate` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `sale`, `mail` |
| Models / routes / tests | 5 / 1 / 0 |
| Tags | affiliate, marketing, attribution |

> Knowledge file is generator output, not human-reviewed.

**Declared models**: `custom.affiliate`, `custom.affiliate.click`, `custom.affiliate.conversion`, `custom.affiliate.link`, `custom.affiliate.payout`

**Endpoints**: `/affiliate/track`

### custom_appointments — Custom Appointments

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_appointments` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `mail`, `calendar`, `portal`, `website` |
| Models / routes / tests | 3 / 2 / 0 |
| Tags | appointment-booking, calendar, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Public-facing self-service appointment booking. Visitors hit `/book/<slug>` for a given `appointment.type`, see a generated slot grid built from the resource's working hours, submit a booking form, and create an `appointment.booking` that (if confirmed) materialises a `calendar.event` on the assigned resource's user calendar. Includes capacity-aware overlap protection and PDP audit (classification `pii`).

**How it works**

- HR/Admin creates `appointment.resource` (name, user_id, timezone default `Asia/Jakarta`, capacity default 1, `working_hours_start/end`, `working_days` CSV like `"1,2,3,4,5"` for Mon-Fri).
- HR/Admin creates `appointment.type` (name, `slug` unique, `duration_minutes`, `buffer_minutes`, `advance_notice_hours` default 4, `max_days_ahead` default 30, `require_confirmation`, `resource_ids` M2M to resources).
- Visitor opens `/book/<slug>` (auth=public, website=True). Controller searches for the active type by slug, picks the first active resource (`resource_ids.filtered("active")[:1]`), builds a slot grid via `_build_slots(atype, resource)`:
- Iterates `day in range(1, min(max_days_ahead+1, 6))` — capped at next 5 days regardless of `max_days_ahead`.
- Filters by `working_days` (ISO weekday).
- For each hour in `[working_hours_start..working_hours_end)`, emits `slot_dt.isoformat()` if `slot_dt >= now + advance_notice_hours`.
- Renders `custom_appointments.booking_page` with `atype`, `resource`, `slots`.
- Visitor POSTs `/book/<slug>/submit` with `start_dt`, `resource_id`, `customer_name`, `customer_email`, `customer_phone`, `notes`. CSRF is enforced (`csrf=True`).
- `appointment.booking.create` (sudo): assigns `name` from `ir.sequence` code `appointment.booking` (fallback `APT-???`); if the type has `require_confirmation=False`, state defaults to `confirmed`; then `_sync_calendar_event()` creates a `calendar.event` on `resource_id.user_id` (skipped if no user_id) with partner_ids = applicant partner if any.
- Capacity-aware `@api.constrains` `_check_slot` runs: blocks if `start_dt >= end_dt` or if overlap (sudo search of confirmed bookings with `start < self.end_dt AND end > self.start_dt`) count `>= resource_id.capacity`.
- Workflow transitions:
- `action_confirm()` — pending → confirmed (only from pending); syncs calendar.event; audit `appointment_confirm`.
- `action_cancel()` — any → cancelled; unlinks `calendar_event_id` if present; audit `appointment_cancel`.
- `action_done()` — → done; audit `appointment_done`.
- `action_no_show()` — → no_show; audit `appointment_no_show`.
- Renders `custom_appointments.booking_confirm` on success.

**Key models**

- `appointment.type` — Bookable service definition; unique `slug` constraint.
- `appointment.resource` — Provider/room/agent; working hours + days.
- `appointment.booking` — Booking record; inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`.

**Important fields**

- `appointment.type.slug` (Char, required, indexed, **unique**) — URL component for `/book/<slug>`.
- `appointment.type.duration_minutes` (Integer, default 30, required).
- `appointment.type.buffer_minutes` (Integer, default 0) — declared but **NOT used** in `_build_slots` or `_check_slot`.
- `appointment.type.advance_notice_hours` (Integer, default 4) — minimum lead time before booking.
- `appointment.type.max_days_ahead` (Integer, default 30) — but `_build_slots` caps at 5 days (`min(max_days_ahead+1, 6)`).
- `appointment.type.require_confirmation` (Boolean) — drives default state on create.
- `appointment.resource.timezone` (Char, default `Asia/Jakarta`) — declared but **not applied** when generating slots (controller uses `datetime.utcnow()`).
- `appointment.resource.capacity` (Integer, default 1) — overlap constraint pivot.
- `appointment.resource.working_days` (Char, default `"1,2,3,4,5"`) — CSV of ISO weekdays.
- `appointment.resource.working_hours_start` / `working_hours_end` (Float, defaults 9.0 / 17.0) — 24h decimal.
- `appointment.booking.state` (Selection: pending/confirmed/cancelled/done/no_show, default pending, tracked, indexed).
- `appointment.booking.start_dt` / `end_dt` (Datetime, required, tracked).
- `appointment.booking.calendar_event_id` (M2o `calendar.event`, readonly) — synced via `_sync_calendar_event`.
- `appointment.booking.name` (Char, default "New") — assigned from sequence code `appointment.booking`.

**Endpoints**: `/book/<string:slug>`, `/book/<string:slug>/submit`

### custom_email_marketing — Custom Email Marketing

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_email_marketing` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_pdp_consent`, `mass_mailing`, `queue_job` |
| Models / routes / tests | 3 / 0 / 2 |
| Tags | marketing, pdp, audit-trail, ab-testing |

> Knowledge file is generator output, not human-reviewed.

Extends CE `mass_mailing` with EE-equivalent and UU-PDP-specific features: a reusable HTML template gallery + apply wizard, a A/B testing harness (`custom.email.ab.test`) that clones the parent mailing into two variants and picks a winner by opens/clicks/replies, a per-mailing PDP consent filter that drops recipients without an active `pdp.consent` for the chosen purpose, a dynamically-rendered UU PDP unsubscribe footer (Bahasa Indonesia) appended at send time, and a 3-strike auto-blacklist on `mailing.trace.set_bounced`.

Delivery channel remains exactly the standard `mass_mailing` SMTP path — this module does NOT add WhatsApp/SMS, only extends the existing email pipeline.

**How it works**

- A user designs a mailing in CE `mass_mailing`. They can click "Apply Template" → opens `custom.email.apply.template.wizard` which fetches a `custom.email.template.gallery` row and writes `subject` + `body_arch` + `body_html` onto the mailing, plus `x_gallery_template_id` for telemetry, and bumps `times_used`.
- Optionally the user sets `x_consent_purpose_id` on the mailing (an existing `pdp.consent.purpose` like "marketing").
- On send (`_action_send_mail` override): if `x_consent_purpose_id` is set, `_filter_recipients_by_consent(res_ids)` resolves each record's partner and calls `pdp.consent.check_consent(partner, purpose_code)`; recipients without active consent are removed and the dropped count is written to `x_consent_filtered_count`.
- If `x_uu_pdp_footer` is True, `_get_pdp_footer_html()` builds an Indonesian-language footer with the controller name (`company.display_name`), DPO email (`company.x_pdp_dpo_email || company.email`), and the standard one-click unsubscribe URL; the footer is temporarily appended to `body_html` for the call to super then restored in `finally`.
- For A/B testing the user creates a `custom.email.ab.test` linked to a parent mailing with two subject+body variants and `split_pct`. `action_split_send()` clones the parent into `[A]` and `[B]` mailings, shuffles the audience, splits it by `split_pct`, calls `action_send_mail(res_ids=...)` on each variant, and schedules `evaluate_after = now + 24h`.
- The cron `cron_evaluate_winner` (every 30 min or as scheduled) picks running tests past their `evaluate_after` and calls `_evaluate_one`, which counts `mailing.trace` events (opens/clicks/replies) per variant, writes `variant_a_score / variant_b_score / winner`, and flips state to `concluded`.
- Tracking: every `mailing.trace.set_opened()` bumps `x_open_count` and stamps `x_first_open_at` on first open; `set_clicked` bumps `x_click_count`; `set_bounced` calls `_blacklist_bounce()` which adds the email to `mail.blacklist` after 3 distinct hard-bounce traces.

**Key models**

- `custom.email.template.gallery` — Reusable HTML template with category/language/thumbnail, `times_used` counter, suggested mailing lists.
- `custom.email.ab.test` — A/B run header (`draft/running/concluded`), two variant subject+body pairs, split %, metric, winner + scores.
- `mailing.mailing` (inherited) — Adds `x_consent_purpose_id`, `x_gallery_template_id`, `x_uu_pdp_footer`, `x_consent_filtered_count`; overrides `_action_send_mail`.
- `mailing.trace` (inherited) — Adds `x_first_open_at`, `x_open_count`, `x_click_count`; overrides `set_opened / set_clicked / set_bounced`.

**Important fields**

- `mailing.mailing.x_consent_purpose_id` (M2o `pdp.consent.purpose`) — gating purpose; recipients without active consent are dropped.
- `mailing.mailing.x_uu_pdp_footer` (Boolean, default True) — UU PDP footer toggle.
- `mailing.mailing.x_consent_filtered_count` (Integer, readonly) — # recipients excluded on last send.
- `mailing.mailing.x_gallery_template_id` (M2o) — telemetry back-link to gallery.
- `custom.email.ab.test.split_pct` (Integer, default 50, constrained 1..99) — % to variant A.
- `custom.email.ab.test.winner_metric` (Selection: opens/clicks/replies) — score metric.
- `custom.email.ab.test.evaluate_after` (Datetime) — cron gate (`sent_at + 24h`).
- `custom.email.ab.test.variant_a_score / variant_b_score / winner` (Integer/Selection) — outcome.
- `mailing.trace.x_first_open_at / x_open_count / x_click_count` (Datetime/Integer) — engagement counters.
- `custom.email.template.gallery.category` (Selection: welcome/newsletter/promo/transactional/reminder) — taxonomy.
- `HARD_BOUNCE_BLACKLIST_THRESHOLD = 3` (module constant) — distinct hard-bounce traces per email before auto-blacklist.

### custom_events — Custom Events

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_events` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_pdp_consent`, `event`, `website_event_track`, `survey`, `custom_whatsapp`, `custom_payment_id` |
| Models / routes / tests | 1 / 0 / 0 |
| Tags | marketing, whatsapp, qr-checkin, pdp, barcode-scan |

> Knowledge file is generator output, not human-reviewed.

Extends CE `event.event` + `event.registration` with EE-equivalent features adapted to the Indonesian market: per-registration QR token + public QR check-in route, WhatsApp ticket delivery via `custom_whatsapp` templates, multi-tier sponsor tracking (`custom.event.sponsor`), multi-session via standard `event.track` (`x_has_tracks` flag), a daily post-event survey cron, and PDP consent gating for marketing follow-up. Capacity / waitlist is implemented by an `action_promote_waitlist` button.

**How it works**

- An organiser configures an `event.event`: optionally sets `x_whatsapp_ticket_template_id`, picks `x_marketing_consent_purpose`, enables `x_qr_checkin_enabled`, flips `x_has_tracks` for multi-session, links `x_post_event_survey_id`, sets `x_end_date` to override `date_end`.
- Sponsors are added as `custom.event.sponsor` rows (tier=platinum/gold/silver/bronze, logo, `amount_paid`, benefits, `website_url`).
- A visitor registers; `event.registration.create` auto-generates `x_qr_token = secrets.token_urlsafe(16)`.
- Organiser clicks "Send WhatsApp Ticket" → `action_send_whatsapp_ticket()` creates one `whatsapp.message` per registration using the event template + partner phone, calls `action_send()`, and stamps `x_whatsapp_ticket_sent=True`.
- At the door, a kiosk hits `/custom_events/checkin/<token>` (controller in this module, not shown in models) which calls `action_qr_checkin(token)` → returns a JSON dict with `ok / already / attendee / event / checked_in_at`. State of CE `event.registration` is flipped to `done` (`attended`) when the field exists.
- Manual check-in from the form: `action_manual_checkin()` re-uses the QR path.
- Daily cron `_cron_send_post_event_survey` finds events whose `x_end_date or date_end < now`, not yet `x_post_event_survey_sent`, with a survey set; for each open registration with email, sends `mail_template_post_event_survey` carrying the survey start URL.
- `action_promote_waitlist()` (event-level) selects registrations in state `waitlist` and calls `action_promote_from_waitlist()` on them (method assumed to exist on the inherited CE event.registration; not defined in this module).

**Key models**

- `event.event` (inherited) — Adds WhatsApp template, QR enable, sponsors, tracks flag, post-event survey + extended end date.
- `event.registration` (inherited) — Adds QR token, check-in stamps, WhatsApp-sent flag, QR check-in action.
- `custom.event.sponsor` — Per-event sponsor with tier, logo, paid amount, benefits, website.

**Important fields**

- `event.event.x_whatsapp_ticket_template_id` (M2o `whatsapp.template`) — template for ticket delivery.
- `event.event.x_marketing_consent_purpose` (Selection: event_followup / none) — PDP gate for post-event marketing.
- `event.event.x_qr_checkin_enabled` (Boolean, default True) — guards public check-in route.
- `event.event.x_has_tracks` (Boolean) — UI hint to expose tracks.
- `event.event.x_post_event_survey_id` (M2o `survey.survey`) — survey link sent after event.
- `event.event.x_post_event_survey_sent` (Boolean, copy=False) — idempotency latch for cron.
- `event.event.x_end_date` (Datetime) — overrides `date_end` for survey cron timing.
- `event.registration.x_qr_token` (Char, indexed, copy=False, secrets.token_urlsafe(16)) — check-in identifier.
- `event.registration.x_checked_in_at` / `x_checked_in_by_user_id` (Datetime, M2o) — check-in audit.
- `event.registration.x_whatsapp_ticket_sent` (Boolean, tracked) — idempotency for WA send.
- `custom.event.sponsor.tier` (Selection: platinum/gold/silver/bronze, indexed).
- `custom.event.sponsor.amount_paid` (Monetary, currency from event.company).

### custom_forum — Custom Forum

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_forum` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_ai_bridge`, `website_forum` |
| Models / routes / tests | 1 / 0 / 0 |
| Tags | knowledge, ai, moderation, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Extends CE `website_forum` with three capabilities: AI toxicity / spam moderation that can auto-close posts and notify moderators (via `custom_ai_bridge`), PDP-aware author display masking (`Anonymous-<id>` alias on `display_name`), and Indonesian-tier reputation badges on `res.users` derived from karma. A trending-topics aggregator (`custom.forum.trending.topic`) rebuilds top-N tag rankings per period via cron. An hourly cron batch-scores unscored active posts.

**How it works**

- A user posts on the forum (`forum.post`, CE-managed state `active/pending/close/offensive/flagged`).
- The hourly cron `cron_ai_moderate_pending_posts` selects up to 50 posts with `x_ai_moderation_score is False AND state=active` and calls `action_ai_moderate()`.
- `action_ai_moderate()` per post: calls `custom.ai._recommend` with `{content: post.content[:4000]}`, parses `score` (float) + `label` (mapped via `_parse_ai_label`: toxic/offensive/abuse → `flag`; junk/advertisement/promotion → `spam`; uncertain/borderline → `review`; else `safe`).
- Writes `x_ai_moderation_score`, `x_ai_moderation_label`, `x_ai_moderated_at`.
- If label ∈ {flag, spam}: posts a chatter note, flips post state to `close` (only if currently in `active/pending`), schedules `mail.mail_activity_data_todo` for every user in `custom_forum.group_manager`.
- If label=spam AND score > `custom_forum.spam_threshold` (default 0.8): emails the manager group via `message_post(partner_ids=...)`.
- Helpful-vote count: `forum.post.vote.create/write/unlink` triggers `_compute_x_helpful_count` (`sum(1 for v in vote_ids if str(v.vote)=='1'`).
- Author masking: when `x_pdp_author_masked=True`, `_compute_display_name` (override of CE) appends `— Anonymous-<id>` to the post's `display_name`. Helper `_get_masked_author_label()` for templates.
- Reputation: `res.users.x_indonesia_badge` (computed, stored) maps `karma` to one of `pemula(0+) / lanjut(200+) / ahli(1000+) / master(5000+)`.
- Trending: `cron_compute_trending` rebuilds `custom.forum.trending.topic` for periods `day/week/month`. Score = `post_count*2 + view_count`; top 10 per forum per period. Old rows for the period are unlinked before rewriting.

**Key models**

- `forum.post` (inherited) — Adds AI moderation fields, helpful count, PDP masking flag, masked display name.
- `forum.post.vote` (inherited) — Recomputes parent's `x_helpful_count` on every CRUD.
- `custom.forum.trending.topic` — Aggregated (forum_id, tag_id, period) trend row; unique constraint.
- `res.users` (inherited) — Adds `x_indonesia_badge` derived from karma.

**Important fields**

- `forum.post.x_ai_moderation_score` (Float 0..1) — toxicity probability.
- `forum.post.x_ai_moderation_label` (Selection: safe/review/flag/spam, default safe).
- `forum.post.x_ai_moderated_at` (Datetime) — last scoring.
- `forum.post.x_pdp_author_masked` (Boolean) — flips display_name to `<title> — Anonymous-<id>`.
- `forum.post.x_helpful_count` (Integer, computed, stored) — count of `vote==+1`.
- `custom.forum.trending.topic.score` (Integer) — `post_count*2 + view_count`.
- `custom.forum.trending.topic.period` (Selection: day/week/month) — refresh cadence.
- `custom.forum.trending.topic.rank` (Integer) — per-forum 1..10.
- `res.users.x_indonesia_badge` (Selection: pemula/lanjut/ahli/master) — karma tier.
- Module constants: `_DEFAULT_SPAM_THRESHOLD = 0.8`, `_AI_BATCH_LIMIT = 50`, `_TOP_N = 10`, `_PERIOD_DAYS = {day:1, week:7, month:30}`.
- `ir.config_parameter` `custom_forum.spam_threshold` — runtime override of spam threshold.

### custom_livechat — Custom Live Chat Extensions

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_livechat` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_ai_bridge`, `custom_helpdesk`, `im_livechat` |
| Models / routes / tests | 3 / 0 / 2 |
| Tags | helpdesk, livechat, ai, audit-trail, pdp |

> Knowledge file is generator output, not human-reviewed.

Extends CE `im_livechat` with EE-equivalent features: convert an active chat (`discuss.channel`) into a `helpdesk.ticket` with priority + last-50-message transcript, canned responses with `:shortcut` expansion, regex-driven chatbot scripts, simple skill-based + round-robin operator routing on the first inbound message, AI suggested reply via `custom_ai_bridge` with payload-hash caching, and a 1-5 visitor satisfaction rating with feedback.

This module is the operator-side companion to the platform's helpdesk: live chat is for synchronous conversation; once it needs to persist as a ticket, escalation creates exactly one `helpdesk.ticket` and links both records.

**How it works**

- A visitor opens a livechat → CE creates a `discuss.channel` of type `livechat`. On the first `message_post` (this module's override) where no `livechat_operator_id` is assigned, `_custom_livechat_pick_operator(body_text)` runs: if `im_livechat.channel.x_skill_tags` contains any keyword appearing in the visitor message, the first matching operator wins; otherwise round-robin by least-busy (count of open channels per operator).
- The agent types `:shortcut` → JS asset (`canned_response_composer.js`) calls `custom.livechat.canned.response.expand_canned(shortcut)` which returns `{shortcut, body, name, found}` and increments `times_used`.
- A chatbot script (`custom.livechat.chatbot.script`) drives the early turns: each `custom.livechat.chatbot.step` has `step_type` ∈ `text / question / forward_to_operator / end`. `get_next_step(current_id, user_msg)` matches `expected_answers` regex (comma-separated) case-insensitively; on match → next sequential step; on miss → `next_step_default`. `forward_to_operator` / `end` terminate.
- The agent clicks "AI Suggested Reply" → `action_ai_suggest_reply()` builds a 10-message history payload, computes a sha1 hash, skips the AI call if `x_last_ai_query == payload_hash` (cache reuse), otherwise calls `custom.ai._recommend` and writes `x_ai_suggested_text` + cache key. The JS asset `ai_reply_clipboard.js` provides "Insert into Reply".
- The agent clicks "Escalate to Helpdesk" → `action_escalate_to_helpdesk()` builds an HTML transcript from the last 50 messages, picks the non-internal partner from `channel_partner_ids`, maps `x_helpdesk_priority` (`low/normal/high/urgent`) → ticket priority `0/1/2/3`, creates a `helpdesk.ticket`, links both ways (`x_helpdesk_ticket_id`, `x_escalated_to_helpdesk=True`), posts notes on both records, and returns an `act_window` opening the ticket. Idempotent: already-escalated channels just reopen the existing ticket.
- "Request Rating" → `action_request_visitor_rating()` flips `x_rating_requested=True` and posts a prompt. `submit_visitor_rating(channel_id, rating, feedback)` validates `rating ∈ {1..5}` and writes `x_rating` + `x_rating_feedback`.

**Key models**

- `discuss.channel` (inherited) — Adds escalation, AI suggest, routing override, satisfaction rating fields.
- `custom.livechat.canned.response` — Shortcut → HTML body lookup (`mail.thread`), unique shortcut.
- `custom.livechat.chatbot.script` — Script header, link to `im_livechat.channel`, `is_active`, `step_ids`.
- `custom.livechat.chatbot.step` — Ordered step (text/question/forward_to_operator/end) with regex `expected_answers` and `next_step_default`.
- `im_livechat.channel` (inherited) — Adds `x_skill_tags` (comma-separated) consumed by routing.

**Important fields**

- `discuss.channel.x_helpdesk_ticket_id` (M2o `helpdesk.ticket`) — escalation link.
- `discuss.channel.x_helpdesk_priority` (Selection: low/normal/high/urgent, default normal) — maps to ticket priority 0..3.
- `discuss.channel.x_escalated_to_helpdesk` (Boolean) — idempotency latch.
- `discuss.channel.x_ai_suggested_text` (Text) / `x_last_ai_query` (Char) — last AI suggestion + sha1 payload hash for caching.
- `discuss.channel.x_rating` (Selection 1..5) / `x_rating_feedback` (Text) / `x_rating_requested` (Boolean).
- `custom.livechat.canned.response.shortcut` (Char, required, unique, min length 2, no spaces).
- `custom.livechat.canned.response.times_used` (Integer, telemetry).
- `custom.livechat.chatbot.step.step_type` (Selection) — drives `get_next_step` dispatch.
- `custom.livechat.chatbot.step.expected_answers` (Char) — comma-separated regex patterns, case-insensitive.
- `im_livechat.channel.x_skill_tags` (Char) — comma-separated lowercase keywords for skill routing.

### custom_marketing_automation — Custom Marketing Automation

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_marketing_automation` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_pdp_consent`, `mail` |
| Models / routes / tests | 4 / 0 / 0 |
| Tags | marketing, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Lightweight marketing-automation engine: define `marketing.segment` (domain on `res.partner`), build a `marketing.campaign` with ordered `marketing.campaign.step` rows (email / wait / tag), and let `_cron_tick` advance each `marketing.participant` through the steps. PDP-marketing-consent is enforced at campaign start by intersecting segment partners with `pdp.consent` records under the `consent_purpose_marketing` purpose.

This is the platform's BRD-only marketing-automation module; it is intentionally smaller than Odoo EE's marketing.automation app and uses `mail.template` for delivery (no separate channel).

**How it works**

- A user creates a `marketing.segment` with `model_id = res.partner` and a `filter_domain` (validated by `_check_domain`).
- A user creates a `marketing.campaign` (draft), assigns the segment, and adds `marketing.campaign.step` rows ordered by `sequence`. Steps are one of `email` (uses `mail_template_id`), `wait`, `tag` (uses `partner_category_id`).
- `action_start()` resolves segment partners, optionally filters by valid marketing consent (`pdp.consent` with `purpose_id = consent_purpose_marketing` and `withdrawn_at = False`), and creates one `marketing.participant` per partner pointing at the first step.
- `_cron_tick` (scheduled action `data/ir_cron_data.xml`) selects all active participants in running campaigns whose `next_action_at <= now()` and calls `_advance()` per participant.
- `_advance()` executes the current step: email → `mail.template.send_mail(force_send=False)` plus PDP audit row; tag → adds `partner_category_id` to `res.partner.category_id`; wait → no-op. It then advances the pointer to the next step, scheduling `next_action_at = now + next_step.wait_hours` (if wait) or +1h otherwise.
- When there are no more steps, `_complete()` flips state to `completed` and stamps `completed_at`.
- `action_opt_out()` (per participant) writes `state=opted_out` and audits.
- `action_pause / action_resume / action_complete` are campaign-level state buttons.

**Key models**

- `marketing.segment` — Saved domain over `res.partner`; `resolve_partners()` returns the matching recordset.
- `marketing.campaign` — Workflow record (`draft/running/paused/completed`) with `mail.thread`.
- `marketing.campaign.step` — Ordered step row (`email/wait/tag`).
- `marketing.participant` — Per-partner walker; inherits `pdp.audited.mixin` (classification `pii`).

**Important fields**

- `marketing.segment.filter_domain` (Char, default `"[]"`) — Python list literal validated via `ast.literal_eval`.
- `marketing.campaign.state` (Selection: draft/running/paused/completed) — drives the cron's selection.
- `marketing.campaign.require_marketing_consent` (Boolean, default True) — gates participant creation by `pdp.consent`.
- `marketing.campaign.segment_id` — required link to the audience.
- `marketing.campaign.step_ids` — One2many, ordered by `sequence`.
- `marketing.campaign.step.kind` (Selection: email/wait/tag) — execution dispatch key.
- `marketing.campaign.step.mail_template_id` / `wait_hours` (default 24.0) / `partner_category_id` — per-kind payload.
- `marketing.participant.state` (Selection: active/completed/opted_out) — index `+ unique (campaign_id, partner_id)`.
- `marketing.participant.next_action_at` (Datetime, default now) — the cron's tick gate.

### custom_sms_id — Custom SMS Indonesia

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_sms_id` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_pdp_consent`, `mail`, `sms` |
| Models / routes / tests | 5 / 0 / 0 |
| Tags | marketing, pdp, audit-trail, crm |

> Knowledge file is generator output, not human-reviewed.

Canonical SMS messaging channel for the platform. Multi-provider SMS adapter for Indonesian SMB tenants supporting Zenziva (Indonesia local) and Twilio (global), with a pluggable adapter pattern (`custom.sms.adapter.base` + per-provider AbstractModel subclasses), PDP-consent gating on marketing sends, and bridging through the standard Odoo `sms.sms` queue.

This is the BRD-canonical landing place for any "send SMS" requirement — OTP, transactional notifications, and (consented) marketing campaigns. Vertical modules should create a `custom.sms.message` and call `action_send`, not implement a provider HTTP client.

**How it works**

- An admin creates a `custom.sms.account` choosing `provider` (`zenziva` / `twilio`) and supplying provider-shaped credentials (Zenziva: `userkey` + `passkey`; Twilio: `account_sid` + `auth_token`). `sandbox_mode=True` by default short-circuits real HTTP.
- A vertical creates a `custom.sms.message(account_id, to_phone, body, purpose)` where `purpose ∈ {otp, transactional, marketing}`.
- `action_send()` resolves consent: looks up the purpose-mapped code in `_PURPOSE_CONSENT_CODE` (`marketing -> sms_marketing`, `transactional`/`otp -> sms_transactional`) and calls `pdp.consent.check_consent(partner, code)`. If `purpose == 'marketing'` and consent missing -> `UserError`. Other purposes log-warn and proceed.
- Adapter dispatch: `custom.sms.adapter.base._get_for_account(account)` resolves to `custom.sms.adapter.zenziva` or `custom.sms.adapter.twilio`. The adapter's `send(account, to_phone, body, purpose=)` returns `{ok, provider_message_id, message}`.
- HTTP layer (`adapter_base._post`): 3 retries, exponential backoff (1/2/4s), `Retry-After` honoured on 429, per-account circuit breaker (10 failures within 60s -> open for 5min). Sandbox skips HTTP entirely.
- On success: `state = 'sent'`, `provider_message_id` stamped, `sent_at = now`. On failure: `state = 'failed'`, `error_message` set, never re-raises.
- Bridge: `sms.sms._send` is overridden — when an active `custom.sms.account` exists for the current company, the SMS is routed through the custom adapter instead of Odoo IAP; otherwise it falls back to upstream IAP send. Sent rows store `x_custom_account_id` for traceability.

**Key models**

- `custom.sms.account` — Per-company per-provider configuration; `sender_id`, `sandbox_mode`, credentials. `action_test_connection` probes via the resolved adapter.
- `custom.sms.message` — Outbound queue row; inherits `mail.thread` + `pdp.audited.mixin`.
- `custom.sms.adapter.base` (AbstractModel) — Dispatcher (`_get_for_account`) + shared HTTP helper `_post` with retry/breaker. Defines `send`/`test_connection`/`poll_status` abstract API.
- `custom.sms.adapter.zenziva` (AbstractModel, inherits base) — Real form-encoded POST to `https://console.zenziva.net/reguler/api/sendsms/`; parses `status=1`/`messageid` JSON response (handles `data`/`messagedata` variants).
- `custom.sms.adapter.twilio` (AbstractModel, inherits base) — Twilio provider slot.
- `sms.sms` (inherited) — `_send` override; adds `x_custom_account_id` traceability field.

**Important fields**

- `custom.sms.account.provider` (Selection: zenziva/twilio) — drives adapter resolution.
- `custom.sms.account.sandbox_mode` (Boolean, default True) — skip real HTTP; return synthetic `zenziva_sandbox_<hex>` ids.
- `custom.sms.account.userkey` / `passkey` (Char, passkey group-gated `custom_sms_id.group_manager`) — Zenziva credentials.
- `custom.sms.account.account_sid` / `auth_token` (Char, auth_token group-gated) — Twilio credentials.
- `custom.sms.account.sender_id` (Char, default `CUSTOM`) — alphanumeric sender ID / shortcode.
- `custom.sms.message.purpose` (Selection: otp/transactional/marketing) — drives consent gating severity (hard-gate marketing only).
- `custom.sms.message.state` (Selection: draft/queued/sent/delivered/failed, tracking).
- `custom.sms.message.consent_verified` (Boolean, readonly) — true iff PDP consent check passed pre-send.
- `custom.sms.message.provider_message_id` (Char, readonly) — upstream id returned on accept.
- `sms.sms.x_custom_account_id` (M2o `custom.sms.account`, readonly) — set automatically when routed through the custom adapter.

### custom_social — Custom Social

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_social` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `mail` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | marketing, social-media, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

A minimal social-media account + outbound post scheduler. Stores `social.account` rows per (`platform`, `handle`) with an encrypted API token (via `custom.ir.config.get_encrypted`), and `social.post` records that move through `draft → scheduled → published / failed / cancelled`. A daily cron picks scheduled posts whose `scheduled_at` is in the past and calls `_publish()` — which currently writes a synthetic `external_post_id` (`"manual-<iso>"`) without actually pushing to any platform. Provider-specific adapters are referenced in the docstring but NOT implemented in this module.

**How it works**

- Admin registers a `social.account` per platform (facebook/instagram/x/linkedin/tiktok/youtube) with a handle. The encrypted token is stored under `custom_social.api_token.<account_id>` via `custom.ir.config`; `api_token_set` is a compute that surfaces presence to the UI.
- A user drafts a `social.post` (required `account_id`, `body`, `scheduled_at`).
- `action_schedule()` flips draft→scheduled (`UserError` if not draft) and writes a PDP audit row.
- `action_publish_now()` calls `_publish()` directly. `_publish()` is the per-platform adapter dispatch hook; the default in this module just synthesises `external_post_id = "manual-<iso-now>"`, stamps `published_at`, audits, and writes state=published. On exception it sets state=failed + `last_error`.
- `_cron_publish_due` (scheduled in `data/ir_cron_data.xml`) every tick searches scheduled posts past `scheduled_at` and calls `_publish()` per post (best-effort, logged on failure).
- `action_cancel()` cancels any non-published post.

**Key models**

- `social.account` — `(platform, handle)` unique; holds metadata + encrypted-token presence flag.
- `social.post` — Outbound post record (`mail.thread + pdp.audited.mixin`, classification `public`).

**Important fields**

- `social.account.platform` (Selection: facebook/instagram/x/linkedin/tiktok/youtube) — channel taxonomy.
- `social.account.handle` (Char, required) — `@handle` or page id; unique per platform.
- `social.account.api_token_set` (Boolean, computed) — non-stored compute over `custom.ir.config.get_encrypted`.
- `social.post.state` (Selection: draft/scheduled/published/failed/cancelled) — main workflow.
- `social.post.scheduled_at` (Datetime, required) — cron gate.
- `social.post.published_at` (Datetime, readonly) — set by `_publish()`.
- `social.post.external_post_id` (Char, readonly) — platform-issued id; currently `"manual-<iso>"`.
- `social.post.last_error` (Text, readonly) — captured exception string on failure.
- `social.post.media_attachment_id` (M2o `ir.attachment`) — optional image/video.

### custom_survey — Custom Survey

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_survey` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `survey`, `custom_hr_appraisal`, `mail` |
| Models / routes / tests | 1 / 0 / 2 |
| Tags | survey, nps, certification, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Extends CE `survey` with EE-gap SMB features: a survey-kind taxonomy (employee_pulse / customer_nps / training_feedback / exit_interview), a certification flow with passing-score + HTML certificate template + email delivery, per-question weighted scoring rolled up into `survey.user_input.x_weighted_score`, NPS summaries with promoter/passive/detractor buckets and CSV export, three-tier anonymity (fully_anonymous strips partner_id from answers), and an optional link to `appraisal.appraisal` that auto-advances appraisal state to `self_review` on first survey completion.

**How it works**

- An admin creates a `survey.survey` and picks `x_survey_kind`. For NPS surveys they pick `x_nps_question_id` (the 0-10 numeric question). For certification surveys they enable `x_is_certification`, set `x_certification_passing_score` (% threshold), provide `x_certificate_template` (HTML with `{participant_name}, {survey_title}, {score}, {issue_date}, {valid_until}` placeholders), and `x_certificate_validity_months`. For appraisal-linked surveys they pick `x_target_appraisal_id`. Anonymity is set via `x_anonymity` (`fully_anonymous / partial / identified`).
- Per-question weight is set on `survey.question.x_score_weight`.
- A respondent fills the survey. On `_create_answer`, if the survey is `fully_anonymous` the new `survey.user_input` has `partner_id`, `email`, `nickname` zeroed (best-effort).
- On submission `_action_done` runs:
- `_compute_weighted_score` recomputes `x_weighted_score = Σ(answer_score × weight) / Σ(max_score × weight) × 100`. `max_score` is the max positive `answer_score` among `suggested_answer_ids`; falls back to 10 for numeric scales.
- If `x_is_certification` and score ≥ passing → `action_issue_certificate(user_input)` renders the HTML template via `.format(...)`, tries `ir.actions.report._run_wkhtmltopdf` to make a PDF (falls back to HTML attachment), attaches to the user_input, and emails the participant.
- If `x_target_appraisal_id` is set → post a note on the appraisal; if appraisal state is `draft` flip to `self_review`.
- For NPS reporting, an admin creates a `custom.survey.nps.summary` with `survey_id`, `date_from`, `date_to`. `_compute_nps` buckets `survey.user_input.line.value_numerical_box` (or `answer_score`) per response: 9-10 → promoter, 7-8 → passive, 0-6 → detractor; `nps_score = (promoter% - detractor%)`.
- `action_export_csv` builds a CSV of selected summaries and returns a download URL.

**Key models**

- `survey.survey` (inherited) — Kind, NPS question, certification, anonymity, appraisal link.
- `survey.question` (inherited) — Adds `x_score_weight`.
- `survey.user_input` (inherited) — Adds `x_weighted_score` (computed, stored) and overrides `_action_done`.
- `custom.survey.nps.summary` — Per-survey, per-date-range NPS report row (`mail.thread`).

**Important fields**

- `survey.survey.x_survey_kind` (Selection: employee_pulse/customer_nps/training_feedback/exit_interview/other).
- `survey.survey.x_nps_question_id` (M2o `survey.question`, domain=`survey_id`) — the 0-10 question.
- `survey.survey.x_target_appraisal_id` (M2o `appraisal.appraisal`) — auto-advances draft → self_review on first completion.
- `survey.survey.x_is_certification` (Boolean) / `x_certification_passing_score` (Float, default 70.0) / `x_certificate_validity_months` (Integer, default 12) / `x_certificate_template` (Html, sanitize=False).
- `survey.survey.x_anonymity` (Selection: fully_anonymous / partial / identified, default partial).
- `survey.question.x_score_weight` (Float, default 1.0).
- `survey.user_input.x_weighted_score` (Float, computed, stored) — percentage 0..100.
- `custom.survey.nps.summary.nps_score` (Float, computed) — range -100 .. +100.
- `custom.survey.nps.summary.promoter_count / passive_count / detractor_count / response_count` (Integer, computed, stored).

### custom_voip — Custom VoIP

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_voip` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `mail` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | voip, crm, pdp, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Lightweight VoIP integration module providing a provider-agnostic abstraction over SIP/PBX backends (Asterisk AMI, generic webhook, Twilio, or manual logging only) plus a persistent call log (`voip.call`) audited under PDP as PII (phone numbers + recording URLs).

Surfaces a click-to-call button on `res.partner` and a smart-count link to the partner's call history. The actual upstream call placement is stubbed — only the bookkeeping side is implemented at this version.

**How it works**

- An admin creates a `voip.provider` row choosing a `kind` (`manual` / `webhook` / `asterisk` / `twilio`) and optionally stores an auth token through `custom.ir.config.get_encrypted` under the key `custom_voip.auth_token.<provider_id>`.
- From a partner form a user hits "Call" -> `res.partner.action_voip_call()` -> picks the lowest-sequence active provider and `voip.call.log_outbound(...)` creates a placeholder `voip.call` row in direction `outbound`, writes a `pdp.audited.mixin` audit entry (event `voip_outbound_started`).
- The actual telephone leg is handled outside Odoo (Asterisk/Twilio). Status is reflected back manually via `action_mark_answered` / `action_mark_missed` / `action_end`.
- `action_end` stamps `ended_at` (which feeds the stored compute `duration_seconds`) and writes a second audit row `voip_call_ended` carrying `duration_seconds` + `outcome`.
- A partner's smart button `action_view_voip_calls` filters `voip.call` by `partner_id`.

**Key models**

- `voip.provider` — Per-company configuration row; stores `kind`, optional `api_base_url`, `account_sid`, `caller_id`, and computes `auth_token_set` by probing `custom.ir.config` encrypted storage.
- `voip.call` — Call log; inherits `mail.thread` + `pdp.audited.mixin` (classification `pii`). Stores direction, partner, user, other_number, timestamps, outcome, optional `recording_url`.
- `res.partner` (inherited) — Adds smart count `x_custom_voip_call_count` and the `action_voip_call` / `action_view_voip_calls` buttons.

**Important fields**

- `voip.provider.kind` (Selection: manual/webhook/asterisk/twilio) — drives downstream dispatch shape (currently all paths use the same placeholder log).
- `voip.provider.auth_token_set` (Boolean, computed) — true iff a secret exists under `custom_voip.auth_token.<id>` in `custom.ir.config`.
- `voip.call.direction` (Selection: inbound/outbound) — required.
- `voip.call.outcome` (Selection: answered/missed/voicemail/busy/failed) — settable via `action_mark_*` helpers.
- `voip.call.other_number` (Char, indexed, required) — the remote leg; the recipient on outbound or caller on inbound.
- `voip.call.duration_seconds` (Integer, stored compute from `started_at`/`ended_at`) — zero until `ended_at` is set.
- `voip.call.recording_url` (Char) — opaque link to the provider's stored recording, treated as PII.

### custom_whatsapp — Custom WhatsApp

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_whatsapp` |
| Version | 19.0.0.4.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_ai_bridge`, `custom_pdp_audit`, `custom_pdp_consent`, `custom_pdp_core`, `mail`, `queue_job`, `sale_management`, `account`, `custom_helpdesk` |
| Models / routes / tests | 4 / 1 / 3 |
| Tags | whatsapp, marketing, pdp, audit-trail, crm, helpdesk |

> Knowledge file is generator output, not human-reviewed.

Canonical WhatsApp messaging channel for the platform. Implements a Meta WhatsApp Cloud API adapter (with a Twilio WhatsApp provider slot) targeted at Indonesian SMB tenants where WhatsApp is the dominant customer-comms channel. Provides per-company account configuration, Meta-approved template management with status polling, PDP-consent-gated outbound queue, async dispatch through `queue_job`, and a public webhook controller for inbound + delivery callbacks.

This is the BRD-canonical landing place for any "send WhatsApp" requirement — vertical modules should integrate via `whatsapp.message.create` + `action_send`, never by re-implementing the Meta HTTP client.

**How it works**

- An admin creates a `whatsapp.account` (provider = `meta_cloud` or `twilio`) with `phone_number_id`, `business_account_id`, `access_token`, `webhook_verify_token`. `sandbox_mode=True` short-circuits real HTTP calls and returns synthetic message ids.
- Meta is configured to point at `/custom_whatsapp/webhook/<account_id>`. The GET handshake echoes `hub.challenge` if `hub.verify_token` matches the stored token. POST events are 200'd unconditionally (Meta retries aggressively if it sees 5xx).
- Templates are created locally in `draft`, then submitted out-of-band to Meta. The cron `whatsapp.template.cron_poll_template_status` polls `/{waba_id}/message_templates?name=<name>` for `pending_review` rows and updates `status` from Meta's `APPROVED/REJECTED/PENDING/...` enum.
- Outbound flow: a vertical (sale / invoice / helpdesk / POS / cart-abandonment) calls `whatsapp.send.wizard` or directly `whatsapp.message.create(...).action_send()`. Consent gate: marketing-category templates require `pdp.consent.check_consent(partner, "whatsapp_marketing")` — otherwise `UserError`. Utility/authentication categories log-warn but proceed.
- `_do_send` builds the Meta payload (template vs plain text), POSTs through `whatsapp.account._post('messages', payload)`, which applies the shared retry policy (3 attempts, exponential backoff, `Retry-After` on 429) + per-account circuit breaker (10 consecutive failures opens for 1h). Sandbox accounts skip HTTP and stamp `sandbox-<hex>` provider ids.
- On Meta-accepted send: state `draft -> sent`, `provider_message_id = wamid`. Webhook `statuses` entries flip `sent -> delivered -> read` (or `-> failed` with `error_message`). Inbound user messages create a new `whatsapp.message` row with `direction='inbound'`, `state='received'`, partner resolved by last-9-digit phone match.
- Bulk dispatch: `action_send_bulk` dispatches inline for ≤5 records, else `with_delay(channel='root.whatsapp')` enqueues one `queue_job` per recipient.

**Key models**

- `whatsapp.account` — Per-company provider credentials + sandbox flag + circuit breaker state (in-process `_CB_STATE`). Hosts `_request`, `_post`, `_get`, `_get_api_url`, `_get_waba_url`, `_get_headers`, `action_test_connection`.
- `whatsapp.message` — Outbound/inbound queue row; inherits `mail.thread` + `pdp.audited.mixin`. Drives the send + status lifecycle.
- `whatsapp.template` — Local representation of a Meta-approved template, with `body_text` containing `{{n}}` placeholders, stored compute `variables_count`, status synced via cron.
- `whatsapp.send.wizard` — TransientModel used by integration buttons on `sale.order` / `account.move` / `helpdesk.ticket`.
- `sale.order`, `account.move`, `helpdesk.ticket` (inherited) — each adds a "Send WhatsApp" button that opens the wizard.

**Important fields**

- `whatsapp.account.provider` (Selection: meta_cloud/twilio) — drives header + endpoint shape.
- `whatsapp.account.sandbox_mode` (Boolean, default True) — when set, `_do_send` and `_request` short-circuit and synthesize ids; protects accidental quota burn.
- `whatsapp.account.access_token` (Char, `groups='custom_whatsapp.group_manager'`) — plaintext today; manifest description flags migration to `custom.ir.config` encrypted storage as a TODO before prod.
- `whatsapp.account.webhook_verify_token` (Char, group-gated) — shared secret echoed against Meta's `hub.verify_token`.
- `whatsapp.message.state` (Selection: draft/queued/sent/delivered/read/failed/received) — full Meta lifecycle.
- `whatsapp.message.provider_message_id` (Char, indexed) — Meta `wamid`; how the webhook resolves status updates back to local rows.
- `whatsapp.message.consent_verified` (Boolean) — true iff PDP consent check passed pre-send.
- `whatsapp.template.category` (Selection: marketing/utility/authentication) — drives the consent purpose code lookup `_CATEGORY_PURPOSE`.
- `whatsapp.template.status` (Selection: draft/pending_review/approved/rejected, tracking) — only `approved` templates are eligible for template-typed sends; non-approved fall back to plain text.
- `whatsapp.template.variables_count` (Integer, stored compute) — distinct `{{n}}` placeholder positions parsed by `_VAR_RE`.
- `whatsapp.template.meta_template_id` (Char, readonly) — upstream identifier; required for the status cron.

**Endpoints**: `/custom_whatsapp/webhook/<int:account_id>`

## Data Compliance (UU PDP) & Audit (Kepatuhan Data (UU PDP) & Audit)

### custom_pdp_audit — Custom PDP Audit

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_pdp_audit` |
| Version | 19.0.0.3.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core` |
| Models / routes / tests | 4 / 0 / 0 |
| Tags | pdp, audit-trail, compliance |

> Knowledge file is generator output, not human-reviewed.

Provides the **append-only, hash-chained audit log** required by UU 27/2022 plus a reusable mixin (`pdp.audited.mixin`) that any model can inherit to push `create`/`write`/`unlink` events into it. The audit log itself lives outside the standard Odoo schema in a dedicated `pdp` PostgreSQL schema (table `pdp.audit_log`, sha256-chained, with a `pdp.verify_audit_chain()` function and a `pdp.audit_log_v` read view). A `pre_init_hook` bootstraps the schema on install so that fresh Odoo databases work without external init scripts.

The Odoo-side model `pdp.audit.log` (note the dot) is a read-only `_auto=False` view over `pdp.audit_log_v`; writes go straight through raw SQL `INSERT` from the mixin (and from other modules like `custom_coretax`, `custom_pdp_masking`).

**How it works**

- On module install, `pre_init_hook` (Odoo 19 receives `env`) creates extensions (`unaccent`, `pg_trgm`, `pgcrypto`, `btree_gin`) and executes `data/02-pdp-schema.sql` (shipped under the addon's `data/`). If absent, install proceeds with a warning and the `pdp` schema is not created — every subsequent audit write will silently fail (logged as ERROR).
- `pdp.audited.mixin` overrides `create()`, `write()`, `unlink()` to call `_pdp_audit_write(action, res_id, sanitized_vals)`. `_sanitize_vals` truncates strings > 512 chars and replaces binaries with `<binary:Nb>`.
- `_pdp_audit_write` inserts via raw SQL into `pdp.audit_log` with actor_user_id, actor_login, tenant_db (`cr.dbname`), model_name, res_id, action, field_changes JSONB, classification (computed), ip_address, user_agent, request_id, reason. PostgreSQL trigger on the table computes `prev_hash_hex`/`hash_hex` (sha256 chain) so tampering is detectable. The INSERT is wrapped in `cr.savepoint(flush=False)` (since 19.0.0.1.1) so a DB-level failure rolls back only the audit statement — never the calling business transaction.
- `_pdp_audit_classification()` returns the highest-priority classification code among the model's PDP-tagged fields, ordered `sensitive_pii > health > financial > pii > confidential > internal > public`.
- `res.partner` and `res.users` are explicitly inherited to `pdp.audited.mixin` so all PII-bearing core records emit audit rows out of the box.
- The Odoo read-only view `pdp.audit.log.init()` rebuilds the SQL view in `tools.drop_view_if_exists` + `CREATE OR REPLACE VIEW`.
- `action_verify_chain` calls `pdp.verify_audit_chain(NULL)` and shows a green or red `display_notification` listing the first 10 broken row ids.

**Key models**

- `pdp.audited.mixin` (AbstractModel) — Mixin that overrides ORM CRUD to emit audit rows. Inherit it on any model that holds PII or other classified data.
- `pdp.audit.log` (Model, `_auto=False`) — Read-only view over `pdp.audit_log_v`; primary UI for inspecting the chain.
- `res.partner` / `res.users` (inherited) — Pre-mixed with `pdp.audited.mixin`.

**Important fields**

- `pdp.audit.log.ts` (Datetime, readonly) — server timestamp set by the PG trigger.
- `pdp.audit.log.actor_user_id` (Integer) / `actor_login` (Char) — caller identity at write time.
- `pdp.audit.log.tenant_db` (Char) — `cr.dbname`; relevant in multi-tenant single-cluster deployments.
- `pdp.audit.log.model_name` (Char, indexed) / `res_id` (Integer) — the affected record.
- `pdp.audit.log.action` (`Char`, DB column `varchar(64)` with CHECK `action ~ '^[a-z][a-z0-9_]{1,63}$'`) — free-form lowercase snake_case action code. Kept open (not a closed enum) so modules add domain actions (`approval_submit`, `fsm_wo_complete`, `pph_withholding_applied`, …) without a migration.
- `pdp.audit.log.field_changes` (Json) — sanitized vals dict; binaries → `"<binary:Nb>"`, strings >512 → truncated with ellipsis.
- `pdp.audit.log.classification` (Char, indexed) — top-priority classification of the source record.
- `pdp.audit.log.ip_address` (Char) / `user_agent` (Text) / `request_id` (Char) — pulled from `request.httprequest.environ` when called inside an HTTP request.
- `pdp.audit.log.prev_hash_hex` / `hash_hex` (Char) — sha256 chain computed by PG trigger.

### custom_pdp_consent — Custom PDP Consent

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_pdp_consent` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `portal` |
| Models / routes / tests | 2 / 2 / 0 |
| Tags | pdp, audit-trail, compliance, consent |

> Knowledge file is generator output, not human-reviewed.

Implements **subject-consent capture and lifecycle** for UU 27/2022 (Indonesian PDP Law). Holds a master taxonomy of consent purposes (`pdp.consent.purpose`) and an append-style log of individual recorded consents (`pdp.consent`) per partner, with computed `active`/`expired`/`withdrawn` state, evidence attachment, version, and an audited withdrawal action.

Provides a customer-facing portal (`/my/consents`) so data subjects can view and withdraw their own consents, and an `@api.model` `check_consent(partner, purpose_code)` API that any downstream module can call before processing PII.

**How it works**

- Admin/DPO defines `pdp.consent.purpose` rows (code, name, `requires_renewal_days`) — seeded from `data/pdp_consent_purpose_data.xml`.
- A consent is recorded by creating a `pdp.consent` (partner_id + purpose_id, optional evidence binary + `evidence_filename`, `version` defaulted to `"1.0"`). On `create()` an audit row `consent_grant` is pushed to `pdp.audit_log`.
- `_compute_expires_at` derives `expires_at = given_at + requires_renewal_days`; `_compute_state` resolves to `active`/`expired`/`withdrawn` reactively.
- Exclusion constraint `_partner_purpose_unique_active` (PostgreSQL `EXCLUDE` with `WHERE withdrawn_at IS NULL`) blocks a second un-withdrawn consent for the same `(partner_id, purpose_id)`.
- Subject (or operator) calls `action_withdraw(reason)` → stamps `withdrawn_at = now()`, writes audit row `consent_withdraw`. Withdrawn rows stay for evidence; they can be superseded by a fresh grant.
- Downstream callers gate processing via `self.env["pdp.consent"].check_consent(partner, "marketing_email")` — returns `True` only if an un-withdrawn, un-expired record exists.
- Portal `/my/consents` lists all consents for `request.env.user.partner_id`; POST to `/my/consents/<id>/withdraw` runs `action_withdraw` (CSRF on, partner-ownership check).

**Key models**

- `pdp.consent.purpose` — Catalog of consent purposes (code, name, `requires_renewal_days`, active, sequence). `code` is globally unique.
- `pdp.consent` — Subject consent record: partner × purpose × given_at, with computed state, evidence binary, audited via `pdp.audited.mixin`.

**Important fields**

- `pdp.consent.partner_id` (M2o `res.partner`, required, `ondelete="cascade"`) — data subject; deleting the partner cascades the consent rows.
- `pdp.consent.purpose_id` (M2o `pdp.consent.purpose`, required, `ondelete="restrict"`) — purpose cannot be deleted while consents reference it.
- `pdp.consent.purpose_code` (Char, `related="purpose_id.code"`, stored) — denormalised for `check_consent` lookups by code.
- `pdp.consent.given_at` (Datetime, default=now, required) — moment of grant.
- `pdp.consent.expires_at` (Datetime, computed/stored from `given_at` + `purpose_id.requires_renewal_days`) — False means no expiry.
- `pdp.consent.withdrawn_at` (Datetime) — set by `action_withdraw`; presence flips state to `withdrawn`.
- `pdp.consent.state` (Selection: active/expired/withdrawn, computed/stored) — derived; not user-writeable.
- `pdp.consent.evidence` (Binary `attachment=True`) + `evidence_filename` (Char) — signed form/screenshot.
- `pdp.consent.version` (Char, default `"1.0"`) — version of the consent text/notice presented to the subject.
- `pdp.consent.purpose.requires_renewal_days` (Integer) — `>0` triggers `expires_at` computation; `0` = perpetual.

**Endpoints**: `/my/consents`, `/my/consents/<int:consent_id>/withdraw`

### custom_pdp_core — Custom PDP Core

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_pdp_core` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core` |
| Models / routes / tests | 2 / 0 / 0 |
| Tags | pdp, compliance, data-classification |

> Knowledge file is generator output, not human-reviewed.

Provides the **PDP data classification taxonomy** that the rest of the PDP suite (`custom_pdp_audit`, `custom_pdp_masking`, `custom_pdp_retention`, `custom_pdp_dsar`) keys off. Declares `pdp.classification` (codes like `pii`, `sensitive_pii`, `financial`, `health`, `confidential`, `internal`, `public`) plus the `x_pdp_classification_id` column on `ir.model.fields` so any stored field on any model can be tagged with one classification.

This is the foundation layer — install it first, define classifications, tag fields. Downstream modules read `x_pdp_classification_id` to decide whether to mask, audit, retain, or include in DSAR exports.

**How it works**

- `data/pdp_classification_data.xml` seeds the canonical classifications. Codes must be unique and contain no spaces (`_check_code`).
- `data/pdp_field_seed.xml` calls `pdp.classification._seed_partner_pii_fields()` to tag common `res.partner` fields (name/phone/mobile/email → `pii`; vat → `financial`). Uses **raw SQL** because Odoo 19 blocks ORM writes to base `ir.model.fields` rows.
- Operators tag additional fields via the `pdp.tag.fields.wizard` (pick model → multiselect fields → choose classification → `action_apply` writes `x_pdp_classification_id` in bulk).
- Downstream consumers query `ir.model.fields` with `("x_pdp_classification_id", "!=", False)` (e.g. `custom_pdp_audit.PdpAuditedMixin._pdp_audit_classification`, `custom_pdp_masking.PdpMaskedMixin._pdp_classified_field_map`, `custom_pdp_dsar.PdpDsarRequest._gather_subject_data`).

**Key models**

- `pdp.classification` — Master classification taxonomy: code, name, requires_consent, requires_masking, default_retention_days, color, active.
- `ir.model.fields` (inherited) — Adds `x_pdp_classification_id` M2o to expose the tag column.
- `pdp.tag.fields.wizard` (TransientModel) — Batch-tag UI: model_id + field_ids (domain-filtered) + classification_id → applies in one write.

**Important fields**

- `pdp.classification.code` (Char, unique, no-spaces) — stable string key (e.g. `pii`, `sensitive_pii`) used across modules.
- `pdp.classification.requires_consent` (Boolean) — flag for upstream gating; this module only stores it (consent check lives in `custom_pdp_consent`).
- `pdp.classification.requires_masking` (Boolean) — hint for `custom_pdp_masking`; not auto-enforced here.
- `pdp.classification.default_retention_days` (Integer, default 0) — hint for `custom_pdp_retention` policy seeding; 0 = governed elsewhere.
- `pdp.classification.color` / `active` — UX/lifecycle only.
- `ir.model.fields.x_pdp_classification_id` (M2o `pdp.classification`, `ondelete="set null"`) — the per-field tag.

### custom_pdp_dsar — Custom PDP DSAR

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_pdp_dsar` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `custom_ai_bridge` |
| Models / routes / tests | 1 / 1 / 0 |
| Tags | pdp, compliance, audit-trail, dsar, ai |

> Knowledge file is generator output, not human-reviewed.

Implements the UU 27/2022 **Data Subject Access Request (DSAR)** workflow: an inbound REST endpoint plus an internal model that walks every `ir.model.fields` tagged with `x_pdp_classification_id`, gathers all rows linked to the subject across models, packages them into a ZIP dossier `ir.attachment`, optionally summarises via `custom.ai`, and exposes the four DSAR kinds — access, erasure (anonymize), rectification, portability.

It is the operator-facing fulfilment surface for subject rights. Every state transition is hash-chained into `pdp.audit_log`.

**How it works**

- Public anonymous client POSTs to `/dsar/request` (JSON-RPC, `csrf=False`) with `subject_email` (required) and optional `subject_nik`, `request_kind`. Controller best-effort-matches a `res.partner` by email and creates `pdp.dsar.request` in state `received`, returning `{ok, dsar_id, reference, state}`.
- DPO opens the record and runs `action_verify()` → state `verifying`, audit row.
- DPO runs `action_gather()`:
- `_gather_subject_data(partner_id)` queries `ir.model.fields` for every tagged field, groups by model, builds a heuristic domain (`id=` for `res.partner`, `partner_id=` for others, `user_id.partner_id=` fallback), `search_read`s up to 10000 rows per model.
- `_build_zip(data)` produces a ZIP with `manifest.json` (timestamps + model list) and one `<safe_model_name>.json` per model.
- `_ai_summary(data)` optionally calls `self.env["custom.ai"]._chat(...)` with the row counts (`quality="fast"`, max_tokens 512, Indonesian system prompt) — failure is swallowed.
- Persists the ZIP as `ir.attachment` (linked back to the DSAR record via `response_attachment_id`), state → `delivered`, stamps `delivered_at`, audit row.
- For erasure: `action_anonymize()` invokes `_anonymize_subject(partner_id)` which overwrites every tagged char/text/html field on every model with `ANON-<sha256-prefix>` and clears binary fields. Does NOT unlink rows.
- `action_reject()` moves to `rejected` with `rejection_reason`.

**Key models**

- `pdp.dsar.request` — The DSAR ticket; inherits `pdp.audited.mixin` + `mail.thread`. Tracks subject email/NIK, resolved partner, kind, state, response attachment, optional AI summary.

**Important fields**

- `pdp.dsar.request.name` (Char, default `DSAR/YYYYMMDD-HHMMSS`, readonly) — human reference exposed in the controller response.
- `pdp.dsar.request.state` (Selection: received/verifying/gathering/delivered/rejected, tracked) — workflow gate.
- `pdp.dsar.request.request_kind` (Selection: access/erasure/rectify/portability) — drives whether dossier vs anonymization runs.
- `pdp.dsar.request.subject_email` / `subject_nik` (Char, tracked) — identity claim from the request.
- `pdp.dsar.request.partner_id` (M2o `res.partner`, indexed) — resolved subject; required before `action_anonymize`.
- `pdp.dsar.request.response_attachment_id` (M2o `ir.attachment`, readonly) — the generated dossier ZIP.
- `pdp.dsar.request.ai_summary` (Text, readonly) — best-effort `custom.ai` digest of the dossier.
- `pdp.dsar.request.delivered_at` / `requested_at` (Datetime) — SLA computation source.
- `pdp.dsar.request.rejection_reason` (Text) — passed into audit row when rejecting.

**Endpoints**: `/dsar/request`

### custom_pdp_masking — Custom PDP Masking

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_pdp_masking` |
| Version | 19.0.0.3.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `account`, `custom_coretax_bupot`, `custom_pph_witholding` |
| Models / routes / tests | 7 / 0 / 1 |
| Tags | pdp, compliance, audit-trail, masking |

> Knowledge file is generator output, not human-reviewed.

Provides **read-time PII masking** for UU 27/2022. Two parallel masking paths are active simultaneously:

1. **Classification-driven mixin** (`pdp.masked.mixin`) — applied per model that opts in; reads `x_pdp_classification_id` on `ir.model.fields` and routes through `pdp.masking._mask` which picks a strategy by field name (`email`/`phone`/`mobile`/`nik`/`vat`/`name`/`display_name`) or by classification.
2. **Registry-driven base hook** (`pdp_registry_hook.BaseMaskingHook` inheriting `"base"`) — applies to **every model in the registry** via a global `read()` override that consults `custom.pdp.field.registry` for explicit `(model, field) → pattern` rules. Patterns are `full / last4 / first_letter / email_domain / hash / redacted`.

A reason-audited `pdp.unmask.wizard` lets privileged users view records in the clear by passing record ids + reason through `pdp_unmasked_ids` context. A discovery wizard scans `ir.model.fields` for likely-PII names and suggests registry entries.

**How it works**

- Operator/admin configures the masking policy via `res.config.settings.pdp_masking_policy` (stored at `ir.config_parameter` key `pdp.masking.policy`): `always_mask` / `mask_in_export_only` / `unmask_with_reason` (default).
- `pdp.masked.mixin.read()` postprocesses rows: if `policy == "always_mask"` always masks; if `mask_in_export_only` always returns clear (export pathway masks elsewhere); if `unmask_with_reason` returns clear only when the user has `custom_pdp_masking.group_view_pii`. Records whose id is in `context["pdp_unmasked_ids"]` are always returned in the clear (after wizard sign-off).
- `pdp_registry_hook.BaseMaskingHook.read()` (mixed into `base`) consults `custom.pdp.field.registry._registry_for(model)` (env-cached); for each applicable rule whose `mask_groups` the current user is NOT in, it overwrites the row value via `_apply_pattern(value, pattern)`. Then it best-effort logs a `pii_mask` row to `pdp.audit_log` aggregating which fields were masked how many times.
- Discovery: `custom.pdp.field.discovery.wizard.action_scan` regex-scans every stored char/text/date(time)/selection field on non-transient models for tokens like `email|phone|nik|npwp|passport|birth|salary|account|iban|swift|address|street|zip|tax_id|gender|marital`, suggests a `(pii_category, mask_pattern)` per `_PATTERN_TO_CATEGORY`. `action_create_selected` materialises the selected suggestions into `custom.pdp.field.registry` rows.
- Unmask flow: a user with the right access opens `pdp.unmask.wizard` for a `(model, csv-of-ids, reason)`, `action_unmask` writes one `unmask` audit row per id with the reason, then opens the act_window with `context["pdp_unmasked_ids"]=ids`.
- `res.partner` is opted into `pdp.masked.mixin` by default.
- `data/pdp_field_registry_seed.xml` calls `custom.pdp.field.registry._seed_optional_hr_fields()` post-install to populate HR PII rules if `hr`/`hr_recruitment` are present.

**Key models**

- `pdp.masking` (AbstractModel) — Stateless masking service; field-name-keyed strategy table.
- `pdp.masked.mixin` (AbstractModel) — Per-model opt-in `read()` override using `x_pdp_classification_id`.
- `custom.pdp.field.registry` — Per-`(model_name, field_name)` masking rule with `pii_category`, `mask_pattern`, and bypass `mask_groups`. Inherits `pdp.audited.mixin`.
- `base` (inherited via `BaseMaskingHook`) — Global `read()` override consulting the registry for all models.
- `pdp.unmask.wizard` (TransientModel) — Reason-audited unmasking request.
- `custom.pdp.field.discovery.wizard` + `.suggestion` (TransientModels) — Heuristic PII scanner.
- `res.config.settings` (inherited) — Adds `pdp_masking_policy` config.
- `res.partner` (inherited) — Adds `pdp.masked.mixin`.

**Important fields**

- `custom.pdp.field.registry.model_id` (M2o `ir.model`, required, cascade) + `model_name` (Char related, stored, indexed) + `field_name` (Char, required, indexed) — keyed pair, unique via `model_field_unique` SQL constraint.
- `custom.pdp.field.registry.pii_category` (Selection: nik/npwp/phone/email/address/dob/account_no/passport/bank_account/medical/biometric/salary/other) — informational tag.
- `custom.pdp.field.registry.mask_pattern` (Selection: full/last4/first_letter/email_domain/hash/redacted) — drives `_apply_pattern`.
- `custom.pdp.field.registry.mask_groups` (M2m `res.groups`) — users in any of these groups see the value in the clear (bypass).
- `pdp.unmask.wizard.model_name` (Char, readonly) / `res_ids_csv` (Char, required) / `reason` (Text, required).
- `res.config.settings.pdp_masking_policy` (Selection at `ir.config_parameter` `pdp.masking.policy`) — three-level policy.
- `pdp.masking._STRATEGY_BY_FIELD_NAME` (module-level dict, not a field) — name→fn mapping for `email/phone/mobile/nik/vat/name/display_name`.

### custom_pdp_retention — Custom PDP Retention

|  |  |
| --- | --- |
| Path | `addons/compliance/custom_pdp_retention` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit` |
| Models / routes / tests | 1 / 0 / 0 |
| Tags | pdp, compliance, audit-trail, retention |

> Knowledge file is generator output, not human-reviewed.

Implements **data retention policies** for UU 27/2022. Operators define one `pdp.retention.policy` per `(model, classification)` pair specifying a retention window in days, a date field to age against, and one of three actions: `anonymize`, `archive`, or `delete`. A daily cron iterates active policies and applies the action to eligible rows in bounded batches, writing a `custom` audit row per execution.

**How it works**

- DPO creates `pdp.retention.policy(model_id, classification_id, retention_days, action, date_field="create_date")`. Constraint `_policy_unique` blocks duplicates per `(model_id, classification_id)`.
- `_compute_display_name` produces `"<model>/<classification.code>"`; `_compute_next_run` projects `last_run + 1 day`.
- `_compute_eligible` (non-stored) calls `_count_eligible()` → `Model.sudo().search_count(_eligible_domain())` where `_eligible_domain` is `[(date_field, "<", now - retention_days)]`.
- Cron `cron_apply_retention(limit_per_policy=500)` (defined in `data/pdp_retention_cron.xml`) iterates active policies and calls `_apply(limit=500)` per policy with per-policy try/except.
- `_apply` searches eligible rows (limit=500) and:
- `delete` → `recs.unlink()`; on failure, `affected=0`, warning logged.
- `archive` → `recs.write({"active": False})` only if the model has an `active` field; otherwise skipped.
- `anonymize` → `_anonymize_records(recs)` overwrites only the fields whose `x_pdp_classification_id == self.classification_id` with `ANON-<sha256-prefix>` (char/text/html) or `False` (binary). Per-record failures are swallowed; returns count of successfully-touched records.
- `last_run` is stamped, and if `affected>0` a `pdp.audit_log` row with action `custom` is appended (via `pdp.audited.mixin._pdp_audit_write`) describing policy/model/action/count.
- Manual button `action_run_now` raises the limit to 2000 and displays a notification.
- Seed defaults loaded from `data/pdp_retention_defaults.xml`.

**Key models**

- `pdp.retention.policy` — Per-(model, classification) retention rule; inherits `pdp.audited.mixin`.

**Important fields**

- `pdp.retention.policy.model_id` (M2o `ir.model`, required, `ondelete="cascade"`) — target model.
- `pdp.retention.policy.model_name` (Char, `related="model_id.model"`, stored, indexed) — denormalised name.
- `pdp.retention.policy.classification_id` (M2o `pdp.classification`, required, `ondelete="restrict"`) — only fields with this classification are anonymized; ignored for `delete`/`archive`.
- `pdp.retention.policy.retention_days` (Integer, required, default 1825 ≈ 5 years) — age cutoff.
- `pdp.retention.policy.action` (Selection: anonymize/archive/delete, default `anonymize`) — what to do.
- `pdp.retention.policy.date_field` (Char, default `create_date`) — field used in `_eligible_domain`; no validation that this field exists or is a Date(time).
- `pdp.retention.policy.last_run` (Datetime, readonly) — stamped after each `_apply`.
- `pdp.retention.policy.next_run` (Datetime, computed/stored from `last_run`) — informational projection (`last_run + 1d`).
- `pdp.retention.policy.records_eligible_count` (Integer, non-stored) — live count via `_count_eligible()`; may be expensive on big tables.
- `pdp.retention.policy.active` (Boolean, default True) — cron only processes active rows.

## Integration & Platform Foundation (Integrasi & Fondasi Platform)

### authenticate_keycloak — Auth Keycloak — Authorization Code Flow

|  |  |
| --- | --- |
| Path | `addons/ee_gap/authenticate_keycloak` |
| Version | 19.0.2.0.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Rendah |
| Depends | `base`, `web`, `base_setup`, `auth_signup`, `auth_oauth`, `custom_core` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | sso, keycloak, oauth2, multi-tenant |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Adds the OAuth2 authorization-code flow (confidential client) to Odoo's auth_oauth, so Keycloak clients with Client Authentication on can log in Auth Keycloak — Authorization Code Flow =======================================

### custom_adapter_framework — Custom Adapter Framework

|  |  |
| --- | --- |
| Path | `addons/core/custom_adapter_framework` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit` |
| Models / routes / tests | 2 / 0 / 1 |
| Tags | audit-trail, multi-tenant, approval-workflow |

> Knowledge file is generator output, not human-reviewed.

Generic outbound-integration framework. Any module that talks to an external HTTP API (Coretax, Pajakku, bank H2H, PPOB providers, etc.) registers a `BaseAdapter` subclass via `@register_adapter("name")`, gets a `custom.adapter.config` row in the UI, and inherits: HMAC signing, retry-with-exponential-backoff, closed/open/half-open circuit breaker, and append-only call log. Removes per-adapter reimplementation of HTTP+auth+resilience plumbing.

**How it works**

- A vendor module subclasses `BaseAdapter` and decorates with `@register_adapter("coretax")` — the class registers into a process-local `_ADAPTER_REGISTRY` dict.
- Ops creates a `custom.adapter.config` record: name, `adapter_type` (selection sourced from registered classes), `base_url`, `auth_method` (none/hmac/bearer/basic), `credential_ref` (key in `ir.config_parameter` holding the secret).
- Business code calls `config.get_adapter()` → returns `cls(config)` instance; then `.call(endpoint, payload, method="POST")` → `AdapterResponse(ok, status_code, data, error, latency_ms, raw_text, headers)`.
- `call()` runs `_cb_precheck` (raise `CircuitBreakerOpenError` if breaker open + cooldown not elapsed); else builds URL+headers, signs body (`X-Timestamp`+`X-Signature` for HMAC auth, `Authorization` for bearer/basic), POSTs via `requests.request(...)`, retries up to `retry_count` times on `RequestException` or 5xx with `min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**attempt)` sleep. 4xx is treated as permanent — no retry, no breaker trip.
- On every call success/failure, writes a `custom.adapter.call.log` row (request hash sha256, status, latency, error) and updates `consecutive_failures`. When failures ≥ `circuit_breaker_threshold`, sets `status="circuit_open"` and stamps `circuit_opened_at`. After `circuit_breaker_cooldown_s` elapsed, next call probes (half-open); success → closed, failure → re-opened.
- `action_health_check()` button calls `cls.health_check()` (default: GET `/health`) and stores `last_health_check`/`last_health_ok`.
- `action_reset_circuit()`, `action_disable()`, `action_enable()` are manual ops toggles.

**Key models**

- `custom.adapter.config` — Per-tenant per-adapter configuration record. Inherits `pdp.audited.mixin`, `mail.thread`. Holds base_url, auth, secret pointer, timeouts, breaker state.
- `custom.adapter.call.log` — Append-only call log; `write()` raises, `unlink()` only as superuser. SHA-256 hash of request body, status, latency, error.
- `BaseAdapter` (plain Python, not an Odoo model) — Subclass-this base providing `call()`, `health_check()`, HMAC signing, retry loop, circuit breaker.

**Important fields**

- `custom.adapter.config.name` (Char, unique, indexed) — adapter instance identifier (e.g. `coretax_prod`, `pajakku_uat`).
- `custom.adapter.config.adapter_type` (Selection, dynamic via `_selection_adapter_type` → registered classes) — picks the Python implementation.
- `custom.adapter.config.base_url` (Char, required) — service root; endpoint paths are appended.
- `custom.adapter.config.auth_method` (Selection none/hmac/bearer/basic, default `hmac`) — drives `_build_headers`.
- `custom.adapter.config.credential_ref` (Char) — KEY in `ir.config_parameter` holding the secret (NOT the secret itself; usually `ENC::...` via `custom.ir.config`).
- `custom.adapter.config.timeout_s` / `retry_count` / `circuit_breaker_threshold` / `circuit_breaker_cooldown_s` (Integer) — resilience knobs. Defaults 15/3/5/60.
- `custom.adapter.config.consecutive_failures` (Integer, readonly) — breaker counter; resets on success.
- `custom.adapter.config.status` (Selection active/disabled/circuit_open, indexed) — current state.
- `custom.adapter.config.circuit_opened_at` (Datetime, readonly) — used to compute cooldown elapsed.
- `custom.adapter.config.last_health_check` / `last_health_ok` — stamped by `action_health_check`.
- `custom.adapter.call.log.config_id` (M2o, ondelete restrict, indexed) — back-link.
- `custom.adapter.call.log.request_hash` (Char, indexed) — `sha256(body)` hex; body bytes never stored to keep log small + PDP-safe.
- `custom.adapter.call.log.response_status` / `latency_ms` / `ok` / `error` — outcome metrics.
- `custom.adapter.call.log.called_at` (Datetime, indexed) — append timestamp.

### custom_approval_engine — Custom Approval Engine

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_approval_engine` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `mail`, `hr_holidays`, `account`, `purchase`, `sale`, `portal` |
| Models / routes / tests | 10 / 3 / 5 |
| Tags | approval-workflow, audit-trail, delegation, sla-escalation |

> Knowledge file is generator output, not human-reviewed.

The canonical generic multi-tier approval workflow for the platform. Any model can opt in by inheriting `approval.mixin`; the engine handles matrix resolution, ordered tier traversal, multi-approver / require-all logic, manual delegation, OOO auto-delegation from `hr.leave`, SLA + escalation cron, immutable audit history, and portal access for external approvers.

This is the SINGLE source of truth for approvals. Any BRD requirement involving "approval matrix", "approval levels", "multi-step approval", "approver groups", "delegation", "out-of-office", "SLA escalation", "auto-approve on timeout", or "approval audit trail" maps here — do NOT propose a new module. Already wired into `account.move` (post), `purchase.order` (confirm), `sale.order` (confirm), `hr.expense` (submit), `custom.expense.report` (submit), `account.analytic.line` (timesheet validation) and `hr.leave` (confirm + OOO source).

**Auto-submit-on-confirm (no manual button)**: the built-in documents no longer expose a "Request Approval" button. Their native action (Confirm/Post/Submit/Validate) calls `approval.mixin._approval_request_or_proceed()` which auto-creates + submits the request when a matrix matches and leaves the record in `pending` (UI label **Waiting Approval**); the action does NOT proceed. After the final tier approves, `approval.request._advance_to_next_tier` calls `record.with_user(requested_by_id)._approval_on_granted()` to re-run the native action (auto-confirm). The older raising gate `_approval_check_required()` is retained for custom models and as the `account.move._post` safety-net.

**How it works**

- **Matrix definition**: an `approval.matrix` declares `model_id` (any `ir.model`, transient excluded), `condition_domain` (Python list literal, evaluated against the candidate record), `priority` (higher wins on ambiguity), `trigger` ∈ manual/on_create/on_state_change, and an ordered set of `approval.matrix.tier` rows.
- **Tier definition**: each `approval.matrix.tier` has `sequence`, `approver_type` ∈ `user`/`group`/`manager_of_creator`/`domain`, `require_all` (Boolean), `sla_hours` (Float, default 24h), and `on_overdue` ∈ `auto_approve`/`escalate_to_next`/`escalate_to_user`/`none` + optional `escalation_user_id`.
- **Matrix resolution**: `approval.matrix._resolve_for(record)` filters by `model_name == record._name` + matching `company_id` + `_domain_matches(condition_domain, record)`, returns highest-priority active match.
- **Request lifecycle**: `approval.request._create_for_record(record, matrix=None)` produces a draft request (idempotent — returns existing draft/pending). `requested_by_id` is set to `record.env.user` (the real acting user, not the superuser the `sudo()` create would otherwise default to) — this drives audit attribution and the post-approval auto-proceed actor. `action_submit()` advances to first tier (sorted by `sequence`), stamps `due_at = now + sla_hours`, calls `_refresh_pending_approvers` and `_notify_pending`. Approver calls `action_approve(comment)` — records line, checks `require_all` (if set, waits until all `pending_approver_ids` have approved at this tier), then `_advance_to_next_tier`. If last tier, state → `approved`, stamps `final_decision_user_id` + `decided_at`. `action_reject(comment)` → state `rejected`. `action_cancel(reason)` allowed from draft/pending.
- **Approver resolution** per tier: `_resolve_approvers(record)` returns the raw approver set based on `approver_type`. Then `_refresh_pending_approvers` walks each user: (1) if active `approval.ooo` with `auto_delegate_to_id` → use delegate; (2) else if active `approval.delegation` (`_find_delegated_to`) for this `res_model` → use `delegate_to_id`; (3) else use user. The final `pending_approver_ids` is the effective list at this tier.
- **Delegation**: `approval.delegation` (manual) has `user_id` (delegator), `delegate_to_id`, `valid_from`/`valid_until`, optional `model_ids` to restrict scope. Lookups: `_find_delegated_to(user)` (user is delegator), `_find_delegating(user)` (user is delegate — used to record `delegated_from_id` on history line).
- **OOO**: `approval.ooo` (often auto-created from `hr.leave`) has `user_id`, `leave_id`, `date_from`/`date_to`, `auto_delegate_to_id`. `_active_for(user)` returns the first active OOO at `now`.
- **SLA cron**: `_cron_check_escalations` (every 15 min via `ir.cron`) finds `state='pending' AND overdue=True` (where `overdue` computes `due_at < now`); per request `_handle_overdue()` dispatches on `tier.on_overdue`: `auto_approve` records line as `base.user_root` + advances tier; `escalate_to_next` records escalation line + advances; `escalate_to_user` rewrites `pending_approver_ids = [escalation_user_id]` + resets `due_at`; `none` just re-notifies.
- **Mixin auto-submit gate**: built-in models override their native action to partition `self` via `_approval_request_or_proceed()` — returns True (proceed) when no matrix matches OR request is `approved`; returns False (wait) after auto-creating + submitting a fresh request for none/rejected/cancelled, or idempotently for an existing draft/pending. The action then runs `super()` only on the proceeding subset. After full approval the engine re-runs the action via `_approval_on_granted` (overridden per model). The older `_approval_check_required()` raising gate is still used by external callers and as the `account.move._post` safety-net.

**Key models**

- `approval.matrix` — Top-level matrix; `priority desc, sequence asc, id asc` resolution order.
- `approval.matrix.tier` — Ordered tier with approver-resolution config + SLA + overdue action.
- `approval.request` — One per (record × matrix) lifecycle. Inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`. Stores `res_model`/`res_id` + computed `res_ref` Reference.
- `approval.request.line` — Immutable history (write/unlink raise UserError unless context flag set); one row per submit/approve/reject/delegate/escalate/cancel/comment action.
- `approval.delegation` — Manual delegation (`user_id` → `delegate_to_id`), optional `model_ids` scope.
- `approval.ooo` — Out-of-office record (often auto from `hr.leave`).
- `approval.mixin` — `AbstractModel`; mix into any downstream model to add `x_custom_approval_request_id` + `x_custom_approval_state` related/computed fields + `action_request_approval`/`action_cancel_approval`/`action_open_approval_request` + the `_approval_request_or_proceed()` auto-submit gate + the `_approval_on_granted()` post-grant hook + the legacy `_approval_check_required()` raising gate.
- `account.move` / `purchase.order` / `sale.order` / `hr.expense` / `custom.expense.report` / `account.analytic.line` / `hr.leave` (inherited) — built-in integration points, each overriding its native action to auto-submit and defining `_approval_on_granted`.

**Important fields**

- `approval.matrix.condition_domain` (Char, default `"[]"`) — Python literal list, eval'd via `ast.literal_eval`, applied as `search_count([('id','=',record.id), *domain])`.
- `approval.matrix.priority` (Integer, default 10) — higher wins; used for "specific override on top of broad default".
- `approval.matrix.model_name` (Char, stored related from `model_id.model`, indexed) — fast lookup key.
- `approval.matrix.trigger` (Selection manual/on_create/on_state_change) — when to auto-create requests (manual = button-driven; the others are hooks for downstream extensions).
- `approval.matrix.tier.approver_type` (Selection user/group/manager_of_creator/domain) — determines `_resolve_approvers`.
- `approval.matrix.tier.require_all` (Boolean) — false = any approver suffices; true = every approver in the resolved set must approve before tier advances.
- `approval.matrix.tier.sla_hours` (Float, default 24, must be > 0) — drives `due_at`.
- `approval.matrix.tier.on_overdue` (Selection auto_approve/escalate_to_next/escalate_to_user/none) — drives `_handle_overdue`.
- `approval.matrix.tier.escalation_user_id` (M2o `res.users`) — required when `on_overdue='escalate_to_user'`.
- `approval.request.state` (Selection draft/pending/approved/rejected/cancelled, tracking, indexed). The `pending` value is **labelled "Waiting Approval"** in the UI (value unchanged — all domains/decorations keying on `'pending'` still work).
- `approval.request.current_tier_id` (M2o `approval.matrix.tier`).
- `approval.request.due_at` (Datetime, tracking) — `now + sla_hours` at each tier advance.
- `approval.request.overdue` (Boolean, computed + searchable via `_search_overdue`) — `state=='pending' AND due_at<now`.
- `approval.request.pending_approver_ids` (M2m `res.users`) — effective list AFTER OOO + delegation resolution.
- `approval.request.history_ids` (O2m `approval.request.line`) — immutable audit.
- `approval.request.final_decision_user_id` / `decided_at` — set on approve/reject.
- `approval.request.line.action` (Selection submitted/approved/rejected/delegated/escalated/cancelled/commented).
- `approval.request.line.delegated_from_id` (M2o `res.users`) — set when actor was acting via active delegation.
- `approval.delegation.model_ids` (M2m `ir.model`) — empty = applies to all models; otherwise restricts.
- `approval.ooo.auto_delegate_to_id` (M2o `res.users`) — required for effective auto-delegation.
- `approval.mixin.x_custom_approval_request_id` (M2o `approval.request`, computed, stored) — latest non-cancelled request.
- `approval.mixin.x_custom_approval_state` (Selection, related, stored) — exposes request state for view-level domain filtering.

**Endpoints**: `/my/approvals`, `/my/approvals/<int:request_id>`, `/my/approvals/<int:request_id>/decide`

### custom_arka_aim_numbering — ARKA-AIM Document Numbering

|  |  |
| --- | --- |
| Path | `addons/_tenants/custom_arka_aim_numbering` |
| Version | 19.0.1.0.0 |
| Scope | Khusus brand (ARKA-AIM) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `sale_management`, `purchase`, `stock`, `account`, `custom_bast`, `custom_core` |
| Models / routes / tests | 0 / 0 / 1 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Per-company document numbering (SQ/SO/PO/INV/DO/BAST) with monthly reset for the ARKA-AIM tenant. ARKA-AIM Document Numbering =========================== Applies the tenant's document-number format from the master-data "Document #" sheet to the two companies in the arkaaim tenant (PT ARKA, PT AIM):

### custom_core — Custom Core

|  |  |
| --- | --- |
| Path | `addons/core/custom_core` |
| Version | 19.0.0.2.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Sedang |
| Depends | `base`, `web`, `mail` |
| Models / routes / tests | 3 / 0 / 1 |
| Tags | multi-tenant, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Foundational shared module for the Custom Odoo 19 Platform. Carries no business logic of its own — it provides cross-cutting primitives that every other custom module reuses: HMAC signing helpers, Fernet-encrypted `ir.config_parameter` storage, an OS-level `secure_endpoint` controller decorator (HMAC + CIDR allowlist + timestamp drift + nonce replay protection with optional Redis), a marker mixin enforcing the `x_custom_` field-prefix convention, and the "Settings > Custom Platform" anchor menu.

**How it works**

- A downstream module signs an outbound request: `header, ts = self.env["custom.security"].sign_payload(body_bytes)` → `{header} = "t=<unix_ts>,v1=<hex_hmac_sha256>"`. Used by `custom_ai_bridge`, `custom_adapter_framework` (its own copy), `custom_super_admin.orchestrator_client`.
- A downstream module stores a secret encrypted at-rest: `self.env["custom.ir.config"].set_encrypted("my.module.api_key", plaintext)` → row in `ir.config_parameter` with value prefixed `ENC::<fernet_token>`. Reading with `get_encrypted(key)` transparently decrypts. Master key from `CORETAX_SERTEL_MASTER_KEY` env (accepts 44-char Fernet, 64-char hex, or any string padded to 32 bytes).
- A downstream controller defends an endpoint: decorator `@secure_endpoint("scope_name")` → checks `X-Forwarded-For` / `remote_addr` against `custom_core.secure_endpoint.<scope>.allowed_cidrs`, verifies `X-Signature` HMAC-SHA256 against `custom_core.secure_endpoint.<scope>.secret`, requires `X-Timestamp` within ±300s, replay-protects via `_NonceStore` (process-local dict + optional Redis when `redis_url` configured). Every accept/reject is logged to `custom.adapter.call.log` (if available).

**Key models**

- `custom.security` — AbstractModel; HMAC signing + verification helpers. Reads secrets from env vars (`GATEWAY_SHARED_SECRET`, `ORCHESTRATOR_SHARED_SECRET`, generic via `sign_for(secret_key, body)`).
- `custom.ir.config` — AbstractModel; Fernet wrapper over `ir.config_parameter` for encrypted-at-rest secrets. Prefix marker `ENC::` distinguishes encrypted rows.
- `custom.mixin.platform` — AbstractModel; marker mixin asserting the `x_custom_` field-prefix convention via `_custom_validate_field_prefix`.
- `res.config.settings` (inherited) — anchor for the "Custom Platform" settings page (read-only label only; downstream modules attach their toggles here).

### custom_currency_nbsp — Currency NBSP / CSV BOM Fix

|  |  |
| --- | --- |
| Path | `addons/core/custom_currency_nbsp` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Rendah |
| Depends | `base`, `web` |
| Models / routes / tests | 1 / 0 / 0 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Render money without non-breaking spaces and prepend a UTF-8 BOM to CSV exports, so amounts stop showing a stray 'Â'. Currency NBSP / CSV BOM Fix =========================== Odoo separates the currency symbol from the amount with a NON-BREAKING SPACE (U+00A0) and prefixes negative amounts with a ZERO WIDTH NO-BREAK SPACE (U+FEFF). In UTF-8 those are the byte sequences ``C2 A0`` and ``EF BB BF``. Any consumer that decodes the output as Latin-1 / cp1252 instead of UTF-8 — Excel opening a CSV without a BOM, wkhtmltopdf on an HTML fragment that lost its charset declaration, some mail clients — renders them as the stray characters ``Â`` and ``ï»¿``::

**Key models**

- nbsp.free.currency

### custom_esb_connector — Custom ESB Connector

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_esb_connector` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (EFN (Erajaya F&B)) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_adapter_framework`, `custom_pdp_audit`, `queue_job`, `stock`, `uom` |
| Models / routes / tests | 11 / 0 / 5 |
| Tags | esb-integration, fnb, master-sync, stock-mirror, outbox |

> Knowledge file is generator output, not human-reviewed.

The Odoo side of the ESB edge. **ESB Core is the source of truth for stock** in the EFN
(Erajaya F&B) vertical; this module mirrors ESB master data and balances into Odoo, and pushes
documents back as native ESB records. It deliberately contains **no business logic** —
counting, forecasting and replenishment live in the consuming vertical module
(`custom_fnb_stock_ops`).

API reference: [`docs/integrations/esb-core-api.md`](../../../docs/integrations/esb-core-api.md).
Raw captured spec: `docs/integrations/esb/esb-core.apidoc.json`.

**Declared models**: `custom.esb.branch`, `custom.esb.document.template`, `custom.esb.location`, `custom.esb.master.sync`, `custom.esb.outbox`, `custom.esb.product.detail`, `custom.esb.purpose`, `custom.esb.session`, `custom.esb.stock.snapshot`, `custom.esb.supplier`, `custom.esb.sync.log`

**Important fields**

- `product.product.x_esb_product_detail_id` — the **stock-unit** `productDetailID`. This, not `productID`, is what every ESB transactional endpoint wants. Use `product._esb_detail_id(kind)` to resolve the purchase/transfer/base unit instead.
- `custom.esb.outbox.idempotency_key` — generated `ODOO-<hex>`, stamped into the document's `additionalInfo` and used to detect an already-created document.
- `custom.esb.outbox.adopted` — true when the guard found the document already existed and adopted it rather than creating a duplicate.
- `custom.esb.session.credential_ref` — an `ir.config_parameter` **key**. The secret is never stored on the record.

### custom_home_console — Custom Home Console

|  |  |
| --- | --- |
| Path | `addons/core/custom_home_console` |
| Version | 19.0.1.0.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Rendah |
| Depends | `web`, `custom_core`, `mail` |
| Models / routes / tests | 0 / 0 / 0 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Spotlight-style home landing: grouped app cards, search, shortcuts, branding Custom Home Console ===================

### custom_operating_unit — Custom Operating Unit

|  |  |
| --- | --- |
| Path | `addons/core/custom_operating_unit` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_core`, `analytic` |
| Models / routes / tests | 2 / 0 / 2 |
| Tags | operating-unit, multi-branch, data-isolation, organisation-hierarchy |

Master data for the branch dimension: Head Office → Area → Store, as a real
model with a hierarchy, plus the user→unit assignment that the record rules in
the bridge modules read. Before this, "Operating Unit" was only an
`account.analytic.account` in a plan of that name, owned by
`custom_levis_localization`, with zero access-control effect.

**Declared models**: `operating.unit`, `operating.unit.mixin`

### custom_operating_unit_docs — Custom Operating Unit — Documents

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_operating_unit_docs` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_operating_unit`, `account`, `stock`, `purchase`, `sale_stock` |
| Models / routes / tests | 9 / 0 / 2 |
| Tags | operating-unit, data-isolation, record-rules, multi-branch |

Turns the Operating Unit from master data into enforced data isolation on the
accounting, stock, purchase and sales documents. Auto-installs wherever those
apps are present, so a tenant without them never sees it.

**Declared models**: `account.bank.statement.line`, `account.move`, `account.move.line`, `account.payment`, `purchase.order`, `sale.order`, `stock.move`, `stock.picking`, `stock.quant`

### custom_report_templates — Custom Report Templates

|  |  |
| --- | --- |
| Path | `addons/ee_gap/custom_report_templates` |
| Version | 19.0.0.6.0 |
| Scope | Umum |
| Maturity / confidence | Beta / Sedang |
| Depends | `account`, `sale`, `purchase`, `custom_core`, `custom_home_console` |
| Models / routes / tests | 0 / 0 / 0 |
| Tags | reporting, branding |

> Knowledge file is generator output, not human-reviewed.

Re-styles the three core business documents — Customer Invoice, Sales
Quotation/Order and Purchase Order — plus a Journal Voucher, to a clean
Wave/Excel-style layout. The layout is shared by every tenant; branding and the
handful of per-tenant differences are read from `res.company`, so no tenant
needs a code fork.

**Key models**

- `res.company` (inherited, `models/res_company.py`) — report configuration only; no behaviour, no overrides.

### custom_role_manager — Custom Role Manager

|  |  |
| --- | --- |
| Path | `addons/core/custom_role_manager` |
| Version | 19.0.0.1.0 |
| Scope | Umum |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_core` |
| Models / routes / tests | 2 / 0 / 2 |
| Tags | rbac, role-bundles, user-provisioning, access-rights |

A **role** layer over native `res.groups`. Administrators pick a named position
("Accounting Supervisor", "Store Manager") and the module reconciles
`res.users.group_ids` for them. Odoo ships nothing like this in Community or
Enterprise; OCA's `base_user_role` is not ported to 19.0 and models a role as a
group, which this platform cannot do (see Gotchas).

**How it works**

- Assign `role_ids` on a user (form, wizard, or `res.users.create`).
- `write`/`create` calls `_apply_security_roles()` unless the `role_apply` context flag is set (that flag is how the engine's own writes avoid recursing).
- The engine computes `target = role_ids._all_group_ids()`, grants `target − group_ids`, revokes `role_granted_group_ids − target − role_baseline_group_ids`, then rewrites the ledger.
- Editing a role's composition re-applies it to every holder, including holders of roles that *inherit* it (`_holder_roles()` walks upward).

**Declared models**: `custom.security.role`, `custom.security.role.assign`

## Industry Verticals (Vertikal Industri)

### custom_fnb_stock_ops — Custom F&B Stock Ops (ESB)

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_fnb_stock_ops` |
| Version | 19.0.0.1.0 |
| Scope | Umum, dikonfigurasi (EFN (Erajaya F&B)) |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_esb_connector`, `custom_wms_cycle_count`, `queue_job` |
| Models / routes / tests | 5 / 0 / 4 |
| Tags | fnb, esb-integration, stock-opname, demand-forecast, replenishment |

> Knowledge file is generator output, not human-reviewed.

Stock Opname, Demand Forecasting and Auto Replenishment for F&B outlets running on **ESB Core**,
built on [`custom_esb_connector`](../../ee_gap/custom_esb_connector/MODULE_KNOWLEDGE.md).
ESB stays the source of truth for stock; Odoo runs the intelligence and pushes the outcome back
as native ESB documents.

**Declared models**: `custom.fnb.demand.forecast`, `custom.fnb.demand.history`, `custom.fnb.replenishment.proposal`, `custom.fnb.replenishment.proposal.line`, `custom.fnb.replenishment.rule`

### custom_ppob_biller_digiflazz — Custom PPOB - Biller: Digiflazz

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_biller_digiflazz` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_ppob_sale` |
| Models / routes / tests | 0 / 0 / 1 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Digiflazz H2H provider adapter (prepaid topup, postpaid inquiry and payment) with MD5 signing and ref_id idempotency. Custom PPOB Suite - Biller: Digiflazz ===================================== First CONCRETE biller adapter for the PPOB vertical. Registers ``ppob_digiflazz`` in the PPOB adapter registry (``custom.ppob.provider.adapter_class``).

### custom_ppob_commission — Custom PPOB - Commission

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_commission` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Beta / Rendah |
| Depends | `custom_ppob_sale`, `custom_pph_witholding`, `custom_coretax_bupot` |
| Models / routes / tests | 3 / 0 / 0 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Two-way PPOB commissions: provider->us income and us->mitra rebate with PPh 23 withholding via the platform engine. Custom PPOB Suite - Commission ============================== Two-way commissions:

**Key models**

- custom.ppob.commission.accrual
- custom.ppob.commission.rule
- custom.ppob.commission.settlement.wizard

### custom_ppob_core — Custom PPOB - Core

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_core` |
| Version | 19.0.1.1.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Beta / Tinggi |
| Depends | `account`, `product`, `custom_core` |
| Models / routes / tests | 5 / 0 / 0 |

Foundation of the **PPOB (Payment Point Online Bank)** vertical — Erajaya's
value-added services business: pulsa, data packages, electricity tokens and bill
payment sold through a network of *mitra* (B2B resellers) on a prepaid model.
Ported from the ERA PPOB R&D suite and rewired onto the platform's own
accounting and tax modules rather than its original standalone ones.

**How it works**

- **Partner extensions** mark a `res.partner` as mitra or provider, carry a per-partner transaction cap, and hold an NPWP flag — the flag drives the PPh withholding rate applied to that partner's commission.
- **Product classification** (`custom.ppob.product.class`) is the routing key: it decides which wallet a transaction draws from and which VAT mode applies — margin, DPP nilai lain, gross, or exempt — per PMK-63/2022 for pulsa and voucher distributors.
- **Product catalogue** holds each sellable item with its denomination, default cost price, an inquiry-required flag for postpaid bills, and GL account overrides where a product must not use its class defaults.
- **Pricing tiers** set per-mitra selling prices per product, so the same denomination sells at different prices to different resellers.
- **Chart-of-account scaffolding** is created idempotently by a post-init hook that searches by code before creating. It slots beside a tenant's existing `l10n_id` or PSAK chart instead of duplicating accounts — which is what lets the vertical be installed onto a database that already has a chart.
- Sequences are created for transactions, wallet moves, bucket moves, VA topups and commission accruals; security groups for user, operations, manager and API integration.

**Key models**

- `custom.ppob.product.class` — the classification that drives wallet routing and VAT mode.
- `custom.ppob.product` — the sellable catalogue entry.
- `custom.ppob.price.tier` + `custom.ppob.price.tier.line` — per-mitra pricing.
- `custom.ppob.account.mapping` — role-addressed GL accounts, resolved by code so the vertical adapts to the tenant's chart.
- `res.partner` (inherited) — mitra/provider flags, transaction cap, NPWP flag.

**Important fields**

- `custom.ppob.product.class.vat_mode` — margin / other-valuation / gross / exempt. This single field decides how PPN is computed for every transaction in the class; getting it wrong misstates output tax across the whole vertical.
- `res.partner` NPWP flag — selects the PPh 23 rate on commission.
- `custom.ppob.account.mapping` — resolved by account *code*, not by ID, which is why the vertical can be installed on charts it did not create.

### custom_ppob_eraspace_bridge — Custom PPOB - ERASPACE Bridge (Mirror)

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_eraspace_bridge` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_ppob_sale`, `custom_ppob_wallet`, `custom_ppob_va`, `custom_ppob_provider`, `custom_core` |
| Models / routes / tests | 5 / 2 / 1 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Mirror ERASPACE POS + H2H feeds into Odoo Finance/Accounting (2-feed HMAC ingest, join by pos_trx_ref, GL-on-terminal). Custom PPOB Suite - ERASPACE Bridge (Revamp I: mirror-only) =========================================================== Revamp I of the ERASPACE PPOB architecture: ERASPACE POS (standalone) and the H2H switcher own the transaction; Odoo is a **downstream, non-authoritative ledger** that mirrors two terminal feeds and projects them into GL.

**Key models**

- custom.ppob.eraspace.backfill.wizard
- custom.ppob.eraspace.connection
- custom.ppob.eraspace.ingest.skipped
- custom.ppob.eraspace.settlement
- custom.ppob.eraspace.txn

**Endpoints**: `/api/ppob/eraspace/h2h`, `/api/ppob/eraspace/pos`

### custom_ppob_oracle_bridge — Custom PPOB - Oracle Bridge

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_oracle_bridge` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_ppob_provider`, `custom_ppob_sale`, `custom_ppob_wallet` |
| Models / routes / tests | 4 / 0 / 3 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Bridge the PPOB suite to the legacy Oracle EVShop pipeline (MSG016T) via stored procedure SellWithDenom_HA + status polling. Custom PPOB Suite - Oracle Bridge ================================= Lets the PPOB vertical run in parallel with the legacy Oracle EVShop pipeline as a second routing mode alongside native H2H. Additive and independently uninstallable; NOT part of the default industry pack (enable per tenant that still runs EVShop).

**Key models**

- custom.ppob.oracle.backfill.wizard
- custom.ppob.oracle.connection
- custom.ppob.oracle.ingest.skipped
- custom.ppob.oracle.member.map

### custom_ppob_pps_gateway — Custom PPOB - PPS Gateway (H2H inbound)

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_pps_gateway` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_ppob_sale`, `custom_ppob_provider`, `custom_ppob_core`, `custom_core` |
| Models / routes / tests | 3 / 7 / 1 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Expose the PPS/EVShop H2H API from Odoo so ERASPACE POS can transact against Odoo as the switcher (Revamp II). Custom PPOB Suite - PPS Gateway (Revamp II: Odoo as switcher) ============================================================= Revamp II makes Odoo REPLACE the vendor PPS/EVShop switcher. ERASPACE POS keeps its existing integration and simply re-points its base URL to Odoo: this module exposes the SAME PPS H2H API surface as a drop-in and maps every request onto the native ``custom.ppob.transaction`` engine + wallet ("deposit") + provider adapter registry. Odoo fulfils to real billers itself (its own adapters); the vendor PPS is NOT called downstream.

**Key models**

- custom.ppob.pps.callback.log
- custom.ppob.pps.game.field
- custom.ppob.pps.mitra.credential

**Endpoints**: `/pps/checknocustomer`, `/pps/direct-topup`, `/pps/game-list`, `/pps/inquiry-pln`, `/pps/sell`, `/pps/statustrx`, `/pps/statustrxwithdeposit`

### custom_ppob_provider — Custom PPOB - Provider

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_provider` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_ppob_core`, `custom_adapter_framework`, `stock`, `purchase` |
| Models / routes / tests | 6 / 0 / 1 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Provider master data, atomic bucket inventory, SKU mapping, adapter abstraction, DP 100% deposit topup. Custom PPOB Suite - Provider ============================ Provider-side management for the PPOB vertical:

**Key models**

- custom.ppob.provider
- custom.ppob.provider.bucket
- custom.ppob.provider.bucket.move
- custom.ppob.provider.sku.map
- custom.ppob.provider.topup.log
- custom.ppob.provider.topup.wizard

### custom_ppob_rollup — Custom PPOB - Daily Rollup

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_rollup` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Beta / Rendah |
| Depends | `custom_ppob_sale`, `sale_management`, `custom_accounting_reports` |
| Models / routes / tests | 1 / 0 / 0 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Aggregate successful PPOB transactions into a daily sale.order + summary faktur per mitra for e-Faktur / Coretax. Custom PPOB Suite - Daily Rollup ================================ Hybrid architecture: real-time ``custom.ppob.transaction`` rows post their own per-transaction sub-ledger + GL entries during the day. This module rolls the successful ones up nightly into one ``sale.order`` + summary ``account.move`` (``out_invoice``) per mitra per day, grouped by product.

**Key models**

- custom.ppob.rollup

### custom_ppob_sale — Custom PPOB - Sale / Transaction

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_sale` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_ppob_wallet`, `custom_ppob_provider` |
| Models / routes / tests | 2 / 0 / 1 |

The **transactional core** of the PPOB vertical: the transaction state machine,
atomic drawdown against both the mitra wallet and the provider deposit, dispatch
to the provider adapter, and the reaper that resolves transactions left hanging.

**How it works**

- `custom.ppob.transaction` runs the state machine `pending → inquiry_ok → in_progress → success / failed / timeout / refunded`.
- On dispatch: atomic wallet debit, atomic provider deposit (bucket) debit, then the provider adapter call. **GL is posted by the wallet and bucket helpers**, each posting its own paired entry — there is no separate compound sale move to reconcile.
- Per-transaction `vat_mode`, `dpp_amount` and `ppn_amount` are computed for reporting and for the daily rollup faktur (PMK-63/2022: margin, DPP nilai lain, gross, exempt). **PPN is recognised in the GL at the rollup faktur, not per transaction** — the volume makes per-transaction recognition unworkable.
- A cron reaper resolves stale `in_progress` transactions by calling the provider adapter's `status()` **before** refunding. It never blind-refunds, and it honours each provider's own `stale_threshold_minutes`. This is the guard against paying a customer twice when the provider was merely slow.
- A manual-sale wizard covers the operations desk.

**Key models**

- `custom.ppob.transaction` — the state machine and the tax fields.
- `custom.ppob.manual.sale.wizard` — operator-initiated sale.
- `custom.ppob.wallet.move`, `custom.ppob.provider.bucket.move` (inherited) — gain the `ppob_transaction_id` back-reference.
- `stock.picking` (inherited) — links physical voucher stock where a product class carries it.

**Important fields**

- `custom.ppob.transaction.state` — the workflow spine; `in_progress` is the state the reaper watches.
- `custom.ppob.transaction.vat_mode` / `dpp_amount` / `ppn_amount` — inherited from the product class, then frozen on the transaction so a later class change cannot restate history.
- Per-provider `stale_threshold_minutes` — how long a transaction may sit in `in_progress` before the reaper investigates it.

### custom_ppob_sla — Custom PPOB - SLA Targets & Throughput

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_sla` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_ppob_sale` |
| Models / routes / tests | 2 / 0 / 2 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

Declarative per-provider/class throughput + latency targets, and hourly throughput sampling that holds both the Oracle historical baseline and Odoo actuals for parallel-run parity. Custom PPOB Suite - SLA Targets & Throughput ============================================ Closes open decision **D4** (target throughput & H2H SLA) by making it configuration rather than a design-time constant, and by shipping the measurement needed to ever verify it.

**Key models**

- custom.ppob.sla.target
- custom.ppob.throughput.sample

### custom_ppob_va — Custom PPOB - Virtual Account

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_va` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Produksi / Tinggi |
| Depends | `custom_ppob_wallet`, `custom_core`, `custom_accounting_full` |
| Models / routes / tests | 3 / 2 / 1 |

The **top-up pipeline for mitra wallets via bank Virtual Account** — BCA, BNI,
BRI, Mandiri and Permata. Two independent paths reach the same wallet credit:
a real-time host-to-host callback, and a reconciliation rule over imported bank
statements for the cases where the callback never arrived.

**How it works**

- **Host-to-Host.** `/api/ppob/va/<bank>/inquiry` and `/api/ppob/va/<bank>/payment` are authenticated per bank with HMAC-SHA256 over timestamp plus body, using the platform secure-endpoint primitives: Redis-backed nonce replay guard, IP allow-list, clock-skew check.
- The hard idempotency guarantee is **not** the nonce guard but a database constraint: `UNIQUE(bank_ref)` on `custom.ppob.va.topup`. A duplicate callback credits the wallet exactly once and returns the original acknowledgement. This matters because banks retry, and a replay window is a time-bounded defence while a unique index is not.
- **Manual / reconcile.** A `va_match` extension of `custom.reconcile.rule` matches bank-statement references against `custom.ppob.va.account` records and credits the correct wallet, reusing `custom_bank_import` and `custom_accounting_full` rather than building a second matching engine.
- An optional per-VA output tax splits each top-up into DPP (the wallet credit) and PPN (Output VAT), through the wallet's tax-inclusive credit primitive.

**Key models**

- `custom.ppob.va.account` — the virtual account assigned to a mitra.
- `custom.ppob.va.topup` — one top-up; carries the unique `bank_ref`.
- `custom.ppob.va.bank.connection` — per-bank credentials and endpoint config.
- `custom.reconcile.rule` (inherited) — the `va_match` matcher.
- `account.bank.statement.line`, `custom.ppob.wallet.move` (inherited).

**Important fields**

- `custom.ppob.va.topup.bank_ref` — **unique**. The single guarantee that a retried callback cannot double-credit a wallet.
- `custom.ppob.va.account.partner_id` — the mitra the VA belongs to; the join the reconcile rule resolves.

**Endpoints**: `/api/ppob/va/<string:bank_code>/inquiry`, `/api/ppob/va/<string:bank_code>/payment`

### custom_ppob_wallet — Custom PPOB - Wallet

|  |  |
| --- | --- |
| Path | `addons/verticals/custom_ppob_wallet` |
| Version | 19.0.1.0.0 |
| Scope | Umum, dikonfigurasi (Eraspace / PPOB-VAS) |
| Maturity / confidence | Beta / Tinggi |
| Depends | `custom_ppob_core` |
| Models / routes / tests | 3 / 0 / 0 |

The **money primitives** the rest of the PPOB suite is built on. One wallet per
(mitra, product class), with debit and credit operations that are atomic against
concurrent transactions — the correctness foundation of a prepaid business where
two simultaneous sales must not both succeed against the same last balance.

**How it works**

- `_atomic_debit` and `_atomic_credit` take a row-level `SELECT ... FOR UPDATE` lock on the wallet, post a paired `account.move`, write a `custom.ppob.wallet.move` sub-ledger line, and update the balance — **all inside one PostgreSQL transaction**. There is no window in which the balance and the ledger disagree.
- `_atomic_credit_with_tax` handles tax-inclusive top-ups: it splits the gross into DPP, which grows the wallet, and PPN, which is routed to the output-tax repartition account. Used by the Virtual Account top-up path.
- A manual adjust and top-up wizard covers the operations desk's corrections; every adjustment goes through the same primitives, so a manual fix leaves the same audit trail as an automatic one.
- Dedicated wallet and sale general journals keep the sub-ledger separable from the tenant's ordinary accounting.

**Key models**

- `custom.ppob.wallet` — one per (mitra, product class); holds the balance and exposes the atomic primitives.
- `custom.ppob.wallet.move` — the sub-ledger line paired with every GL move.
- `custom.ppob.wallet.adjust.wizard` — manual adjustment and top-up.

**Important fields**

- `custom.ppob.wallet.balance` — never written directly; only the atomic helpers update it, and always in the same transaction as the ledger line.
- `custom.ppob.wallet.move.ppob_transaction_id` — the back-reference added by `custom_ppob_sale`, which is how a wallet movement is traced to the sale that caused it.

## Platform Admin & Odoo-as-a-Service (Administrasi Platform & Odoo-as-a-Service)

### custom_brd_analyzer — Custom BRD Analyzer

|  |  |
| --- | --- |
| Path | `addons/operations/custom_brd_analyzer` |
| Version | 19.0.0.5.0 |
| Scope | Platform |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_ai_features`, `custom_ai_bridge`, `custom_approval_engine`, `custom_super_admin`, `project`, `custom_documents`, `mail`, `portal`, `queue_job` |
| Models / routes / tests | 9 / 4 / 2 |

> No module knowledge file exists. The summary below is derived from the manifest; treat it as an index entry, not a specification.

AI-powered Business Requirements Document gap analyzer for the platform module hub Custom BRD Analyzer ===================

**Key models**

- brd.analysis
- brd.document
- brd.document.section
- brd.knowledge.regen.wizard
- brd.lesson
- brd.recommendation
- brd.reject.as.lesson.wizard
- custom.module.capability.entry
- custom.module.capability.tag

**Endpoints**: `/brd/<int:doc_id>/report`, `/brd/<int:doc_id>/report.pdf`, `/brd/<int:doc_id>/share`, `/brd/share/<string:token>`

### custom_dev_cycle — Custom Dev Cycle Tracking

|  |  |
| --- | --- |
| Path | `addons/operations/custom_dev_cycle` |
| Version | 19.0.1.0.0 |
| Scope | Platform |
| Maturity / confidence | Produksi / Sedang |
| Depends | `project`, `mail`, `custom_brd_analyzer`, `custom_onboarding_journey` |
| Models / routes / tests | 3 / 2 / 2 |
| Tags | audit-trail, approval-workflow, multi-tenant |

> Knowledge file is generator output, not human-reviewed.

Tracks the full implementation lifecycle of every BRD-derived recommendation, from backlog through deployment, with GitHub/GitLab webhook auto-sync. Bridges three previously disconnected things: a `brd.recommendation` (what the customer needs), the resulting code (PR with CI status), and the deployment (per-environment release artifact on `custom.hub.module.deployment`). The state machine + webhook auto-transitions remove manual status updates.

**How it works**

- A BA accepts a `brd.recommendation` → creates a `dev.cycle` (state `backlog`). `_compute_branch_suggestion` auto-fills `branch_name` as `feature/brd-<id>-<slug>`.
- Dev clicks `action_create_project_task` → ensures a `project.project` named "Dev Cycle Tasks" exists (or uses `journey_id.project_id` if exposed) and creates a linked `project.task` with description containing branch/repo/BRD references.
- Dev opens a PR. GitHub webhook POSTs to `/devcycle/webhook/github` (HMAC-validated via `X-Hub-Signature-256` against `dev_cycle.github_webhook_secret` ir.config_parameter). `_resolve_cycle` matches: existing `dev.cycle.pr.pr_url` → reuse cycle, else `branch_name` → cycle. `dev.cycle.pr.upsert_from_webhook` creates/updates the PR row with `provider`, `pr_number`, `pr_url`, `state` (draft/open/merged/closed), `ci_status` (pending/success/failure/error), `reviewers`, `merged_at`, `merged_by`.
- `_apply_state_to_cycle` auto-transitions the parent cycle: PR `open` while cycle is `in_dev` → cycle moves to `code_review`; PR `merged` + `ci_status=success` while cycle is before `deployed` → cycle moves to `deployed`. Posts a chatter note.
- GitLab equivalent at `/devcycle/webhook/gitlab` validates `X-Gitlab-Token` against `dev_cycle.gitlab_webhook_secret`.
- Manual transitions: `action_start` (→ in_dev, stamps `started_at`), `action_to_review`, `action_to_qa`, `action_to_uat`, `action_deploy`, `action_done` (stamps `completed_at`). `action_transition_state(new)` enforces `STATE_SEQUENCE = [backlog, in_dev, code_review, qa, uat, deployed, done]`: forward jumps any length, backward only one step.
- `dev.cycle.deployment` rows link a cycle to a `custom.hub.module.deployment` and `tenant.environment` with `outcome` (success/failure/rolled_back).
- `actual_md` is computed from `project_task_id.effective_hours / 8.0` when present; manually overridable.

**Key models**

- `dev.cycle` — One per BRD recommendation. State machine over `[backlog, in_dev, code_review, qa, uat, deployed, done]`. Inherits `mail.thread`.
- `dev.cycle.pr` — One per GitHub/GitLab PR. Cascade-deletes with cycle. Unique `(cycle_id, pr_url)`. Holds CI status and merge metadata.
- `dev.cycle.deployment` — One per per-environment deployment of the cycle's code. Links to `custom.hub.module.deployment` and `tenant.environment`.
- `brd.recommendation` (inherited via `brd_recommendation_extension.py`) — gets a back-reference `dev_cycle_ids` (One2many) so the BRD UI can see implementation progress.

**Important fields**

- `dev.cycle.state` (Selection backlog/in_dev/code_review/qa/uat/deployed/done, indexed, tracking) — drives `action_transition_state` rules.
- `dev.cycle.env_progress` (Selection dev/staging/uat/prod) — currently deployed-to environment (independent of `state`).
- `dev.cycle.brd_recommendation_id` (M2o brd.recommendation, set_null, indexed) — source recommendation.
- `dev.cycle.journey_id` (M2o onboarding.journey, set_null) — onboarding context.
- `dev.cycle.module_target_id` (M2o custom.hub.module.catalog, set_null) — which Hub module will be deployed.
- `dev.cycle.branch_name` (Char, computed `feature/brd-<id>-<slug>`, store, readonly=False) — git branch convention.
- `dev.cycle.repo_url` (Char) — git repo URL.
- `dev.cycle.assignee_id` (M2o res.users, tracking) — developer.
- `dev.cycle.estimate_md` / `actual_md` (Float) — man-days; actual auto-computed from linked project task hours.
- `dev.cycle.project_task_id` (M2o project.task, set_null, copy=False) — created by `action_create_project_task`.
- `dev.cycle.started_at` / `completed_at` (Datetime, readonly) — stamped by state transitions.
- `dev.cycle.pr_ids` / `deployment_ids` (One2many) + `pr_count` / `deployment_count` (computed) — smart-button counts.
- `dev.cycle.pr.pr_number` (Integer, indexed), `pr_url` (Char, required), `state` (Selection draft/open/merged/closed), `ci_status` (Selection pending/success/failure/error, indexed), `reviewers` (Char CSV), `merged_at` / `merged_by` / `last_synced_at` — PR mirror.
- `dev.cycle.deployment.outcome` (Selection success/failure/rolled_back, indexed) — per-env release result.

**Endpoints**: `/devcycle/webhook/github`, `/devcycle/webhook/gitlab`

### custom_hub_console — Custom Hub Control Center

|  |  |
| --- | --- |
| Path | `addons/control_plane/custom_hub_console` |
| Version | 19.0.0.2.0 |
| Scope | Platform |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_super_admin`, `custom_ai_features`, `custom_brd_analyzer`, `custom_ops_monitor`, `mail` |
| Models / routes / tests | 8 / 0 / 2 |
| Tags | multi-tenant, audit-trail, approval-workflow, ai |

> Knowledge file is generator output, not human-reviewed.

Top-level **control-plane** wrapper for the platform: aggregates tenants, modules, deployments, audit, monitoring, and AI usage under one navigation tree, and provides the per-tenant Hub dashboard that ops/CSM teams use to drive day-to-day operations. Owns the **module catalog** (scanned from `addons/`), the **per-tenant deployment ledger** with canary/rollback orchestration, an **append-only hash-chained audit log**, and the **AI usage roll-up**. Lives on the platform master DB alongside `custom_super_admin`.

**How it works**

- **Catalog scan**: `custom.hub.module.catalog._action_scan_all()` walks `addons/core|compliance|ee_gap|operations|verticals/<module>/__manifest__.py`, parses each manifest with `ast.literal_eval`, counts `_name=` / `_inherit=` via regex inside `models/*.py`, and upserts a `custom.hub.module.catalog` row with `module_name`, `version`, `category` (core/compliance/ee_gap/operations/vertical), `summary`, model counts, and `maturity` heuristic (≥5 own models + `tests/` → production; 0 → scaffold; else partial). Triggered by the rescan wizard or scan cron.
- **Deploy to tenant**: User clicks `action_open_deploy_wizard` on a catalog row → `custom.hub.deploy.module.wizard` → creates `custom.hub.module.deployment(catalog_id, tenant_id, deploy_mode={install,upgrade,uninstall})` and calls `action_deploy()`. The deploy method POSTs `POST /v1/tenants/<slug>/modules/<mode>` body `{module: <name>}` via `custom.super.admin.orchestrator.client._request` (HMAC-signed). On success: state → installed/uninstalled. On failure: state → failed + `error_message` (does NOT raise — wizard commits).
- **Canary path (Track C)**: `action_resolve_dependencies` → topo-sort of `catalog.depends_module_ids`, written as JSON to `dep_graph_resolved_json`. `action_take_pre_backup` → calls `orchestrator.run_backup(slug, kind="manual")`, syncs the backup ledger, links newest snapshot as `rollback_snapshot_id`. `action_deploy_canary` → POSTs with `phase=canary` and `environment=<staging env name>` (resolved via `_pick_canary_environment` from `tenant.environment`). `action_healthcheck` → reads latest `custom.ops.tenant.health` snapshot for the tenant; pass iff `status="green"` AND `snapshot_at >= now()-5min`. `action_rollout_full` → blocked unless `healthcheck_passed`; POSTs `phase=full`. `action_rollback` → calls `orchestrator.restore_backup(slug, snapshot.s3_key)`, sets `canary_phase=rolled_back` and `state=failed`.
- **Audit chain**: Every `_log_audit` call creates a `custom.hub.audit.event` row via `log()`. `create()` resolves `prev_hash` from latest existing row, computes `hash = sha256(canonical_json({timestamp, user_id, event_type, tenant_id, object_ref, summary, payload, prev_hash}))`. `write()` and `unlink()` ALWAYS raise `UserError` — truly append-only. `verify_chain()` re-walks and reports `bad_ids`. Genesis row seeded from `data/audit_event_seed.xml` with `prev_hash=""`.
- **AI usage roll-up**: `custom.hub.ai.usage._cron_refresh(lookback_days=7)` calls `Bridge._hub_usage_iter(since=cutoff)` IF the bridge implements that helper; buckets by `(tenant_id, date, model_name)`; upserts (unique constraint). `cache_hit_rate_pct` is computed from `cache_read_tokens / (input + cache_read + cache_creation)`.
- **Per-tenant Hub view**: `tenant.registry` (inherited) gets `business_domain`, `deployment_topology`, `vpn_endpoint`, `assigned_module_ids`, `assigned_capability_ids`, computed `health_status` (pulls from `custom.ops.tenant.health` if installed, else `unknown`), `last_incident_id`. All sibling-module access is guarded by `_hub_is_module_installed(name)`.
- **OWL dashboard**: `web.assets_backend` registers `hub_dashboard.js`/`.xml`/`.scss`; an `ir.actions.client` action `hub_dashboard_action` opens the heatmap + cards UI; menus wired up `post_init_hook="_post_install_link_menus"`.

**Key models**

- `custom.hub.module.catalog` — Catalog of every platform addon scanned from `addons/`. Unique by `module_name`. Carries capability tags + dep graph.
- `custom.hub.module.deployment` — One row per (module, tenant) operation. Inherits `mail.thread`, `mail.activity.mixin`. Holds canary state, rollback snapshot link, healthcheck result.
- `custom.hub.audit.event` — Append-only hash-chained audit log. `write`/`unlink` raise. `verify_chain()` validates the chain.
- `custom.hub.ai.usage` — Per-tenant per-day per-model AI usage aggregate; unique `(tenant_id, date, model_name)`.
- `tenant.registry` (inherited) — Adds business_domain, deployment_topology, VPN endpoint, assigned modules/capabilities, computed health.
- `custom.hub.deploy.module.wizard` — TransientModel; staging form before `create + action_deploy`.
- `custom.hub.rescan.catalog.wizard` — TransientModel; triggers `_action_scan_all`.

**Important fields**

- `custom.hub.module.catalog.module_name` (Char, unique, indexed) — `__manifest__.py` directory name.
- `custom.hub.module.catalog.category` (Selection core/compliance/ee_gap/operations/vertical, indexed) — derived from `addons/<bucket>/` location.
- `custom.hub.module.catalog.maturity` (Selection scaffold/partial/production, indexed) — heuristic from model count + tests.
- `custom.hub.module.catalog.capability_tag_ids` (M2m custom.module.capability.tag) — BRD-analyzer tag mapping.
- `custom.hub.module.catalog.depends_module_ids` (M2m self) — dep graph used by `action_resolve_dependencies`.
- `custom.hub.module.catalog.models_own_count` / `models_inherit_count` — `_name=` and `_inherit=` regex matches.
- `custom.hub.module.deployment.deploy_mode` (Selection install/upgrade/uninstall, indexed) — operation type.
- `custom.hub.module.deployment.state` (Selection pending/installing/installed/upgrading/failed/uninstalled, indexed, tracking) — lifecycle.
- `custom.hub.module.deployment.canary_phase` (Selection none/canary/staged/full/rolled_back, indexed, tracking) — Track C phase.
- `custom.hub.module.deployment.rollback_snapshot_id` (M2o tenant.backup, set_null) — pre-deploy snapshot.
- `custom.hub.module.deployment.healthcheck_passed` (Boolean) / `healthcheck_at` (Datetime) — canary gate.
- `custom.hub.module.deployment.dep_graph_resolved_json` (Text, JSON) — `{"order": [...], "missing": [...]}`.
- `custom.hub.module.deployment.environment_id` (M2o tenant.environment, injected by `custom_tenant_infra`) — optional target environment.
- `custom.hub.audit.event.event_type` (Selection vertical_provision/vertical_suspend/module_deploy/module_upgrade/brd_approve/incident_acknowledge/ai_config_change/secret_rotate/genesis, indexed) — taxonomy.
- `custom.hub.audit.event.prev_hash` / `hash` (Char) — SHA-256 hex chain.
- `custom.hub.audit.event.object_ref` (Reference, dynamic whitelist `_selection_object_ref`: tenant.registry / catalog / deployment / res.users) — related object.
- `custom.hub.audit.event.payload` (Json) — event-specific data; part of hash.
- `custom.hub.ai.usage.cache_hit_rate_pct` (Float, computed, stored) — `cache_read / (input + cache_read + cache_creation) * 100`.
- `tenant.registry.business_domain` (Selection rental/manufacturing/retail/services/government/finance/healthcare/logistics/ppob/wms/other, indexed, tracking).
- `tenant.registry.health_status` (Selection green/yellow/red/unknown, computed, store=False) — passthrough to `custom.ops.tenant.health.status` latest.

### custom_onboarding_journey — Custom Onboarding Journey

|  |  |
| --- | --- |
| Path | `addons/control_plane/custom_onboarding_journey` |
| Version | 19.0.1.0.0 |
| Scope | Platform |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_brd_analyzer`, `custom_super_admin`, `custom_approval_engine`, `custom_tenant_infra`, `project`, `mail`, `portal` |
| Models / routes / tests | 6 / 2 / 2 |
| Tags | multi-tenant, approval-workflow, audit-trail, crm |

> Knowledge file is generator output, not human-reviewed.

Single state machine that walks every prospective tenant from first intake to live tenant handover. Provides `onboarding.journey` with an explicit allowed-transitions graph, an append-only `onboarding.stage.transition` audit trail, a public-intake controller (`/onboarding/public/intake` + `/onboarding/public/status/<token>`) gated by Cloudflare Turnstile + per-IP rate-limiting, bi-directional sync with `project.project` (kanban columns ↔ stages with loop prevention and last-write-wins on `sync_version`), and a Go/No-Go wizard that creates an `approval.request`. Links the journey to BRD docs, the eventual `tenant.registry`, the `tenant.vps`, and the `tenant.environment`.

**How it works**

- **Public intake**: Marketing site POSTs to `/onboarding/public/intake` with `{company_name, contact_email, ...optional brd_file_base64s, vertical_target, cf_turnstile_token, ...}`. Controller hashes source IP (SHA-256), enforces per-IP rate limit (process-local bucket, configurable `per_hour`), verifies Turnstile if `cf_turnstile_secret` configured, then `onboarding.public.submission.create_from_payload(payload)` writes a raw inbox row and returns `{token, status_url}`.
- **Promote to journey**: BA reviews submissions, clicks `action_promote_to_journey` → finds/creates `res.partner` by email → creates `onboarding.journey` with `stage=brd_uploaded` if `brd_file_base64s` present, else `intake`. For each uploaded BRD, decodes base64 (handles `data:...;base64,` prefix), creates `ir.attachment` then `brd.document(name, document_attachment_id, journey_id, ...)` and re-points the attachment.
- **Stage machine**: `_FORWARD` defines allowed transitions per stage: `draft → intake → brd_uploaded → brd_analyzed → recommendations_ready → go_no_go → provisioning_requested → provisioning_in_progress → tenant_live → handover → closed`. Any non-terminal stage can move to `rejected` or `on_hold`; `on_hold` can resume to any non-terminal stage. `write()` validates the transition (raises `ValidationError`), bumps `sync_version`, appends `onboarding.stage.transition`, posts chatter, auto-archives the linked `project.project` on `closed`. The append-only transition model's `write()` raises `AccessError` (only superuser may `unlink`).
- **Bi-directional project sync** (`journey_project_sync.py`): `create()` calls `_ensure_project` (creates `project.project` from template). On stage write, `_sync_stage_to_project_tasks(new_stage)` moves the "stage marker" task to the column from `STAGE_TO_COLUMN`. The reverse direction (task column change → journey stage update via `COLUMN_TO_STAGE`) is also wired. Loop prevention: both sides check `self.env.context.get("_skip_journey_sync")` and short-circuit. Conflicts resolved by `sync_version` last-write-wins.
- **Wizards**: `onboarding.intake.wizard` captures structured intake. `onboarding.brd.upload.wizard` uploads a BRD to the journey. `onboarding.go.no.go.wizard` creates an `approval.request` linked via `approval_request_id`; the journey advances to `provisioning_requested` on approval.
- **Public status endpoint** `/onboarding/public/status/<public_status_token>` exposes non-sensitive read-only stage + progress for the prospect.

**Key models**

- `onboarding.journey` — Central state machine. Inherits `mail.thread`, `mail.activity.mixin`. Links partner, BRDs, approval, tenant, VPS, environment, project.
- `onboarding.stage.transition` — Append-only audit row per stage move. `write()` raises `AccessError`.
- `onboarding.public.submission` — Raw inbox for public-site form submissions. Promoted to `onboarding.journey` by BA action.
- `brd.document` (extended via `brd_document_extension.py`) — adds `journey_id` back-reference.
- `brd.recommendation` (extended via `brd_recommendation_extension.py`) — adds `journey_id` derived link.

**Important fields**

- `onboarding.journey.stage` (Selection from `STAGE_SELECTION`, required, indexed, tracking) — drives the entire workflow.
- `onboarding.journey.partner_id` (M2o res.partner, restrict, tracking) — the prospect/customer.
- `onboarding.journey.brd_document_ids` (One2many brd.document) + `brd_recommendation_ids` (related, readonly) — uploaded analysis input + AI-generated recommendations.
- `onboarding.journey.approval_request_id` (M2o approval.request, set_null, copy=False) — Go/No-Go approval anchor.
- `onboarding.journey.tenant_registry_id` (M2o tenant.registry, set_null, copy=False) — materialized tenant.
- `onboarding.journey.tenant_vps_id` (M2o tenant.vps, set_null, copy=False) — provisioned VPS.
- `onboarding.journey.tenant_environment_id` (M2o tenant.environment, set_null, copy=False) — `prod` environment row.
- `onboarding.journey.project_id` (M2o project.project, set_null, copy=False, indexed) — synced kanban project.
- `onboarding.journey.project_orphaned` (Boolean, default False, copy=False) — set when project was archived/deleted but journey continues.
- `onboarding.journey.mandays_estimate` (Integer, computed, stored, depends `brd_recommendation_ids.estimated_md`) — sum of BRD recommendation effort.
- `onboarding.journey.target_go_live` (Date, tracking) — committed go-live date.
- `onboarding.journey.owner_id` / `ba_id` (M2o res.users, tracking) — owner + business analyst.
- `onboarding.journey.company_profile_json` (Text) — intake-captured JSON.
- `onboarding.journey.public_status_token` (Char, unique, indexed, default `secrets.token_urlsafe(24)`) — URL token for public status page.
- `onboarding.journey.sync_version` (Integer, default 0, copy=False) — last-write-wins counter for project sync.
- `onboarding.journey.progress_pct` (Integer, computed, stored, depends `stage`) — % of happy-path length.
- `onboarding.stage.transition.from_stage` / `to_stage` (Char) — transition delta. `write()` raises.
- `onboarding.public.submission.raw_payload_json` (Text, required) — verbatim incoming payload.
- `onboarding.public.submission.source_ip_hash` (Char, indexed) — SHA-256 hash of source IP (PDP-friendly, no raw IP).
- `onboarding.public.submission.status` (Selection submitted/promoted/rejected, required, indexed) — inbox lifecycle.
- `onboarding.public.submission.public_token` (Char, unique, indexed, `secrets.token_urlsafe(24)`) — anonymous tracking token.

**Endpoints**: `/onboarding/public/intake`, `/onboarding/public/status/<string:token>`

### custom_ops_monitor — Custom Ops Monitor

|  |  |
| --- | --- |
| Path | `addons/operations/custom_ops_monitor` |
| Version | 19.0.0.1.0 |
| Scope | Platform |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `custom_pdp_audit`, `custom_super_admin`, `mail`, `web` |
| Models / routes / tests | 3 / 1 / 1 |
| Tags | multi-tenant, anomaly-detection, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Server-side ops dashboard that turns Prometheus, the `custom-predictor` ML service, and Alertmanager webhooks into Odoo records so the platform ops team has a single pane of glass per tenant — without leaving Odoo. Three pillars: minute-by-minute **tenant health snapshots** (`custom.ops.tenant.health`), hourly **capacity forecasts** (`custom.ops.capacity.forecast`), and webhook-ingested **incidents** (`custom.ops.incident`) that auto-create `mail.activity` for on-call.

**How it works**

- **Health snapshots**: `_cron_collect_snapshots` (60s) iterates `tenant.registry` `state=active`, runs a fixed PromQL set via `PrometheusClient.values_by_label(result, "db")`, creates one `custom.ops.tenant.health` row per tenant tagged with `snapshot_at=now()`. Computed `health_score` (0-100) penalizes CPU>50, mem>60, disk>70, error_rate, stale/failed backups; computed `status` thresholds: ≥75 green, ≥50 yellow, <50 red. Backup freshness: ≤26h ok, ≤36h stale, otherwise failed.
- **Capacity forecasts**: `_cron_regenerate` (hourly) reads the last 30 days of `custom.ops.tenant.health` per tenant per metric (cpu/memory/disk/db_size), POSTs `{metric, history}` to the predictor URL (`custom_ops_monitor.predictor_url`, default `http://predictor:8000/forecast`), stores `forecast_30d/90d/365d` + confidence interval + `recommended_action` per row. `_compute_severity` flags `critical` when `forecast_30d > ceiling*0.9`, `warn` when `forecast_90d > ceiling*0.8` (ceilings: cpu/memory/disk = 100; db_size = None → always info).
- **Incidents**: Alertmanager POSTs to `/api/ops/alert` (HMAC-secured via `@secure_endpoint('ops_alertmanager')`). Controller calls `custom.ops.incident.ingest_alertmanager_payload(payload)` which iterates `payload["alerts"]` and upserts one row per alert keyed by `fingerprint`. New firing → `_schedule_ack_activity()` assigns a `mail.activity` ("Acknowledge: ...") to the first user in `custom_ops_monitor.group_ops_engineer`. Resolved alerts on existing rows → state=resolved + `resolved_at`; resolved status on unknown fingerprint is dropped (no row created).
- **Dashboard**: OWL component (`web.assets_backend`) renders the per-tenant heatmap tile, drills into time-series, and embeds a Grafana iframe at the URL set in `custom_super_admin.grafana_base_url`.

**Key models**

- `custom.ops.tenant.health` — Per-minute snapshot of CPU/memory/disk/error rate/backup freshness per tenant.
- `custom.ops.capacity.forecast` — Forecasts from the predictor service per (tenant, metric).
- `custom.ops.incident` — Alertmanager-driven incident record. Inherits `mail.thread`, `mail.activity.mixin`. `(fingerprint)` unique for upsert dedup.
- `PrometheusClient` — Plain Python helper (not a Model); thin urllib wrapper around `/api/v1/query` and `/api/v1/query_range`. Instantiated on demand.

**Important fields**

- `custom.ops.tenant.health.tenant_id` (M2o tenant.registry, cascade) — owner.
- `custom.ops.tenant.health.snapshot_at` (Datetime, indexed) — series timestamp.
- `custom.ops.tenant.health.cpu_pct` / `memory_pct` / `disk_pct` / `error_rate_pct` (Float) — raw metric values.
- `custom.ops.tenant.health.memory_mb_used/total` / `disk_gb_used/total` / `db_size_mb` (Integer) — absolute volumes.
- `custom.ops.tenant.health.request_rate_per_min` / `redis_hit_rate_pct` (Float) — throughput + cache health.
- `custom.ops.tenant.health.last_backup_at` (Datetime, copied from tenant) + `backup_status` (Selection ok/stale/failed, classified by `_classify_backup`) — backup freshness.
- `custom.ops.tenant.health.health_score` (Integer, computed, stored) — 0-100.
- `custom.ops.tenant.health.status` (Selection green/yellow/red, computed, stored, indexed) — RAG bucket.
- `custom.ops.capacity.forecast.metric` (Selection cpu/memory/disk/db_size, indexed) — forecast subject.
- `custom.ops.capacity.forecast.forecast_30d` / `forecast_90d` / `forecast_365d` (Float) — projections.
- `custom.ops.capacity.forecast.confidence_lower` / `confidence_upper` (Float) — predictor's CI.
- `custom.ops.capacity.forecast.recommended_action` (Char) — predictor-supplied prose.
- `custom.ops.capacity.forecast.severity` (Selection info/warn/critical, computed, stored) — derived from `forecast_*` vs `_CAPACITY_CEILING`.
- `custom.ops.incident.alert_name` / `severity` (info/warning/critical/page) / `fired_at` / `resolved_at` / `summary` / `description` / `runbook_url` — alert payload mirror.
- `custom.ops.incident.fingerprint` (Char, indexed, unique) — Alertmanager dedup key.
- `custom.ops.incident.state` (Selection firing/acknowledged/resolved, indexed) — lifecycle.
- `custom.ops.incident.raw_payload` (Text, truncated to 10000 chars) — forensic preservation.
- `custom.ops.incident.name` (Char, computed `[<tenant.slug|global>] <alert_name>`) — display.

**Endpoints**: `/api/ops/alert`

### custom_super_admin — Custom Super Admin (Platform Operations)

|  |  |
| --- | --- |
| Path | `addons/control_plane/custom_super_admin` |
| Version | 19.0.0.2.0 |
| Scope | Platform |
| Maturity / confidence | Produksi / Sedang |
| Depends | `custom_core`, `mail` |
| Models / routes / tests | 7 / 0 / 1 |
| Tags | multi-tenant, audit-trail, approval-workflow |

> Knowledge file is generator output, not human-reviewed.

Ops-only **multi-tenant control plane** running in the platform's `master_admin` database. Provides the UI and HMAC-signed orchestrator client that lets ops and CSM provision, suspend, resume, archive, backup, and restore tenants without SSH. Mirrors the master DB's `tenant_registry.tenants`, `tenant_registry.backups`, and the append-only hash-chained `tenant_registry.action_log_v` view into Odoo models via cron — Odoo never writes to the source registry directly; writes go through the orchestrator REST API which then re-publishes to the registry. Plus a Grafana iframe link, retention-aware backup ledger, and croniter-aware scheduled-backup mechanism.

**How it works**

- **Sync from orchestrator**: `_cron_sync_from_orchestrator` (every minute) calls `orchestrator_client.list_tenants()` → `_upsert_many` writes/updates `tenant.registry` rows; slugs missing from upstream are marked `archived` locally. `_cron_sync_for(slug)` per-tenant variant is called after each action button.
- **Provision a tenant**: User opens `tenant.provision.wizard` → orchestrator POST `/v1/tenants` with payload → wizard waits → sync cron picks up the new row.
- **Lifecycle actions** on a `tenant.registry` row:
- `action_suspend` → `orchestrator_client.suspend(slug, reason)` → resync → notify.
- `action_resume` → `orchestrator_client.resume(slug)`.
- `action_archive` → `orchestrator_client.archive(slug, retention_days=30)` (sets `purge_after` in master DB).
- `action_trigger_backup` → `orchestrator_client.run_backup(slug, kind="manual")` → calls `tenant.backup._cron_sync_for(slug)` to mirror the new backup row → success toast with `s3_key`/`size_bytes`.
- `action_open_restore_wizard` → `tenant.restore.wizard` (pick a `tenant.backup`, optional target db) → orchestrator restore.
- `action_open_replicate_wizard` → `tenant.replicate.wizard` (clone prod to staging-style env).
- `action_open_grafana` → opens `<grafana_base_url>/d/tenant?var-db=<db_name>` in new tab.
- **Backup ledger**: `tenant.backup` mirrored from master DB via `_cron_sync_all` (uses orchestrator `list_backups(slug)`); per-row `_compute_size_human` formats bytes. Scheduled backups driven by `croniter` parsing `tenant.registry.backup_schedule` (default `"0 2 * * *"`).
- **Action log mirror**: `tenant.action.log._cron_sync` queries the master DB directly via `cr.execute("SELECT ... FROM tenant_registry.action_log_v WHERE id > %s ORDER BY id ASC LIMIT 5000")` — works ONLY because the runtime postgres user has been GRANTed `tenant_registry_reader` and the master and runtime DBs are in the same cluster. Skips silently if the `tenant_registry` schema isn't visible (e.g. running from a tenant DB instead of master_admin). `action_verify_chain()` calls master-side `tenant_registry.verify_action_chain()`.
- **All write methods on `tenant.registry`** are restricted to `custom_super_admin.group_super_admin`; the model is read-only otherwise from the UI.

**Key models**

- `tenant.registry` — Local mirror of master DB `tenant_registry.tenants`. Inherits `mail.thread`. Source of truth is master DB; UI writes go through orchestrator.
- `tenant.backup` — Mirror of master DB `tenant_registry.backups` ledger. Carries `s3_key`, `checksum_sha256`, `outcome`, `expires_at`.
- `tenant.action.log` — Append-only mirror of master DB `tenant_registry.action_log_v` (hash-chained). Direct SQL pull, schema-existence-guarded.
- `custom.super.admin.orchestrator.client` — AbstractModel; HMAC-signed httpx wrapper for `${ORCHESTRATOR_URL}/v1/...`.
- `tenant.provision.wizard` / `tenant.restore.wizard` / `tenant.replicate.wizard` — TransientModels; staging forms before orchestrator calls.

**Important fields**

- `tenant.registry.slug` (Char, required, indexed, copy=False, unique constraint) — DNS-safe tenant identifier.
- `tenant.registry.db_name` (Char, required) — postgres DB name for the tenant.
- `tenant.registry.state` (Selection provisioning/active/suspended/archived/failed, indexed, default provisioning) — lifecycle.
- `tenant.registry.activated_at` / `suspended_at` / `archived_at` / `purge_after` / `last_seen_at` (Datetime) — lifecycle stamps from orchestrator.
- `tenant.registry.last_backup_at` / `last_backup_size_bytes` / `last_backup_id` — latest backup pointer.
- `tenant.registry.csm_user_id` (M2o res.users) — assigned customer success manager.
- `tenant.registry.features` (Json) — orchestrator-managed feature flags.
- `tenant.registry.sync_error` (Text) — last orchestrator error per tenant.
- `tenant.registry.backup_schedule` (Char, default `"0 2 * * *"`) — 5-field cron expression (UTC) parsed by `croniter`.
- `tenant.registry.backup_retention_days` (Integer, default 30) — retention horizon.
- `tenant.registry.pitr_enabled` (Boolean, default False) — WAL-archiving toggle (set on master side).
- `tenant.registry.last_scheduled_backup_at` (Datetime, readonly) — last cron-driven backup timestamp.
- `tenant.backup.master_id` (Integer, indexed, required, unique constraint) — id in master DB.
- `tenant.backup.kind` (Selection manual/daily/monthly/yearly, required) — backup taxonomy.
- `tenant.backup.s3_key` / `checksum_sha256` (Char) — storage pointer + integrity.
- `tenant.backup.outcome` (Selection pending/success/failure, required) — result.
- `tenant.backup.size_human` (Char, computed) — pretty `n.n KB/MB/GB/TB/PB`.
- `tenant.backup.expires_at` (Datetime) — retention expiry.
- `tenant.action.log.master_id` (Integer, required, indexed, unique) — id in master DB action log.
- `tenant.action.log.detail` (Json), `outcome` (Selection success/failure/partial), `prev_hash_hex` / `hash_hex` (Char) — hash chain from master.

### custom_tenant_infra — Custom Tenant Infra

|  |  |
| --- | --- |
| Path | `addons/control_plane/custom_tenant_infra` |
| Version | 19.0.0.1.0 |
| Scope | Platform |
| Maturity / confidence | Produksi / Rendah |
| Depends | `custom_super_admin`, `custom_ops_monitor`, `custom_hub_console` |
| Models / routes / tests | 4 / 0 / 1 |
| Tags | multi-tenant, audit-trail |

> Knowledge file is generator output, not human-reviewed.

Manages the per-tenant **VPS fleet** end-to-end from Odoo. Lets ops register a VPS, harden it, install Docker/Caddy, deploy the Odoo stack for one or more `tenant.environment` rows (dev/staging/prod), sync addons, run healthchecks, and decommission — all by clicking buttons that delegate to the HMAC-signed orchestrator API. Adds versioned jinja2 bootstrap-script templates stored as `ir.attachment` so ops can edit hardening scripts without a code deploy. Adds `environment_id` and `target_environment_id` fields onto hub_console's deployment model + canary wizard (because `custom_hub_console` cannot depend on `custom_tenant_infra` — dependency goes the other way).

**How it works**

- **Register a VPS**: Ops creates `tenant.vps` (name, hostname unique, public_ip, ssh_port=22, ssh_user=root, `ssh_credential_ref` like `vault://prod/vps/{id}/ssh_key`, provider, region, hardware specs). State starts `registered`.
- **Link environments**: Create `tenant.environment` rows (env_type dev/staging/prod, `tenant_registry_id`, `db_name`, `vps_id`). SQL constraint `EXCLUDE (vps_id WITH =) WHERE (env_type = 'prod')` ensures one prod env per VPS; `unique(tenant_registry_id, env_type)` ensures one env per type per tenant.
- **Bootstrap**: `action_bootstrap()` → `_set_state("hardening")` → `deployer.bootstrap(vps)` → POST `/v1/vps/{id}/bootstrap` (jinja2-rendered hardening + Docker + Caddy script). On success `_set_state("bootstrapping")` then `"active"`. Failure raises `UserError` with the orchestrator error.
- **Deploy stack**: `action_deploy_odoo_stack()` requires state ∈ {active, degraded}. For each linked environment, calls `deployer.deploy_stack(vps, env)` → POST `/v1/vps/{id}/deploy-stack` with `env_type`, `tenant_slug`, `db_name`. Appends progress to `bootstrap_log` (OWL console streams via SSE).
- **Sync addons**: `action_sync_addons()` → for each env, `deployer.sync_addons(vps, env)` → POST `/v1/vps/{id}/sync-addons` (git pull + restart on the VPS).
- **Healthcheck**: `action_healthcheck()` → `deployer.healthcheck(vps)`, expects `{ok: bool}`. On `ok=False` while active → state transitions to `degraded`; on `ok=True` while degraded → back to `active`. Stamps `last_health_check_at`.
- **Decommission**: `action_decommission()` → orchestrator call → state `decommissioned` (terminal).
- **Bootstrap templates**: `tenant.vps.bootstrap.template` stores versioned jinja2 scripts per `script_kind` (harden_os/install_docker/install_caddy/deploy_odoo) as `ir.attachment`. The orchestrator renders them with VPS-specific variables before scp'ing.
- **Hub deploy integration**: `custom.hub.module.deployment.environment_id` (injected here) lets canary deploys target a specific environment.

**Declared models**: `tenant.environment`, `tenant.vps`, `tenant.vps.bootstrap.template`, `tenant.vps.deployer`

**Important fields**

- `tenant.vps.state` (Selection registered/hardening/bootstrapping/active/degraded/decommissioned, indexed, tracking) — validated via `ALLOWED_TRANSITIONS` in `_assert_transition`.
- `tenant.vps.hostname` (Char, required, tracking, unique constraint) — DNS-resolvable hostname.
- `tenant.vps.public_ip` (Char, tracking) — IPv4/IPv6.
- `tenant.vps.ssh_user` (Char, default `root`, required) / `ssh_port` (Integer, default 22, required).
- `tenant.vps.ssh_credential_ref` (Char, required) — vault pointer (`vault://...` or `env://VPS_SSH_KEY_PATH`). NEVER raw key material.
- `tenant.vps.provider` (Selection biznet/idcloudhost/digitalocean/hetzner/aws/other) — hosting provider.
- `tenant.vps.cpu_cores` / `ram_mb` / `disk_gb` (Integer) — capacity.
- `tenant.vps.os_version` / `docker_version` (Char) — detected by SSH facter during bootstrap.
- `tenant.vps.prometheus_target_url` / `grafana_dashboard_uid` (Char) — monitoring wiring.
- `tenant.vps.bootstrap_log` (Text) — append-only log stream `[<iso_ts>] <line>\n`, written by `_append_log`. Streamed to OWL via SSE.
- `tenant.vps.last_health_check_at` (Datetime) — last `action_healthcheck` timestamp.
- `tenant.vps.environment_ids` (One2many tenant.environment) + computed `environment_count`.
- `tenant.environment.env_type` (Selection dev/staging/prod, required, default dev) — environment class.
- `tenant.environment.db_name` (Char, required, validated non-blank by `_check_db_name`) — postgres DB.
- `tenant.environment.odoo_url` (Char) — public URL (set by orchestrator after deploy).
- `tenant.environment.addons_revision` (Char) — git SHA currently deployed.
- `tenant.environment.last_deploy_id` (Char) — orchestrator run id of last deploy.
- `tenant.environment.last_deploy_at` (Datetime).
- `tenant.environment.name` (Char, computed `<slug>/<env_type>`).
- `tenant.vps.bootstrap.template.script_kind` (Selection harden_os/install_docker/install_caddy/deploy_odoo, indexed, required) — script taxonomy.
- `tenant.vps.bootstrap.template.script_attachment_id` (M2o ir.attachment, restrict, required) — holds the jinja2 body.
- `tenant.vps.bootstrap.template.variables_json` (Json) — default jinja2 variables merged with per-VPS values at render time.

## Third-party components (OCA) and templates

Vendored or reference-only. Counted in the total so the figures reconcile, but not described in depth — they are not features delivered to a tenant.

- `auth_jwt` 19.0.1.0.2 —
        JWT bearer token authentication.
- `base_rest` 18.0.1.1.1 —
        Develop your own high level REST APIs for Odoo thanks to this addon.

- `custom_vertical_example` 19.0.0.1.0 — Reference vertical template used as a starting point
- `partner_firstname` 19.0.1.0.0 — Split first name and last name for non company partners
- `queue_job` 19.0.2.0.1 — Job Queue
