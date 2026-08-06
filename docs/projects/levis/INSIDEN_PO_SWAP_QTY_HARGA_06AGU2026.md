# Laporan Insiden — Kolom Quantity/Unit Price Tertukar pada Upload PO

**Database:** `prd_levis_begbal` · **Tanggal kejadian:** 6 Agustus 2026 · **Status:** selesai ditangani
**Dokumen PO terdampak:** `PO/T/EBR/2026/08/00132` s/d `00149` (18 PO)

---

## 1. Ringkasan eksekutif

Delapan belas PO diunggah lewat fitur impor bawaan Odoo dengan **kolom Quantity dan Unit
Price tertukar** — misalnya 413.011 pcs @ Rp 1, yang seharusnya 1 pcs @ Rp 413.011. Satu
receipt sempat divalidasi sebelum ketahuan, sehingga 124.233.901 pcs masuk ke stok dan
Rp 191.294.913 terposting ke GR/IR.

Seluruh dampak sudah dipulihkan. **GL kembali ke posisi sebelum insiden, COGS tidak
terdampak sama sekali, dan harga pokok 200 produk sudah dikembalikan ke nilai semula.**
Ke-15 PO yang masih hidup sudah diperbaiki isinya tanpa mengubah nomor dokumen.

| Aspek | Status akhir |
|---|---|
| Stok | Pulih — internal kembali ke baseline 46.884 pcs |
| GL / GR/IR | Pulih — Rp 191.294.913 di-reverse penuh, kontribusi insiden **nol** |
| COGS | **Tidak terdampak** — belum pernah ada COGS run di database ini |
| Harga pokok (200 produk) | Pulih — cocok ≤1% dengan harga di PO pada 200/200 produk |
| Isi 18 PO | 15 diperbaiki di tempat, 3 dibatalkan tim |
| Pencegahan | Guard aktif di 6 database Levi's |

Nilai rupiah PO **tidak pernah salah**. Swap kolom mempertahankan qty × harga, jadi
`amount_untaxed` setiap PO tetap benar sejak awal. Yang rusak hanya kuantitas, harga
satuan, dan segala sesuatu yang diturunkan dari keduanya.

---

## 2. Kronologi

| Waktu (UTC) | Kejadian |
|---|---|
| 06:22 – 07:15 | 18 PO diunggah lewat impor bawaan, kolom tertukar |
| 07:16 | Receipt `27917/IN/00001` divalidasi → 124.233.901 pcs masuk stok, 200 jurnal GR-VAL terposting |
| 07:16 – 09:32 | **Jendela harga pokok rusak** — 200 produk bernilai belasan rupiah |
| 07:43 – 07:44 | Tim membatalkan sendiri PO `00147`–`00149` |
| 09:32 | Skrip pemulihan dijalankan — retur, reversal GL, harga pokok dipulihkan |
| 09:41 – 10:16 | Tim melanjutkan impor normal (PO `00150`–`00163`), kuantitas wajar |
| 10:34 | Isi 15 PO diperbaiki (tukar balik qty ⇄ harga), 15 receipt baru terbit |

---

## 3. Dampak GR/IR — pulih penuh

### 3.1 Yang terposting saat receipt salah divalidasi

| Akun | Nama | Debit | Kredit | Jurnal |
|---|---|---|---|---|
| 1113100021 | Inventories-textile | 119.592.694 | — | STJ/2026/08/12243 – 12411 (98 entri) |
| 1113100023 | Inventories-accessories | 71.702.219 | — | STJ/2026/08/12212 – 12323 (102 entri) |
| 2103109121 | GR/IR Clearing-Third Parties-textile | — | 119.592.694 | idem |
| 2103109123 | GR/IR Clearing-Third Parties-accessories | — | 71.702.219 | idem |
| | **Total** | **191.294.913** | **191.294.913** | 200 entri |

### 3.2 Reversal

200 jurnal reversal terposting dengan nilai **identik terbalik** (STJ/2026/08/12412 – 12611).
Netto insiden terhadap GR/IR maupun persediaan = **Rp 0**.

Retur barangnya sendiri sengaja **tidak** membukukan jurnal. Kalau dibiarkan membukukan
otomatis, ia akan menilai barang keluar pada harga pokok yang sudah rusak
(Rp 1.425.707.029) dan **melebih-reverse GL sekitar Rp 1,23 miliar**. Jadi jurnal retur
ditekan, lalu 200 jurnal aslinya di-reverse secara eksplisit — presisi sampai rupiah
terakhir.

### 3.3 Saldo GR/IR saat ini

| Akun | Saldo |
|---|---|
| 2103109121 GR/IR Clearing-Third Parties-textile | −30.420.652.235 |
| 2103109123 GR/IR Clearing-Third Parties-accessories | −1.226.147.044 |

Kenaikan sejak pemulihan sebesar **+Rp 1.728.419.763** berasal **100% dari receipt sah
tim** (PO `00150`–`00163`, 14 picking divalidasi 09:41–10:16) — angkanya cocok persis,
jadi tidak ada sisa insiden yang menyelinap.

Sisi persediaan dan GR/IR masih mirror sempurna (1113100021 = −2103109121) karena **belum
ada satu pun vendor bill** yang meng-clear GR/IR. Ini kondisi normal, bukan gejala.

### 3.4 Yang akan masuk GR/IR berikutnya

15 receipt hasil perbaikan masih berstatus *Ready* dan akan membukukan saat divalidasi:

| Akun valuasi | Picking | Baris | Qty | Nilai |
|---|---|---|---|---|
| 1113100021 Inventories-textile | 15 | 1.479 | 2.803 pcs | 1.716.816.107 |
| 1113100023 Inventories-accessories | 4 | 114 | 243 pcs | 79.733.346 |
| | | | **3.046 pcs** | **1.796.549.453** |

---

## 4. Dampak COGS — nihil

Tiga alasan terpisah, masing-masing sudah cukup:

1. **Belum pernah ada COGS run di database ini.** Tabel `levis_cogs_run` kosong, jadi tidak
   ada COGS yang terlanjur dibukukan pada harga pokok yang rusak.
2. **COGS run tidak membaca nilai stock move.** Perhitungannya
   `pos.order.line.qty × product.standard_price` (`custom_levis_localization/models/cogs_run.py`).
   Karena `standard_price` sudah dipulihkan, run berikutnya otomatis benar.
3. **Tidak ada barang keluar di jendela harga rusak.** Sepanjang 07:16–09:32 tidak ada satu
   pun move keluar ke customer atau POS — satu-satunya outgoing adalah retur pemulihan itu
   sendiri.

> **Catatan risiko untuk ke depan:** seandainya COGS run atau pengiriman terjadi di dalam
> jendela seperti itu, barang akan dinilai pada harga rusak dan **tidak bisa diperbaiki
> Odoo secara otomatis** — `stock.move.value` adalah kolom tersimpan dan `_run_fifo_vacuum`
> sudah tidak ada di Odoo 19. Karena itu penanganan cepat pada insiden semacam ini penting.

---

## 5. Harga pokok — dipulihkan dan diverifikasi silang

Kategori memakai FIFO, sehingga "kedatangan" 1.588.688 pcs @ Rp 1 di samping 14 pcs yang
sudah ada menggerus harga pokok rata-rata:

| SKU | Sebelum insiden | Saat rusak | Setelah dipulihkan |
|---|---|---|---|
| 00501373603232 | 1.588.688 | 14,99 | 1.588.688 |
| 002GV00010OS | 413.011 | 4,00 | 413.011 |
| 002GW00000OS | 698.987 | 20,00 | 698.987 |

Pemulihan memakai aljabar rata-rata FIFO —
`C = (cost_now × (qty_before + qty_in) − qty_in × p) / qty_before` — dengan seluruh
variabel diketahui. Hasilnya diuji silang terhadap harga di PO (yaitu angka yang nyasar ke
kolom Quantity): **cocok ≤1% pada 200 dari 200 produk**. Dua produk yang sebelumnya tidak
punya stok (`001PZ000903130`, `005BX0001085`) tidak punya rata-rata untuk dibalik, jadi
harganya diambil langsung dari PO dan dicatat terpisah.

---

## 6. Residu yang masih terbuka — nilai move pada dokumen lama

`stock_move.value` pada receipt `27917/IN/00001` dan returnya kini masing-masing
**Rp 98.701.163.756.661** (98,7 triliun):

| Move | SKU | Qty | Harga di PO | Harga pokok | `value` sekarang | Nilai yang dibukukan GL |
|---|---|---|---|---|---|---|
| 29931 | 00501373603232 | 1.588.688 | 1 | 1.588.688 | 2.523.929.561.344 | 1.588.688 |
| 29881 | 003NE000303030 | 1.016.737 | 1 | 1.016.737 | 1.033.754.127.169 | 1.016.737 |
| | | | | **200 move** | **98.701.163.756.661** | **191.294.913** |

**Penyebab:** saat PO `00132` direset ke draft lalu dikonfirmasi ulang (10:34:32), Odoo
menilai ulang move `done` lama itu terhadap `standard_price` yang sudah dipulihkan —
413.011 × 413.011.

**Dampaknya terbatas:**
- **Nol jurnal terbit.** Tidak ada `account_move` yang dibuat setelah 10:30.
- Receipt dan returnya membawa angka **identik**, jadi saling meniadakan — GL, saldo GR/IR,
  dan nilai persediaan on-hand (Rp 31.646.799.279 untuk 49.893 pcs) semuanya tetap benar.
- Yang akan tampak salah **hanya laporan bruto**, misalnya "nilai barang diterima Agustus".

**Opsi penanganan** (menunggu keputusan):

| Opsi | Konsekuensi |
|---|---|
| Samakan dengan yang dibukukan GL (Rp 191.294.913 per sisi) | Nilai move konsisten dengan jejak GL; laporan bruto wajar |
| Nolkan kedua sisi | Laporan bruto maupun net bersih dari jejak insiden |
| Biarkan | GL/COGS/on-hand sudah benar; cukup dicatat sebagai anomali laporan bruto Agustus |

Kolom `value` adalah kolom tersimpan biasa tanpa kaitan ke jurnal, jadi ketiga opsi
tidak menyentuh GL sama sekali.

---

## 7. Pencegahan yang sudah terpasang

`purchase.order.line._check_levis_qty_price_swap` — constraint yang menolak baris dengan
kuantitas yang jelas-jelas sebuah harga.

- **Harus constraint, bukan peringatan onchange.** Impor bawaan Odoo tidak pernah
  menjalankan onchange — persis lewat jalur itulah data ini masuk.
- Ambang batas dapat disetel per database lewat parameter sistem
  `custom_levis_localization.po_swap_guard_qty` (default 10.000) dan
  `.po_swap_guard_price` (default 100); isi `0` untuk mematikan.
- Pesan penolakan berbahasa Indonesia dan menyebut nama produk beserta angkanya.
- Terdeploy dan terbukti aktif di 6 database Levi's (`rnd_levis`, `prd_levis`,
  `prd_levis_begbal`, `prd_detail_levis`, `prd_levis_AP`, `demo_updated_levis`).
- Pesanan grosir asli tidak terganggu selama harga satuannya wajar.

Diverifikasi: dari 28 PO yang diunggah tim setelah insiden, **nol** yang kolomnya tertukar.

---

## 8. Referensi teknis

| Item | Lokasi |
|---|---|
| Guard | `addons/_tenants/custom_levis_localization/models/purchase_order.py` (modul 19.0.1.25.0) |
| Skrip pemulihan stok/GL/harga pokok | `scripts/tenants/levis/85_revert_po_qty_price_swap.py` |
| Skrip perbaikan isi PO | `scripts/tenants/levis/86_fix_po_qty_price_swap.py` |
| Pull request | #111 (guard + pemulihan), #112 (perbaikan isi PO) |
| Cadangan pra-eksekusi | dump `prd_levis_begbal` sebelum perubahan pertama |

Kedua skrip berjalan dry-run secara default dan membatalkan seluruh perubahan bila
verifikasi internalnya gagal.

---

## 9. Hal lain yang perlu konfirmasi

`PO/T/EBR/2026/07/00104` dan `PO/T/EBR/2026/07/00105` dibuat 5 Agustus tetapi bernomor
**Juli** karena `date_order` dimundurkan. Di luar cakupan insiden ini, tetapi perlu
dipastikan apakah memang disengaja.
