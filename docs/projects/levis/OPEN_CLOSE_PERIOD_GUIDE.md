# Levi's Odoo — Panduan Open / Close Period (Accounting)

Panduan ini menjawab permintaan tim Accounting (sheet after-go-live #4): *"guide
untuk melakukan open period dan close period di Odoo"*.

> **Konsep penting.** Odoo **tidak** memakai objek "periode akuntansi" yang
> dibuka/ditutup satu-satu seperti sebagian ERP lain. Yang dipakai Odoo adalah
> **Lock Date (Tanggal Kunci)**: sebuah tanggal batas. Semua jurnal **pada atau
> sebelum** tanggal itu terkunci (tidak bisa dibuat/diubah/dihapus).
> - **Menutup periode (close)** = **memajukan** Lock Date ke akhir periode.
> - **Membuka kembali (open/reopen)** = **memundurkan** Lock Date (kecuali Hard
>   Lock Date — lihat peringatan di bawah).

Semua langkah butuh user dengan grup **Accounting / Adviser (Full Accounting
Features)**. Kerjakan uji coba di `rnd_levis` dulu sebelum `prd_levis` /
`prd_levis_begbal` / `prd_detail_levis`.

---

## 1. Jenis Lock Date di Odoo 19

Menu: **Accounting → Accounting → Lock Dates** (atau **Settings → Users &
Companies → Companies →** tab akun; atau Accounting → Configuration → Settings →
bagian *Fiscal Periods*). Field pada company:

| Label di UI | Field | Efek |
|---|---|---|
| **Global Lock Date** | `fiscalyear_lock_date` | Kunci **semua** jurnal (semua user) s/d tanggal ini. Ini yang dipakai untuk **tutup buku bulanan/tahunan**. Bisa dimundurkan (reversible). |
| **Tax Return Lock Date** | `tax_lock_date` | Kunci perubahan yang berdampak ke **pelaporan pajak (PPN)** s/d tanggal ini. Set setelah SPT Masa dilaporkan. Reversible. |
| **Sales Lock Date** | `sale_lock_date` | Kunci jurnal **penjualan** (mis. invoice pelanggan / POS) s/d tanggal ini. Reversible. |
| **Purchase Lock date** | `purchase_lock_date` | Kunci jurnal **pembelian** (vendor bill) s/d tanggal ini. Reversible. |
| **Hard Lock Date** | `hard_lock_date` | Kunci **permanen & tidak bisa dimundurkan**. ⚠️ Gunakan hanya bila yakin periode final. |

> Field `user_*_lock_date` adalah bayangan per-user (Odoo menyimpan siapa & kapan
> mengubah). Jangan diisi manual.

---

## 2. MENUTUP periode (Close Period)

Lakukan **setelah** seluruh transaksi periode masuk & tervalidasi (lihat
checklist Bagian 4).

1. Buka **Accounting → Accounting → Lock Dates**.
2. Pada **Global Lock Date**, isi **tanggal akhir periode** yang mau ditutup —
   mis. tutup Juli 2026 → `31/07/2026`.
3. Jika SPT Masa PPN periode itu sudah dilaporkan, isi **Tax Return Lock Date**
   dengan tanggal yang sama (`31/07/2026`).
4. **Save**. Sejak saat ini, tidak ada user (termasuk adviser) yang bisa
   membuat/mengubah/menghapus jurnal bertanggal ≤ 31/07/2026.

Efek: percobaan posting/edit ke periode terkunci akan ditolak Odoo dengan pesan
*"You cannot add/modify entries prior to and inclusive of the lock date"*.

---

## 3. MEMBUKA kembali periode (Open / Reopen Period)

Kadang perlu koreksi jurnal di bulan yang sudah ditutup (mis. temuan audit,
reklas). Selama periode itu **belum** kena **Hard Lock Date**, periode bisa
dibuka lagi:

1. Buka **Accounting → Accounting → Lock Dates**.
2. **Mundurkan Global Lock Date** ke sebelum periode yang mau dikoreksi — mis.
   mau buka Juli 2026 → set Global Lock Date ke `30/06/2026` (atau kosongkan).
3. Jika koreksi berdampak pajak dan Tax Return Lock Date menutupinya, mundurkan
   juga **Tax Return Lock Date**.
4. **Save**, lakukan koreksi jurnal, lalu **tutup lagi** (Bagian 2).

> **Praktik yang disarankan:** buka periode sesingkat mungkin, lakukan koreksi,
> langsung tutup kembali — supaya tidak ada transaksi baru "nyelip" ke periode
> yang seharusnya final.

### ⚠️ Hard Lock Date tidak bisa dibuka
`hard_lock_date` bersifat **permanen**: setelah diisi, Odoo **tidak** mengizinkan
memundurkannya, dan periode di bawahnya tidak akan pernah bisa dibuka lagi.
Gunakan hanya untuk periode yang benar-benar final (mis. setelah audit tahunan
selesai). Untuk tutup buku bulanan rutin, cukup **Global Lock Date** (reversible).

---

## 4. Checklist tutup buku bulanan (Levi's)

Urutan ini mengikuti swimlane **D08 Period Close** dan Manual Guide Levi's.
Sebelum memajukan Global Lock Date, pastikan:

1. **Semua file periode sudah di-import** (X101, X24, X70D, dst.) dan sesi POS
   ter-tutup. Suspense/clearing penjualan **nol** (rekonsiliasi X70D = Rp0).
2. **Semua vendor bill & payment** periode itu ter-posting; GR/IR clearing net
   ke nol.
3. **Jurnal PPh & Faktur Pajak** periode itu lengkap (cek *Rekap PPh Pemotongan*
   dan *Rekap Faktur Pajak / Import PPN Masukan*).
4. **Periodic COGS run** (`levis.cogs.run`) untuk periode itu sudah dijalankan
   per Operating Unit (valuasi Odoo 19 tidak ada FIFO-vacuum otomatis).
5. **Bank reconciliation** selesai.
6. **Trial Balance** & laporan keuangan sudah dicek (tidak ada selisih vs EBR).
7. Baru **set Global Lock Date = akhir bulan**; set **Tax Return Lock Date**
   setelah SPT Masa PPN dilaporkan.

---

## 5. Catatan khusus Levi's

- **Load TB/GL awal ke periode lampau:** jika perlu meng-import Trial Balance /
  GL ke bulan yang sudah lewat, **kosongkan/mundurkan dulu Global Lock Date**;
  kalau tidak, import akan ditolak karena periode terkunci (lihat proses load
  EBR TB). Kunci lagi setelah selesai.
- **Company-dependent:** Lock Date diset **per company**. Pastikan company aktif =
  company Levi's yang benar saat mengubahnya.
- **Bukan pengembangan:** ini murni konfigurasi UI — tidak perlu deploy kode.
