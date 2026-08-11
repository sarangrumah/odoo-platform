---
title: Penjualan, Retail & POS
domain: penjualan-retail-pos
---

# 7. Penjualan, Retail & POS

{{n.domain.penjualan-retail-pos}} modul. Domain ini menopang tenant retail yang
sudah **live** — Levi's / PT Era Busana Retailindo — dan karena itu berisi jalur
data dengan volume terbesar di platform.

## 7.1 Jalur impor data retail

Toko Levi's berjalan di atas **XStore**, yang tidak memiliki konektor. Yang ada
adalah ekspor laporan berformat XLSX dan CSV: master material, on-hand, detail
penjualan, dan settlement tender.

`custom_retail_import` adalah mesin ingest untuk itu — **sepenuhnya generik**.
Sebuah profil impor mendeklarasikan format, baris header, pemetaan kolom, dan
namespace; wizard melakukan pratinjau kering dan menyaring duplikat lewat SHA256;
eksekutor memuat secara idempoten lewat external ID. Yang khusus Levi's hanyalah
profil-profil di dalam datanya. Modul ini punya nomor versi tertinggi di seluruh
platform, yang mencerminkan berapa banyak kasus tepi data retail nyata yang sudah
ditemui dan ditangani.

Tiga modul melengkapinya:

- **API master produk** (`custom_retail_import_api`) menerima dorongan JSON dari
  MDM HUB alih-alih menarik laporan terjadwal. Ia dipisahkan dari mesin utama
  karena Odoo membangun peta rute per basis data: menaruh controller di modul
  bersama akan mengekspos `/api/mdm/*` di semua basis data Levi's sekaligus.
  Memasangnya hanya di tempat yang diinginkan membuat rute itu **tidak ada** di
  tempat lain — jaminan yang lebih kuat daripada flag runtime.
- **Jembatan POS** (`custom_retail_import_pos`) membukukan penjualan dan retur
  POS hasil impor dengan akun pajak, diskon, dan retur yang diambil dari berkas
  sumbernya, bukan dari default.
- **Rekonsiliasi** (`custom_retail_import_recon`) mencocokkan per transaksi antara
  berkas penjualan dan apa yang benar-benar terbukukan di Odoo.

> Pembukuan hasil impor dikendalikan **per parameter, per basis data** dan mati
> secara bawaan. Ini disengaja: sebuah basis data pengembangan yang menerima
> berkas produksi tidak boleh ikut membukukan jurnal. Mengaktifkannya adalah
> keputusan sadar per lingkungan.

## 7.2 POS, e-commerce, dan langganan

**POS Indonesia** (`custom_pos_id`) menambahkan QRIS, pembulatan rupiah, dan
struk elektronik lewat WhatsApp atau SMS.

**eCommerce Indonesia** (`custom_ecommerce`) menyediakan registri kurir lokal —
JNE, JNT, SiCepat, AnterAja, Pos — dan checkout Midtrans/Xendit, ditambah
pelacakan keranjang terbengkalai. **Storefront API**
(`custom_storefront_api`) mengekspos REST JSON headless untuk storefront Next.js:
katalog, keranjang, autentikasi JWT, checkout, bukti pembayaran, dan wishlist.
Keduanya sudah membawa konfigurasi untuk GentleWoman, tenant di luar grup
Erajaya.

**CRM** (`custom_crm`) menutup selisih Enterprise dengan penambangan prospek,
skoring prediktif, pengayaan data, formulir web, dan otomasi.
**Langganan** (`custom_subscription`) menangani penagihan berulang dengan
analitik MRR/LTV dan prediksi churn.

## 7.3 Lokalisasi Levi's

`custom_levis_localization` adalah modul khusus brand terbesar di platform,
dengan 26 berkas model. Isinya adalah kumpulan aturan yang benar-benar hanya
berlaku di EBR: HS Code pada produk, batas kuantitas penerimaan, keputusan untuk
**tidak membukukan jurnal persediaan saat penerimaan barang**, jurnal billing,
voucher pembayaran, pemetaan MID bank, dan mesin kliring piutang POS per toko.

Ia tidak dapat dipakai ulang apa adanya — dan memang tidak dimaksudkan demikian.
Yang generik dari pekerjaan Levi's sudah dipromosikan keluar: mesin impor retail,
retur pembelian, biaya admin pembayaran, dan voucher pembayaran semuanya hidup di
`ee_gap/` dan tersedia untuk tenant lain.

## 7.4 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
