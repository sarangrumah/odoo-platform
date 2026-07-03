# Kebutuhan Report Tim Tax (dari Transaksi Terkait Pajak)

> **Status:** Draft kebutuhan (BRD-level). Tujuan dokumen: mendefinisikan
> report apa saja yang dibutuhkan tim tax, **di-collect dari transaksi yang
> mengandung data pajak** (faktur jual/beli, pembayaran, payroll), lengkap
> dengan sumber field, kolom output, filter, frekuensi, format, dan status
> (sudah ada / gap).
>
> Konteks: lokalisasi Indonesia, PPN & PPh, Coretax DJP (PER-11/PJ/2025),
> e-Faktur & e-Bupot Unifikasi, ASPP Pajakku. Lihat [coretax.md](coretax.md)
> untuk alur integrasi Coretax.

---

## 1. Prinsip & ruang lingkup

1. **Report = agregasi transaksi**, bukan input manual. Setiap angka di report
   harus bisa ditelusuri balik ke `account.move` / `account.move.line` /
   `account.payment` / `hr.payslip` sumbernya (drill-down).
2. **Satu masa pajak = satu periode report.** Default periode = bulan takwim
   (masa PPN/PPh), dengan opsi rentang tanggal bebas untuk analisa.
3. **Ikuti format resmi DJP** untuk report yang menjadi lampiran SPT (e-Faktur,
   e-Bupot Unifikasi, SPT 1721). Report internal (rekonsiliasi, monitoring)
   boleh format bebas.
4. **Multi-tenant / multi-company:** setiap report difilter per `company_id`
   (NPWP yang melapor). Tidak boleh bocor lintas tenant.
5. **Auditable:** semua model pajak sudah mewarisi `pdp.audited.mixin`
   (append-only, hash-chained). Report tidak mengubah data, hanya membaca.

---

## 2. Sumber data — dari transaksi mana angka pajak diambil

| Transaksi | Model | Field/relasi pajak yang di-collect |
|---|---|---|
| **Faktur Penjualan / Nota Retur** | `account.move` (`out_invoice`, `out_refund`) | `x_custom_nsfp`, `x_custom_coretax_status`, `x_custom_coretax_status_code`, `x_custom_tanggal_faktur_pajak`, `x_custom_has_faktur_pajak`, `x_custom_coretax_replacement_of_id`/`_replaced_by_id`, tax lines (`tax_line_id`), DPP (`tax_ids` di base line) |
| **Tagihan Vendor / Nota Retur Beli** | `account.move` (`in_invoice`, `in_refund`) | PPN Masukan (tax lines), `x_custom_withholding_line_ids`, `x_custom_total_withheld`, `x_custom_has_bukti_potong`, `x_custom_no_bukti_potong`, `x_custom_bukti_potong_ids` |
| **Baris withholding** | `account.move.withholding.line` | `pph_kind` (23/4(2)/26/22/21), `category_id`, `base_amount` (DPP), `tarif`, `tax_amount`, `bupot_id` |
| **Pembayaran** | `account.payment` | aplikasi withholding (`custom.witholding.application`), journal items (voucher) |
| **Payroll / Slip Gaji** | `hr.payslip` | `pph21`, `bupot_id`; dari `hr.employee`: NPWP, NIK, `x_custom_ptkp_status`, `x_custom_ter_category`, `x_custom_employment_type` |
| **Master pajak** | `account.tax` | `x_custom_dpp_method` (regular/nilai_lain), `x_custom_dpp_factor`, `x_custom_dpp_category` (PMK 131/2024) |
| **Lawan transaksi** | `res.partner` | `x_custom_npwp`, `x_custom_nik`, `x_custom_npwp_status`, `x_custom_pkp`, `x_custom_foreign_counterparty` |
| **Bukti Potong (dikeluarkan/diterima)** | `custom.coretax.bukti.potong`, `custom.bupot.unifikasi(.line)` | jenis PPh, DPP, tarif, nilai, arah (issued/received), NPWP pemotong/dipotong |
| **Ledger submission ASPP** | `custom.coretax.transaction`, `custom.coretax.pajakku.usage` | status kirim, NSFP kembali, retry, hitung faktur/bupot per masa |

---

## 3. Katalog report yang dibutuhkan

Legenda **Status**: ✅ sudah ada · 🟡 sebagian (komponen ada, report belum) · ❌ gap.
Legenda **Format**: `XLSX` analisa/arsip · `CSV` impor aplikasi DJP · `PDF` cetak/tanda terima · `XML` Coretax/e-Faktur/e-Bupot.

### A. PPN — Pajak Pertambahan Nilai

#### TAX-PPN-01 · Rekap Faktur Pajak Keluaran (e-Faktur Output)
- **Tujuan:** daftar seluruh Faktur Pajak keluaran dalam satu masa → dasar SPT Masa PPN (Lampiran A2/B2) & pelaporan e-Faktur.
- **Sumber:** `account.move` (`out_invoice`/`out_refund`, `state=posted`) + tax line PPN keluaran + `x_custom_nsfp`, `x_custom_tanggal_faktur_pajak`, `x_custom_coretax_status_code`.
- **Kolom output:** No. urut · Kode & No. Seri FP (NSFP) · Tgl Faktur Pajak · NPWP/NIK & Nama Pembeli · Status PKP lawan · DPP · PPN · PPnBM (jika ada) · Kode transaksi (01/02/03/04/07/08…) · Status faktur (normal/pengganti/batal) · No. FP diganti.
- **Filter:** masa (bulan) · company · kode transaksi · status Coretax.
- **Frekuensi:** Masa (bulanan) · deadline lapor SPT Masa PPN akhir bulan berikutnya.
- **Format:** `XLSX` + `CSV` (skema impor e-Faktur) + `XML` (Coretax).
- **Konsumen:** Tax officer (pelaporan), auditor.
- **Status:** 🟡 e-Faktur XML export sudah ada (`custom_coretax`); **rekap tabular per masa (XLSX/CSV) belum** → gap.

#### TAX-PPN-02 · Rekap Faktur Pajak Masukan (e-Faktur Input) yang dapat dikreditkan
- **Tujuan:** daftar Faktur Pajak masukan → kredit pajak di SPT Masa PPN (Lampiran B1/B2).
- **Sumber:** `account.move` (`in_invoice`/`in_refund`) + tax line PPN masukan; flag dapat/ tidak dapat dikreditkan.
- **Kolom output:** No. Seri FP lawan · Tgl FP · NPWP & Nama Penjual · DPP · PPN Masukan · Dapat dikreditkan (Y/T) · Alasan tidak dapat dikreditkan.
- **Filter:** masa · company · dapat dikreditkan · kredit vs biaya.
- **Frekuensi:** Masa. **Format:** `XLSX` + `CSV`. **Konsumen:** Tax officer.
- **Status:** 🟡 sama seperti PPN-01 (rekap per masa belum ada).

#### TAX-PPN-03 · SPT Masa PPN 1111 (Induk + Lampiran AB/A2/B1/B2/B3)
- **Tujuan:** formulir induk SPT Masa PPN siap lapor (rekapitulasi PPN keluaran, masukan, kurang/lebih bayar, kompensasi).
- **Sumber:** agregasi TAX-PPN-01 + TAX-PPN-02 per masa.
- **Kolom output:** total DPP & PPN keluaran (per kode transaksi) · total DPP & PPN masukan · PPN kurang/(lebih) bayar · kompensasi masa sebelumnya · PPN disetor.
- **Frekuensi:** Masa. **Format:** `PDF` (induk) + `CSV`. **Konsumen:** Tax manager (approval sebelum lapor).
- **Status:** ❌ gap (butuh mapping ke struktur formulir 1111).

#### TAX-PPN-04 · Rekonsiliasi PPN (Keluaran − Masukan)
- **Tujuan:** posisi PPN kurang/lebih bayar & cross-check saldo GL akun PPN vs rekap faktur.
- **Sumber:** tax lines (`tax_line_id`) + saldo akun PPN Keluaran/Masukan di GL.
- **Kolom output:** PPN Keluaran · PPN Masukan · Net PPN · Saldo GL akun PPN · Selisih (harus 0) · breakdown per fiscal position.
- **Frekuensi:** Masa. **Format:** `XLSX`. **Konsumen:** Tax + Accounting.
- **Status:** 🟡 **sebagian sudah ada** di `custom.report.tax` (Output/Input + "Net PPN (Output − Input)" + per fiscal position). **Belum ada:** kolom rekonsiliasi vs saldo GL & selisih.

#### TAX-PPN-05 · Laporan DPP Nilai Lain (PMK 131/2024)
- **Tujuan:** audit trail perhitungan DPP nilai lain / PPN efektif 11% via 11/12 (transisi 2025) & kategori khusus.
- **Sumber:** `account.tax` (`x_custom_dpp_method`, `x_custom_dpp_factor`, `x_custom_dpp_category`) + move line yang memakainya.
- **Kolom output:** Transaksi · Kategori DPP (impor, emas, kendaraan bekas, jasa freight, dll.) · DPP penuh · Faktor · DPP nilai lain · Tarif · PPN.
- **Frekuensi:** Masa / on-demand. **Format:** `XLSX`. **Konsumen:** Tax officer, auditor.
- **Status:** ❌ gap (field ada, report belum).

#### TAX-PPN-06 · Monitoring NSFP & Status Faktur
- **Tujuan:** pantau siklus NSFP: draft → submitted → approved (NSFP terisi) → rejected DJP; deteksi faktur belum ber-NSFP mendekati deadline.
- **Sumber:** `account.move.x_custom_coretax_status`, `x_custom_nsfp`, `x_custom_coretax_submission_uuid`, `custom.coretax.transaction`.
- **Kolom output:** No. faktur internal · Tgl · Status Coretax · NSFP · UUID submission · Umur (hari sejak posting) · Aksi (activity ke AR clerk jika rejected).
- **Frekuensi:** Harian/real-time (dashboard). **Format:** `XLSX` + list view Odoo. **Konsumen:** Tax officer, ops.
- **Status:** ❌ gap (data ada di ledger, report/dashboard belum).

#### TAX-PPN-07 · Daftar Faktur Pengganti & Pembatalan
- **Tujuan:** rekap koreksi masa — faktur pengganti (kode status 01–09) dan pembatalan (02) untuk pelaporan koreksi.
- **Sumber:** `x_custom_coretax_status_code`, `x_custom_coretax_replacement_of_id`/`_replaced_by_id`.
- **Kolom output:** NSFP asal · NSFP pengganti · Kode status · Tgl · Alasan · Selisih DPP/PPN.
- **Frekuensi:** Masa. **Format:** `XLSX`. **Status:** ❌ gap (workflow Faktur Pengganti ada di `custom_tax_id`; report rekap belum).

### B. PPh Pemotongan/Pemungutan (perusahaan sebagai pemotong)

#### TAX-PPH-01 · Rekap Bukti Potong PPh Unifikasi (e-Bupot: 22/23/4(2)/15/26)
- **Tujuan:** dasar SPT Masa PPh Unifikasi & lampiran e-Bupot Unifikasi per masa.
- **Sumber:** `custom.coretax.bukti.potong` / `custom.bupot.unifikasi.line` + `account.move.withholding.line`.
- **Kolom output:** No. Bukti Potong · Tgl · NPWP/NIK & Nama dipotong · Jenis PPh · Kode objek pajak · DPP · Tarif · PPh dipotong · Status upload DJP.
- **Filter:** masa · jenis PPh · status upload.
- **Frekuensi:** Masa · deadline SPT Masa PPh Unifikasi tgl 20 bulan berikutnya.
- **Format:** `XLSX` + `PDF` (bukti potong) + `XML` (e-Bupot Unifikasi v2).
- **Konsumen:** Tax officer.
- **Status:** 🟡 XML export e-Bupot + PDF per lembar **sudah ada** (`custom_coretax_bupot`); **rekap tabular per masa (XLSX) belum** → gap.

#### TAX-PPH-02 · Rekap PPh Pasal 23 per Jenis Penghasilan
- **Tujuan:** rincian PPh 23 (jasa, sewa, royalti, dividen, bunga, hadiah, komisi…) per lawan transaksi.
- **Sumber:** `account.move.withholding.line` (`pph_kind='pph_23'`) + `category_id`.
- **Kolom output:** Kategori jasa · NPWP & Nama · DPP · Tarif (2%/15%) · PPh · No. Bukti Potong.
- **Frekuensi:** Masa. **Format:** `XLSX`. **Status:** ❌ gap (data granular ada, rekap belum).

#### TAX-PPH-03 · Rekap PPh Pasal 4(2) Final
- **Tujuan:** rincian PPh final (sewa tanah/bangunan, konstruksi, dll.).
- **Sumber:** withholding line `pph_kind='pph_4_2'`. **Kolom:** objek · DPP · tarif · PPh · bukti potong. **Format:** `XLSX`. **Status:** ❌ gap.

#### TAX-PPH-04 · Rekap PPh Pasal 26 (Lawan Transaksi Luar Negeri)
- **Tujuan:** PPh 26 atas pembayaran ke WP luar negeri (tarif 20% atau tarif P3B/tax treaty).
- **Sumber:** withholding line `pph_kind='pph_26'` + `res.partner.x_custom_foreign_counterparty`.
- **Kolom:** negara · NPWP LN/TIN · DPP · tarif (20%/treaty) · PPh · No. CoD/DGT jika ada. **Format:** `XLSX`. **Status:** ❌ gap.

#### TAX-PPH-05 · Rekap PPh Pasal 22 (Impor / Pemungutan)
- **Tujuan:** PPh 22 impor (2,5% API) & pemungutan lain.
- **Sumber:** withholding line `pph_kind='pph_22'` + fiscal position Impor.
- **Kolom:** dokumen impor/PIB · DPP · tarif · PPh 22. **Format:** `XLSX`. **Status:** ❌ gap.

#### TAX-PPH-06 · PPh 21 — Rekap Masa & SPT 1721 (dari Payroll)
- **Tujuan:** rekap pemotongan PPh 21 karyawan per masa + SPT Masa 1721 + SPT 1721 A1 tahunan.
- **Sumber:** `hr.payslip.pph21` + `hr.payslip.bupot_id`; `hr.employee` (NPWP/NIK, `x_custom_ptkp_status`, `x_custom_ter_category`, `x_custom_employment_type`).
- **Kolom output:** Karyawan · NPWP/NIK · PTKP · Kategori TER (A/B/C) · Bruto · PPh 21 (TER bulanan / progresif) · No. Bukti Potong 1721.
- **Frekuensi:** Masa (rekap) + Tahunan (1721 A1). **Format:** `PDF` (1721 A1) + `XML` + `XLSX` (rekap masa).
- **Konsumen:** Tax + HR/Payroll.
- **Status:** 🟡 **SPT 1721 A1 tahunan (PDF+XML) sudah ada** (`custom_hr_payroll_id`); **rekap masa PPh 21 tabular belum** → gap.

### C. Kredit Pajak & Angsuran (perusahaan sebagai pihak yang dipungut)

#### TAX-CR-01 · Daftar Kredit Pajak — Bukti Potong Diterima (PPh 22/23 dipotong pihak lain)
- **Tujuan:** kumpulan bukti potong yang **diterima** dari lawan → kredit pajak di SPT (mengurangi PPh terutang / angsuran).
- **Sumber:** `custom.coretax.bukti.potong` arah *received* (impor bupot XML/PDF, lihat coretax.md §Bukti potong import); saldo akun *Uang Muka PPh*.
- **Kolom output:** No. bukti potong pemotong · NPWP pemotong · Jenis PPh · DPP · PPh dipotong · Faktur jual terkait · Status rekonsiliasi.
- **Frekuensi:** Masa / tahunan (SPT). **Format:** `XLSX`. **Konsumen:** Tax officer.
- **Status:** 🟡 workflow impor bupot ada di doc; **report agregat kredit pajak belum** → gap.

#### TAX-CR-02 · Monitoring PPh Pasal 25 (Angsuran)
- **Tujuan:** pantau kewajiban angsuran PPh 25 bulanan vs setoran.
- **Sumber:** jurnal angsuran PPh 25 (GL) + dasar perhitungan dari SPT Tahunan.
- **Kolom:** masa · angsuran terutang · disetor · tgl setor/NTPN · selisih. **Format:** `XLSX`. **Status:** ❌ gap.

### D. Rekonsiliasi & Ekualisasi (untuk pemeriksaan / SPT Tahunan)

#### TAX-REC-01 · Ekualisasi Peredaran Usaha (Omzet PPN vs PPh Badan)
- **Tujuan:** cocokkan total penyerahan di SPT Masa PPN dgn peredaran usaha di PPh Badan/GL; identifikasi selisih (uang muka, non-BKP, ekspor, dll.).
- **Sumber:** rekap PPN keluaran (TAX-PPN-01) vs laporan penjualan/GL pendapatan.
- **Kolom:** omzet PPN setahun · omzet PPh/GL · selisih · rekonsiliasi item. **Frekuensi:** Tahunan/kuartalan. **Format:** `XLSX`. **Status:** ❌ gap.

#### TAX-REC-02 · Rekonsiliasi PPN GL vs SPT (equalisasi PK/PM)
- **Tujuan:** saldo akun PPN Keluaran/Masukan di GL = total di SPT Masa. **Sumber:** GL + tax lines. **Format:** `XLSX`. **Status:** 🟡 (bergabung dgn TAX-PPN-04).

#### TAX-REC-03 · Rekonsiliasi PPh Terutang vs Disetor
- **Tujuan:** per jenis PPh (21/23/4(2)/26/22/25): terutang (dari transaksi) vs disetor (NTPN) vs dilaporkan. **Sumber:** withholding lines + jurnal setoran. **Format:** `XLSX`. **Status:** ❌ gap.

#### TAX-REC-04 · Ekualisasi Biaya vs Objek Pemotongan PPh
- **Tujuan:** pastikan setiap biaya yang merupakan objek PPh sudah dipotong; deteksi biaya objek PPh tanpa bukti potong (risiko koreksi pemeriksaan).
- **Sumber:** `account.move.line` biaya + `product.template.x_custom_withholding_category_id` + withholding lines. **Format:** `XLSX`. **Status:** ❌ gap (high value untuk audit defense).

### E. Compliance, Data Quality & Monitoring

#### TAX-MON-01 · Dashboard Status Submission Coretax / Pajakku (ASPP)
- **Tujuan:** pantau submission per masa: pending / approved / rejected / error; SLA & antrean ASPP.
- **Sumber:** `custom.coretax.transaction`, config Pajakku (`pajakku_pending_tx`, `pajakku_error_tx`, `pajakku_last_test_ok`).
- **Kolom:** dokumen · jenis · status · retry · NSFP/no. bupot kembali · pesan error. **Frekuensi:** real-time. **Format:** dashboard + `XLSX`. **Status:** ❌ gap (data ada di ledger; view monitoring belum).

#### TAX-MON-02 · Data Quality Lawan Transaksi (NPWP/NIK & Sertel)
- **Tujuan:** cegah tolakan DJP — deteksi NPWP/NIK invalid/kosong, lawan non-PKP, sertel mendekati kedaluwarsa, DPP ≤ 0 sebelum export.
- **Sumber:** `res.partner.x_custom_npwp_status`/`x_custom_has_valid_npwp`, Bulk Pre-Export Validation Wizard (`custom_tax_id`), `coretax.sertel.history`.
- **Kolom:** lawan · NPWP/NIK · status validasi · PKP · #transaksi terdampak · masalah. **Frekuensi:** sebelum tiap export + mingguan. **Format:** `XLSX`. **Status:** 🟡 wizard validasi ada; **report standing data-quality belum**.

#### TAX-MON-03 · Usage / Billing Meter Pajakku
- **Tujuan:** hitung pemakaian ASPP (faktur & bupot terkirim) per tenant per masa untuk billing/kontrol kuota.
- **Sumber:** `custom.coretax.pajakku.usage`. **Kolom:** tenant · masa · #API call · #faktur · #bupot. **Format:** `XLSX`. **Konsumen:** Finance/Ops. **Status:** 🟡 model ada; report belum.

#### TAX-MON-04 · Audit Trail Pajak (untuk pemeriksaan DJP)
- **Tujuan:** jejak append-only atas perubahan status faktur/bupot & submission untuk audit defense. **Sumber:** `pdp.audited.mixin` di semua model pajak. **Format:** `XLSX`/`PDF`. **Status:** 🟡 data terekam; ekstraksi report belum.

---

## 4. Ringkasan format & jadwal pelaporan

| Report | Frekuensi | Deadline umum | Format utama |
|---|---|---|---|
| Rekap FP Keluaran/Masukan, SPT Masa PPN 1111 | Masa (bulanan) | Setor akhir bln berikutnya; lapor akhir bln berikutnya | CSV/XML/PDF |
| e-Bupot Unifikasi (PPh 22/23/4(2)/15/26) | Masa | Setor tgl 15; lapor tgl 20 | XLSX/XML/PDF |
| PPh 21 rekap + SPT 1721 | Masa + Tahunan | Setor tgl 10; lapor tgl 20; 1721 tahunan | PDF/XML/XLSX |
| Rekonsiliasi & ekualisasi | Bulanan/Tahunan | Internal / persiapan SPT Tahunan | XLSX |
| Monitoring Coretax/Pajakku & data quality | Real-time/mingguan | Internal | Dashboard/XLSX |

---

## 5. Gap analysis & prioritas

| Prioritas | Report | Status | Alasan |
|---|---|---|---|
| **P1** | TAX-PPN-01/02 Rekap FP Keluaran & Masukan (XLSX/CSV) | 🟡 | Dasar SPT Masa PPN; wajib bulanan; XML sudah ada tapi tim tax butuh rekap yang bisa dibaca/dicek. |
| **P1** | TAX-PPH-01 Rekap e-Bupot Unifikasi per masa (XLSX) | 🟡 | Dasar SPT Masa PPh Unifikasi; per lembar sudah ada, rekap masa belum. |
| **P1** | TAX-PPN-04 Rekonsiliasi PPN + saldo GL | 🟡 | Sudah ada Net PPN; tinggal tambah kolom rekonsiliasi GL & selisih. |
| **P2** | TAX-PPN-03 SPT Masa PPN 1111 (induk) | ❌ | Formulir induk siap lapor. |
| **P2** | TAX-PPH-02..05 Rekap PPh 23/4(2)/26/22 | ❌ | Rincian per jenis untuk cek & lampiran. |
| **P2** | TAX-MON-02 Data Quality NPWP/NIK | 🟡 | Kurangi tolakan DJP; wizard ada, jadikan report standing. |
| **P2** | TAX-PPN-06 Monitoring NSFP & status faktur | ❌ | Cegah faktur nyangkut menjelang deadline. |
| **P3** | TAX-CR-01 Kredit Pajak (bupot diterima) | 🟡 | Untuk SPT Tahunan / kredit pajak. |
| **P3** | TAX-REC-01/03/04 Ekualisasi & rekonsiliasi PPh | ❌ | Persiapan pemeriksaan / SPT Tahunan Badan. |
| **P3** | TAX-PPN-05 DPP Nilai Lain, TAX-PPN-07 Faktur Pengganti | ❌ | Audit trail perhitungan & koreksi. |
| **P4** | TAX-MON-01/03/04 Dashboard Coretax, Usage, Audit trail | 🟡 | Ops/billing/audit; data sudah tercatat. |
| **P4** | TAX-CR-02 PPh 25 angsuran | ❌ | Monitoring angsuran. |

---

## 6. Persyaratan data quality (prasyarat report akurat)

Report hanya sebaik data transaksinya. Yang harus divalidasi di hulu:

1. **NPWP/NIK lawan transaksi** terisi & valid (15 digit legacy atau 16 digit
   NIK-based) — `res.partner.x_custom_npwp_status`.
2. **Kode transaksi & kode objek pajak** terisi konsisten di setiap faktur/bupot.
3. **DPP > 0** dan metode DPP (regular / nilai_lain) benar sebelum export.
4. **Status PKP** lawan (`x_custom_pkp`) benar → menentukan fiscal position & PPN.
5. **Sertel valid** (expiry > 30 hari) sebelum submission Coretax.
6. **Setiap objek PPh punya kategori withholding** (`product.template.x_custom_withholding_category_id`) agar pemotongan otomatis jalan.

---

## 7. Acceptance criteria (untuk setiap report saat diimplementasi)

- [ ] Angka total report = saldo GL / rekap SPT terkait (reconciles, selisih 0).
- [ ] Difilter per `company_id`; tidak bocor lintas tenant.
- [ ] Mendukung parameter masa (bulan) & rentang tanggal bebas.
- [ ] Setiap baris bisa drill-down ke `account.move`/`payslip`/`bukti.potong` sumber.
- [ ] Export XLSX/CSV/PDF sesuai format kolom di atas; report SPT ikut skema DJP.
- [ ] Hanya membaca (read-only); tidak mengubah transaksi.
- [ ] Hormati hak akses (tim tax vs accounting vs ops).

---

## 8. Baseline yang sudah ada (jangan bikin ulang)

| Kapabilitas | Modul | Catatan |
|---|---|---|
| Tax Report (Output/Input/Withholding + Net PPN + per fiscal position, XLSX) | `ee_gap/custom_accounting_reports` (`custom.report.tax`) | Basis TAX-PPN-04; extend, jangan buat baru. |
| e-Faktur XML export/import (7 jenis dokumen) + NSFP stamp | `compliance/custom_coretax` | Sumber TAX-PPN-01. |
| e-Bupot Unifikasi XML export + PDF per lembar + upload nomor | `compliance/custom_coretax_bupot` | Sumber TAX-PPH-01. |
| SPT 1721 A1 (PDF + XML) | `ee_gap/custom_hr_payroll_id` | Bagian TAX-PPH-06. |
| Bulk Pre-Export Validation (NPWP/NIK/DPP/sertel) | `ee_gap/custom_tax_id` | Basis TAX-MON-02. |
| Ledger submission + usage meter ASPP | `ee_gap/custom_coretax_pajakku` | Sumber TAX-MON-01/03. |
| Engine report dinamis (XLSX/PDF, filter, drill-down) | `custom_accounting_reports` (`custom.report.engine`) | **Framework untuk semua report baru di atas.** |

---

## 9. Status implementasi (update 2026-07-03)

Batch **P1** sudah diimplementasi di modul `ee_gap/custom_accounting_reports`
(menu **Accounting > Reporting > Reports**), dibangun di atas
`custom.report.engine` dengan akses field Coretax/PPh secara defensif:

| Report | Model | Menu | Status |
|---|---|---|---|
| TAX-PPN-01/02 Rekap Faktur Pajak (Keluaran & Masukan) | `custom.report.faktur.pajak` | Rekap Faktur Pajak | ✅ Implemented (PDF + XLSX; filter Keluaran/Masukan, masa, company, lawan transaksi) |
| TAX-PPH-01 Rekap Bukti Potong PPh Unifikasi | `custom.report.bupot` | Rekap Bukti Potong PPh | ✅ Implemented (arah Diterbitkan/Diterima, per jenis PPh; sumber `custom.coretax.bukti.potong`, degrade gracefully bila modul absen) |
| TAX-PPN-04 Rekonsiliasi PPN vs Buku Besar | `custom.report.tax` (extended) | Tax Report | ✅ Implemented (blok "Rekonsiliasi PPN vs Buku Besar" + kolom Selisih; muncul di PDF & XLSX) |

Batch **P2** juga sudah diimplementasi (menu & pola sama):

| Report | Model | Menu | Status |
|---|---|---|---|
| TAX-PPN-03 SPT Masa PPN 1111 (Induk) | `custom.report.spt.ppn` | SPT Masa PPN 1111 | ✅ Implemented (ringkasan DPP/PPN Keluaran vs Masukan → PPN Kurang/(Lebih) Bayar) |
| TAX-PPH-02..05 Rekap PPh per Jenis Penghasilan | `custom.report.pph.withholding` | Rekap PPh Pemotongan | ✅ Implemented (sumber `account.move.withholding.line`; grup per jenis PPh + jenis penghasilan/`tax.withholding.category`; filter 22/23/4(2)/26/21) |
| TAX-PPN-06 Monitoring NSFP & Status Faktur | `custom.report.nsfp.monitoring` | Monitoring NSFP | ✅ Implemented (status Coretax, umur hari, flag "BELUM ber-NSFP") |
| TAX-MON-02 Data Quality NPWP/NIK | `custom.report.npwp.quality` | Data Quality NPWP/NIK | ✅ Implemented (scan lawan transaksi bermasalah + jumlah transaksi) |

Batch **P3 & P4** juga sudah diimplementasi (menu & pola sama):

| Report | Model | Menu | Status |
|---|---|---|---|
| TAX-PPN-05 Laporan DPP Nilai Lain (PMK 131/2024) | `custom.report.dpp.nilai.lain` | Laporan DPP Nilai Lain | ✅ Implemented (DPP penuh × faktor → DPP nilai lain, per kategori) |
| TAX-PPN-07 Daftar Faktur Pengganti | `custom.report.faktur.pengganti` | Daftar Faktur Pengganti | ✅ Implemented (kode 01–09, NSFP asal → pengganti) |
| TAX-REC-01 Ekualisasi Omzet PPN vs Buku Besar | `custom.report.ekualisasi.omzet` | Ekualisasi Omzet | ✅ Implemented (DPP Keluaran vs pendapatan GL + selisih) |
| TAX-REC-04 Ekualisasi Biaya vs Objek Pemotongan PPh | `custom.report.pph.equalisasi` | Ekualisasi Biaya vs Objek PPh | ✅ Implemented (baris biaya objek PPh + flag "BELUM dipotong") |
| TAX-MON-01 Monitoring Submission Coretax/Pajakku | `custom.report.coretax.submission` | Monitoring Submission Coretax | ✅ Implemented (per status: queued/submitted/approved/rejected/error) |
| TAX-MON-03 Usage Meter Pajakku | `custom.report.pajakku.usage` | Usage Meter Pajakku | ✅ Implemented (API calls, faktur/bupot submits, errors per masa) |

**Verifikasi:** 15 test area pajak hijau di `tests/test_reports.py` —
P1 (5): `test_faktur_pajak_keluaran`, `test_faktur_pajak_masukan_sign`,
`test_tax_report_reconciliation`, `test_tax_report_subtotals`,
`test_bupot_report`; P2 (4): `test_spt_ppn_induk`,
`test_pph_withholding_report`, `test_nsfp_monitoring`, `test_npwp_quality`;
P3/P4 (6): `test_dpp_nilai_lain`, `test_faktur_pengganti`,
`test_ekualisasi_omzet`, `test_pph_equalisasi`,
`test_coretax_submission_query`, `test_pajakku_usage` — dijalankan via
`odoo -d <db> -u custom_accounting_reports --test-enable --test-tags=/custom_accounting_reports`.

> **Update:** seluruh suite `custom_accounting_reports` kini hijau (25 test, 0
> gagal). 2 test pre-existing non-pajak yang sempat merah sudah diperbaiki:
> `test_aged_receivable_buckets` (ekspektasi bucket usang setelah bucket
> 181-365 ditambahkan) dan `test_general_ledger_flat_layout` (`_build_flat_lines`
> kini `flush_all()` sebelum raw SQL agar `parent_state` yang baru di-post
> terlihat).

### Penyesuaian UI

- **Submenu "Laporan Pajak":** 13 report dikelompokkan di
  Accounting › Reporting › Reports › **Laporan Pajak** (terpisah dari report
  keuangan umum).
- **Drill-down "Lihat Transaksi":** tombol di tiap wizard (kecuali report
  ringkasan SPT PPN & Ekualisasi Omzet) membuka transaksi sumbernya
  (`account.move`, `account.move.line`, `custom.coretax.bukti.potong`,
  `account.move.withholding.line`, `custom.coretax.transaction`,
  `custom.coretax.pajakku.usage`, `res.partner`) sebagai list Odoo native.

### Sudah tercakup / di-defer

- **TAX-CR-01 Kredit Pajak (bukti potong diterima)** — sudah tercakup oleh
  `custom.report.bupot` dengan arah **"Diterima"** (tidak dibuat report baru).
- **TAX-REC-03 PPh Terutang vs Disetor** — **di-defer**: engine withholding
  belum memposting jurnal ke GL (lihat komentar di
  `custom_tax_id/models/account_move_inherit.py._post`), jadi sisi "disetor"
  belum ada sumber data. Dibuka lagi setelah posting per-rule di-lock.
- **TAX-CR-02 PPh 25 Angsuran** — **di-defer**: belum ada model angsuran PPh 25.
- **TAX-MON-04 Audit Trail Pajak** — **di-defer**: data sudah terekam via
  `pdp.audited.mixin` / `pdp.audit_log`; ekstraksi ke report tersendiri
  bernilai marginal, dijadikan follow-up.

---

*Referensi regulasi: UU HPP · PMK 131/2024 (DPP nilai lain / PPN efektif) ·
PMK 58/2022 · PP 58/2023 (PPh 21 TER) · PER-11/PJ/2025 (Coretax, e-Faktur,
e-Bupot). Lihat juga [coretax.md](coretax.md).*
