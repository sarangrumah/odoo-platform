# Spesifikasi Export GL 2-Sisi (Two-Sided) — EBR → Odoo

**Tujuan:** memungkinkan import General Ledger EBR ke Odoo sebagai **jurnal detail per
voucher** (bukan ringkasan), sehingga transaksi bisa di-*tracking* dan P&L terpecah
**per Operating Unit (Branch/Store)**.

**Masalah export saat ini:** sheet `GL EBR 2026` bersifat **single-sided** — tiap baris
hanya membawa **satu sisi** (Debit *atau* Kredit), akun lawan (contra) tidak ada, dan hanya
±5% baris punya `Document No`. Akibatnya:
- Total Debit ≠ Total Kredit (80 M vs 13 jt) → tidak bisa jadi jurnal yang balance.
- Baris tidak bisa dikelompokkan jadi satu voucher (mayoritas `Document No` kosong).
- **Revenue per toko hilang** (sisi kredit penjualan tidak ada), jadi P&L per OU tidak
  bisa direkonstruksi.

Odoo mewajibkan **setiap jurnal balance (Σ Debit = Σ Kredit)**. Dokumen ini menjelaskan
format yang dibutuhkan agar sekali export langsung bisa diimport.

---

## Aturan utama (WAJIB)

1. **Setiap baris = satu sisi (leg) dari satu jurnal.** Isi **hanya** kolom `D` **atau**
   `C`, tidak keduanya, dengan angka positif.
2. **Setiap voucher harus lengkap dua sisi dan balance.** Kumpulan baris dengan
   `Document No` yang sama harus memenuhi **Σ D = Σ C** (selisih 0). Ini termasuk sisi
   yang selama ini hilang (mis. kredit Pendapatan, kredit Piutang saat pelunasan).
3. **`Document No` wajib terisi di SETIAP baris** dan unik per voucher. Semua baris satu
   transaksi memakai `Document No` yang sama. **Tidak boleh kosong.**
4. **`Account Number` harus persis** dengan kode CoA EBR yang dipakai di Odoo
   (mis. `1106000001`, `5120010001`). Jangan pakai kode SAP lama.
5. **`Branch/Store` wajib** di baris yang berdimensi toko — terutama semua baris
   **Revenue, COGS, dan beban Selling** — supaya P&L pecah per Operating Unit. Untuk
   transaksi kantor pusat gunakan nilai konsisten `Head Quarter`.
6. **`Business Partner` wajib** di baris **Piutang (AR)** dan **Hutang (AP)** — untuk
   subledger per customer/vendor. Format bebas, tapi konsisten (mis. `PT Metropolitan Kentjana`).
7. **Nama toko harus konsisten** dengan master toko Odoo (lihat daftar di bagian bawah).
8. **Angka**: tanpa pemisah ribuan, titik untuk desimal (mis. `10930941.82`). Mata uang IDR.
9. **Tanggal**: format `YYYY-MM-DD` (mis. `2026-06-30`).

---

## Kolom (urutan & nama header — pertahankan persis)

| # | Header | Wajib | Keterangan |
|---|--------|:---:|------------|
| 1 | `No` | – | Nomor urut baris (opsional) |
| 2 | `Year` | ✓ | Tahun fiskal, mis. `2026` |
| 3 | `Period` | ✓ | Awal bulan periode, mis. `2026-06-01` |
| 4 | `Transaction Type` | ✓ | Jenis transaksi (lihat tabel di bawah) — menentukan Journal di Odoo |
| 5 | **`Document No`** | ✓✓ | **ID voucher. WAJIB, unik per voucher, sama untuk semua baris satu jurnal** |
| 6 | `Invoice Reference` | – | No. invoice/referensi eksternal |
| 7 | `Document Date` | ✓ | Tanggal dokumen `YYYY-MM-DD` |
| 8 | `Posting Date` | ✓ | Tanggal posting `YYYY-MM-DD` (dipakai sebagai tanggal jurnal Odoo) |
| 9 | **`Account Number`** | ✓✓ | Kode akun **CoA EBR (Odoo)** |
| 10 | `Account Description` | – | Nama akun (informasi) |
| 11 | **`D`** | ✓* | Nilai Debit (positif). Kosong jika baris ini kredit |
| 12 | **`C`** | ✓* | Nilai Kredit (positif). Kosong jika baris ini debit |
| 13 | `Amount` | – | Boleh diisi `D − C` (informasi); importer pakai `D`/`C` |
| 14 | `Notes` | – | Keterangan baris (dipakai sebagai label baris jurnal) |
| 15 | `Sales Receipt Bank Mapping` | – | Info tambahan |
| 16 | **`Business Partner`** | ✓ (AR/AP) | Customer/vendor pada baris piutang/hutang |
| 17 | **`Branch/Store`** | ✓ (P&L) | Toko/OU — wajib untuk baris Revenue/COGS/beban Selling |
| 18 | `Remarks` | – | Catatan bebas |

`✓*` = tepat salah satu dari `D`/`C` terisi per baris.

---

## Pemetaan `Transaction Type` → Journal Odoo

| `Transaction Type` | Journal Odoo | Sisi yang HARUS lengkap (contoh) |
|---|---|---|
| `Sales Invoice` | INV | Dr Piutang **/ Cr Pendapatan (per toko)** ← sisi kredit ini yang selama ini hilang |
| `Sales Receipt` | Bank | Dr Bank **/ Cr Piutang (per partner)** ← sisi kredit ini yang hilang |
| `Purchase Invoice Non-Trade` | BILL | Dr Beban/Aset **/ Cr Hutang (per vendor)** |
| `Purchase Invoice Trade` | BILL | Dr Persediaan/GR-IR **/ Cr Hutang** |
| `Purchase Payment` | Bank | Dr Hutang **/ Cr Bank** |
| `Cash & Bank` | Bank | kedua sisi kas/bank ↔ lawannya |
| `General Journal` | MISC | bebas, asal balance |
| `Opening Balance 2026` | EBRTB | (sudah ditangani terpisah lewat TB — tidak perlu di GL) |

> Jika nama Transaction Type berbeda, beri tahu kami supaya pemetaan journal disesuaikan.

---

## Contoh voucher yang BENAR (2-sisi, balance)

### Contoh 1 — Sales Invoice (penjualan 1 toko)
Satu `Document No`, dua baris, **balance** (Dr 10.000.000 = Cr 10.000.000), dan
**revenue punya Branch/Store** → inilah yang membuat P&L pecah per OU:

| Document No | Transaction Type | Posting Date | Account Number | D | C | Business Partner | Branch/Store |
|---|---|---|---|---|---|---|---|
| SI/PIM1/0601 | Sales Invoice | 2026-06-05 | 1106000001 | 10000000 | | Customer Umum | Pondok Indah Mall 1 |
| SI/PIM1/0601 | Sales Invoice | 2026-06-05 | 5120010001 | | 10000000 | | Pondok Indah Mall 1 |

### Contoh 2 — Sales Receipt (pelunasan piutang ke bank)
| Document No | Transaction Type | Posting Date | Account Number | D | C | Business Partner | Branch/Store |
|---|---|---|---|---|---|---|---|
| SR/BCA/0610 | Sales Receipt | 2026-06-10 | 1103019310 | 10000000 | | | Pondok Indah Mall 1 |
| SR/BCA/0610 | Sales Receipt | 2026-06-10 | 1106000001 | | 10000000 | Customer Umum | Pondok Indah Mall 1 |

### Contoh 3 — Purchase Invoice Non-Trade (sewa kantor)
| Document No | Transaction Type | Posting Date | Account Number | D | C | Business Partner | Branch/Store |
|---|---|---|---|---|---|---|---|
| PI/1200000022 | Purchase Invoice Non-Trade | 2026-06-26 | 7214001000 | 13440000 | | PT Era Sukses A | Head Quarter |
| PI/1200000022 | Purchase Invoice Non-Trade | 2026-06-26 | 2103300001 | | 13440000 | PT Era Sukses A | Head Quarter |

---

## Checklist validasi sebelum kirim (agar sekali import langsung jalan)

- [ ] **Σ D = Σ C** untuk seluruh file (grand total balance).
- [ ] **Setiap `Document No` balance** (Σ D = Σ C per voucher, selisih 0).
- [ ] **Tidak ada baris tanpa `Document No`.**
- [ ] Tiap baris: **tepat satu** dari `D`/`C` terisi (tidak dua-duanya, tidak kosong dua-duanya).
- [ ] Semua `Account Number` ada di **CoA EBR Odoo** (kode baru, bukan SAP lama).
- [ ] Semua baris **Revenue / COGS / beban Selling** punya `Branch/Store`.
- [ ] Semua baris **Piutang / Hutang** punya `Business Partner`.
- [ ] Nama `Branch/Store` sesuai daftar master toko.

---

## Daftar nama Branch/Store (master OU Odoo)

Gunakan **persis** salah satu berikut (plus `Head Quarter` untuk kantor pusat):

```
Aeon BSD City, Bandung Indah Plaza, Central Park, Galaxy Mall 3 Surabaya,
Gandaria City, Grand Indonesia, Grand Metropolitan Bekasi, Head Quarter,
Kelapa Gading Mall, Lotte Shopping Avenue, Mall of Indonesia,
Metropolitan Mall Bekasi, Pakuwon Mall Surabaya, Paris Van Java Bandung,
Plaza Senayan, Pondok Indah Mall 1, Pondok Indah Mall 2, Senayan City,
Summarecon Mall Bandung, Trans Studio Cibubur, Trans Studio Mall Bandung,
Tunjungan Plaza 3 Surabaya
```

> Catatan: di export lama sempat ada nilai `Belum ada info` — mohon diganti dengan nama
> toko yang benar, atau `Head Quarter` bila memang transaksi pusat.

---

## Setelah file diterima

1. Export → simpan ke CSV (`gl_ebr.csv`) via `scripts/tenants/levis/59_export_ebr.py`.
2. Import per voucher: `scripts/tenants/levis/61_load_gl.py` (grouping by `Document No`,
   Branch/Store → analytic, Business Partner → partner, Transaction Type → journal).
3. Rekonsiliasi: saldo per akun + pergerakan P&L per OU dicocokkan ke laporan EBR.

Importer akan **menolak & melaporkan** voucher yang tidak balance (bukan diam-diam
di-post), jadi bila ada baris yang belum lengkap dua sisinya akan terlihat jelas.
