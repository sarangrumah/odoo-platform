# Business Requirements Document (BRD)
## Implementasi PPOB / Bill-Payment Switching di atas Odoo 19

| | |
|---|---|
| **Dokumen** | 01 — Business Requirements Document |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Pembaca** | Sponsor, Product Owner, Finance Lead, Ops Lead, BA |
| **Prasyarat** | [`00-Project-Initiation-Document.md`](00-Project-Initiation-Document.md) |

---

## Contents

1. [Latar belakang](#1-latar-belakang)
2. [Masalah bisnis yang diselesaikan](#2-masalah-bisnis-yang-diselesaikan)
3. [Tujuan bisnis & KPI](#3-tujuan-bisnis--kpi)
4. [Ruang lingkup](#4-ruang-lingkup)
5. [Proses bisnis target](#5-proses-bisnis-target)
6. [Daftar kebutuhan bisnis (BR)](#6-daftar-kebutuhan-bisnis-br)
7. [Aturan bisnis kunci](#7-aturan-bisnis-kunci)
8. [Pemangku kepentingan & peran](#8-pemangku-kepentingan--peran)
9. [Asumsi & ketergantungan](#9-asumsi--ketergantungan)
10. [Risiko bisnis](#10-risiko-bisnis)

---

## 1. Latar belakang

Penyelenggara PPOB menjual produk digital (pulsa, paket data, token & tagihan listrik, air,
BPJS, e-wallet, voucher game) melalui **jaringan mitra prepaid**. Mitra menyetor saldo lebih
dulu; setiap penjualan mendebit saldo itu seketika, lalu sistem meneruskan permintaan ke
**biller** melalui switcher.

Tiga hal membuat model ini berbeda dari retail biasa:

1. **Uang bergerak sebelum barang dipastikan terkirim.** Saldo mitra didebit, lalu biller
   dipanggil. Bila biller gagal, saldo wajib kembali otomatis dan berpasangan jurnal.
2. **Marjin tipis dan bervolume tinggi.** Selisih beberapa ratus rupiah per transaksi
   dikalikan puluhan ribu transaksi per hari — kesalahan pembukuan kecil menjadi material.
3. **Perlakuan PPN khusus.** PMK-63/2022 menetapkan dasar pengenaan atas **nilai lain /
   marjin**, bukan nilai bruto transaksi.

## 2. Masalah bisnis yang diselesaikan

| # | Masalah saat ini | Akibat |
|---|---|---|
| P1 | Saldo mitra dipegang aplikasi terpisah dari buku besar | Saldo dan GL tak pernah sama pada hari yang sama; rekonsiliasi manual mingguan |
| P2 | Eksekusi biller dan pembukuan berada di dua sistem | Marjin per produk/mitra tidak terlihat tanpa rekap manual |
| P3 | Transaksi menggantung diselesaikan manual | Risiko refund ganda atau mitra dirugikan |
| P4 | Deposit biller tidak terpantau | Penjualan berhenti mendadak karena deposit habis |
| P5 | Top-up mitra dicocokkan manual dari rekening koran | Mitra menunggu; risiko salah kredit |
| P6 | PPN & PPh dihitung dari rekap spreadsheet | Risiko koreksi pajak dan keterlambatan Coretax |
| P7 | Tidak ada pengukuran throughput/latensi | Tak ada dasar objektif untuk SLA ke mitra maupun ke biller |

## 3. Tujuan bisnis & KPI

| # | KPI | Baseline | Target |
|---|---|---|---|
| K1 | Selisih saldo wallet mitra vs akun liability GL | manual/mingguan | **0**, otomatis harian |
| K2 | Transaksi terjual ganda | tak terukur | **0** |
| K3 | Transaksi menggantung > SLA tanpa resolusi otomatis | manual | **0** |
| K4 | Waktu tersedianya laporan marjin | D+7 manual | **D+1 otomatis** |
| K5 | Top-up mitra terkredit otomatis | manual | **≥ 95%** |
| K6 | Faktur ringkas per mitra terbit otomatis | manual | **100% hari kerja** |
| K7 | p95 latensi jalur jual | tak terukur | **terukur & di bawah target SLA** |
| K8 | Deposit biller menyentuh nol tanpa peringatan | insidental | **0 kejadian** |

## 4. Ruang lingkup

### 4.1 In-scope

- Master data PPOB: kelas produk, katalog, tier harga, mitra, provider/biller, pemetaan akun.
- Wallet mitra prepaid dengan buku pembantu berpasangan GL.
- Top-up mitra melalui Virtual Account bank dan rekonsiliasi rekening koran.
- Deposit biller (bucket) beserta top-up DP-100% dan perlakuan PPN masukan.
- Mesin transaksi: routing, failover, idempotensi, refund otomatis, reaper.
- Integrasi biller melalui adapter; gateway H2H masuk untuk kanal penjualan.
- Komisi dua arah (dari provider dan ke mitra) beserta PPh 23 dan bukti potong.
- Rollup faktur harian per mitra untuk e-Faktur/Coretax.
- Target SLA, sampling throughput, dan monitoring operasional.

### 4.2 Out-of-scope (kecuali dinyatakan lain dalam SOW per klien)

- Aplikasi mitra/outlet (mobile/web) dan pengalaman pengguna di sisi mitra.
- Perjanjian komersial dengan biller dan bank.
- Perizinan penyelenggaraan.
- Sistem lama yang digantikan (dimatikan oleh klien).
- Migrasi riwayat transaksi di luar saldo pembuka dan periode rekonsiliasi yang disepakati.

## 5. Proses bisnis target

```
   MITRA                         ODOO                             BILLER / BANK
     |                             |                                    |
     |  1. top-up ke VA bank       |                                    |
     |---------------------------->|<--- callback pembayaran -----------|
     |                             |  kredit wallet + jurnal            |
     |                             |                                    |
     |  2. jual (API/kanal)        |                                    |
     |---------------------------->|                                    |
     |                             |  cek cap & saldo                   |
     |                             |  debit wallet   (jurnal)           |
     |                             |  debit deposit  (jurnal)           |
     |                             |  dispatch ------------------------>|
     |                             |<-- sukses / gagal / pending -------|
     |<-- struk / token / error ---|                                    |
     |                             |  gagal  -> refund wallet+deposit   |
     |                             |  pending-> reaper tanya status     |
     |                             |                                    |
     |                             |  3. akhir hari:                    |
     |                             |     rollup faktur ringkas / mitra  |
     |                             |     akrual komisi + PPh 23         |
     |                             |     sampling throughput & SLA      |
```

## 6. Daftar kebutuhan bisnis (BR)

**Prioritas MoSCoW:** M = Must, S = Should, C = Could, W = Won't (rilis ini).
**Status platform:** SUDAH ADA = terverifikasi di repo 2026-08-11 · PERLU DIBANGUN = belum ada,
dibiayai eksplisit di dokumen 05 · KONFIGURASI = ada, perlu disetel per klien.

### 6.1 Master data — `BR-MD`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-MD-01 | Produk PPOB dikelompokkan dalam **kelas** (telko, PLN, air, BPJS, e-wallet, game) dengan akun default per kelas | M | SUDAH ADA |
| BR-MD-02 | Katalog produk memiliki kode unik, denominasi, harga modal default, dan penanda "perlu inquiry" | M | SUDAH ADA |
| BR-MD-03 | Harga jual ke mitra ditentukan **tier** (mis. Silver/Gold/Platinum) per produk | M | SUDAH ADA |
| BR-MD-04 | Mitra dan provider adalah partner dengan penanda khusus, kode mitra unik, dan tier melekat | M | SUDAH ADA |
| BR-MD-05 | Mitra dapat dibatasi **cap transaksi harian dan bulanan** | S | SUDAH ADA |
| BR-MD-06 | Akun GL dipetakan lewat **peran** (revenue, COGS, deposit, PPN keluaran/masukan, dsb.), bukan hard-code kode akun | M | SUDAH ADA |
| BR-MD-07 | Master dapat diimpor massal dari berkas klien (produk, tier, mitra, SKU map) | S | KONFIGURASI |

### 6.2 Wallet mitra — `BR-WL`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-WL-01 | Setiap mitra memiliki saldo per **kelas produk** per perusahaan (unik) | M | SUDAH ADA |
| BR-WL-02 | Debit dan kredit saldo bersifat **atomik**, aman terhadap transaksi paralel | M | SUDAH ADA |
| BR-WL-03 | Debit ditolak bila melampaui saldo + **credit limit** | M | SUDAH ADA |
| BR-WL-04 | Wallet dapat **dibekukan**; wallet beku menolak debit dan kredit | M | SUDAH ADA |
| BR-WL-05 | Setiap pergerakan saldo menghasilkan **jurnal berpasangan** pada transaksi DB yang sama | M | SUDAH ADA |
| BR-WL-06 | Buku pembantu wallet menyimpan saldo setelah setiap mutasi (`balance_after`) untuk audit | M | SUDAH ADA |
| BR-WL-07 | Saldo mitra dapat dibaca sistem luar untuk rekonsiliasi | M | PERLU DIBANGUN (G1) |
| BR-WL-08 | Sistem luar dapat **menahan (hold), meng-commit, dan melepas** saldo secara sinkron dan idempoten | M | PERLU DIBANGUN (G1) |
| BR-WL-09 | Saldo pembuka mitra dapat dimuat dari sistem lama dengan jurnal migrasi yang dapat ditelusuri | M | PERLU DIBANGUN |

### 6.3 Top-up mitra — `BR-TU`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-TU-01 | Setiap mitra dapat memiliki **Virtual Account** per bank (BCA, BRI, BNI, Mandiri, dst.) | M | SUDAH ADA |
| BR-TU-02 | Bank dapat menanyakan validitas VA (**inquiry**) dan memperoleh identitas mitra | M | SUDAH ADA |
| BR-TU-03 | Notifikasi pembayaran bank **mengkredit wallet otomatis** beserta jurnalnya | M | SUDAH ADA |
| BR-TU-04 | Callback ganda dari bank **tidak pernah** mengkredit dua kali (idempoten pada referensi bank) | M | SUDAH ADA |
| BR-TU-05 | Top-up juga dapat masuk lewat **rekonsiliasi rekening koran** bila bank tidak mengirim callback | S | SUDAH ADA |
| BR-TU-06 | Top-up dapat diperlakukan **inklusif pajak** bila kebijakan klien menghendaki (split DPP/PPN) | S | SUDAH ADA |
| BR-TU-07 | Top-up yang tidak dapat dipetakan masuk **antrean tinjauan**, bukan gagal diam-diam | M | SUDAH ADA |

### 6.4 Deposit biller — `BR-DP`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-DP-01 | Deposit per biller dicatat dalam **bucket**: satu bucket untuk semua produk (bulky) atau satu per denominasi | M | SUDAH ADA |
| BR-DP-02 | Pemakaian deposit bersifat **atomik** dan menolak saldo kurang | M | SUDAH ADA |
| BR-DP-03 | Saldo deposit tidak boleh negatif (dijaga di tingkat basis data) | M | SUDAH ADA |
| BR-DP-04 | **Low-water-mark** per bucket sebagai dasar peringatan deposit menipis | M | SUDAH ADA |
| BR-DP-05 | Top-up deposit ke biller mengikuti pola **DP 100%** dengan pemisahan DPP dan PPN masukan | M | SUDAH ADA |
| BR-DP-06 | Diskon dari biller saat top-up diakui sebagai pendapatan/pengurang biaya sesuai kebijakan | S | SUDAH ADA |
| BR-DP-07 | Saldo deposit awal dapat dimuat saat cutover dan direkonsiliasi dengan saldo riil biller | M | PERLU DIBANGUN |

### 6.5 Transaksi & routing — `BR-TX`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-TX-01 | Transaksi memiliki status jelas: pending, inquiry OK, diproses, sukses, gagal, timeout, refund | M | SUDAH ADA |
| BR-TX-02 | Permintaan yang sama dari mitra **tidak pernah dieksekusi dua kali** (kunci idempotensi unik per mitra) | M | SUDAH ADA |
| BR-TX-03 | Permintaan ulang dengan kunci sama **mengembalikan hasil transaksi asli** | M | SUDAH ADA |
| BR-TX-04 | Provider dipilih otomatis dari pemetaan SKU berdasarkan prioritas dan status provider (**failover**) | M | SUDAH ADA |
| BR-TX-05 | Harga modal mengikuti provider yang benar-benar dipanggil, bukan default produk | M | SUDAH ADA |
| BR-TX-06 | Produk dua langkah (tagihan) mendukung **inquiry** sebelum pembayaran | M | SUDAH ADA |
| BR-TX-07 | Kegagalan biller **otomatis mengembalikan** saldo mitra dan deposit beserta jurnal balik | M | SUDAH ADA |
| BR-TX-08 | Refund bersifat idempoten — tidak pernah mengembalikan dua kali | M | SUDAH ADA |
| BR-TX-09 | Transaksi menggantung diresolusi otomatis dengan **menanyakan status ke biller**; jawaban "masih diproses" tidak memicu refund | M | SUDAH ADA |
| BR-TX-10 | Ambang "menggantung" dapat disetel **per provider** | M | SUDAH ADA |
| BR-TX-11 | Transaksi gagal dapat **diulang** sebagai percobaan baru yang tetap tertaut ke asalnya | S | SUDAH ADA |
| BR-TX-12 | Ops dapat melakukan refund manual setelah konfirmasi ke biller | M | SUDAH ADA |

### 6.6 Integrasi biller — `BR-BL`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-BL-01 | Biller baru ditambahkan sebagai **adapter** tanpa mengubah mesin transaksi | M | SUDAH ADA |
| BR-BL-02 | Tersedia adapter **simulasi** untuk pengujian tanpa memanggil biller riil | M | SUDAH ADA |
| BR-BL-03 | Kredensial biller disimpan **per tenant** di luar record bisnis | M | SUDAH ADA |
| BR-BL-04 | Setiap panggilan biller tercatat (endpoint, latensi, status, galat) | M | SUDAH ADA |
| BR-BL-05 | Jalur pembayaran **tidak melakukan retry otomatis** agar tidak menjual dua kali | M | SUDAH ADA |
| BR-BL-06 | Adapter biller riil tersedia untuk setiap biller yang dipakai klien | M | PERLU DIBANGUN per biller (G4) |

### 6.7 Kanal masuk — `BR-CH`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-CH-01 | Kanal penjualan dapat bertransaksi ke Odoo lewat API tanpa mengubah aplikasi kanal (**drop-in** kontrak switcher lama) | M | SUDAH ADA |
| BR-CH-02 | Kanal dapat menanyakan status transaksi dan saldo mitra | M | SUDAH ADA |
| BR-CH-03 | Tersedia inquiry nama pelanggan e-wallet dan inquiry PLN | M | SUDAH ADA |
| BR-CH-04 | Katalog produk game beserta field dinamis dapat dibaca kanal; top-up game menerima payload dinamis | S | SUDAH ADA |
| BR-CH-05 | Hasil transaksi asinkron dikirim balik ke kanal lewat **callback** dalam SLA, dengan status polling sebagai cadangan | M | SUDAH ADA |
| BR-CH-06 | Setiap kanal/mitra memiliki kredensial sendiri dan **daftar IP yang diizinkan** | M | SUDAH ADA |
| BR-CH-07 | Perlindungan replay dan kesegaran waktu ditegakkan pada endpoint kanal | M | PERLU DIBANGUN (G5) |

### 6.8 Keuangan & pajak — `BR-FI`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-FI-01 | Penjualan dan harga modal ter-posting ke GL **saat transaksi**, bukan lewat rekap manual | M | SUDAH ADA |
| BR-FI-02 | Marjin per transaksi terhitung otomatis | M | SUDAH ADA |
| BR-FI-03 | PPN mengikuti mode per kelas produk: **marjin (PMK-63)**, nilai lain, bruto, atau bebas | M | SUDAH ADA |
| BR-FI-04 | PPN diakui pada **faktur ringkas harian per mitra**, bukan per transaksi | M | SUDAH ADA |
| BR-FI-05 | Rollup harian bersifat idempoten — menjalankan ulang tidak menggandakan faktur | M | SUDAH ADA |
| BR-FI-06 | Jurnal ringkasan non-GL dikecualikan dari laporan keuangan agar tidak dihitung ganda | M | SUDAH ADA |
| BR-FI-07 | Komisi **dari provider** dan **ke mitra** dihitung dari aturan berbasis kelas/produk/mitra | M | SUDAH ADA |
| BR-FI-08 | Komisi ke mitra dipotong **PPh 23** sesuai status NPWP mitra, dengan bukti potong | M | SUDAH ADA |
| BR-FI-09 | Akrual komisi dapat diselesaikan (settlement) secara massal | S | SUDAH ADA |
| BR-FI-10 | Laporan marjin per produk, mitra, dan biller tersedia harian | M | KONFIGURASI |

### 6.9 Operasional & SLA — `BR-OP`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-OP-01 | Target throughput dan latensi dapat dideklarasikan per provider dan per kelas produk | S | SUDAH ADA |
| BR-OP-02 | Throughput, tingkat sukses, dan latensi p95 tersampel otomatis per jam | S | SUDAH ADA |
| BR-OP-03 | Pelanggaran target ditandai otomatis pada sampel | S | SUDAH ADA |
| BR-OP-04 | Baseline historis sistem lama dapat disimpan berdampingan dengan aktual Odoo untuk **uji paritas** | M | SUDAH ADA |
| BR-OP-05 | Data masuk yang tidak dapat dipetakan masuk **antrean tinjauan** lengkap dengan alasan dan payload asli | M | SUDAH ADA |
| BR-OP-06 | Tersedia **backfill** untuk memasukkan ulang data periode tertentu | S | SUDAH ADA |
| BR-OP-07 | Peringatan deposit menipis sampai ke kanal notifikasi ops | M | PERLU DIBANGUN |

### 6.10 Non-fungsional — `BR-NF`

| # | Kebutuhan | Prioritas | Status |
|---|---|:--:|---|
| BR-NF-01 | Debit paralel pada mitra yang sama tidak boleh menghasilkan saldo negatif | M | SUDAH ADA |
| BR-NF-02 | Seluruh endpoint uang ditandatangani dan dibatasi IP | M | SUDAH ADA |
| BR-NF-03 | Rahasia tidak pernah disimpan di record bisnis | M | SUDAH ADA |
| BR-NF-04 | Setiap perubahan status transaksi terekam pada jejak audit | M | SUDAH ADA |
| BR-NF-05 | Sistem menahan volume puncak yang disepakati dengan latensi p95 di bawah target | M | KONFIGURASI + uji beban |
| BR-NF-06 | Komponen jalur uang terlindungi test otomatis | M | PERLU DIBANGUN (G3) |
| BR-NF-07 | Konfigurasi go-live dapat direproduksi lewat skrip, bukan langkah manual | S | PERLU DIBANGUN (G6) |
| BR-NF-08 | Cutover dapat dibatalkan (rollback) per irisan selama window yang disepakati | M | KONFIGURASI |

**Rekapitulasi:** 80 kebutuhan — **67 SUDAH ADA, 9 PERLU DIBANGUN, 4 KONFIGURASI**.

## 7. Aturan bisnis kunci

| # | Aturan |
|---|---|
| AB-01 | Saldo mitra tidak boleh berubah tanpa jurnal berpasangan pada transaksi basis data yang sama. |
| AB-02 | Debit ditolak bila melebihi saldo + credit limit; tidak ada pengecualian di jalur otomatis. |
| AB-03 | Satu mitra + satu kunci idempotensi = satu transaksi, selamanya. |
| AB-04 | Jawaban biller "masih diproses" bukan kegagalan; transaksi dibiarkan sampai status final. |
| AB-05 | Refund hanya dilakukan setelah kegagalan dikonfirmasi, dan hanya sekali. |
| AB-06 | Harga modal yang dibukukan adalah harga provider yang benar-benar dipanggil. |
| AB-07 | PPN diakui pada faktur ringkas harian per mitra, tidak per transaksi. |
| AB-08 | Deposit biller tidak boleh negatif. |
| AB-09 | Jalur pembayaran ke biller tidak pernah di-retry otomatis. |
| AB-10 | Data masuk yang tidak dapat dipetakan tidak boleh dibuang — masuk antrean tinjauan. |
| AB-11 | Komisi ke mitra tanpa NPWP dipotong dengan tarif PPh 23 yang lebih tinggi sesuai ketentuan. |
| AB-12 | Perluasan irisan cutover hanya setelah selisih rekonsiliasi irisan sebelumnya nol. |

## 8. Pemangku kepentingan & peran

| Pemangku kepentingan | Kepentingan utama | Keputusan yang dipegang |
|---|---|---|
| Sponsor | Nilai bisnis, biaya, waktu | Go/no-go, anggaran |
| Product Owner PPOB | Fungsi & prioritas | Prioritas kebutuhan, penerimaan fungsional |
| Finance Lead | Ketepatan GL & pajak | COA, mode PPN per kelas, kebijakan komisi/PPh |
| Ops Lead | Kelancaran harian | Prosedur eksepsi, ambang deposit, jam operasi |
| Mitra (pengguna akhir) | Saldo benar, transaksi cepat | — |
| IT / Integrasi klien | Konektivitas & keamanan | Allowlist IP, kredensial, jalur jaringan |
| Biller & bank | Kepatuhan kontrak API | Spesifikasi & kuota |
| Auditor internal | Jejak audit | Kriteria audit |

## 9. Asumsi & ketergantungan

- Model kanal adalah **mitra prepaid** (top-up dulu, lalu jual). Model pascabayar mitra tidak
  termasuk kecuali disepakati terpisah.
- Satu mata uang (IDR) dan satu perusahaan per tenant, kecuali dinyatakan lain.
- Klien menyediakan spesifikasi + sandbox untuk setiap biller, bank, dan kanal.
- Kebijakan pajak diputuskan Finance Lead sebelum konfigurasi dimulai.
- Snapshot saldo mitra dan deposit biller tersedia pada tanggal cutover.

## 10. Risiko bisnis

| # | Risiko | Dampak | Mitigasi |
|---|---|---|---|
| RB-1 | Mitra kehilangan kepercayaan karena saldo tidak cocok saat cutover | Kritis | Dual-run saldo + gerbang paritas + komunikasi ke mitra |
| RB-2 | Kerugian karena transaksi terjual dua kali | Kritis | Idempotensi tingkat basis data + jalur pay tanpa retry |
| RB-3 | Biller tanpa endpoint status membuat transaksi menggantung | Tinggi | Persyaratan kontrak biller; prosedur ops manual bila tidak tersedia |
| RB-4 | Penjualan berhenti karena deposit biller habis | Tinggi | Low-water-mark + peringatan + prosedur top-up |
| RB-5 | Koreksi pajak akibat salah mode PPN | Tinggi | Keputusan mode PPN per kelas ditandatangani Finance sebelum konfigurasi |
| RB-6 | Volume puncak melampaui asumsi | Sedang | Sampling throughput sejak SIT + uji beban sebelum go-live |
| RB-7 | Ketergantungan pada satu biller | Sedang | Failover berbasis prioritas SKU map dengan minimal dua rute per produk utama |

---

*Dokumen berikutnya: [`02-FSD.md`](02-FSD.md) — spesifikasi fungsional dan acceptance test.*
