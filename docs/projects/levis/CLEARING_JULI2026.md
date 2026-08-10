# Clearing Juli 2026 — `prd_levis_begbal`

Status per **11-Agu-2026**: **63 jurnal masih DRAFT**, menunggu persetujuan Accounting.
Baseline sudah diverifikasi ulang hari ini — angkanya masih identik dengan review 7-Agu,
tidak perlu regenerate apa pun.

Dokumen ini menjelaskan (1) apa yang sebenarnya dibutuhkan, (2) angka posisi hari ini,
(3) langkah eksekusi kalau clearing jadi dijalankan, (4) yang tersisa dan butuh keputusan.

---

## 1. Kenapa perlu clearing

Struktur Juli **berbeda dari Juni** — jangan pakai pola `AR_CLEARING_JUNI2026.md`:

| | Juni 2026 | Juli 2026 |
|---|---|---|
| Mode import | decouple | X70D tender-split |
| Sisi debit penjualan | AR `1106000001` lewat GL EBR | **POS Receivable per tender `1106000101..110`** |
| Sisi bank | dari GL EBR | **import bank statement** (IBCA/IBRI/OBCA) |
| Bentuk clearing | Dr deposit / Cr AR | **Dr `1103000002` Bank Suspense + Dr `7104000001` MDR / Cr POS Receivable** |

Akibatnya, tanpa clearing: penjualan Juli menumpuk sebagai piutang POS Rp 16,93 M yang
tidak pernah bertemu dengan uang masuk di bank, dan seluruh setoran bank Juli menggantung
di Bank Suspense. Neraca Juli tidak dapat dibaca.

## 2. Isi 63 jurnal draft

Semua di jurnal **GLJV**, ref `EBR-CLR-JULI-2026-<blok>-<tanggal>`, seluruhnya bertanggal
dalam Juli, seluruhnya balance (diverifikasi ulang 11-Agu, imbalance = 0).

| Blok | Entri | Total debit | Isi |
|---|---:|---:|---|
| **A** | 30 | 16.435.330.892 | Settlement toko → bank. Dr Bank Suspense + Dr MDR / Cr POS Receivable per tender |
| **B** | 2 | 365.428.222 | Collection AR Juni yang uangnya masuk di Juli. Cr `1106000001` |
| **C** | 31 | 15.255.196.967 | Sweep ATS BCA rek IN `1103019310` → rek OUT `1103019320`, lawan Bank Suspense |
| | **63** | **32.055.956.081** | |

Blok **S** (perbaikan statement) dan **D** (4 baris RIREC PASKAL 23-Jul tanpa OU) sudah
permanen sejak 4-Agu — tidak perlu dijalankan lagi.

**Gotcha yang sudah tertanam di data** (jangan diutak-atik ulang):
- Sisi kredit **tidak** memakai split tender EBR. 35 kombinasi toko×hari berbeda dengan
  X70D dan PASKAL 24-Jul tendernya kosong; script hanya memakai total per toko×tanggal
  transaksi, split akunnya diambil dari baris RIREC yang masih open.
- MDR per toko dibagi **pro-rata** ke tanggal settle, karena mutasi bank dan COMPILE SALES
  beda hari (settle D vs D+1) dan baru sama kalau diakumulasi sebulan.
- `1103000002` ber-`reconcile = false`, jadi 2.535 statement line Juli **tidak akan pernah
  bisa di-match** di widget bank-rec. Kontrolnya murni saldo akun — itu wajar dan disengaja.

## 3. Posisi hari ini vs sesudah posting

Diukur 11-Agu-2026, jendela **Juli saja** (`date < 2026-08-01`). Kolom "sesudah" bukan
proyeksi di atas kertas — ini hasil **rehearsal posting sungguhan yang lalu di-rollback**
(`CLR_POST=1 CLR_DRY=1`), jadi angkanya sudah terbukti.

| Akun | Sekarang | Sesudah 63 jurnal | Ket. |
|---|---:|---:|---|
| `1103000002` Bank Suspense | 52.374.507,97 | **1.530.199.113,09** | lihat §5 |
| `7104000001` Beban MDR | 26.448.556,73 | **94.186.098,68** | |
| `1106000001` AR EBR | 368.378.122,00 | **2.949.900,00** | tinggal residu tipis |
| POS Receivable Juli open | 16.925.825.341 (2.640 baris) | **490.494.449 (89 baris)** | lihat §5 |

Rekonsiliasi otomatis akan menutup 5.198 baris POS receivable di 10 akun tender.

Sisa terbuka per akun tender sesudah posting:

| Akun | Sekarang | Draft | Sisa |
|---|---:|---:|---:|
| 1106000101 CASH | 1.063.747.221 | −1.034.114.356 | 29.632.865 |
| 1106000102 DOMESTIC_CARD | 4.512.792.559 | −4.347.613.794 | 165.178.765 |
| 1106000103 VISA | 2.145.330.273 | −2.071.836.478 | 73.493.795 |
| 1106000104 MASTERCARD | 838.719.647 | −823.488.172 | 15.231.475 |
| 1106000105 OTHER_CC | 3.793.331.718 | −3.709.625.613 | 83.706.105 |
| 1106000106 CREDIT_CARD | 3.964.496.311 | −3.861.211.726 | 103.284.585 |
| 1106000107 JCB | 18.626.239 | −18.626.239 | 0 |
| 1106000108 BRI_CC | 539.335.596 | −525.870.337 | 13.465.259 |
| 1106000109 AMEX | 47.895.027 | −41.393.427 | 6.501.600 |
| 1106000110 OVO | 1.550.750 | −1.550.750 | 0 |
| | | | **490.494.449** |

**Yang berubah sejak review 7-Agu:** hanya masuknya data Agustus — POS Receivable Agustus
5.038.215.650 (775 baris) dan 386 statement line Agustus yang menambah `1103000002`
sebesar 313.660,65. **Tidak menyentuh angka Juli sama sekali**; saldo akhir akun
`1103000002` all-time nanti 1.530.512.773,74 = 1.530.199.113,09 (Juli) + 313.660,65 (Agu).
Agustus akan butuh putaran clearing sendiri.

## 4. Langkah eksekusi

> **Prasyarat: approval Accounting atas workbook**
> `/srv/sftp-share/files/Persetujuan_Clearing_Juli2026.xlsx` (13 sheet, ada kolom tanda tangan).
> `fiscalyear_lock_date` = 2026-06-30, jadi Juli terbuka — tidak ada lock yang perlu digeser.

### ⚠️ Script 81 tidak bisa dipakai untuk mem-posting

Resep lama ("jalankan ulang `81_clearing_juli.py` dengan `CLR_POST=1`") **tidak berfungsi**.
Setiap blok di script 81 `return` lebih awal begitu ref-nya sudah ada
(`81_clearing_juli.py:212,293,356`), sehingga `created` tetap kosong dan cabang
`if POST and moves:` (`:395`) tidak pernah dieksekusi. Script 81 hanya bisa mem-posting entri
yang ia buat **pada run yang sama**. Menjalankannya hari ini = no-op yang mencetak
"block A already exists -- skipped" lalu keluar.

Karena itu dibuat **`scripts/tenants/levis/90_post_clearing_juli.py`**: mencari 63 draft
lewat ref, memvalidasi (jumlah, balance per jurnal, tanggal harus di Juli, lock date belum
menutup Juli), mem-posting, merekonsiliasi POS receivable per akun, lalu membandingkan hasil
dengan angka yang diharapkan. Default-nya **report-only** — tidak menulis apa pun tanpa
`CLR_POST=1`.

### Urutan perintah

```bash
cd /opt/odoo-platform
export PGPASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)

# 1. backup — tidak ada backup otomatis untuk DB tenant
docker exec -e PGPASSWORD="$PGPASSWORD" odoo19-platform-postgres pg_dump -U odoo -Fc \
  -d prd_levis_begbal -f /tmp/prd_levis_begbal_pre_post_clearing_juli.dump
docker cp odoo19-platform-postgres:/tmp/prd_levis_begbal_pre_post_clearing_juli.dump \
  /opt/odoo-platform/backups/

# 2. rehearsal: posting sungguhan lalu rollback — harus keluar "delta 0.00" empat kali
docker exec -i -e CLR_POST=1 -e CLR_DRY=1 odoo19-platform-odoo \
  odoo shell -d prd_levis_begbal --no-http \
  < scripts/tenants/levis/90_post_clearing_juli.py

# 3. eksekusi sungguhan
docker exec -i -e CLR_POST=1 odoo19-platform-odoo \
  odoo shell -d prd_levis_begbal --no-http \
  < scripts/tenants/levis/90_post_clearing_juli.py
```

Jalankan dari checkout `/opt` (lihat memory `odoo-platform-checkouts`); pastikan
`git pull` dulu supaya `90_post_clearing_juli.py` ada di sana.

### Kriteria terima

Output langkah 3 harus persis:

```
posted 63 entries: GLJV/2026/07/0034 .. GLJV/2026/07/0096
after  balance 1103000002 = 1530199113.09  (expected 1530199113.09, delta 0.00)
after  balance 7104000001 = 94186098.68    (expected 94186098.68, delta 0.00)
after  balance 1106000001 = 2949900.00     (expected 2949900.00, delta 0.00)
after  POS receivable July open: 490494449.00 on 89 lines  (delta 0.00)
```

Kalau ada delta ≠ 0 → **jangan lanjut**, ada mutasi Juli baru yang masuk sesudah 11-Agu;
regenerate JSON lewat `80_prep_clearing_juli.py` (draft lama harus dihapus dulu, guard-nya
menolak double).

### Rollback

Sebelum commit: cukup batalkan (script otomatis rollback kalau `CLR_DRY=1`).
Sesudah commit: **restore dari dump langkah 1**. Jangan coba `button_draft` — di Odoo 19
reset-to-draft tidak melepas rekonsiliasi (lihat memory `odoo19-button-draft-keeps-reconciliation`),
jadi 5.198 baris POS receivable akan tetap ter-match padahal jurnalnya sudah draft.

### Bahan yang sudah awet

`/srv/sftp-share/files/clearing-juli-2026/` — `clearing_juli.json` (persis yang membuat 63
draft yang ada sekarang), `EBR_JULI_2026.xlsx`, `MUTASI_BCA_JULI.csv`.
Workbook: `Draft_Clearing_Juli2026.xlsx` (validasi, 4-Agu) dan
`Persetujuan_Clearing_Juli2026.xlsx` (approval; regenerate 11-Agu — dua sheet AEON, sheet
`LANGKAH-EKSEKUSI`, indeks isi workbook, dan kolom SESUDAH ditandai terbukti lewat uji).
Backup pra-clearing: `/opt/odoo-platform/backups/prd_levis_begbal_20260804_pre_clearing_juli.dump`.

## 5. Yang tetap terbuka sesudah clearing — butuh keputusan klien

Clearing ini **tidak menyelesaikan** empat hal berikut. Semuanya sudah teridentifikasi,
tidak ada yang tersembunyi.

### a. Bank Suspense sisa 1.530.199.113 — **prioritas tertinggi**
Hampir seluruhnya satu baris: BRI 27-Jul **"CAIR CEK UNTUK RTGS" 1.533.030.000**, rekening
tujuannya belum dipastikan. Sisanya AEON 1.400.925 + timing 834.652.
→ perlu konfirmasi Treasury: uang ini pindah ke rekening mana.

### b. POS Receivable 76.926.875 — transaksi "KOL"
32 transaksi OLS SES GRAND INDONESIA 15-Jul, tender CASH, kolom approval berisi
`KOL <nama influencer>`, tanpa `CASH RECEIVED DATE`/`STATUS`. Barang **diberikan gratis**
tapi POS mencatatnya sebagai penjualan tunai harga penuh, sehingga tidak ikut blok A dan
akan menggantung permanen di `1106000101`. (Total kas 15-Jul di akun itu 107.721.140,
KOL adalah 76.926.875 di antaranya.)
→ pilihan: **(i)** reklas ke beban promosi, atau **(ii)** batalkan di X-Store lalu import
ulang sebagai free goods — opsi (ii) membawa implikasi PPN cuma-cuma.

### c. Sisa 412.665.600 — murni timing
Transaksi tanggal 31-Jul yang settle D+1 di Agustus. Bukan masalah; akan tertutup sendiri
oleh clearing Agustus.

### d. Selisih Rp 950
Sales Juli Odoo 16.940.433.421 vs workbook 16.940.432.471. Immaterial, dicatat saja.

Jembatan angka 490.494.449 = 412.665.600 (timing 31-Jul) + 76.926.875 (KOL) + 901.974 (lain-lain).

## 5A. Detail selisih AEON BSD CITY — tender EBR vs X70D

Toko `OLS SES - AEON BSD CITY` (analytic id 12, MID BCA 004648627 / 885004648627).
Sepanjang Juli ada **5 titik** di mana COMPILE SALES EBR tidak sepakat dengan X70D.
Total sebulan: X70D 480.187.184 vs EBR 480.187.234 — **netto beda hanya Rp 50**.

| # | Trans date | Transnum | Nilai | X70D (sumber Odoo) | EBR COMPILE SALES | Dampak |
|---|---|---|---:|---|---|---|
| 1 | 02-Jul | 317 | 225.950 | `OFFLINE_OTHER_CARD` → `1106000105` | `OFFLINE_DOMESTIC_CARD` → `1106000102` (metode "BCA- REGULAR OF US") | netral |
| 2 | 05-Jul | 551 | 832.320 | `OFFLINE_VISA` → `1106000103` | `OFFLINE_MASTERCARD` → `1106000104` (metode "BCA- REGULAR ON US") | netral |
| 3 | 06-Jul | 617, 619, 622 | **1.400.875** | trans-date **06-Jul**, register 1 | trans-date **07-Jul**, register 2/3/4 | **tidak ter-clearing** |
| 4 | 08-Jul | 682 | 650.900 / 650.950 | 650.900 | 650.950 | **Rp 50 tidak ter-clearing** |
| 5 | 29-Jul | 1585 | 2.049.800 | `OFFLINE_DOMESTIC_CARD` → `1106000102` | `OFFLINE_OTHER_CREDITCARD` → `1106000105` | netral |

**Kenapa #1, #2, #5 tidak berdampak.** Ketiganya salah-kelas tender **di dalam hari yang
sama**, jadi saling menutup. `81_clearing_juli.py` memang sengaja hanya memakai **total per
toko × trans-date** dari workbook, lalu mengambil split akunnya dari baris RIREC yang masih
open (`allocate()`, `:186`). Selama selisihnya tidak melintasi hari, kesalahan klasifikasi
EBR tidak pernah sampai ke jurnal. Ini persis alasan desain "jangan pakai split tender EBR".

**#3 — pergeseran tanggal, bukan salah tender.** Tender-nya sama-sama
`OFFLINE_DOMESTIC_CARD`; yang berbeda adalah tanggalnya, jadi mekanisme di atas tidak
menolong. Bukti dari X70D (`retail_import_line`, log 203, file `X70D_..._20260706T193032Z`):

```
trans_date  register  transnum  tender_type              amount
2026-07-06     1        613     OFFLINE_DOMESTIC_CARD    750,950
2026-07-06     1        617     OFFLINE_DOMESTIC_CARD    749,950
2026-07-06     1        619     OFFLINE_DOMESTIC_CARD    600,925
2026-07-06     1        622     OFFLINE_DOMESTIC_CARD     50,000
                                                       ---------
                                              617+619+622  1,400,875
```

EBR mencatat **transnum dan nominal yang identik** tetapi bertanggal 07-Jul dan dengan
nomor register 2, 3, dan 4. Sepanjang Juli X70D hanya mengenal **register 1** di AEON BSD
CITY, dan urutan transnum 613 → 617 → 619 → 622 jelas berlanjut di hari yang sama.
Kesimpulan: **kesalahan ada di workbook EBR** (tanggal bergeser +1 hari sekaligus nomor
register salah), bukan perbedaan fakta bisnis. X70D yang benar.

**Akibatnya pada blok A:**

| Jurnal | Trans date | Diminta EBR | Tersedia di Odoo | Dikreditkan | Selisih |
|---|---|---:|---:|---:|---:|
| `...-A-2026-07-07` | 06-Jul | 20.962.700 | 22.363.575 | 20.962.700 | 1.400.875 debit dibiarkan terbuka |
| `...-A-2026-07-08` | 07-Jul | 15.105.750 | 13.704.875 | 13.704.875 | **short 1.400.875** |
| `...-A-2026-07-09` | 08-Jul | 12.438.575 | 12.438.525 | 12.438.525 | **short 50** |

Karena `allocate()` mengisi dari baris terbesar dulu, sisa 1.400.875 pada 06-Jul mendarat di
akun `1106000104` dan `1106000105`. Di sisi bank, jurnal 08-Jul hanya mendebit Bank Suspense
**13.652.344,47 + MDR 52.530,53**, padahal versi penuhnya 15.047.849,94 + 57.900,06.

Total tidak terserap untuk AEON = **1.400.925** = 1.395.555,28 (Bank Suspense) +
5.369,72 (MDR). Blok A mengkredit AEON 457.775.509 lawan angka workbook 459.176.434 —
selisihnya persis 1.400.925, sama dengan diagnosa nomor 4 di sheet validasi.

**Peringatan pembacaan angka.** Langkah rekonsiliasi terakhir mencocokkan seluruh baris Juli
**per akun, lintas toko** (`90_post_clearing_juli.py`, mengikuti `81:399`). Karena itu sesudah
posting sisa AEON yang tampak hanya **21.010.800** — persis seluruh transaksi 31-Jul, murni
timing — dan 1.400.875 tadi terserap oleh kelebihan toko lain di akun yang sama. Jadi
**sisa per toko tidak bisa dibaca lagi setelah posting; hanya total per akun yang valid.**
Efek yang sama membuat KOL 15-Jul (§5 butir b) muncul sebagai sisa bertanggal 30-Jul:
sisa 490.494.449 seluruhnya berlabel 30-Jul (77.828.849 = 76.926.875 KOL + 901.974) dan
31-Jul (412.665.600), tanpa satu pun baris tersisa di 15-Jul.

**Workbook untuk dikirim ke EBR.** Dua sheet baru sudah digabungkan ke workbook persetujuan
`/srv/sftp-share/files/Persetujuan_Clearing_Juli2026.xlsx` (jadi 13 sheet), dibangkitkan oleh
`82_workbook_approval_clearing_juli.py` yang tetap read-only:

- **`AEON-SELISIH`** — daftar selisih per transaksi (X70D vs COMPILE SALES, lengkap dengan
  transnum kedua sisi), total sebulan, perbandingan harian per akun, tabel dampak ke blok A,
  tabel sisi bank (debit Bank Suspense yang dibukukan vs seharusnya), dan tindak lanjut.
- **`AEON-TRX-DETAIL`** — baris mentah kedua sistem berdampingan per kasus, termasuk kolom
  REGISTER dan METODE PEMBAYARAN, sehingga EBR bisa langsung menemukan barisnya.

Pencocokannya bertahap dan bukan berdasarkan TRANSNUM: EBR cukup sering salah ketik nomor
transnum (digit hilang/tersisip) sehingga kunci transnum melaporkan typo seolah selisih uang.
Urutannya: (1) cocok persis tanggal+akun+nominal, (2) sisa yang netto nol di dalam satu
tanggal×akun dibuang sebagai pemecahan baris, (3) cocok nominal → beda tanggal atau beda
tender, (4) cocok tanggal+akun → beda nilai, (5) sisanya sepihak. Tanpa langkah 2 workbook
melaporkan 17 "selisih" palsu; dengan langkah 2, tersisa 7 yang nyata.

**Tindak lanjut yang diminta ke EBR:**
1. Koreksi trans date trx **617/619/622** AEON dari 07-Jul ke **06-Jul** (dan nomor register
   ke 1). Tidak perlu jurnal koreksi — cukup workbook diperbaiki lalu blok A di-regenerate,
   atau diterima apa adanya dengan konsekuensi Rp 1.395.505 kas AEON menetap di Bank Suspense.
2. Konfirmasi nilai trx **682** 08-Jul: X70D 650.900 vs EBR 650.950. Ini satu-satunya
   selisih netto AEON sebulan.
3. Perbaiki pemetaan `METODE PEMBAYARAN` → `TENDER TYPE` di sisi EBR untuk
   "BCA- REGULAR OF/ON US" dan "BCA - DEBIT OTHER" (kasus #1/#2/#5). Tidak berdampak
   akuntansi sekarang, tapi akan berdampak begitu selisihnya kebetulan melintasi hari.

## 6. Agustus

Data Agustus sudah mulai masuk (POS Receivable 5.038.215.650 / 775 baris, 386 statement
line). Clearing Agustus adalah pekerjaan terpisah dan **tidak boleh dicampur** ke putaran
Juli ini — guard ref `EBR-CLR-JULI-2026-*` sudah memisahkannya, tapi `80_prep_clearing_juli.py`
perlu diparameterisasi bulan sebelum dipakai untuk Agustus.

---

Lihat juga: `AR_CLEARING_JUNI2026.md`, memory `levis-july-clearing-prd-begbal`,
`levis-june-ar-clearing-completed`, `bank-import-multiformat-accounting-date`,
`levis-closed-period-no-backdate`.
