---
title: Keuangan & Akuntansi
domain: keuangan-akuntansi
---

# 3. Keuangan & Akuntansi

Domain terbesar di platform: **{{n.domain.keuangan-akuntansi}} modul**. Isinya
adalah kapabilitas akuntansi yang tidak ada di Odoo Community dan biasanya
menjadi alasan utama membeli lisensi Enterprise — dibangun sendiri, sehingga
tidak ada biaya lisensi per pengguna untuknya.

## 3.1 Yang menutup selisih Community versus Enterprise

**Mesin laporan keuangan** (`custom_accounting_reports`) adalah modul dengan
churn tertinggi kedua di seluruh platform, dan itu bukan kebetulan: laporan
adalah tempat kebenaran akuntansi diuji. Ia menyediakan Laba Rugi, Neraca, Buku
Besar, Neraca Saldo, Arus Kas, Aging Piutang dan Utang, Buku Kas dan Bank, Partner
Ledger, serta laporan pajak — semuanya dengan penelusuran ke jurnal asal.

**Rekonsiliasi manual** (`custom_account_reconcile`) mengembalikan menu dan wizard
rekonsiliasi bergaya Enterprise ke Community. Tanpa modul ini, mencocokkan
pembayaran dengan faktur di Community adalah pekerjaan satu per satu.

**Aset tetap** (`custom_accounting_asset`) membawa register aset, jadwal
penyusutan, cron posting bulanan, dan alur pelepasan aset — dipakai oleh dua
tenant live.

**Konsolidasi dan antar-perusahaan** (`custom_accounting_full`) menangani
otomasi transaksi antar-perusahaan, eliminasi, laporan konsolidasi, batas kredit,
tahun fiskal, dan tingkat follow-up penagihan.

Melengkapinya: jurnal dan pembayaran berulang, pendapatan/beban ditangguhkan,
pembayaran batch dengan ekspor file transfer bank Indonesia, impor rekening
koran multi-format, serta pelaporan keberlanjutan ESG untuk POJK 51/2017.

## 3.2 Kas, bank, dan pembayaran

Sekelompok modul kecil menutup hal-hal yang tampak sepele tetapi menghentikan
pekerjaan harian bila tidak ada: metode pembayaran **GIRO** dan **Bank Transfer**
pada jurnal bank, **voucher pembayaran dan kuitansi** yang bisa dicetak lengkap
dengan terbilang, dan **biaya admin bank multi-COA** pada wizard Register
Payment.

**Uang muka dan kas kecil** (`custom_petty_cash`) adalah kapabilitas yang tidak
dimiliki Odoo Enterprise sekalipun: permintaan bertipe, persetujuan Finance,
pencairan lewat bank, realisasi, penyelesaian, dan Kartu Uang Muka per karyawan,
termasuk penanganan multi-mata uang. Sudah terpasang di dua tenant live.

## 3.3 Finance Portal — Odoo di depan SAP

Empat modul membentuk **Finance Portal**, sebuah pola yang berbeda dari sisa
domain ini dan layak dipahami tersendiri.

Di sini Odoo berperan sebagai **sistem interaksi** di depan SAP S/4HANA yang tetap
menjadi **sistem pencatatan**. Odoo menjalankan formulir pengajuan, persetujuan
dua tahap Tax Review → Finance Review, dan validasi anggaran. Dokumen yang
disetujui didorong ke SAP, yang membukukan GL atau MIRO dan membayar.

Keputusan desain yang penting bagi Finance: **Odoo tidak pernah membukukan jurnal
sendiri di jalur ini.** Ia hanya mencerminkan status dari SAP. Tidak ada
mekanisme di sini yang bisa menciptakan versi kedua dari kebenaran di buku besar.

Empat jenis dokumen ditangani: uang muka beserta realisasinya, reimbursement,
tagihan vendor (dengan portal vendor), dan penyelesaian perjalanan dinas sebagai
cerminan data HRIS. Integrasi SAP-nya **menurun dengan anggun**: tanpa konfigurasi
adapter yang aktif, dorongan ke SAP jatuh ke stub lokal dan penjadwal tidak
melakukan apa-apa — portal tetap dapat dipakai sebelum konektor SAP siap.

## 3.4 Bagan akun

Dua template bagan akun tersedia. **Bagan Akun Erajaya** (`l10n_erajaya`)
menyediakan standar grup 10 digit — 534 akun, 29 grup akun, 78 pajak — dan dipakai
bersama oleh ARKA-AIM dan Levi's. **Bagan Akun PSAK** (`l10n_id_psak_custom`)
menyediakan alternatif 5 digit untuk tenant di luar standar grup.

Keduanya muncul sebagai pilihan di Settings → Accounting → Chart Template, dan
dipilih sekali saat perusahaan dibuat. Keduanya dinilai *Kerangka* pada kolom
Kematangan karena tidak memuat model Python dan tidak membawa pengujian; secara
operasional keduanya sudah dipakai di basis data produksi.

## 3.5 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
