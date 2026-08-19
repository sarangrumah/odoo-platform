# Levi's Odoo — Panduan Open / Close Period (Accounting)

Panduan ini menjawab permintaan tim Accounting (sheet after-go-live #4): *"guide
untuk melakukan open period dan close period di Odoo, termasuk setting exception
user pada period yang sudah closed"*.

Versi klien (Google Docs, bahasa non-teknis) dibagikan terpisah; dokumen ini
adalah rujukan internal yang memuat detail perilaku sistem.

> **Konsep penting.** Odoo **tidak** memakai objek "periode akuntansi" yang
> dibuka/ditutup satu-satu seperti sebagian ERP lain. Yang dipakai Odoo adalah
> **Lock Date (Tanggal Kunci)**: sebuah tanggal batas. Semua jurnal **pada atau
> sebelum** tanggal itu terkunci (tidak bisa dibuat/diubah/dihapus).
> - **Menutup periode (close)** = **memajukan** Lock Date ke akhir periode.
> - **Membuka kembali (open/reopen)** = **memundurkan** Lock Date.

Semua langkah butuh user dengan grup **Accounting Manager**
(`account.group_account_manager`). Uji coba di `rnd_levis` dulu sebelum
`prd_levis` / `prd_levis_begbal`.

---

## 1. Jenis Lock Date di Odoo 19

Menu: **Invoicing → Configuration → Lock Dates** (wizard dari
`custom_accounting_full`, hanya terlihat oleh Accounting Manager). Keempat field
yang sama juga ada di form company, grup *Lock Dates*.

| Label di UI | Field | Efek |
|---|---|---|
| **Global Lock Date** | `fiscalyear_lock_date` | Kunci **semua** jurnal s/d tanggal ini. Ini yang dipakai untuk **tutup buku bulanan/tahunan**. Reversible. |
| **Tax Return Lock Date** | `tax_lock_date` | Kunci jurnal yang mengandung pajak s/d tanggal ini. Diisi setelah SPT Masa dilaporkan. Reversible. |
| **Sales Lock Date** | `sale_lock_date` | Kunci invoice pelanggan & credit note s/d tanggal ini. Reversible. |
| **Purchase Lock Date** | `purchase_lock_date` | Kunci vendor bill & refund s/d tanggal ini. Reversible. |

**`hard_lock_date` sengaja TIDAK diekspos** — baik di wizard maupun di form
company. Core menolak memundurkan atau menghapusnya, sehingga satu kali salah
ketik mengunci pembukuan selamanya tanpa jalan kembali selain edit database.
Penutupan periode cukup memakai keempat tanggal lunak di atas.

Wizard menulis lewat `res.company.write`, jadi seluruh guard core tetap jalan:
pengecekan bank statement line yang belum direkonsiliasi, entri chatter pada
company (`tracking=True`), dan pembuatan ulang lock exception yang masih aktif.
Setiap perubahan juga dicatat ke `pdp.audit_log`.

---

## 2. MENUTUP periode (Close Period)

Lakukan **setelah** seluruh transaksi periode masuk & tervalidasi (lihat
checklist Bagian 5).

1. Buka **Invoicing → Configuration → Lock Dates**.
2. Pastikan **Company** benar — lock date berlaku per company.
3. Isi **Global Lock Date** = tanggal akhir periode, mis. `31/07/2026`.
4. Isi **Tax Return Lock Date** bila SPT Masa periode itu sudah dilaporkan.
5. Baca kotak peringatan (Bagian 3), lalu **Apply**.

Tabel **Current Lock Dates** di bagian bawah wizard menampilkan kondisi seluruh
company, jadi wizard ini juga bisa dipakai sekadar untuk mengecek: buka, lihat,
Cancel.

Percobaan posting/edit ke periode terkunci ditolak dengan pesan *"You cannot
add/modify entries prior to and inclusive of …"* — **kecuali** user tersebut
punya lock exception (Bagian 4).

---

## 3. Peringatan di wizard dan artinya

### Kuning — "… draft journal entry(ies) are dated on or before the Global Lock Date"

Ada jurnal **draft** bertanggal di dalam periode yang akan dikunci. Mengunci
periode tidak menghapusnya; saat nanti di-posting, Odoo **memajukan tanggal
akuntansinya melewati lock date**, sehingga transaksi Juli bisa mendarat di
Agustus tanpa disadari. Posting atau hapus dulu bila periode mau difinalkan.

### Merah — "… bank statement line(s) … are still unreconciled"

Core **menolak** menyimpan Global Lock Date selama masih ada baris rekening
koran yang belum direkonsiliasi di periode itu; Apply akan gagal. Tombol **Show
them** di dalam kotak membuka daftarnya. Cara merekonsiliasi: lihat
`GL_OPEN_ITEM_CLEARING_GUIDE.md`.

### Kuning — "… lock date exception(s) are active on this company"

Lihat Bagian 4. Ini yang paling sering disalahpahami.

---

## 4. Lock exception: user yang dikecualikan

Lock date **bukan kata terakhir**. Core mengevaluasi
`res.company._get_user_lock_date()`, yang mendahulukan `account.lock_exception`
aktif milik user tersebut (atau exception tanpa `user_id`, yang berlaku untuk
**semua orang**). Selama exception hidup, tanggal milik user itulah yang
berlaku.

Akibatnya sebuah periode bisa terbaca tertutup di form company padahal orang
tertentu masih bisa memposting ke dalamnya.

### Kondisi `prd_levis_begbal` per 19 Agustus 2026

- Global Lock Date company: **31 Juli 2026**
- **6 exception aktif tanpa `end_datetime`** pada **31 Mei 2026**: azis.sugiman,
  devina.himelda, dimas.leonaldy, logi.falakh, reduan.caperi, zefanya.wijaya —
  alasan tercatat *"Input transaksi Juni 2026 - exception permanen per user
  (permintaan user)"*.

Keenamnya **disengaja** dan dibuat atas permintaan tim. Jangan dicabut tanpa
konfirmasi. Selalu cek tabel exception sebelum menyatakan sebuah periode
tertutup.

### Melihat exception

Wizard **Lock Dates** menampilkan tabel: user (atau **EVERYONE**), lock date
mana yang dilonggarkan, tanggal penggantinya, kapan berakhir (**never** bila
permanen), dan alasannya.

### Membuat / mencabut exception

Odoo CE **tidak menyediakan menu** untuk `account.lock_exception` — tidak ada
`ir.actions.act_window` maupun menuitem untuk model itu. Pembuatan dan pencabutan
dilakukan lewat script oleh tim IT. Format permintaan dari Accounting: user
(atau "semua"), lock date mana, tanggal pengganti, **batas waktu**, dan alasan
bisnis.

Anjurkan exception **berbatas waktu** (`end_datetime` terisi). Exception permanen
membuat lock date kehilangan arti dan biasanya baru ketahuan saat audit.

### Jebakan utama

**Mengisi lock date baru tidak menghapus exception.** Core justru membuat ulang
setiap exception aktif terhadap tanggal company yang baru, sehingga exception
tetap hidup dengan tanggal lamanya. Menutup Agustus tidak menutup celah Juni
bagi keenam user di atas.

---

## 5. MEMBUKA kembali periode (Open / Reopen Period)

1. Buka **Invoicing → Configuration → Lock Dates**.
2. Mundurkan **Global Lock Date** ke sebelum periode yang mau dikoreksi — mis.
   buka Juli 2026 → `30/06/2026` (atau kosongkan).
3. Mundurkan juga **Tax Return Lock Date** bila koreksinya berdampak pajak.
4. **Apply**, lakukan koreksi, lalu **tutup lagi** (Bagian 2).

> **Praktik yang disarankan:** buka sesingkat mungkin, koreksi, langsung tutup
> kembali. Bila periode itu sudah dilaporkan ke manajemen/DJP, pilihan yang lebih
> benar adalah membukukan koreksi di **periode berjalan** — lihat
> `docs/projects/levis/` untuk kasus-kasus reklas yang sudah pernah dijalankan.

---

## 6. Checklist tutup buku bulanan (Levi's)

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
5. **Bank reconciliation** selesai — ini juga syarat teknis Odoo untuk menyimpan
   Global Lock Date.
6. **GL Open Items** ditinjau (GR/IR, uang muka, intercompany) — lihat
   `GL_OPEN_ITEM_CLEARING_GUIDE.md`.
7. **Trial Balance** & laporan keuangan sudah dicek (tidak ada selisih vs EBR).
8. Baru **set Global Lock Date = akhir bulan**; set **Tax Return Lock Date**
   setelah SPT Masa PPN dilaporkan.
9. Buka ulang wizard: pastikan tabel Current Lock Dates sesuai dan tidak ada
   exception tak terduga.

---

## 7. Catatan khusus Levi's

- **Load TB/GL awal ke periode lampau:** bila perlu meng-import Trial Balance /
  GL ke bulan yang sudah lewat, **kosongkan/mundurkan dulu Global Lock Date**;
  kalau tidak, import ditolak karena periode terkunci (lihat proses load EBR TB).
  Kunci lagi setelah selesai.
- **Per company:** pastikan company aktif = company Levi's yang benar.
- **Bukan pengembangan:** murni konfigurasi UI — tidak perlu deploy kode.
- **Jangan pakai `hard_lock_date`** lewat jalur apa pun (shell, data file). Tidak
  ada jalan kembali.
