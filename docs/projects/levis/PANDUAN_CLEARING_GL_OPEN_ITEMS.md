# Panduan Clearing GL Open Items

Menjawab sheet After Go Live baris **#23** ("guide cara clearing GL Open Item"),
**#72** ("cara clear line transaksi plus-minus supaya tidak muncul di Aging
ataupun GL Open Item") dan sebagian **#48**.

Angka di dokumen ini diambil dari `prd_levis_begbal` per **18-Sep-2026**.
Jalankan ulang skrip yang disebut di bagian akhir untuk memperbarui angkanya.

---

## 1. Apa arti "open item" di Odoo

Sebuah akun masuk GL Open Items kalau kotak **Allow Reconciliation**
(`account.account.reconcile`) dicentang. Tidak ada daftar terpisah, tidak ada
flag khusus, dan tidak ada XML yang perlu diubah.

**Menambah COA ke GL Open Items** (ini jawaban #48):

1. *Accounting ▸ Configuration ▸ Chart of Accounts*
2. Cari COA-nya, buka, centang **Allow Reconciliation**, simpan.

Dua COA yang Anda uji sudah tercentang di produksi:

| COA | Nama | Allow Reconciliation |
|---|---|---|
| 1116100007 | Other prepaid expenses | ✅ sudah |
| 1116200001 | Prepaid rent - current portion | ✅ sudah |

Jadi keduanya **sudah** tampil di GL Open Items; tidak ada yang perlu dikerjakan lagi.

> ⚠️ Jangan mencentang `reconcile` secara massal. Akun kas sengaja **tidak**
> reconcilable — mencentangnya membuat setiap penyelesaian uang muka ikut
> merekonsiliasi kas, yang bukan perilaku akun float.

---

## 2. Membaca GL Open Items

*Invoicing ▸ Reporting ▸ Reports ▸ GL Open Items / Outstanding*

Tiga layout:

| Layout | Satu baris artinya |
|---|---|
| Summary | satu akun |
| Partner | satu partner di dalam satu akun |
| Detail | satu sisa yang **belum saling menutup** |

**Penting:** laporan ini sudah melakukan *FIFO netting*. Debit dan kredit yang
sudah saling meniadakan hilang dari daftar, walau jurnalnya belum
direkonsiliasi secara formal. Yang tersisa adalah posisi terbuka yang
sebenarnya.

---

## 3. Kenapa Aged Report dan GL Open Items berbeda barisnya (#73)

Ini pertanyaan yang sering muncul, dan jawabannya **bukan selisih uang**.
Diukur per 31-Agu-2026:

| Laporan | Jumlah baris | Total outstanding |
|---|---|---|
| Aged Receivable (detail) | **1.331** | Rp 3.088.025.495 |
| GL Open Items | **114** | Rp 3.088.025.495 |
| **Selisih uang** | | **Rp 0** |

Totalnya **ikat sampai rupiah**. Yang berbeda adalah pertanyaannya:

* **Aged Receivable** menjawab *"dokumen mana yang belum lunas, dan sudah berapa
  lama"* → satu baris per dokumen. Ini daftar kerja **penagihan**.
* **GL Open Items** menjawab *"berapa yang belum saling menutup"* → satu baris
  per sisa sesudah netting. Ini daftar kerja **clearing**.

Ada satu sebab tambahan yang membuat selisihnya terasa ekstrem di EBR: **seluruh
1.331 baris receivable terbuka tidak punya partner** (settlement POS dan jurnal
bank). Aged Receivable karena itu menampilkan satu grup "No Partner", dan netting
GL Open Items menjadi seagresif mungkin karena semua baris berbagi kunci partner
yang sama.

Bukti rinci: `Rekonsiliasi_Aging_vs_OpenItems.xlsx` di folder share.

---

## 4. Clearing baris plus-minus (#72)

Contoh yang Anda tanyakan, COA **2103400001 Non trade payable - Related parties**.
Keadaannya per 18-Sep-2026:

| | Jumlah |
|---|---|
| Baris terposting | 7 |
| Sudah terekonsiliasi | 4 |
| **Masih terbuka** | **3** |
| Saldo terbuka | −Rp 20.240.400 |

Dari 3 baris terbuka itu, **satu pasang bernilai Rp 6.200.000** (satu debit, satu
kredit) yang seharusnya saling menutup. Setelah dipasangkan, baris terbuka turun
dari 3 menjadi 1.

### Caranya

1. *Invoicing ▸ Accounting ▸ Reconciliation ▸ Reconcile*
2. Pilih akunnya (2103400001) — atau buka lewat tombol **Open Lines** dari layar
   Reconcile Overview.
3. Centang baris debit dan baris kredit yang jumlahnya sama.
4. Klik **Reconcile**.

Sesudah itu baris tersebut hilang dari Aging **dan** dari GL Open Items, karena
keduanya membaca sisa, bukan baris mentah.

### Kalau jumlahnya tidak sama persis

Gunakan **Write-off** di dialog yang sama: selisihnya dibukukan ke COA yang Anda
pilih, dan kedua baris ikut tertutup. Jangan membuat jurnal manual untuk
"merapikan" — jurnal manual menambah baris terbuka baru, bukan menutup yang lama.

### Yang TIDAK boleh dilakukan

* **Jangan** reset to draft lalu post ulang hanya untuk merapikan tampilan. Di
  Odoo 19 rekonsiliasi **tetap melekat** saat dokumen di-draft, dan posting ulang
  menghitung ulang baris pajak yang diketik tangan.
* **Jangan** menghapus baris. Yang hilang dari daftar harus hilang karena
  tertutup, bukan karena dihapus.

---

## 5. Clearing massal GR/IR

Untuk GR/IR jangan memakai layar Reconcile satu per satu — jumlahnya ribuan.
Sejak 17-Sep-2026 setiap vendor bill yang diposting **me-netting akrual GR/IR-nya
sendiri**, dan bill lama sudah di-backfill. Hasilnya:

| | Sebelum | Sesudah |
|---|---|---|
| Baris GR/IR terbuka | 68.345 | **7.978** |
| Seluruh baris reconcilable | 71.273 | **12.316** |

Sisa Rp 5,1 miliar di 2103109121 **bukan** tunggakan rekonsiliasi: itu penerimaan
September yang memang belum ditagih vendor. Angkanya bisa dilihat per baris di
Purchase Report dengan kolom **Status Bill = "Belum di-bill"**, dan ikat persis ke
saldo GR/IR terbuka.

---

## 6. Skrip pendukung

| Skrip | Kegunaan |
|---|---|
| `scripts/tenants/levis/125_recon_aging_vs_open_items.py` | Rekonsiliasi Aged vs GL Open Items per tanggal posisi (#73) |
| `scripts/tenants/levis/114_grir_backfill_reconcile.py` | Backfill netting GR/IR untuk bill lama |

Keduanya SELECT-only kecuali disebutkan lain, dan dijalankan lewat `odoo shell`.
