---
title: Gudang & Inventori
domain: gudang-inventori
---

# 6. Gudang & Inventori

{{n.domain.gudang-inventori}} modul membentuk sebuah **Warehouse Management
System lengkap** di atas Odoo Community. Ini kelompok modul paling matang di
platform: hampir seluruhnya dinilai *Produksi*, dan sebagian besar sudah diuji
dalam skenario proof-of-concept ujung ke ujung.

## 6.1 Mesin gudang

**Putaway** (`custom_wms_putaway`) adalah mesin penempatan bertingkat yang dapat
dikonfigurasi: aturan berjenjang memutuskan bin mana yang diusulkan untuk setiap
baris penerimaan, dan usulannya diberi peringkat, bukan sekadar diambil yang
pertama cocok.

**Slotting bergaya SAP** (`custom_wms_sap_slotting`) menambahkan dua dimensi yang
tidak dimodelkan mesin dasar: Storage Type (*Lagertyp*) dan Storage Section
(*Lagerbereich*), masing-masing dengan urutan pencarian sendiri. Gudang yang
bermigrasi dari SAP WM mengharapkan pencarian berjalan dalam urutan itu.
Seluruhnya ditambahkan lewat pewarisan, sehingga tenant yang tidak memakai
slotting SAP tidak perlu ikut memutakhirkan modul putaway bersama.

**QC penerimaan** (`custom_wms_inbound_qc`) memasang gerbang karantina: barang
masuk tidak dapat direservasi sampai lolos QC, dan barang tak dikenal
diregistrasi alih-alih ditolak diam-diam.

**Cycle count** (`custom_wms_cycle_count`) menjalankan stock opname berbasis
rencana dengan persetujuan selisih. **Transfer Order Engine**
(`custom_wms_to_engine`) memicu perpindahan internal berdasarkan aturan: batas
stok minimum, kedaluwarsa, dan konsolidasi.

## 6.2 Perangkat genggam

`custom_wms_hht` adalah aplikasi handheld yang benar-benar memindahkan stok —
menggantikan shell demo yang hanya *mencatat* pemindaian. Antarmukanya berbasis
tugas dengan lencana antrean kerja per modul: terima, putaway, pick dan pack,
package, count, bin-to-bin, dan pemeriksaan stok baca-saja.

Ia sengaja dipisahkan dari `custom_hht_bridge` yang menyediakan shell PWA, API
REST ber-HMAC per perangkat, dan antrean offline. Alasannya operasional:
jembatan itu terpasang di basis data produksi ARKA yang tidak memiliki satu pun
model WMS, dan tidak boleh ikut dipaksa naik versi untuk fitur khusus gudang.

Antrean offline bersifat idempoten pada pasangan `(device_id, client_id)`,
sehingga pemindaian yang terkirim ulang setelah koneksi pulih tidak
menggandakan pergerakan stok.

## 6.3 Barcode dan penerimaan

**Barcode** (`custom_barcode`) menyediakan pemindaian scan-in dan scan-out
setara Enterprise, termasuk nomenklatur GS1. **Barcode produk ganda**
(`custom_product_barcode`) mengizinkan beberapa barcode alternatif untuk satu
varian — satu varian, satu stok, semuanya dapat dipindai.

**Kelengkapan penerimaan** (`custom_wms_receiving_ext`) menutup celah yang halus
tetapi mahal: tanggal kedaluwarsa GS1 yang sebelumnya diurai lalu dibuang kini
benar-benar ditulis ke lot, nomor batch pemasok disimpan sehingga penarikan
produk dapat ditelusuri ke batch pemasoknya, dan pemindaian IMEI polos tidak lagi
jatuh sebagai "tidak ditemukan". Ditambah wizard impor penerimaan massal dari
CSV/XLSX dengan template kosong yang bisa diunduh.

## 6.4 Dokumen dan laporan

**Dokumen dan label** (`custom_wms_docs`) menghasilkan picking list, packing
list, lembar scan, dan label harga.

**Paket laporan** (`custom_wms_reports`) menyediakan enam analisis — retur
pembelian, ringkasan stok dengan nilai, stock take, spot check, transfer, dan
scrap. Seluruh model analisisnya adalah **SQL view baca-saja**, sehingga tidak
mungkin menyimpang dari data operasional yang diringkasnya. Setiap laporan
mengekspor ke **XLSX dengan barcode Code128 tertanam** di dua tingkat — satu untuk
dokumen, satu untuk baris — sehingga lembar kerjanya tetap dapat dipindai di luar
Odoo.

## 6.5 Pembelian dan antar-perusahaan

**Retur pembelian** (`custom_po_return`) menangani retur ke vendor berbasis
kuantitas dengan alokasi FIFO lintas PO dan penerimaan, beserta nota kredit
otomatis. **Pengadaan antar-perusahaan**
(`custom_intercompany_procurement`) mencerminkan purchase order dan pengiriman
antar perusahaan sekelompok secara otomatis — pola yang lahir dari kebutuhan
grup Erajaya, tetapi ditulis generik.

**Validasi penerimaan asinkron** (`custom_receipt_async`) memindahkan validasi
penerimaan berukuran besar ke antrean latar belakang, sehingga operator tidak
menunggu.

> Satu modul di domain ini, `custom_stock_delivery_report_fix`, **sengaja
> dinonaktifkan**. Ia adalah tambalan untuk template surat jalan bawaan Odoo dan
> hanya diaktifkan bila cacat itu muncul kembali. Ia tetap dihitung agar total
> modul dapat direkonsiliasi.

## 6.6 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
