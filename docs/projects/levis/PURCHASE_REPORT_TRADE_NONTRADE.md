# Levi's Odoo — Panduan Purchase Report: Pemisahan Trade / Non-Trade

Panduan pemakaian **Purchase Report** setelah ditambahkan dimensi **Trade /
Non-Trade** (rilis `custom_accounting_reports` 19.0.0.21.0, 19 Agustus 2026).

Purchase Report adalah *register pembelian*: satu baris per **baris produk pada
vendor bill yang sudah diposting**, bukan per PO. Yang baru: setiap baris kini
membawa **stream pembeliannya** (Trade atau Non-Trade), sehingga register bisa
disaring, dikelompokkan, dan dicetak per stream.

> **Trade vs Non-Trade dalam konteks EBR.**
> **Trade** = pembelian barang dagangan (merchandise Levi's yang dijual kembali).
> **Non-Trade** = pembelian selain barang dagangan — jasa, sewa, ATK, perlengkapan
> toko, biaya operasional. Keduanya sengaja dipisah karena memakai **akun hutang
> yang berbeda**: Trade → `2103100001` *Trade Payables - Third parties*,
> Non-Trade → `2103300001` *Non trade payable - Third parties*.

---

## 1. Membuka laporan

Menu: **Accounting → Reporting → Reports → Purchase Report**

Yang muncul adalah jendela filter (wizard). Isi filter, lalu pilih salah satu
dari tiga tombol keluaran di bagian bawah.

Butuh hak akses grup **Accounting Reports** (`group_report_user`) — sama seperti
laporan-laporan lain di menu *Reports*.

---

## 2. Isi filter

| Field | Keterangan |
|---|---|
| **Date from / Date to** | Rentang **tanggal jurnal (accounting date)** bill, bukan tanggal PO. Default: 1 Januari tahun berjalan s/d hari ini. |
| **Group By** | `No grouping` / `By Vendor` / `By Product` / `By Month` / **`By Trade / Non-Trade`** (baru). Setiap grup diberi baris **Subtotal**. |
| **Purchase Type** | **(baru)** `All` / `Trade` / `Non-Trade` / `Unclassified`. Menyaring register ke satu stream saja. |
| **Posted Only** | Default aktif = hanya bill **Posted**. Matikan bila ingin ikut menghitung bill **Draft** (angka tidak akan cocok dengan GL). |
| **Companies** | Default perusahaan aktif. |
| **Vendors** | Kosongkan untuk semua vendor. |

> **Catatan.** Field **Purchase Type** hanya muncul di database Levi's. Di tenant
> lain (mis. ARKA-AIM) yang tidak memakai skema Trade/Non-Trade, filter dan kolom
> `Type` otomatis tersembunyi dan laporan tampil seperti sebelumnya.

---

## 3. Tiga cara memisahkan Trade dan Non-Trade

Pilih sesuai kebutuhan — ketiganya bisa dikombinasikan.

### a. Kolom `Type` — semua stream dalam satu daftar

Tanpa mengubah apa pun, register sekarang punya kolom **Type** (kolom ketiga,
sesudah *Bill No*) yang berisi `Trade`, `Non-Trade`, atau `Unclassified`. Cocok
untuk penelusuran cepat atau kalau hasilnya mau diolah lagi di Excel (tinggal
pakai filter/pivot pada kolom Type).

### b. Filter `Purchase Type` — satu stream saja

Set **Purchase Type = Trade** (atau `Non-Trade`) untuk mendapat register yang
**hanya** berisi stream tersebut, lengkap dengan grand total stream itu. Ini yang
dipakai kalau laporannya mau diserahkan ke pihak berbeda, atau dilampirkan pada
rekonsiliasi hutang per akun.

Nama file Excel ikut menyesuaikan: `Purchase_Report_Trade_2026-07-01_2026-07-31.xlsx`,
dan cetakan PDF menampilkan baris **"Purchase Type: Trade"** di bawah header.

### c. Group By `By Trade / Non-Trade` — dua-duanya, dengan subtotal

Set **Group By = By Trade / Non-Trade** dan biarkan **Purchase Type = All**.
Hasilnya satu laporan berisi kedua stream, masing-masing ditutup baris
**Subtotal: Trade** dan **Subtotal: Non-Trade**, lalu **Grand Total** di paling
bawah. Ini bentuk yang paling enak dipakai untuk rekap bulanan: satu halaman,
dua angka, dan totalnya langsung terlihat cocok.

---

## 4. Tiga bentuk keluaran

| Tombol | Hasil |
|---|---|
| **View** | Tabel interaktif di layar. Paling cepat; bisa langsung dibaca dan di-scroll. |
| **Print PDF** | Cetakan resmi, lengkap dengan header perusahaan, periode, dan blok tanda tangan. PDF menampilkan kolom yang lebih ringkas (Date, Bill No, Type, Vendor, Product, Qty, Untaxed, Tax, Total). |
| **Export Excel** | File `.xlsx` dengan **seluruh** kolom, termasuk Description, Unit Price, dan Disc %. Ini yang dipakai kalau angkanya mau diolah lagi. |

Ketiganya memakai filter yang sama persis, jadi angkanya identik.

---

## 5. Dari mana Odoo tahu sebuah bill itu Trade atau Non-Trade

Urutannya begini — Odoo memakai yang pertama ketemu:

1. **Field `Purchase Type` pada vendor bill itu sendiri.** Terisi otomatis dari
   PO saat bill dibuat lewat *Create Bill*, atau dipilih manual di form bill
   (radio button di sebelah nama vendor) untuk bill tanpa PO.
2. **Bill yang dibalik (reversed entry).** Credit note yang dibuat lewat tombol
   *Reverse* kadang tidak membawa stream sendiri — Odoo membacanya dari bill asal.
3. **PO sumber baris tersebut.** Kalau bill-nya tetap kosong, stream diambil dari
   Purchase Order yang menurunkan baris itu.
4. Kalau ketiganya kosong → baris dilaporkan sebagai **`Unclassified`**.

Karena rantai fallback ini, `Unclassified` di prd_levis_begbal saat ini **nol** —
seluruh pembelian sudah terklasifikasi.

### Kalau muncul baris `Unclassified`

Artinya ada bill yang dibuat manual tanpa memilih Purchase Type dan tanpa PO.
Perbaikannya di sumber, bukan di laporan:

1. Jalankan laporan dengan **Purchase Type = Unclassified** untuk mendapat daftar
   nomor bill-nya.
2. Buka bill tersebut. Bila masih **Draft**, cukup isi field **Purchase Type**.
3. Bila sudah **Posted**, jangan langsung di-*reset to draft* — perubahan stream
   ikut memindahkan **akun hutang** dan **penomoran**. Konsultasikan dengan tim
   Accounting; umumnya jalan yang benar adalah jurnal reklasifikasi.

---

## 6. Yang ikut ditentukan oleh Trade / Non-Trade

Supaya tidak kaget saat angka laporan dicocokkan ke GL, stream ini bukan sekadar
label laporan. Di Levi's ia juga menentukan:

| | Trade | Non-Trade |
|---|---|---|
| Akun hutang (payable) | `2103100001` Trade Payables - Third parties | `2103300001` Non trade payable - Third parties |
| Penomoran PO | `PO/T/EBR/YYYY/MM/#####` | `PO/NT/EBR/YYYY/MM/#####` |
| Penomoran vendor bill | `BILL/T/...` | `BILL/NT/...` |
| GR/IR clearing | per kategori produk (*stock variation*) | `2103300008` |

Jadi **Purchase Report dengan filter Trade seharusnya sejalan dengan mutasi akun
`2103100001`**, dan Non-Trade dengan `2103300001` — dengan catatan laporan ini
menampilkan **nilai baris produk** (DPP + pajak per baris), sementara akun hutang
memuat nilai total dokumen termasuk komponen lain seperti PPh potong.

---

## 7. Cara cepat memvalidasi hasil

1. Jalankan laporan **Purchase Type = All**, catat Grand Total *Untaxed*.
2. Jalankan lagi dengan **Trade**, lalu **Non-Trade**, dan **Unclassified**.
3. **Trade + Non-Trade + Unclassified harus sama persis dengan All.**

Contoh nyata di `prd_levis_begbal` (periode 2026, posted saja, per 19 Agustus 2026):

| Purchase Type | Untaxed |
|---|---|
| Trade | 44.373.987.923,53 |
| Non-Trade | 10.108.847.001,67 |
| Unclassified | 0,00 |
| **All** | **54.482.834.925,20** |

Kalau penjumlahannya tidak cocok, kemungkinan besar filter periode atau
**Posted Only** berbeda antar percobaan — bukan bug perhitungan.

---

## 8. Pertanyaan yang sering muncul

**Apakah laporan ini menghitung PO atau bill?**
Bill (vendor bill / credit note) yang sudah diposting. PO yang belum ditagih tidak
muncul. Untuk analisis PO, pakai daftar Purchase Orders — di sana juga sudah ada
filter **Trade** / **Non-Trade** dan group-by **Purchase Type**.

**Bagaimana perlakuan retur / credit note?**
Baris *in_refund* dihitung **negatif**, sehingga mengurangi total stream-nya.

**Kenapa angka saya beda dengan Trial Balance?**
Purchase Report memakai *tanggal jurnal* dan hanya baris **produk**. Baris biaya
lain-lain pada bill (mis. pembulatan) dan komponen potongan pajak tidak masuk
kolom Untaxed. Untuk pencocokan ke GL, pakai General Ledger pada akun hutang
terkait.

**Filter Purchase Type tidak muncul di layar saya.**
Berarti database yang Anda buka bukan database Levi's, atau modul
`custom_levis_localization` belum terpasang di sana. Ini perilaku yang disengaja.

**Apakah Excel-nya bisa langsung di-pivot?**
Bisa. Kolom `Type` ada di sheet, jadi cukup pilih *Insert → PivotTable* dan
tempatkan `Type` di Rows serta `Untaxed`/`Total` di Values.

---

## 9. Catatan teknis

- Modul: `custom_accounting_reports` **19.0.0.21.0** (PR #183, merge ke `main`
  19 Agustus 2026 sebagai `49c8f74`).
- Terpasang di 9 database: `prd_levis_begbal`, `prd_levis`, `rnd_levis`,
  `demo_updated_levis`, `gentlewoman`, `prd_arkaaim`, `trn_arkaaim`, `rnd_ppob`,
  `tst_b2`. Kolom/filter Trade–Non-Trade hanya aktif di database yang memasang
  `custom_levis_localization`.
- Dokumen terkait: [OPEN_CLOSE_PERIOD_GUIDE.md](OPEN_CLOSE_PERIOD_GUIDE.md) untuk
  penguncian periode sebelum laporan periode itu difinalkan.
