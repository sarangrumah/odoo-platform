---
title: Perpajakan Indonesia
domain: perpajakan-indonesia
---

# 4. Perpajakan Indonesia

{{n.domain.perpajakan-indonesia}} modul menangani kewajiban perpajakan Indonesia,
seluruhnya dinilai *Produksi* kecuali satu jembatan kecil. Ini domain dengan
kepadatan regulasi tertinggi di platform, dan karena itu paling sering menyentuh
peraturan yang berubah.

## 4.1 Coretax DJP

`custom_coretax` mengimplementasikan permukaan kepatuhan Coretax sesuai
PER-11/PJ/2025: siklus **NSFP** pada jurnal, ekspor dan impor XML untuk tujuh
jenis dokumen utama, catatan **Bukti Potong**, serta penyimpanan **Sertifikat
Elektronik** (.p12) terenkripsi. Kata sandi sertifikat tidak pernah disimpan;
setiap akses sertifikat menulis baris audit.

Alur kerjanya mengikuti kenyataan operasional: operator menghasilkan XML,
mengunggahnya ke portal Coretax, lalu mengimpor kembali XML tanggapan DJP. Sebuah
abstraksi adapter memungkinkan jalur host-to-host menggantikan unggah manual di
kemudian hari tanpa mengubah alur penggunanya —
`custom_coretax_pajakku` sudah mengisi jalur itu untuk Pajakku sebagai ASPP.

**Bukti Potong Unifikasi** (`custom_coretax_bupot`) menangani PPh 22, 23, 4(2),
15, dan 26 dengan ekspor XML dan pembaruan nomor dari DJP.

**Ekspor template Coretax** (`custom_coretax_export`) menghasilkan workbook yang
sesuai format impor DJP: e-Faktur Keluaran (FK/OF), Retur Masukan, serta Bupot
Unifikasi dan PPh 21. Ini yang dipakai sehari-hari oleh dua tenant live.

## 4.2 Pemotongan PPh

Dua modul menangani PPh, dan pembagian tugasnya perlu dipahami karena keduanya
pernah membukukan hal yang sama dua kali.

`custom_tax_id` adalah mesin utama: pemotongan PPh 23, 4(2), dan 26, PPN **DPP
Nilai Lain** sesuai PMK 131/2024, serta Faktur Pengganti. Ia menyimpan kategori
dan aturan pemotongan, dan menghasilkan jurnal pemotongan saat tagihan
dibukukan. Registri kode objek pajak berisi 107 kategori yang dapat dipetakan ke
akun per tenant.

`custom_pph_witholding` adalah mesin generik yang lebih tua — registri tarif,
perhitungan, dan log penerapan — yang juga terpakai oleh payroll untuk PPh 21.

> Peringatan operasional yang layak diketahui: ketika pajak PPh dikonfigurasi
> sebagai pajak native Odoo **dan** dijalankan lewat mesin pemotongan sekaligus,
> jurnal terbentuk dua kali. Ini pernah terjadi di produksi dan sudah diperbaiki;
> konfigurasi tenant baru harus memilih salah satu jalur, bukan keduanya.

Satu jembatan kecil, `custom_accounting_recurring_tax_id`, membawa kode objek PPh
dari template tagihan berulang ke tagihan yang dihasilkannya. Ia terpasang
otomatis hanya ketika kedua modul induknya ada.

## 4.3 Hubungan dengan bagan akun

Modul perpajakan tidak membawa akun sendiri. Akun PPh dan PPN berasal dari
template bagan akun yang dipilih tenant — `l10n_erajaya` untuk tenant grup,
`l10n_id_psak_custom` untuk yang lain — dan dipetakan lewat konfigurasi. Itulah
sebabnya kedua template itu tercatat di Bab 3 dengan rujukan silang ke bab ini,
bukan sebaliknya.

## 4.4 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
