# Template impor pajak — Coretax & Mitra Pajakku

Empat template resmi yang dikirim klien pada 17-Sep-2026. Disimpan di repo karena
ketiadaannya adalah satu-satunya hal yang memblokir sheet baris **#34** (Faktur Pajak
Keluaran) dan **#35** (Retur Pajak Masukan) selama berbulan-bulan — gate **G8** dan **G9**
di rencana After Go Live.

NPWP di header keempatnya `1000000006199490` = **PT ERA Busana Retailindo**, jadi template
ini memang disiapkan untuk tenant ini, bukan contoh generik.

## Apa yang sudah ada di kode, dan apa yang belum

Diverifikasi 17-Sep-2026 dengan membandingkan kolom template terhadap konstanta di
`addons/ee_gap/custom_coretax_export`.

| Template | Struktur | Kode | Status |
|---|---|---|---|
| **Faktur Pajak Keluaran — MITRA PAJAK** | sheet `Import FK`: baris `FK` 35 kolom + baris `OF` 16 kolom | `models/coretax_fk_builder.py` → `FK_COLUMNS` / `OF_COLUMNS` | **Cocok byte-identik.** Nama dan urutan 35 + 16 kolom sama persis |
| **Retur Pajak Masukan — CORETAX** | sheet `Retur` 12 kolom + `DetailRetur` 15 kolom | `wizards/coretax_template_export.py` → `RETUR_COLUMNS` / `RETUR_DETAIL_COLUMNS` | **Cocok.** Lihat catatan di bawah soal kolom ke-15 |
| **Faktur Pajak Keluaran — CORETAX** | sheet `Faktur` 18 kolom + `DetailFaktur` 14 kolom + 4 sheet referensi | — | **Belum ada** |
| **Retur Pajak Masukan — MITRA PAJAK** | satu sheet: baris `RM` 24 kolom + baris `OF` 23 kolom | — | **Belum ada** |

Exporter yang sudah ada dijalankan lewat wizard `custom.coretax.template.export.wizard`
(pilihan `fk` dan `retur`).

### Jebakan: header `DetailRetur` di berkas sample kurang satu kolom

Sheet `DetailRetur` pada *Sample Template Retur Pajak Masukan CORETAX.xlsx* hanya menulis
**14** header, berhenti di `Tarif PPnBM`. Kode menulis **15**, dengan `PPNBM Retur` di akhir.

**Kode yang benar.** Sheet `Keterangan` di berkas yang sama mencantumkan `PPNBM Retur`
sebagai kolom **wajib** ("Ya | Ya | Isikan dengan nilai 0 jika tidak ada Retur PPnBM").
Header di sheet sample-nya yang tidak lengkap, bukan exporternya yang kelebihan kolom.
Jangan "memperbaiki" kode agar cocok dengan sample.

## Kenapa kedua export masih kosong

Kodenya jalan; datanya yang tidak ada. Dijalankan di `prd_levis_begbal` untuk masa 07 dan 08
tahun 2026, keduanya menghasilkan **0 baris** tanpa error.

**Faktur Pajak Keluaran — tidak mungkin dari data ini, dan itu struktural.**
Template menuntut identitas pembeli per faktur: NPWP/NIK Pembeli, Jenis ID, Nama, Alamat,
ID TKU Pembeli. Yang ada di database: **0 faktur penjualan** (satu-satunya `out_invoice`
berstatus *cancel*), dan **2.096 baris PPN keluaran** Jun–Sep 2026 pada akun 2104300001
yang **seluruhnya tanpa partner** — semuanya jurnal POS digunggung. Retail PKP Pedagang
Eceran memang tidak menerbitkan faktur per pembeli; bentuk pelaporan yang benar adalah
rekap digunggung, yang sudah live sebagai `custom.report.ppn.digunggung`.

**Retur Pajak Masukan — terhalang alur, bukan format.**
Template menuntut `Nomor Faktur` (NSFP faktur vendor yang diretur) dan `NPWP Penjual`.
Sisi sumbernya sehat: **784 dari 911** vendor bill terposting punya NSFP (86 %). Yang tidak
ada adalah nota kreditnya — hanya **3** `in_refund` terposting, **nol** punya NSFP, dan
ketiganya tanpa baris pajak. Retur fisik ke vendor memang terjadi (200 stock move ke lokasi
supplier) tetapi tidak menghasilkan nota kredit yang membawa NSFP asal dan PPN.

Jadi yang dibutuhkan T15 bukan exporter baru, melainkan alur retur pembelian yang
menerbitkan nota kredit ber-NSFP dan berbaris pajak — bersinggungan dengan #26 / T10.
