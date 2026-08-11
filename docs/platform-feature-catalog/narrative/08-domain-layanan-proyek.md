---
title: Layanan, Proyek & Sewa
domain: layanan-proyek
---

# 8. Layanan, Proyek & Sewa

{{n.domain.layanan-proyek}} modul yang menopang dua lini berbeda: **penyewaan
aset** untuk ARKA-AIM, dan **manajemen delivery** untuk tim VAS PMO Erajaya
sendiri.

## 8.1 Penyewaan aset

`custom_rental` menangani siklus sewa penuh: tarif bertingkat, jadwal, BAST,
denda keterlambatan, portal pelanggan, dan pengiriman stok. Ia dibangun untuk
bisnis sewa dan pertunjukan drone ARKA-AIM, tetapi ditulis generik.

Tiga modul memperluasnya:

- **Paket sewa via BOM** membundel drone beserta perangkat pendukungnya sebagai
  kit, dan mengisi baris BAST otomatis saat pickup dan pengembalian.
- **Penagihan sewa** membuat faktur saat barang kembali — biaya sewa, denda
  keterlambatan, dan kerusakan dalam satu dokumen.
- **Pemeriksaan kualitas sewa** membuat quality check otomatis saat pengembalian
  dan menautkan aset sewa ke equipment pemeliharaan, sehingga riwayat kerusakan
  satu unit terbaca sebagai satu garis waktu.

**Laporan operasional armada** (`custom_ops_reports`) melengkapinya dengan opname
aset, pergerakan per event, suku cadang, kesehatan pemeliharaan, dan riwayat
perbaikan.

**BAST** sendiri adalah modul inti (`custom_bast`): dokumen serah terima generik
dengan tanda tangan ganda dan jejak audit, dapat dibuat langsung dari Sales
Order lewat `custom_sale_bast`.

## 8.2 Manajemen delivery — VAS PMO

Empat modul membentuk aplikasi PMO yang dipakai tim Value-Added Services Erajaya
untuk mengelola pekerjaannya sendiri:

- **Portofolio proyek** (`custom_project_portfolio`) memodelkan **vertikal
  brand** sebagai sumbu utama — setiap pekerjaan menggantung pada satu brand
  Erajaya — ditambah portofolio, sprint mingguan, dan tahap Hold serta
  Waiting-User-Verification yang menghentikan jam SLA.
- **Change Request** (`custom_project_cr`) memperlakukan CR sebagai record
  tersendiri, bukan sebagai task biasa: triase, analisis dampak, persetujuan
  berjenjang, dan penomoran resmi.
- **Notifikasi** (`custom_project_notify`) mengirim pemberitahuan berbasis aturan
  ke WhatsApp, email, dan Odoo lewat antrean outbox.
- **API PMO** (`custom_project_api`) menyediakan permukaan REST ber-JWT dan HMAC
  untuk aplikasi Next.js di depannya.

Keempatnya adalah satu-satunya modul di platform yang dokumen pengetahuannya
sudah berstatus **reviewed**.

## 8.3 Layanan pelanggan dan lapangan

**Helpdesk** (`custom_helpdesk`) menyediakan alur tiket dengan SLA, eskalasi, dan
portal pelanggan. **Field service** (`custom_field_service`) menangani penugasan
teknisi, work order di lokasi, pemakaian material, dan tanda tangan pelanggan.
**Timesheet** (`custom_timesheet`) menghubungkan pencatatan waktu billable ke
penagihan dan ke komponen lembur payroll.

## 8.4 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
